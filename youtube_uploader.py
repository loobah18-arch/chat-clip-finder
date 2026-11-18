#!/usr/bin/env python3
"""
YouTube Shorts Auto-Uploader for Chat Clip Finder.
Uploads 9:16 vertical clips directly to YouTube channel via Data API v3.

Algorithm protection (same Candle Gate as auto-clipper-shorts), checked before every upload:
  Layer 0  24-hour spacing: never upload within 24 h of the last Short (inline wait if <= 30 min left)
  Layer 1  early momentum: last Short hit >= 2,000 views in its first 24 h -> let it run
           (near 1,700-1,999 -> 1-hour timer, then re-check)
  Layer 2  viral velocity: last Short still doing >= 2,500 views/hr -> hold until it cools for 24 h
Blocked uploads exit with code 2 (a clean "deferred", not a failure). --force skips the gate.
Every real upload is logged to upload_history.json, which the gates read.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
import requests

from candle_gate import CandleGate

HISTORY_FILE = Path(__file__).resolve().parent / "upload_history.json"
EXIT_DEFERRED = 2


def log(msg):
    print(msg, flush=True)


def youtube_client():
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    return build("youtube", "v3", credentials=Credentials(token=get_access_token()))


def record_upload(video_id, title, video_path, privacy, source_url="", status="uploaded"):
    try:
        records = json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if HISTORY_FILE.exists() else []
    except Exception:
        records = []
    records.append({
        "video_id": video_id, "title": title, "url": f"https://youtube.com/shorts/{video_id}",
        "source_url": source_url, "video_path": str(video_path), "privacy": privacy,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": status,
    })
    HISTORY_FILE.write_text(json.dumps(records[-200:], indent=2, ensure_ascii=False), encoding="utf-8")


def run_timer(seconds, interval=600, sleep_fn=time.sleep):
    remaining = seconds
    log(f"⏱️ Starting automatic timer for {seconds // 60} minutes...")
    while remaining > 0:
        step = min(remaining, interval)
        log(f"⏱️ Timer active: {remaining // 60} minute(s) until re-check...")
        sleep_fn(step)
        remaining -= step


def check_candle_gate(force=False, client=None, auto_timer=True, gate=None, sleep_fn=time.sleep):
    """(can_upload, message). Fail-open on errors, like the other repos."""
    if force:
        return True, "Upload forced by user override (--force)."
    gate = gate or CandleGate()
    if client is None:
        try:
            client = youtube_client()
        except Exception as e:
            return True, f"Could not reach YouTube for the gate ({e}); clearance granted"
    result = gate.evaluate_live_channel(client)
    ev = result.get("candle_evaluation", {})
    if not ev:
        return result.get("can_upload", True), result.get("reason", "Clearance granted.")
    if ev.get("requires_spacing_sleep") and auto_timer:
        secs = ev.get("spacing_sleep_seconds", 0)
        log(f"⏱️ [SpacingGuard] {secs // 60}m left of the 24h spacing, waiting inline...")
        sleep_fn(secs)
        return True, "✅ 24-Hour Spacing Cleared after inline wait."
    if ev.get("requires_timer") and auto_timer:
        log(f"⏳ {ev.get('recommendation')}")
        run_timer(ev.get("timer_seconds", 3600), sleep_fn=sleep_fn)
        ev = gate.evaluate_live_channel(client).get("candle_evaluation", {})
    return ev.get("can_upload", True), f"[{ev.get('active_layer', 'gate')}] {ev.get('recommendation', 'Clearance granted.')}"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]


def get_access_token():
    """Exchange OAuth credentials for a fresh access token."""
    creds_file = os.path.expanduser("~/.youtube_credentials.json")
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

    if not (client_id and client_secret and refresh_token) and os.path.exists(creds_file):
        try:
            with open(creds_file, "r") as f:
                d = json.load(f)
            client_id = client_id or d.get("client_id")
            client_secret = client_secret or d.get("client_secret")
            refresh_token = refresh_token or d.get("refresh_token")
        except Exception:
            pass

    if not (client_id and client_secret and refresh_token):
        raise RuntimeError("Missing YouTube credentials: set CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN")

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to refresh access token ({resp.status_code}): {resp.text}")

    return resp.json()["access_token"]


def upload_short(video_path: Path, title: str, description: str = "", tags: list = None, privacy: str = "public"):
    """Resumable upload of a video to YouTube Shorts."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials

    access_token = get_access_token()
    creds = Credentials(token=access_token)
    youtube = build("youtube", "v3", credentials=creds)

    clean_title = title.strip()
    if "#shorts" not in clean_title.lower():
        clean_title = f"{clean_title[:85]} #Shorts"

    tags = tags or ["shorts", "gaming", "streamer", "twitch"]
    tags = [t for t in tags if t][:15]

    body = {
        "snippet": {
            "title": clean_title,
            "description": (description or f"{clean_title}\n\n#Shorts #Gaming #TwitchHighlights")[:4900],
            "tags": [t.replace("#", "") for t in tags],
            "categoryId": "20",  # Gaming
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"🚀 Uploading '{clean_title}' to YouTube...")
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"   ↳ Upload progress: {int(status.progress() * 100)}%")

    video_id = resp.get("id")
    video_url = f"https://youtube.com/shorts/{video_id}"
    print(f"✅ Published successfully: {video_url}")
    return video_id


