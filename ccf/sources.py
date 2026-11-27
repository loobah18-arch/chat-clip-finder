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
from typing import Optional

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


def _ytdlp_base(cookies=None, proxy=None, client=None, pot=True, no_cookies=False):
    exe = shutil.which("yt-dlp")
    cmd = [exe] if exe else [sys.executable, "-m", "yt_dlp"]
    cmd += ["-v", "--no-warnings", "--no-playlist", "--retries", "3", "--fragment-retries", "5", "--socket-timeout", "45"]
    if shutil.which("node"):
        cmd += ["--js-runtimes", "node", "--remote-components", "ejs:github"]

    if client:
        cmd += ["--extractor-args", f"youtube:player_client={client}"]

    is_web_client = "web" in (client or "") or client is None
    po_token = os.environ.get("YT_PO_TOKEN")
    visitor_data = os.environ.get("YT_VISITOR_DATA")
    if pot and is_web_client:
        if po_token and visitor_data:
            cmd += [
                "--extractor-args", f"youtube:po_token=web.gvs+{po_token}",
                "--extractor-args", f"youtube:visitor_data={visitor_data}",
            ]
        else:
            bgutil_url = os.environ.get("BGUTIL_BASE_URL", "http://127.0.0.1:4416")
            cmd += ["--extractor-args", f"youtubepot-bgutilhttp:base_url={bgutil_url}"]

    if not no_cookies:
        cookies_file = find_cookies(cookies)
        if cookies_file:
            cmd += ["--cookies", cookies_file]
    else:
        cmd += ["--no-cookies"]

    proxy = proxy or os.environ.get("YOUTUBE_PROXY")
    if proxy:
        cmd += ["--proxy", proxy]

    return cmd


def _run(cmd, what, timeout=300):
    logged_cmd = [c if not c.startswith("--cookies") else "--cookies [REDACTED]" for c in cmd]
    print(f"   $ {' '.join(logged_cmd)} ... ({what})", flush=True)
    try:
        res = subprocess.run(cmd, timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{what} timed out after {timeout}s.")
    if res.returncode != 0:
        err_lines = [line for line in (res.stdout or "").splitlines() if line.strip()]
        err_msg = next((line for line in err_lines if "ERROR:" in line), err_lines[-1] if err_lines else f"exit {res.returncode}")
        print(f"   ❌ Output snippet from failed {what} (exit {res.returncode}):\n      {err_msg}", flush=True)
        raise RuntimeError(f"{what} failed (exit {res.returncode}): {err_msg}")


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
        for client, use_cookies, use_pot in [
            (None, True, True),
            ("mweb", True, True),
            ("ios", False, False),
        ]:
            cmd = _ytdlp_base(cookies=cookies if use_cookies else None, proxy=proxy, client=client, pot=use_pot, no_cookies=not use_cookies) + [
                "-4", "--skip-download", "--write-subs", "--sub-langs", "live_chat",
                "-o", tmpl, url
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if res.returncode == 0:
                    hits = sorted(out_dir.glob("chat*.live_chat.json"))
                    if hits:
                        return hits[0]
            except Exception:
                pass
        hits = sorted(out_dir.glob("chat*.live_chat.json"))
        return hits[0] if hits else None
    return None


def video_info(url, cookies=None, proxy=None):
    """Title, channel and duration via yt-dlp (works for Twitch and YouTube)."""
    import json
    for client, use_cookies, use_pot in [
        (None, True, True),
        ("mweb", True, True),
        ("ios", False, False),
        ("visionos", False, False),
    ]:
        cmd = _ytdlp_base(cookies=cookies if use_cookies else None, proxy=proxy, client=client, pot=use_pot, no_cookies=not use_cookies) + [
            "-4", "-J", "--skip-download", url
        ]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if out.returncode == 0:
                d = json.loads(out.stdout)
                return {
                    "title": d.get("title", ""),
                    "channel": d.get("channel") or d.get("uploader") or "",
                    "duration": float(d.get("duration") or 0),
                    "was_live": bool(d.get("was_live")),
                }
        except Exception:
            continue
    return {"title": "", "channel": "", "duration": 0.0, "was_live": False}


def _find_media_file(path: Path) -> Optional[Path]:
    path = Path(path)
    if path.is_file() and path.stat().st_size > 10000:
        return path
    base = str(path.with_suffix(""))
    for ext in [".mp4", ".webm", ".mkv"]:
        cand = Path(base + ext)
        if cand.is_file() and cand.stat().st_size > 10000:
            if cand != path:
                cand.rename(path)
                return path
            return cand
        cand2 = Path(str(path) + ext)
        if cand2.is_file() and cand2.stat().st_size > 10000:
            cand2.rename(path)
            return path
    return None


def download_section(url, start, end, out_path, cookies=None, proxy=None, tdl="TwitchDownloaderCLI"):
    """Download only [start, end] seconds of the video, 1080p max."""
    from .timefmt import hms
    out_path = Path(out_path)
    k = kind_of(url)
    if k == "twitch" and (shutil.which(tdl) or Path(tdl).exists()):
        tw_id_match = re.search(r"(\d{6,})", url)
        tw_id = tw_id_match.group(1) if tw_id_match else url
        try:
            _run([tdl, "videodownload", "--id", tw_id, "-b", hms(start), "-e", hms(end),
                  "-o", str(out_path)], "Twitch segment download")
            found = _find_media_file(out_path)
            if found:
                return found
        except Exception as e:
            print(f"   ⚠️ TwitchDownloaderCLI failed: {e}; falling back to yt-dlp for Twitch...", flush=True)

    if k == "file":
        _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-to", str(end), "-i", url,
              "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", "-c:a", "aac", "-b:a", "192k",
              str(out_path)], "local segment copy")
        return out_path

    if k != "youtube":
        cmd = _ytdlp_base(cookies, proxy, no_cookies=True) + [
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/b[height<=1080]",
            "--download-sections", f"*{start:.2f}-{end:.2f}", "--force-keyframes-at-cuts",
            "--merge-output-format", "mp4", "-o", str(out_path), url]
        _run(cmd, "segment download")
        found = _find_media_file(out_path)
        return found or out_path

    # YouTube: Multi-tier cascading fallback (strictly >=720p, <=1080p, aligned with gameplay-walkthrough-shorts)
    fmt_hd = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/22/b[height>=720]/18"
    tiers = [
        # Tier 1: web,mweb with PO Token / bgutil + validated cookies
        ("web,mweb", fmt_hd, "Tier 1: 1080p web,mweb + bgutil/cookies", True),
        # Tier 2: Default yt-dlp auto client negotiation (no cookies)
        (None, fmt_hd, "Tier 2: auto client (no cookies)", False),
        # Tier 3: Apple VisionOS client (no cookies)
        ("visionos", fmt_hd, "Tier 3: 1080p visionos (no cookies)", False),
        # Tier 4: web,mweb with PO Token / bgutil (no cookies)
        ("web,mweb", fmt_hd, "Tier 4: 1080p web,mweb + bgutil (no cookies)", False),
        # Tier 5: iOS client (no cookies)
        ("ios", fmt_hd, "Tier 5: 1080p ios HLS (no cookies)", False),
        # Tier 6: Android VR (no cookies)
        ("android_vr", fmt_hd, "Tier 6: 1080p android_vr (no cookies)", False),
        # Tier 7: Progressive 720p format 22
        ("android", "22/best[height>=720]/18", "Tier 7: 720p progressive (format 22)", False),
    ]

    last_err = None
    section_arg = f"*{hms(start)}-{hms(end)}"
    for client, fmt, label, use_cookies in tiers:
        try:
            print(f"   🔄 Attempting segment download via {label}...", flush=True)
            cmd = _ytdlp_base(
                cookies=cookies if use_cookies else None,
                proxy=proxy,
                client=client,
                pot=True,
                no_cookies=not use_cookies
            ) + [
                "-4",
                "-f", fmt,
                "--download-sections", section_arg,
                "--merge-output-format", "mp4",
                "-o", str(out_path),
                url
            ]
            _run(cmd, f"segment download ({client})")
            found = _find_media_file(out_path)
            if found:
                print(f"   ✅ Segment downloaded successfully via {client}", flush=True)
                return found
        except Exception as e:
            print(f"   ⚠️ {label} failed: {e}", flush=True)
            last_err = e

    raise RuntimeError(f"segment download failed all tiers. Last error: {last_err}")


