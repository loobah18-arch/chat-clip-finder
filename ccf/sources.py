"""Where the stream comes from: Twitch VODs, YouTube videos / past live streams, or a local file.

YouTube needs a cookies file to get past "Sign in to confirm you're not a bot" (always on GitHub's
servers). The file is found the ClipKaro way: --cookies, then $YOUTUBE_COOKIES_FILE, then
youtube_cookies.txt / cookies.txt / any *cookies*.txt in the working folder (newest first).
An optional proxy (--proxy or $YOUTUBE_PROXY) helps when the runner's IP is blocked anyway.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

YT_RE = re.compile(r"(youtube\.com|youtu\.be)/", re.I)
TWITCH_RE = re.compile(r"(twitch\.tv/videos/|^\d{6,}$)", re.I)


def kind_of(url):
    if not url:
        return None
    if YT_RE.search(url):
        return "youtube"
    if TWITCH_RE.search(url.strip()):
        return "twitch"
    if Path(url).exists():
        return "file"
    return "ytdlp"  # anything else yt-dlp understands (Kick, X, ...)


def find_cookies(explicit=None):
    for p in (explicit, os.environ.get("YOUTUBE_COOKIES_FILE")):
        if p and Path(p).is_file():
            return str(p)
    named = [p for p in ("youtube_cookies.txt", "cookies.txt") if Path(p).is_file()]
    if named:
        return named[0]
    found = sorted((p for p in glob.glob("*cookies*.txt") if Path(p).is_file()),
                   key=lambda p: -Path(p).stat().st_mtime)
    return found[0] if found else None


def _ytdlp_base(cookies=None, proxy=None):
    exe = shutil.which("yt-dlp")
    cmd = [exe] if exe else [sys.executable, "-m", "yt_dlp"]
    cmd += ["--no-warnings", "--no-playlist", "--retries", "5", "--fragment-retries", "10"]
    cookies = find_cookies(cookies)
    if cookies:
        cmd += ["--cookies", cookies]
    proxy = proxy or os.environ.get("YOUTUBE_PROXY")
    if proxy:
        cmd += ["--proxy", proxy]
    return cmd


def _run(cmd, what):
    print(f"   $ {' '.join(c if ' ' not in c else repr(c) for c in cmd[:3])} ... ({what})", flush=True)
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"{what} failed (exit {res.returncode}). For YouTube, refresh your cookies "
                           f"(export them again while logged in) or set a proxy.")


def fetch_chat(url, out_dir, cookies=None, proxy=None, tdl="TwitchDownloaderCLI"):
    """Download the chat replay. Returns the chat file path, or None if the video has no chat."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    k = kind_of(url)
    if k == "twitch":
        out = out_dir / "chat.json"
        _run([tdl, "chatdownload", "--id", url, "-o", str(out)], "Twitch chat download")
        return out
    if k in ("youtube", "ytdlp"):
        tmpl = str(out_dir / "chat")
        cmd = _ytdlp_base(cookies, proxy) + ["--skip-download", "--write-subs", "--sub-langs", "live_chat",
                                              "-o", tmpl, url]
        try:
            _run(cmd, "YouTube live-chat replay download")
        except RuntimeError as e:
            print(f"   ! {e}", flush=True)
            return None
        hits = sorted(out_dir.glob("chat*.live_chat.json"))
        return hits[0] if hits else None
    return None


def video_info(url, cookies=None, proxy=None):
    """Title, channel and duration via yt-dlp (works for Twitch and YouTube)."""
    import json
    cmd = _ytdlp_base(cookies, proxy) + ["-J", "--skip-download", url]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.returncode == 0:
            d = json.loads(out.stdout)
            return {"title": d.get("title", ""), "channel": d.get("channel") or d.get("uploader") or "",
                    "duration": float(d.get("duration") or 0), "was_live": bool(d.get("was_live"))}
    except Exception:
        pass
    return {"title": "", "channel": "", "duration": 0.0, "was_live": False}


def download_section(url, start, end, out_path, cookies=None, proxy=None, tdl="TwitchDownloaderCLI"):
    """Download only [start, end] seconds of the video, 1080p max."""
    from .timefmt import hms
    out_path = Path(out_path)
    k = kind_of(url)
    if k == "twitch" and (shutil.which(tdl) or Path(tdl).exists()):
        _run([tdl, "videodownload", "--id", url, "-b", hms(start), "-e", hms(end),
              "-o", str(out_path)], "Twitch segment download")
        return out_path
    if k == "file":
        _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-to", str(end), "-i", url,
              "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", "-c:a", "aac", "-b:a", "192k",
              str(out_path)], "local segment copy")
        return out_path
    cmd = _ytdlp_base(cookies, proxy) + [
        "-f", "bv*[height<=1080][fps<=60]+ba/b[height<=1080]/b",
        "--download-sections", f"*{start:.2f}-{end:.2f}", "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4", "-o", str(out_path), url]
    _run(cmd, "segment download")
    return out_path


def download_audio(url, out_path, cookies=None, proxy=None):
    """Whole-stream audio only (small), used to find moments when there is no chat."""
    out_path = Path(out_path)
    if kind_of(url) == "file":
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", url, "-vn", "-ac", "1", "-ar", "16000",
              str(out_path)], "audio extract")
        return out_path
    cmd = _ytdlp_base(cookies, proxy) + ["-f", "ba/b", "-x", "--audio-format", "m4a",
                                         "-o", str(out_path.with_suffix(".%(ext)s")), url]
    _run(cmd, "audio download")
    return out_path.with_suffix(".m4a")