def main():
    parser = argparse.ArgumentParser(description="Upload video(s) to YouTube Shorts")
    parser.add_argument("video", nargs="?", help="Path to video file (.mp4)")
    parser.add_argument("--posts", help="posts.json from chat_clips.py: upload every clip with its own title")
    parser.add_argument("--title", help="Video title (single-video mode)")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--tags", default="shorts,twitch,highlights,gaming", help="Comma-separated tags")
    parser.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    parser.add_argument("--max", type=int, default=1,
                        help="--posts mode: how many Shorts to upload this run (default 1, the best clip)")
    parser.add_argument("--force", action="store_true", help="skip the Candle Gate protection layers")
    parser.add_argument("--no-timer", action="store_true", help="don't wait inline for the gate's timers")

    args = parser.parse_args()
    if args.posts:
        with open(args.posts, encoding="utf-8") as f:
            posts = json.load(f)
        posts = [p for p in posts if Path(p["file"]).exists()]
        if not posts:
            print("No clips in posts.json, nothing to upload.")
            return
        ok, msg = check_candle_gate(args.force, auto_timer=not args.no_timer)
        log(f"🚦 Candle Gate: {msg}")
        if not ok:
            log("🛑 Upload deferred by the Candle Gate to protect the last Short's push.")
            sys.exit(EXIT_DEFERRED)
        uploaded = failed = 0
        for p in posts:
            if uploaded >= args.max:
                break
            path = Path(p["file"])
            try:
                vid = upload_short(path, p["title"], p.get("description", ""), p.get("tags"), args.privacy)
                record_upload(vid, p["title"], path, args.privacy, p.get("source_url", ""))
                uploaded += 1
            except Exception as e:  # try the next clip if one fails
                failed += 1
                print(f"Upload failed for {path}: {e}", file=sys.stderr)
        sys.exit(0 if uploaded else 1)

    if not args.video or not args.title:
        parser.error("give a video and --title, or --posts posts.json")
    video_path = Path(args.video)
    if not video_path.exists():
        print(f"Error: file not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    ok, msg = check_candle_gate(args.force, auto_timer=not args.no_timer)
    log(f"🚦 Candle Gate: {msg}")
    if not ok:
        log("🛑 Upload deferred by the Candle Gate to protect the last Short's push.")
        sys.exit(EXIT_DEFERRED)
    vid = upload_short(video_path, args.title, args.description, tags, args.privacy)
    record_upload(vid, args.title, video_path, args.privacy)


if __name__ == "__main__":
    main()
