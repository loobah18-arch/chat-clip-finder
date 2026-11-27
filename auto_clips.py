#!/usr/bin/env python3
"""Hands-free mode: find today's top GTA 6 streams/videos, clip the ones not done yet.

    python3 auto_clips.py                      # 2 new sources, 3 Shorts each, into clips/
    python3 auto_clips.py --count 3 --top 2
    python3 auto_clips.py --list               # just show what it would pick

Remembers what it already clipped in state/processed.json, so each run picks new videos.
Extra flags after `--` go straight to chat_clips.py (e.g. -- --emotes --layout stack).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from ccf import discover, sources

STATE = Path("state/processed.json")


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    # keep the newest 500 so the file stays small
    items = sorted(state.items(), key=lambda kv: kv[1].get("at", 0), reverse=True)[:500]
    STATE.write_text(json.dumps(dict(items), indent=1, ensure_ascii=False), encoding="utf-8")


def produce_viceprint_short(out_dir: Path, topic_id=None, proxy=None, cookies=None):
    """Produces a complete Short in the 15M-view Viceprint formula."""
    from ccf import viceprint, render
    out_dir.mkdir(parents=True, exist_ok=True)
    history_file = Path("upload_history.json")
    records = []
    if history_file.exists():
        try:
            records = json.loads(history_file.read_text(encoding="utf-8"))
        except Exception:
            records = []

    topic = viceprint.pick_topic(records, preferred_id=topic_id)
    print(f"\n🎙️ [Viceprint Mode] Selected Topic: '{topic['title']}'", flush=True)

    narration_audio = out_dir / "narration.mp3"
    print("   Synthesizing narration via edge-tts (180 WPM fast pacing)...", flush=True)
    words, duration = viceprint.synthesize_narration(topic["script"], narration_audio)
    print(f"   Generated {len(words)} words ({duration:.1f}s)", flush=True)

    raw_footage = out_dir / "raw_gameplay.mp4"
    search_q = f"ytsearch1:{topic['search_query']}"
    print(f"   Downloading background GTA 6 gameplay: '{topic['search_query']}'...", flush=True)
    dl_cmd = [
        "yt-dlp", "--no-warnings", "--default-search", "ytsearch1",
        "--download-sections", f"*0-{int(duration + 10)}",
        "-f", "bestvideo[height>=720]+bestaudio/best[height>=720]/best",
        "--merge-output-format", "mp4",
        "-o", str(raw_footage),
    ]
    if cookies:
        dl_cmd += ["--cookies", str(cookies)]
    if proxy:
        dl_cmd += ["--proxy", proxy]
    dl_cmd.append(search_q)

    dl_ok = False
    try:
        res = subprocess.run(dl_cmd, capture_output=True, text=True)
        dl_ok = (res.returncode == 0 and raw_footage.exists())
    except Exception as exc:
        print(f"   ! Download exception ({exc})", flush=True)

    if not dl_ok or not raw_footage.exists():
        print("   ! Footage download unavailable; generating synthesized backdrop video for test/pipeline fallback...", flush=True)
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x111625:s=1920x1080:d={duration+2}:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw_footage)
        ], check=True, capture_output=True)

    mixed_input = out_dir / "mixed_input.mp4"
    mix_filter = "[0:a]volume=0.12[bgm];[1:a]volume=1.0[voc];[bgm][voc]amix=inputs=2:duration=first[aout]"
    mix_cmd = [
        "ffmpeg", "-y", "-i", str(raw_footage), "-i", str(narration_audio),
        "-filter_complex", mix_filter,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{duration:.2f}", str(mixed_input)
    ]
    res = subprocess.run(mix_cmd, capture_output=True)
    if res.returncode != 0:
        fallback_cmd = [
            "ffmpeg", "-y", "-i", str(raw_footage), "-i", str(narration_audio),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{duration:.2f}", str(mixed_input)
        ]
        subprocess.run(fallback_cmd, check=True, capture_output=True)

    out_short = out_dir / f"{topic['id']}.mp4"
    print(f"   Rendering Short in Viceprint format (1:1 square on blurred background)...", flush=True)
    render.render(
        mixed_input, out_short, layout="viceprint", words=words,
        hook=topic["hook"], credit="@grandtheftclipper",
        progress_bar=True, require_cam=False, duration=duration,
        caption_style="viceprint"
    )

    post = viceprint.create_viceprint_post(topic, out_short, words, duration, channel_handle="@grandtheftclipper")
    (out_dir / "posts.json").write_text(json.dumps([post], indent=2, ensure_ascii=False), encoding="utf-8")
    return [post]
    argv = list(sys.argv[1:] if argv is None else argv)
    passthru = []
    if "--" in argv:
        i = argv.index("--")
        argv, passthru = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--game", default="gta6", help='"gta6" (default) or any game name, e.g. "valorant", "minecraft"')
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
                   help="Dual Mode: 'auto' (alternates / fallback), 'stream' (facecam stack), 'viceprint' (narrated secrets)")
    p.add_argument("--topic", default=None, help="Viceprint topic id (e.g. 'secret_workout', 'creepiest_secret')")
    p.add_argument("--list", action="store_true", help="only print what would be clipped")
    a = p.parse_args(argv)

    import datetime
    if datetime.date.today() <= datetime.date(2026, 12, 1) and a.game != "gta6":
        print(f"🎯 [GTA 6 Priority] Override active until 1 December 2026: focusing on GTA 6 (requested {a.game}).", flush=True)
        a.game = "gta6"

    cookies = sources.find_cookies(a.cookies)
    proxy = a.proxy or os.environ.get("YOUTUBE_PROXY")
    state = load_state()

    out_root = Path(a.out)
    out_root.mkdir(parents=True, exist_ok=True)

    # Determine mode in Dual Mode
    selected_mode = a.mode
    history_file = Path("upload_history.json")
    last_mode = None
    if history_file.exists():
        try:
            records = json.loads(history_file.read_text(encoding="utf-8"))
            if records and isinstance(records, list):
                for rec in reversed(records):
                    if rec.get("status") == "uploaded":
                        last_mode = rec.get("mode") or ("viceprint" if rec.get("layout") == "viceprint" else "stream")
                        break
        except Exception:
            pass

    if selected_mode == "auto":
        # Dual Mode: alternate between stream stack and viceprint secrets
        if last_mode == "viceprint":
            selected_mode = "stream"
            print("🔄 [Dual Mode] Last upload was Viceprint; targeting Streamer Stack mode today.", flush=True)
        else:
            selected_mode = "viceprint"
            print("🔄 [Dual Mode] Last upload was Streamer Stack; targeting Viceprint mode today.", flush=True)

    if selected_mode == "viceprint":
        sub = out_root / "01_viceprint"
        posts = produce_viceprint_short(sub, topic_id=a.topic, proxy=proxy, cookies=cookies)
        (out_root / "posts.json").write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n🎉 {len(posts)} Viceprint Short rendered successfully. Title in {out_root}/posts.json", flush=True)
        return 0 if posts else 1

    print(f"🔎 Looking for today's top {'GTA 6' if a.game == 'gta6' else a.game} streams and videos...", flush=True)
    picks, ranked = discover.discover(a.game, a.count, a.min_minutes, a.min_views, set(state),
                                      cookies, proxy, a.streamers)
    print(f"\n{len(ranked)} new candidates passed the filters. Top 10:")
    for i, c in enumerate(ranked[:10], 1):
        mins = int(c["duration"] // 60) if c["duration"] else "?"
        tag = "ended stream" if c["live_status"] == "was_live" else "video"
        print(f"  {i:>2}. {(format(c['views'], ',') if c.get('views_known', True) else '?'):>9} views  {mins:>4} min  {tag:<12} {c['channel'][:22]:<22} | {c['title'][:60]}")
    if a.list or not picks:
        if not picks:
            print("\n⚠️ No new stream candidates passed the filters. Falling back to Viceprint mode to maintain daily cadence...", flush=True)
            sub = out_root / "01_viceprint_fallback"
            posts = produce_viceprint_short(sub, topic_id=a.topic, proxy=proxy, cookies=cookies)
            (out_root / "posts.json").write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")
            return 0 if posts else 1
        return 0

    all_posts, done = [], 0
    candidates = ranked if ranked else picks
    for n, c in enumerate(candidates, 1):
        if done >= a.count:
            break
        sub = out_root / f"{done + 1:02d}_{c['id'].replace(':', '_')}"
        print(f"\n🎬 [Short {done + 1}/{a.count} - Candidate {n}/{len(candidates)}] {c['channel']} | {c['title']}\n   {c['url']}", flush=True)
        cmd = [sys.executable, "chat_clips.py", "--url", c["url"], "--game", "gta6" if a.game == "gta6" else "none", "--top", str(a.top),
               "--out", str(sub), "--credit", c["channel"] or "", "--layout", "stack", "--require-cam", "--chat-delay", "4.0",
               "--before", "34", "--after", "18"]
        if cookies:
            cmd += ["--cookies", str(cookies)]
        if proxy:
            cmd += ["--proxy", proxy]
        if c["platform"] == "twitch":
            cmd += ["--tdl", a.tdl]
        cmd += passthru
        rc = subprocess.run(cmd).returncode
        state[c["id"]] = {"title": c["title"], "channel": c["channel"], "url": c["url"],
                          "at": int(time.time()), "ok": rc == 0}
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

    if not all_posts:
        print("\n⚠️ Streamer clipping yielded no usable clips (e.g. no facecam). Falling back to Viceprint mode...", flush=True)
        sub = out_root / "01_viceprint_fallback"
        all_posts = produce_viceprint_short(sub, topic_id=a.topic, proxy=proxy, cookies=cookies)

    (out_root / "posts.json").write_text(json.dumps(all_posts, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n🎉 {len(all_posts)} Shorts from {done} source(s). Titles in {out_root}/posts.json")
    return 0 if all_posts else 1


if __name__ == "__main__":
    sys.exit(main())
