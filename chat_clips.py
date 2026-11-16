#!/usr/bin/env python3
"""
chat-clips: find the best moments of a Twitch stream from its chat, and cut them as vertical clips.

Usage:
    python3 chat_clips.py chat.json [options]

Options:
    --vod <ID/URL>      Twitch VOD ID or URL (downloads only the clips needed)
    --video <file.mp4>  Cut from a local video file
    --emotes            Filter by reaction emotes/keywords (LMAO, KEKW, 💀, WTF, NO WAY, etc.)
    --min-score <num>   Minimum spike multiplier threshold to clip (e.g. 2.5 or 4.0)
    --layout <type>     Vertical format: 'stack' (cam top, game bottom), 'blur' (ambient 16:9), 'crop' (center zoom)
    --cam <pos>         Webcam location for 'stack': 'auto', 'bottom-left', 'top-left', 'bottom-right', 'top-right'
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
import re
import json
import math
import shutil
import subprocess
from pathlib import Path

REACTION_PATTERN = re.compile(
    r'\b(lmao+|kekw|omegalul|lol+|rofl|dead|💀|😭|icant|wtf|no\s*way|holy|omg|yooo+|clutch|fail|cooked|doxxed|w|l)\b',
    re.IGNORECASE
)


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
        "layout": "stack",
        "cam": "auto",
        "emotes": False,
        "min_score": 1.0,
        "dry_run": False,
    }

    skip_next = False
    for i, a in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if a == "--dry-run":
            options["dry_run"] = True
        elif a in ("--emotes", "--filter-emotes"):
            options["emotes"] = True
        elif a.startswith("--"):
            key = a[2:].replace("-", "_")
            if i + 1 < len(args):
                val = args[i + 1]
                if key in ("bucket", "top", "before", "after", "gap"):
                    options[key] = int(val)
                elif key == "min_score":
                    options[key] = float(val)
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


def detect_webcam_crop(video_file, default_pos="bottom-left"):
    """
    Detects streamer webcam coordinates (x, y, w, h) on 16:9 1920x1080 source.
    Defaults to bottom-left quadrant if auto-detection is unavailable.
    """
    PRESETS = {
        "bottom-left": (0, 240, 460, 360),
        "top-left": (0, 0, 460, 360),
        "bottom-right": (1460, 240, 460, 360),
        "top-right": (1460, 0, 460, 360),
    }

    if default_pos in PRESETS and default_pos != "auto":
        return PRESETS[default_pos]

    # Attempt OpenCV face detection if available
    try:
        import cv2
        cascade_candidates = [
            "/data/data/com.termux/files/usr/share/opencv5/haarcascades/haarcascade_frontalface_default.xml",
            "/data/data/com.termux/files/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
            "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        ]
        casc_path = next((p for p in cascade_candidates if os.path.exists(p)), None)
        if casc_path:
            cap = cv2.VideoCapture(str(video_file))
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                clf = cv2.CascadeClassifier(casc_path)
                faces = clf.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40))
                if len(faces) > 0:
                    fx, fy, fw, fh = faces[0]
                    # Center a 460x360 box around face center
                    cx = max(0, min(1920 - 460, fx + fw // 2 - 230))
                    cy = max(0, min(1080 - 360, fy + fh // 2 - 180))
                    return (cx, cy, 460, 360)
    except Exception:
        pass

    return PRESETS.get(default_pos, PRESETS["bottom-left"])


def get_filter_args(layout="stack", cam_pos="auto", video_sample=None):
    if layout == "crop":
        return ["-vf", "crop=w=floor(ih*9/16/2)*2:h=ih:x=(iw-ow)/2:y=0,scale=1080:1920,setsar=1"]
    elif layout == "stack":
        cx, cy, cw, ch = detect_webcam_crop(video_sample, default_pos=cam_pos) if video_sample else (0, 240, 460, 360)
        # Cam at top (1080x720), ambient blur in middle, gameplay at bottom (1080x1080 at y=840)
        fc = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.35[bg];"
            f"[0:v]crop=w={cw}:h={ch}:x={cx}:y={cy},scale=1080:720[cam];"
            f"[0:v]crop=w=1440:h=1080:x=240:y=0,scale=1080:1080[game];"
            f"[bg][cam]overlay=0:0[t1];"
            f"[t1][game]overlay=0:840[v_out]"
        )
        return ["-filter_complex", fc, "-map", "[v_out]", "-map", "0:a?"]
    else:
        # Default 'blur': Ambient blurred background with full 16:9 widescreen in center
        fc = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.15[bg];"
            "[0:v]scale=1080:-1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v_out]"
        )
        return ["-filter_complex", fc, "-map", "[v_out]", "-map", "0:a?"]


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
    filtered_count = 0
    for c in comments:
        if isinstance(c, (int, float)):
            times.append(float(c))
        elif isinstance(c, dict) and "content_offset_seconds" in c:
            val = c["content_offset_seconds"]
            body = c.get("message", {}).get("body", "")
            if isinstance(val, (int, float)) and val >= 0:
                if opts["emotes"]:
                    if REACTION_PATTERN.search(body):
                        times.append(float(val))
                        filtered_count += 1
                else:
                    times.append(float(val))

    if not times:
        if opts["emotes"]:
            print("Error: No messages matched reaction emotes/keywords. Try running without --emotes.", file=sys.stderr)
        else:
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
    around = max(1, round(300 / bucket_size))
    scores = []
    for i in range(num_buckets):
        left = max(0, i - around)
        right = min(num_buckets, i + around + 1)
        base = calculate_median(counts[left:right])
        score = counts[i] / (base + 1.0)
        scores.append(score)

    # 4. Find top peaks with gap separation and minimum score filter
    order = sorted(range(num_buckets), key=lambda idx: scores[idx], reverse=True)
    top_n = opts["top"]
    min_gap = opts["gap"]
    min_score = opts["min_score"]
    peaks = []

    for idx in order:
        if len(peaks) >= top_n:
            break
        if counts[idx] < 5 or scores[idx] < min_score:
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
    graph_str = "".join(bars[min(len(bars) - 1, round((c / top_val) * (len(bars) - 1)))] for c in cols)

    mode_label = " (Reaction Emote Filter Active)" if opts["emotes"] else ""
    print(f"\n💬 {len(times)} chat messages{mode_label}, ⏱ {format_hms(total_length)} of stream\n")
    print(graph_str)
    spacing = max(1, len(cols) - len(format_hms(total_length)) - 7)
    print(f"0:00:00{' ' * spacing}{format_hms(total_length)}\n")

    if not peaks:
        print(f"No moments reached the minimum multiplier threshold of {min_score}x. Try lowering --min-score.")
        sys.exit(0)

    print("Top Moments:")
    out_dir = Path(opts["out"])
    out_dir.mkdir(parents=True, exist_ok=True)

    moments_data = []
    before = opts["before"]
    after = opts["after"]
    for i, p in enumerate(peaks):
        clip_start = max(0, p["t"] - before)
        clip_end = p["t"] + after
        duration = clip_end - clip_start
        clip_file = f"clip_{i + 1:02d}.mp4"
        print(f"#{i + 1}  {format_hms(p['t'])}  {p['msgs']} msgs in {bucket_size}s  ({p['score']}x normal)  -> clip {format_hms(clip_start)} to {format_hms(clip_end)}")
        moments_data.append({
            "rank": i + 1,
            "t": p["t"],
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
    print(f"\n✅ Saved moment data to {moments_file}.")

    if opts["dry_run"]:
        print("Dry run requested; skipping video cutting.")
        sys.exit(0)

    if not opts["vod"] and not opts["video"]:
        print("To cut video clips, provide --vod <ID/URL> or --video <local.mp4>")
        sys.exit(0)

    # 6. Cut vertical clips
    tdl_bin = resolve_tdl(opts["tdl"])
    layout = opts.get("layout", "stack")
    cam_pos = opts.get("cam", "auto")

    codec_args = [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k"
    ]

    for item in moments_data:
        out_path = out_dir / item["clipFile"]
        print(f"\n✂️ Cutting #{item['rank']} -> {out_path} ({item['clipStart']} to {item['clipEnd']}, {item['duration']}s, layout: {layout})")

        filter_args = get_filter_args(layout=layout, cam_pos=cam_pos, video_sample=opts["video"])

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
            print(f"  Downloading stream segment with {tdl_bin}...")
            run_cmd([
                tdl_bin, "videodownload",
                "--id", opts["vod"],
                "-b", item["clipStart"],
                "-e", item["clipEnd"],
                "-o", str(piece_path)
            ])
            print(f"  Rendering 9:16 vertical 1080x1920 ({layout}) with ffmpeg...")
            filter_args_piece = get_filter_args(layout=layout, cam_pos=cam_pos, video_sample=str(piece_path))
            run_cmd([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(piece_path),
                *filter_args_piece,
                *codec_args,
                str(out_path)
            ])
            if piece_path.exists():
                piece_path.unlink()

        print(f"  ✅ Saved: {out_path}")

    print(f"\n🎉 Finished! Processed {len(moments_data)} clips in {out_dir}/")


if __name__ == "__main__":
    main()
