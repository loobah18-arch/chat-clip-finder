#!/usr/bin/env python3
"""
24-Hour Spacing Pre-flight Gate (Layer 0 front-runner for the Hypit pipeline).

Reuses candle_gate.CandleGate.evaluate_upload_spacing() so the workflow can
skip the entire expensive pipeline (tests, TTS, PO token, 5-tier download,
render) when fewer than 24 hours have elapsed since the last successful
YouTube upload — instead of discovering that at the upload step.

Decision matrix (fail-open by design, mirroring candle_gate.py):
  - no history / no valid entries / parse error  -> proceed (fail-open)
  - elapsed >= 24h                               -> proceed
  - remaining <= 30 min                          -> inline sleep, then proceed
  - otherwise                                    -> skip pipeline (proceed=false)

Manual workflow_dispatch runs set PREFLIGHT_BYPASS to always proceed.
Exit code is always 0; the decision is carried via the `proceed` GitHub
Actions output so downstream `if:` conditions stay simple.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from candle_gate import CandleGate

DEFAULT_HISTORY = Path(__file__).resolve().parent / "upload_history.json"
DEFAULT_MIN_SPACING_HOURS = 24.0
DEFAULT_MAX_INLINE_WAIT_HOURS = 0.5
HARD_SLEEP_CAP_SECONDS = 1900  # defensive: below the preflight job's 45-min timeout


def _parse_timestamp(raw: str) -> datetime:
    ts = raw.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _last_valid_upload(records):
    """Latest entry representing a real successful upload. Skips dry-run ids,
    failed/non-uploaded statuses, and entries without a usable timestamp."""
    for rec in reversed(records if isinstance(records, list) else []):
        if not isinstance(rec, dict):
            continue
        vid = str(rec.get("video_id") or rec.get("youtube_id") or "")
        if not vid or vid.startswith("dry_run"):
            continue
        if rec.get("status") not in {"uploaded", "published"} and not rec.get("published", False):
            continue
        raw_ts = rec.get("timestamp")
        if not raw_ts or not isinstance(raw_ts, str):
            continue
        return rec, raw_ts
    return None, None


def decide(
    history_path=DEFAULT_HISTORY,
    now=None,
    min_spacing_hours: float = DEFAULT_MIN_SPACING_HOURS,
    max_inline_wait_hours: float = DEFAULT_MAX_INLINE_WAIT_HOURS,
    youtube_client=None,
    state_file=None,
) -> dict:
    """Pure decision function (no sleeping, no side effects) for testability."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    try:
        history = Path(history_path)
        records = json.loads(history.read_text(encoding="utf-8")) if history.exists() else []
    except Exception as exc:
        return {"proceed": True, "sleep_seconds": 0, "elapsed_hours": None,
                "last_video_id": None, "remaining_seconds": 0, "due_at": "", "next_cron": "0 * * * *",
                "reason": f"fail-open: unreadable history ({exc})"}

    rec, raw_ts = _last_valid_upload(records)
    if rec is None:
        return {"proceed": True, "sleep_seconds": 0, "elapsed_hours": None,
                "last_video_id": None, "remaining_seconds": 0, "due_at": "", "next_cron": "0 * * * *",
                "reason": "no prior successful upload found; pipeline cleared"}

    try:
        published_at = _parse_timestamp(raw_ts)
    except Exception as exc:
        return {"proceed": True, "sleep_seconds": 0, "elapsed_hours": None,
                "last_video_id": rec.get("video_id") or rec.get("youtube_id"), "remaining_seconds": 0, "due_at": "", "next_cron": "0 * * * *",
                "reason": f"fail-open: unparseable timestamp {raw_ts!r} ({exc})"}

    vid = rec.get("video_id") or rec.get("youtube_id")
    elapsed_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
    gate = CandleGate(state_file=Path(state_file)) if state_file else CandleGate()
    spacing = gate.evaluate_upload_spacing(
        elapsed_hours, min_spacing_hours, max_inline_wait_hours
    )

    due_at = published_at + timedelta(hours=min_spacing_hours)
    next_cron = f"{due_at.minute} {due_at.hour} * * *"

    base = {"elapsed_hours": round(elapsed_hours, 2), "last_video_id": vid, "next_cron": next_cron}
    if not spacing["can_upload"] and not spacing["requires_spacing_sleep"]:
        remaining = max(int(round((min_spacing_hours - elapsed_hours) * 3600)), 0)
        return {**base, "proceed": False, "sleep_seconds": 0, "remaining_seconds": remaining,
                "due_at": due_at.strftime("%Y-%m-%dT%H:%M:%SZ"), "reason": spacing["recommendation"]}

    if spacing["requires_spacing_sleep"]:
        return {**base, "proceed": True,
                "sleep_seconds": min(spacing["spacing_sleep_seconds"], HARD_SLEEP_CAP_SECONDS),
                "remaining_seconds": 0, "due_at": "",
                "reason": spacing["recommendation"]}

    # Layer 1 & Layer 2: check live channel performance when youtube_client is available
    if youtube_client is not None:
        try:
            live = gate.evaluate_live_channel(youtube_client=youtube_client, history_path=Path(history_path), now=now)
            candle_eval = live.get("candle_evaluation", {}) if isinstance(live, dict) else {}
            if candle_eval and not candle_eval.get("can_upload", True):
                timer_sec = int(candle_eval.get("timer_seconds", 3600))
                due_time = now + timedelta(seconds=timer_sec)
                return {
                    **base,
                    "proceed": False,
                    "sleep_seconds": 0,
                    "remaining_seconds": timer_sec,
                    "due_at": due_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "next_cron": f"{due_time.minute} {due_time.hour} * * *",
                    "reason": candle_eval.get("recommendation", "Blocked by Candle Gate Layer 1/2"),
                }
        except Exception as exc:
            print(f"⚠️ Live telemetry evaluation failed ({exc}); falling back to Layer 0 spacing.", flush=True)

    return {**base, "proceed": True, "sleep_seconds": 0, "remaining_seconds": 0, "due_at": "", "reason": spacing["recommendation"]}


