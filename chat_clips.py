#!/usr/bin/env python3
"""
chat-clips: find the best moments of a Twitch stream from its chat, and cut them as vertical clips.

Usage:
    python3 chat_clips.py chat.json [options]

Options:
    --vod <ID/URL>      Twitch VOD ID or URL (downloads only the clips needed)
    --video <file.mp4>  Cut from a local video file
    --top <number>      Number of clips to make (default: 5)
    --before <seconds>  Seconds before spike to start clip (default: 20)
    --after <seconds>   Seconds after spike to end clip (default: 10)
    --gap <seconds>     Minimum seconds between two clips (default: 90)
    --bucket <seconds>  Window size for counting messages (default: 10)
    --out <dir>         Output directory (default: clips)
    --tdl <path>        Path to TwitchDownloaderCLI executable
    --dry-run           Only find moments and write moments.json, skip video cutting
    --help, -h          Show help message
"""

import sys
import os
import json
import math
import shutil
import subprocess
from pathlib import Path


def parse_args():
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        sys.exit(0 if ("-h" in args or "--help" in args) else 1)

    options = {
        "chat_file": None,
        "bucket": 10,
        "top": 5,
        "before": 20,
        "after": 10,
        "gap": 90,
        "out": "clips",
        "vod": None,
        "video": None,
        "tdl": None,
        "layout": "blur",
        "dry_run": False,
    }

    skip_next = False
    for i, a in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if a == "--dry-run":
            options["dry_run"] = True
        elif a.startswith("--"):
            key = a[2:].replace("-", "_")
            if i + 1 < len(args):
                val = args[i + 1]
                if key in ("bucket", "top", "before", "after", "gap"):
                    options[key] = int(val)
                else:
                    options[key] = val
                skip_next = True
        elif options["chat_file"] is None:
            options["chat_file"] = a

    if not options["chat_file"]:
        print("Error: Please provide a chat JSON file.")
        sys.exit(1)

    return options


def resolve_tdl(custom_path=None):
    if custom_path:
        return custom_path
    if os.path.exists("./TwitchDownloaderCLI"):
        return "./TwitchDownloaderCLI"
    if os.path.exists("./TwitchDownloaderCLI.exe"):
        return "./TwitchDownloaderCLI.exe"
    if sys.platform == "win32":
        return "TwitchDownloaderCLI.exe"
    return "TwitchDownloaderCLI"


def format_hms(seconds):
    seconds = max(0, int(round(seconds)))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"


