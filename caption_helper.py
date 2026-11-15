#!/usr/bin/env python3
"""
Caption Helper for Chat Clip Finder (Step 9 of the Guide)

Generates clean vertical-optimized subtitles (.srt or .ass) and burns them
onto vertical 9:16 clips using FFmpeg.

Usage:
    python3 caption_helper.py <clip.mp4> [options]

Options:
    --text "Text here"   Burn a fixed hook text (e.g. "Wait for it...", "Chat lost it here")
    --srt <file.srt>     Burn an existing SRT subtitle file
    --out <file.mp4>     Output file path (default: <input>_captioned.mp4)
    --style <style>      Subtitle styling preset: 'bold_yellow', 'clean_white', 'tiktok'
"""

import sys
import subprocess
from pathlib import Path


STYLE_PRESETS = {
    "bold_yellow": (
        "Fontname=Arial,FontSize=22,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,"
        "BackColour=&H80000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=120"
    ),
    "clean_white": (
        "Fontname=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=120"
    ),
    "tiktok": (
        "Fontname=Impact,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=4,Shadow=2,Alignment=2,MarginV=140"
    ),
}


def burn_text(input_mp4, text, output_mp4, duration=4.0):
    """Burns an opening hook text into the first few seconds of a vertical clip."""
    # Escapes text for FFmpeg drawtext filter
    escaped_text = text.replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")
    drawtext_filter = (
        f"drawtext=text='{escaped_text}':fontcolor=white:fontsize=56:box=1:"
        f"boxcolor=black@0.6:boxborderw=16:x=(w-text_w)/2:y=(h-text_h)/3:"
        f"enable='between(t,0,{duration})'"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", input_mp4,
        "-vf", drawtext_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy",
        output_mp4
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Created hook-captioned clip: {output_mp4}")


def burn_subtitles(input_mp4, srt_file, output_mp4, style="bold_yellow"):
    """Burns SRT subtitle track into vertical 9:16 clip."""
    style_str = STYLE_PRESETS.get(style, STYLE_PRESETS["bold_yellow"])
    sub_filter = f"subtitles='{srt_file}':force_style='{style_str}'"

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", input_mp4,
        "-vf", sub_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy",
        output_mp4
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Created subtitled clip: {output_mp4}")


def main():
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    input_file = args[0]
    in_path = Path(input_file)
    if not in_path.exists():
        print(f"Error: Video file not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    out_file = None
    hook_text = None
    srt_file = None
    style = "bold_yellow"

    i = 1
    while i < len(args):
        if args[i] == "--out" and i + 1 < len(args):
            out_file = args[i + 1]
            i += 2
        elif args[i] == "--text" and i + 1 < len(args):
            hook_text = args[i + 1]
            i += 2
        elif args[i] == "--srt" and i + 1 < len(args):
            srt_file = args[i + 1]
            i += 2
        elif args[i] == "--style" and i + 1 < len(args):
            style = args[i + 1]
            i += 2
        else:
            i += 1

    if not out_file:
        out_file = str(in_path.with_name(f"{in_path.stem}_captioned{in_path.suffix}"))

    if srt_file:
        burn_subtitles(input_file, srt_file, out_file, style=style)
    elif hook_text:
        burn_text(input_file, hook_text, out_file)
    else:
        print("Please provide --text 'hook text' or --srt 'subtitles.srt'.")
        print("Tip: Most viral shorts use an opening hook: --text 'Wait for it 😳'")


if __name__ == "__main__":
    main()