def main() -> int:
    bypass = (
        os.environ.get("PREFLIGHT_BYPASS", "").strip().lower() in {"1", "true", "yes"}
        or "--bypass" in sys.argv
    )

    zero_sleep = os.environ.get("PREFLIGHT_ZERO_SLEEP", "").strip().lower() in {"1", "true", "yes"}
    max_inline = 0.0 if zero_sleep else DEFAULT_MAX_INLINE_WAIT_HOURS

    if bypass:
        result = {"proceed": True, "sleep_seconds": 0, "elapsed_hours": None,
                  "last_video_id": None, "remaining_seconds": 0, "due_at": "", "next_cron": "0 * * * *",
                  "reason": "PREFLIGHT_BYPASS set (manual dispatch) — spacing gate bypassed"}
    else:
        yt_client = None
        try:
            from youtube_uploader import youtube_client
            yt_client = youtube_client()
        except Exception as exc:
            print(f"⚠️ Skipping live Layer 1/2 check ({exc}); evaluating Layer 0 history only.", flush=True)
        try:
            result = decide(youtube_client=yt_client, max_inline_wait_hours=max_inline)
        except Exception as exc:  # belt-and-braces fail-open
            result = {"proceed": True, "sleep_seconds": 0, "elapsed_hours": None,
                      "last_video_id": None, "remaining_seconds": 0, "due_at": "", "next_cron": "0 * * * *",
                      "reason": f"fail-open: unexpected gate error ({exc})"}

    if result["proceed"] and result["sleep_seconds"] > 0:
        print(f"⏱️ Inline spacing sleep: {result['sleep_seconds'] // 60}m "
              f"{result['sleep_seconds'] % 60}s (within "
              f"{DEFAULT_MAX_INLINE_WAIT_HOURS * 60:.0f}-min inline window)")
        time.sleep(result["sleep_seconds"])

    icon = "✅ PROCEED" if result["proceed"] else "🛑 SKIP"
    print(f"{icon} | elapsed={result['elapsed_hours']}h | last_upload={result['last_video_id']}")
    if not result["proceed"] and result.get("due_at"):
        print(f"⏰ Next upload due at {result['due_at']} ({result['remaining_seconds']}s from now, cron: '{result.get('next_cron')}')")
    print(result["reason"])

    out_file = os.environ.get("GITHUB_OUTPUT")
    if out_file:
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(f"proceed={'true' if result['proceed'] else 'false'}\n")
            f.write(f"sleep_seconds={result['sleep_seconds']}\n")
            f.write(f"remaining_seconds={result.get('remaining_seconds', 0)}\n")
            f.write(f"due_at={result.get('due_at', '')}\n")
            f.write(f"next_cron={result.get('next_cron', '0 * * * *')}\n")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### 🕯️ 24-Hour Spacing Pre-flight\n\n"
                    f"{icon} — elapsed **{result['elapsed_hours']}h** since last upload "
                    f"(`{result['last_video_id']}`)\n\n> {result['reason']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