def download_audio(url, out_path, cookies=None, proxy=None):
    """Whole-stream audio only (small), used to find moments when there is no chat."""
    out_path = Path(out_path)
    if kind_of(url) == "file":
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", url, "-vn", "-ac", "1", "-ar", "16000",
              str(out_path)], "audio extract")
        return out_path

    target_m4a = out_path.with_suffix(".m4a")
    tmpl = str(out_path.with_suffix(".%(ext)s"))

    # For Twitch or non-YouTube
    if kind_of(url) != "youtube":
        cmd = _ytdlp_base(cookies, proxy) + ["-f", "ba/b/bestaudio/18/b", "-x", "--audio-format", "m4a",
                                             "-o", tmpl, url]
        _run(cmd, "audio download")
        return target_m4a

    # YouTube audio tiers
    fmt_audio = "ba/b/bestaudio/18/b"
    tiers = [
        ("visionos", fmt_audio, "Tier 1: visionos audio (no cookies)", False),
        ("ios", "best/18/b", "Tier 2: ios audio (no cookies)", False),
        ("web,mweb", fmt_audio, "Tier 3: web,mweb + bgutil audio", True),
        ("android_vr", "best/18/b", "Tier 4: android_vr audio (no cookies)", False),
        ("android", "18/b", "Tier 5: android audio (no cookies)", False),
    ]

    last_err = None
    for client, fmt, label, use_cookies in tiers:
        try:
            print(f"   🔄 Attempting audio download via {label}...", flush=True)
            cmd = _ytdlp_base(
                cookies=cookies if use_cookies else None,
                proxy=proxy,
                client=client,
                pot=use_cookies,
                no_cookies=not use_cookies
            ) + [
                "-4",
                "--downloader", "native",
                "-f", fmt,
                "-x", "--audio-format", "m4a",
                "-o", tmpl,
                url
            ]
            _run(cmd, f"audio download ({client})")
            if target_m4a.exists() and target_m4a.stat().st_size > 1000:
                print(f"   ✅ Audio downloaded successfully via {client}", flush=True)
                return target_m4a
            for cand in out_path.parent.glob(f"{out_path.stem}.*"):
                if cand.is_file() and cand.stat().st_size > 1000:
                    return cand
        except Exception as e:
            print(f"   ⚠️ {label} failed: {e}", flush=True)
            last_err = e

    raise RuntimeError(f"audio download failed all tiers. Last error: {last_err}")