def calculate_median(arr):
    if not arr:
        return 0
    s = sorted(arr)
    return s[len(s) // 2]


def run_cmd(cmd_list):
    res = subprocess.run(cmd_list)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {res.returncode}: {' '.join(cmd_list)}")


def main():
    opts = parse_args()
    chat_path = Path(opts["chat_file"])
    if not chat_path.exists():
        print(f"Error: Chat file not found: {chat_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(chat_path, "r", encoding="utf-8") as f:
            chat_data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON from {chat_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # 1. Parse comments
    if isinstance(chat_data, list):
        comments = chat_data
    else:
        comments = chat_data.get("comments", [])

    times = []
    for c in comments:
        if isinstance(c, (int, float)):
            times.append(float(c))
        elif isinstance(c, dict) and "content_offset_seconds" in c:
            val = c["content_offset_seconds"]
            if isinstance(val, (int, float)) and val >= 0:
                times.append(float(val))

    if not times:
        print("Error: No chat messages found. Is this a TwitchDownloader chat .json file?", file=sys.stderr)
        sys.exit(1)

    # 2. Count messages per bucket
    video_len = 0
    if isinstance(chat_data, dict) and "video" in chat_data and isinstance(chat_data["video"], dict):
        video_len = chat_data["video"].get("length", 0)
    total_length = max(max(times), video_len)

    bucket_size = opts["bucket"]
    num_buckets = math.ceil(total_length / bucket_size) + 1
    counts = [0] * num_buckets
    for t in times:
        idx = int(t // bucket_size)
        if idx < num_buckets:
            counts[idx] += 1

    # 3. Score calculation (Local Median Baseline)
    # Compares each bucket to the surrounding 5 minutes (300 seconds)
    around = max(1, round(300 / bucket_size))
    scores = []
    for i in range(num_buckets):
        left = max(0, i - around)
        right = min(num_buckets, i + around + 1)
        base = calculate_median(counts[left:right])
        score = counts[i] / (base + 1.0)
        scores.append(score)

    # 4. Find top peaks with gap separation
    order = sorted(range(num_buckets), key=lambda idx: scores[idx], reverse=True)
    top_n = opts["top"]
    min_gap = opts["gap"]
    peaks = []

    for idx in order:
        if len(peaks) >= top_n:
            break
        if counts[idx] < 5:  # Minimum threshold for a chat explosion
            continue
        t = idx * bucket_size
        if any(abs(p["t"] - t) < min_gap for p in peaks):
            continue
        peaks.append({
            "t": t,
            "msgs": counts[idx],
            "score": round(scores[idx], 1),
        })

    peaks.sort(key=lambda p: p["t"])

    # 5. ASCII visualization & summary
    bars = " ▁▂▃▄▅▆▇█"
    cols_count = 60
    per = max(1, math.ceil(num_buckets / cols_count))
    cols = []
    for k in range(math.ceil(num_buckets / per)):
        window = counts[k * per : (k + 1) * per]
        cols.append(max(window) if window else 0)

    top_val = max(cols) if cols and max(cols) > 0 else 1
    bar_str = "".join(bars[min(8, round((c / top_val) * 8))] for c in cols)

    print(f"\n💬 {len(times)} chat messages, ⏱ {format_hms(total_length)} of stream\n")
    print(bar_str)
    end_str = format_hms(total_length)
    spacing = max(1, len(cols) - len(end_str) - 7)
    print(f"0:00:00{' ' * spacing}{end_str}\n")

    print("Top Moments:")
    before = opts["before"]
    after = opts["after"]
    out_dir = Path(opts["out"])
    out_dir.mkdir(parents=True, exist_ok=True)

    moments_data = []
    for rank, p in enumerate(peaks, 1):
        clip_start = max(0, p["t"] - before)
        clip_end = p["t"] + after
        duration = clip_end - clip_start
        clip_file = f"clip_{rank:02d}.mp4"
        print(f"#{rank}  {format_hms(p['t'])}  {p['msgs']} msgs in {bucket_size}s  ({p['score']}x normal)  -> clip {format_hms(clip_start)} to {format_hms(clip_end)}")
        moments_data.append({
            "rank": rank,
            "t": p["t"],
            "timestamp": format_hms(p["t"]),
            "msgs": p["msgs"],
            "score": p["score"],
            "start": clip_start,
            "end": clip_end,
            "clipStart": format_hms(clip_start),
            "clipEnd": format_hms(clip_end),
            "duration": duration,
            "clipFile": clip_file,
        })

    moments_file = out_dir / "moments.json"
    with open(moments_file, "w", encoding="utf-8") as f:
        json.dump(moments_data, f, indent=2)

    if opts["dry_run"] or (not opts["vod"] and not opts["video"]):
        print(f"\n✅ Saved moments list to {moments_file}.")
        print("To cut video clips, provide --vod <ID/URL> or --video <local.mp4>")
        sys.exit(0)

    # 6. Cut vertical clips (9:16 layout)
    tdl_bin = resolve_tdl(opts["tdl"])
    layout = opts.get("layout", "blur")

    if layout == "crop":
        filter_args = ["-vf", "crop=w=floor(ih*9/16/2)*2:h=ih:x=(iw-ow)/2:y=0,scale=1080:1920,setsar=1"]
    else:
        # Default 'blur': Ambient blurred background with full 16:9 widescreen in center
        filter_args = [
            "-filter_complex",
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.15[bg];"
            "[0:v]scale=1080:-1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        ]

    codec_args = [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k"
    ]

    for item in moments_data:
        out_path = out_dir / item["clipFile"]
        print(f"\n✂️ Cutting #{item['rank']} -> {out_path} ({item['clipStart']} to {item['clipEnd']}, {item['duration']}s, layout: {layout})")

        if opts["video"]:
            run_cmd([
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(item["start"]),
                "-t", str(item["duration"]),
                "-i", opts["video"],
                *filter_args,
                *codec_args,
                str(out_path)
            ])
        else:
            piece_path = out_dir / f"piece_{item['rank']}.mp4"
            print(f"  Downloading segment via {tdl_bin}...")
            run_cmd([
                tdl_bin, "videodownload",
                "--id", opts["vod"],
                "-b", item["clipStart"],
                "-e", item["clipEnd"],
                "-o", str(piece_path)
            ])
            print(f"  Rendering 9:16 vertical 1080x1920 ({layout}) with ffmpeg...")
            run_cmd([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(piece_path),
                *filter_args,
                *codec_args,
                str(out_path)
            ])
            if piece_path.exists():
                piece_path.unlink()

    print(f"\n✨ Done! {len(moments_data)} vertical clips generated in ./{opts['out']}/")


if __name__ == "__main__":
    main()
