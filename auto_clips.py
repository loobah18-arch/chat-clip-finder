#!/usr/bin/env python3
"""Hands-free Dual Mode Short generator for GTA 6:
  - Mode A (stream): Top streamer webcam stack + Instagram comment sticker
  - Mode B (viceprint): Unbranded 1:1-in-9:16 blur + kinetic 1-2 word popping captions

    python3 auto_clips.py                      # Dual Mode (auto-alternates & falls back)
    python3 auto_clips.py --mode viceprint     # Unbranded Viceprint formula
    python3 auto_clips.py --mode stream        # Streamer facecam stack
    python3 auto_clips.py --list               # Show what it would pick

Remembers what it already clipped in state/processed.json, so each run picks new videos.
Extra flags after `--` go straight to chat_clips.py (e.g. -- --emotes --layout stack).
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ccf import captions, discover, sources

STATE = Path("state/processed.json")
EXIT_NO_CLIPS = 3


def load_state() -> Dict[str, Any]:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(state.items(), key=lambda kv: kv[1].get("at", 0), reverse=True)[:500]
    STATE.write_text(json.dumps(dict(items), indent=1, ensure_ascii=False), encoding="utf-8")


def _load_upload_history(history_path: Path = Path("upload_history.json")) -> List[Dict[str, Any]]:
    if not history_path.exists():
        return []
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def resolve_mode(requested_mode: str, history_path: Path = Path("upload_history.json")) -> str:
    """Resolves 'auto' Dual Mode by alternating against the last real upload in upload_history.json."""
    if requested_mode != "auto":
        return requested_mode

    last_mode = None
    for rec in reversed(_load_upload_history(history_path)):
        if not isinstance(rec, dict):
            continue
        vid = str(rec.get("video_id") or "")
        if not vid or vid.startswith("dry_run"):
            continue
        if rec.get("status") not in {"uploaded", "published"} and not rec.get("published", False):
            continue
        last_mode = rec.get("mode") or ("viceprint" if rec.get("layout") == "viceprint" else "stream")
        break

    if last_mode == "viceprint":
        return "stream"
    return "viceprint"


def _uploaded_source_ids(records: List[Dict[str, Any]]) -> set:
    ids = set()
    for rec in records:
        src = str(rec.get("source_url") or "")
        m = re.search(r"(?:v=|youtu\.be/|videos/)([A-Za-z0-9_-]{6,15})", src)
        if m:
            ids.add(f"yt:{m.group(1)}")
    return ids


def produce_viceprint_short(
    out_dir: Path,
    state: Dict[str, Any],
    topic_id: Optional[str] = None,
    proxy: Optional[str] = None,
    cookies: Optional[str] = None,
    whisper_model: str = "small",
    list_only: bool = False,
) -> List[Dict[str, Any]]:
    """Discovers fresh GTA 6 secret/gameplay footage and renders an unbranded Viceprint Short."""
    from ccf import render, viceprint

    out_dir.mkdir(parents=True, exist_ok=True)
    records = _load_upload_history()
    seen_ids = {k for k, v in state.items() if isinstance(v, dict) and v.get("ok", False)} | _uploaded_source_ids(records)

    print("🔎 Searching for fresh GTA 6 secrets, tips & gameplay footage for Viceprint mode...", flush=True)
    candidates = viceprint.discover_viceprint_candidates(
        count=12, seen_ids=seen_ids, cookies=cookies, proxy=proxy
    )
    if not candidates:
        print("   ! No fresh Viceprint candidates found after filtering.", flush=True)
        return []

    print(f"\n{len(candidates)} Viceprint candidates ranked. Top 5:")
    for i, c in enumerate(candidates[:5], 1):
        mins = int(c["duration"] // 60) if c.get("duration") else "?"
        print(f"  {i:>2}. {c.get('views', 0):>9,} views  {mins:>3} min  {c.get('channel', '')[:20]:<20} | {c.get('title', '')[:58]}")

    if list_only:
        return []

    for idx, cand in enumerate(candidates, 1):
        cand_dir = out_dir / f"cand_{idx:02d}_{cand['id'].replace(':', '_')}"
        cand_dir.mkdir(parents=True, exist_ok=True)
        piece = cand_dir / "piece.mp4"
        print(f"\n🎬 [Viceprint Candidate {idx}/{len(candidates)}] {cand['title']}\n   {cand['url']}", flush=True)

        try:
            start_s, end_s = viceprint.pick_best_segment(
                cand["url"], cand.get("duration", 0), cand_dir, target_len=54.0, cookies=cookies, proxy=proxy
            )
            print(f"   Downloading segment {start_s:.1f}s -> {end_s:.1f}s via cascading HD tiers...", flush=True)
            sources.download_section(cand["url"], start_s, end_s, piece, cookies=cookies, proxy=proxy)

            src_w, src_h, raw_dur = render.probe(piece)
            if src_h < 360:
                print(f"   ! Skipping candidate: resolution {src_w}x{src_h} < 360p", flush=True)
                piece.unlink(missing_ok=True)
                state[cand["id"]] = {"title": cand["title"], "url": cand["url"], "at": int(time.time()), "ok": False}
                save_state(state)
                continue
            if src_h < 720:
                print(f"   ℹ️ Notice: Source resolution is {src_w}x{src_h}; upscaling cleanly to 1080x1080 with unsharp enhancement.", flush=True)

            words = captions.transcribe(piece, model_size=whisper_model)
            print(f"   Transcribed {len(words)} spoken words in segment.", flush=True)

            out_short = out_dir / f"viceprint_{cand['id'].replace(':', '_')}.mp4"
            if not topic_id and len(words) >= 35:
                # Path A: Video already contains clear spoken guide/explanation -> snap & style cleanly
                dur = captions.snap_speech_boundaries(words, min(raw_dur, 57.0), min_duration=38.0)
                print(f"   Snapped spoken clip to {dur:.1f}s; rendering unbranded Viceprint layout...", flush=True)
                render.render(
                    piece, out_short, layout="viceprint", words=words,
                    hook="", credit="", progress_bar=True, require_cam=False,
                    duration=dur, caption_style="viceprint"
                )
                title = viceprint._clean_viceprint_title(cand["title"])
                desc = f"{title}\n\n#Shorts #GTA6 #Gaming"
                tags = ["gta 6", "gta 6 secrets", "gta 6 tips", "gta 6 gameplay", "gaming", "shorts"]
                wc = len(words)
            else:
                # Path B: No-commentary gameplay or explicit --topic -> edge-tts + fast 3s jumpcuts + ducked game audio
                topic = viceprint.pick_topic(records, preferred_id=topic_id)
                print(f"   Applying Viceprint narration & 3s jump-cuts for topic: '{topic['title']}'", flush=True)
                narration_mp3 = cand_dir / "narration.mp3"
                n_words, dur = viceprint.synthesize_narration(topic["script"], narration_mp3)
                jumpcut_vid = cand_dir / "jumpcut.mp4"
                viceprint.build_viceprint_jumpcuts(piece, dur + 0.5, jumpcut_vid, cut_sec=3.0)

                mixed_input = cand_dir / "mixed_input.mp4"
                mix_cmd = [
                    "ffmpeg", "-y", "-loglevel", "error", "-i", str(jumpcut_vid), "-i", str(narration_mp3),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{dur:.2f}", str(mixed_input)
                ]
                subprocess.run(mix_cmd, check=True)
                render.render(
                    mixed_input, out_short, layout="viceprint", words=n_words,
                    hook="", credit="", progress_bar=True, require_cam=False,
                    duration=dur, caption_style="viceprint"
                )
                title = topic["title"]
                desc = f"{topic['script']}\n\n#Shorts #GTA6 #Gaming"
                tags = topic["tags"]
                wc = len(n_words)

            state[cand["id"]] = {
                "title": cand["title"], "channel": cand.get("channel", ""),
                "url": cand["url"], "at": int(time.time()), "ok": True, "mode": "viceprint"
            }
            save_state(state)
            piece.unlink(missing_ok=True)
            post = viceprint.create_viceprint_post(
                out_short, title=title, description=desc, tags=tags,
                words_count=wc, duration=dur, source_url=cand["url"]
            )
            (out_dir / "posts.json").write_text(json.dumps([post], indent=2, ensure_ascii=False), encoding="utf-8")
            return [post]
        except Exception as exc:
            print(f"   ! Candidate failed ({exc}); trying next candidate...", flush=True)
            state[cand["id"]] = {"title": cand["title"], "url": cand["url"], "at": int(time.time()), "ok": False}
            save_state(state)
            piece.unlink(missing_ok=True)

    return []


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    passthru = []
    if "--" in argv:
        i = argv.index("--")
        argv, passthru = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--game", default="gta6", help='"gta6" (default) or any game name')
    p.add_argument("--count", type=int, default=1, help="how many new streams/videos to clip (default 1)")
    p.add_argument("--top", type=int, default=1, help="Shorts per stream/video (default 1)")
    p.add_argument("--min-views", type=int, default=1000)
    p.add_argument("--min-minutes", type=int, default=10)
    p.add_argument("--streamers", default="streamers.txt")
    p.add_argument("--out", default="clips")
    p.add_argument("--cookies")
    p.add_argument("--proxy")
    p.add_argument("--tdl", default="TwitchDownloaderCLI")
    p.add_argument("--mode", default="auto", choices=["auto", "stream", "viceprint"],
                   help="Dual Mode: 'auto' (alternates & falls back), 'stream' (facecam stack), 'viceprint' (unbranded secrets/gameplay)")
    p.add_argument("--topic", default=None, help="Viceprint topic id override (e.g. 'secret_workout')")
    p.add_argument("--whisper-model", default="small")
    p.add_argument("--list", action="store_true", help="only print what would be picked")
    a = p.parse_args(argv)

    if datetime.date.today() <= datetime.date(2026, 12, 1) and a.game != "gta6":
        print(f"🎯 [GTA 6 Priority] Override active until 1 December 2026: focusing on GTA 6 (requested {a.game}).", flush=True)
        a.game = "gta6"

    cookies = sources.find_cookies(a.cookies)
    proxy = a.proxy or os.environ.get("YOUTUBE_PROXY")
    state = load_state()

    out_root = Path(a.out)
    out_root.mkdir(parents=True, exist_ok=True)

    selected_mode = resolve_mode(a.mode)
    if a.mode == "auto":
        print(f"🔄 [Dual Mode] Auto-selected '{selected_mode}' based on upload history.", flush=True)

    if selected_mode == "viceprint":
        sub = out_root / "01_viceprint"
        posts = produce_viceprint_short(
            sub, state=state, topic_id=a.topic, proxy=proxy, cookies=cookies,
            whisper_model=a.whisper_model, list_only=a.list
        )
        if a.list:
            return 0
        if posts:
            (out_root / "posts.json").write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\n🎉 {len(posts)} Viceprint Short rendered successfully. Saved to {out_root}/posts.json", flush=True)
            return 0
        print("\n⚠️ No eligible Viceprint Short could be rendered.", flush=True)
        return EXIT_NO_CLIPS

    print(f"🔎 Looking for today's top {'GTA 6' if a.game == 'gta6' else a.game} streams and videos...", flush=True)
    picks, ranked = discover.discover(a.game, a.count, a.min_minutes, a.min_views, set(state),
                                      cookies, proxy, a.streamers)
    print(f"\n{len(ranked)} new candidates passed the filters. Top 10:")
    for i, c in enumerate(ranked[:10], 1):
        mins = int(c["duration"] // 60) if c["duration"] else "?"
        tag = "ended stream" if c["live_status"] == "was_live" else "video"
        print(f"  {i:>2}. {(format(c['views'], ',') if c.get('views_known', True) else '?'):>9} views  {mins:>4} min  {tag:<12} {c['channel'][:22]:<22} | {c['title'][:60]}")

    if a.list:
        if not picks:
            print("\nNothing new in Stream mode; checking Dual Mode Viceprint fallback list:")
            produce_viceprint_short(out_root / "01_viceprint_preview", state=state, topic_id=a.topic,
                                    proxy=proxy, cookies=cookies, list_only=True)
        return 0

    all_posts, done = [], 0
    if picks:
        candidates = ranked if ranked else picks
        for n, c in enumerate(candidates, 1):
            if done >= a.count:
                break
            sub = out_root / f"{done + 1:02d}_{c['id'].replace(':', '_')}"
            print(f"\n🎬 [Short {done + 1}/{a.count} - Candidate {n}/{len(candidates)}] {c['channel']} | {c['title']}\n   {c['url']}", flush=True)
            cmd = [sys.executable, "chat_clips.py", "--url", c["url"], "--game", "gta6" if a.game == "gta6" else "none", "--top", str(a.top),
                   "--out", str(sub), "--credit", c["channel"] or "", "--layout", "stack", "--require-cam", "--chat-delay", "4.0",
                   "--before", "34", "--after", "18", "--whisper-model", a.whisper_model]
            if cookies:
                cmd += ["--cookies", str(cookies)]
            if proxy:
                cmd += ["--proxy", proxy]
            if c["platform"] == "twitch":
                cmd += ["--tdl", a.tdl]
            cmd += passthru
            rc = subprocess.run(cmd).returncode
            state[c["id"]] = {"title": c["title"], "channel": c["channel"], "url": c["url"],
                              "at": int(time.time()), "ok": rc == 0, "mode": "stream"}
            save_state(state)
            posts_file = sub / "posts.json"
            if rc == 0 and posts_file.exists():
                posts = json.loads(posts_file.read_text(encoding="utf-8"))
                for post in posts:
                    post["source_url"] = c["url"]
                    post["source_title"] = c["title"]
                    post["mode"] = "stream"
                all_posts += posts
                done += 1
            else:
                print(f"   ! skipped (exit {rc}), trying next candidate...", flush=True)

    if not all_posts and a.mode != "stream":
        print("\n⚠️ No valid streamer with facecam found; falling back to Viceprint mode to maintain daily cadence...", flush=True)
        sub = out_root / "01_viceprint_fallback"
        all_posts = produce_viceprint_short(
            sub, state=state, topic_id=a.topic, proxy=proxy, cookies=cookies,
            whisper_model=a.whisper_model, list_only=False
        )

    if not all_posts:
        print("\n⚠️ No usable Shorts could be generated today.", flush=True)
        return EXIT_NO_CLIPS

    (out_root / "posts.json").write_text(json.dumps(all_posts, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n🎉 {len(all_posts)} Shorts saved. Titles in {out_root}/posts.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
