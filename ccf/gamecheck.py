"""Prove that a downloaded clip really shows the game we are about to claim.

A stream title is a claim, not evidence. A Twitch VOD can sit in the "Grand Theft
Auto VI" category while the streamer plays something else, which is exactly how a
NARAKA: BLADEPOINT VOD ended up under a GTA 6 title. This module looks for
evidence instead of names:

  1. container tags and chapter names - TwitchDownloader and yt-dlp copy the
     source title, description, comment field and chapters into the mp4
  2. the words actually printed on screen, read with Tesseract when it is
     installed (opencv + pytesseract + the tesseract binary)

A known other-game name in either place vetoes the clip. A GTA 6 marker in the
on-screen text, or in the file's own metadata, is what lets it through.
Fail-closed: no evidence, no Short.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

GAME_LABEL = "GTA 6"

# (pattern, human label). Vetoed in either metadata or on-screen text.
OTHER_GAMES = [
    (r"naraka|bladepoint", "Naraka: Bladepoint"),
    (r"valorant", "VALORANT"),
    (r"fortnite", "Fortnite"),
    (r"minecraft", "Minecraft"),
    (r"call\s+of\s+duty|warzone|black\s+ops", "Call of Duty"),
    (r"apex\s+legends", "Apex Legends"),
    (r"counter[-\s]?strike|\bcs2\b|\bcs:?go\b", "Counter-Strike"),
    (r"\bdota\b", "Dota"),
    (r"league\s+of\s+legends", "League of Legends"),
    (r"genshin", "Genshin Impact"),
    (r"\bpubg\b", "PUBG"),
    (r"overwatch", "Overwatch"),
    (r"elden\s+ring", "Elden Ring"),
    (r"cyberpunk", "Cyberpunk 2077"),
    (r"roblox", "Roblox"),
    (r"free\s+fire", "Free Fire"),
    (r"marvel\s+rivals", "Marvel Rivals"),
    (r"delta\s+force", "Delta Force"),
    (r"black\s+myth", "Black Myth: Wukong"),
    (r"escape\s+from\s+tarkov", "Escape from Tarkov"),
    (r"rainbow\s+six", "Rainbow Six"),
    (r"\bbattlefield\b", "Battlefield"),
    (r"\bhalo\b", "Halo"),
    (r"destiny\s+2", "Destiny 2"),
    (r"rocket\s+league", "Rocket League"),
    (r"dead\s+by\s+daylight", "Dead by Daylight"),
    (r"helldivers", "Helldivers"),
    (r"baldur'?s\s+gate", "Baldur's Gate"),
    (r"red\s+dead", "Red Dead Redemption"),
    (r"resident\s+evil|silent\s+hill|assassin'?s\s+creed|\bfifa\b|ea\s?fc|nba\s?2k", "another game"),
    # \b after the version digit, so "Grand Theft Auto VI" is not read as "V"
    (r"gta\s?(5|v)\b|gta\s?online|grand\s+theft\s+auto\s+(5|v|online)\b|san\s+andreas", "an older GTA"),
]

# Evidence that the footage really is the game we claim it is. "Vice City" and
# "Leonida" are GTA 6's own setting and show up on screen and in VOD chapters.
GTA_MARKERS = re.compile(
    r"\b(gta\s?6|gta\s?vi|grand\s+theft\s+auto\s+(6|vi)|vice\s+city|leonida|vice\s+beach|rockstar)\b",
    re.I,
)


def can_read_screen_text() -> bool:
    """True when opencv + pytesseract + the tesseract binary are all available."""
    if not shutil.which("tesseract"):
        return False
    try:
        import cv2  # noqa: F401
        import pytesseract  # noqa: F401
    except Exception:
        return False
    return True


def _flatten(value) -> str:
    if isinstance(value, dict):
        return "\n".join(_flatten(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(_flatten(v) for v in value)
    return "" if value is None else str(value)


def metadata_text(video_path) -> str:
    """Tags + chapter names the downloader copied into the container."""
    exe = shutil.which("ffprobe") or "ffprobe"
    try:
        res = subprocess.run(
            [exe, "-v", "error", "-show_format", "-show_chapters", "-show_streams", "-of", "json",
             str(video_path)],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if res.returncode != 0 or not (res.stdout or "").strip():
        return ""
    try:
        data = json.loads(res.stdout)
    except ValueError:
        return ""
    parts = [_flatten((data.get("format") or {}).get("tags") or {})]
    for stream in data.get("streams") or []:
        parts.append(_flatten(stream.get("tags") or {}))
    for chapter in data.get("chapters") or []:
        parts.append(_flatten((chapter.get("tags") or {}).get("title") or ""))
    return "\n".join(p for p in parts if p)


def screen_text(video_path, frames: int = 8) -> str:
    """Words printed on screen, sampled across the clip. Empty when OCR is unavailable."""
    if not can_read_screen_text():
        return ""
    import cv2
    import pytesseract

    captions = []
    cap = cv2.VideoCapture(str(video_path))
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        for k in range(frames):
            if total:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (k + 0.5) / frames))
            ok, frame = cap.read()
            if not ok:
                continue
            try:
                captions.append(pytesseract.image_to_string(frame))
            except Exception:
                continue
    finally:
        cap.release()
    return "\n".join(captions)


def classify(meta_text: str = "", on_screen: str = "", ocr_available: bool = True,
             require_screen_text: bool = False):
    """Decide from evidence alone. Returns (ok, reason).

    Pure function: no ffmpeg, no OCR, no network - so it can be unit tested.
    """
    blob = f"{meta_text or ''}\n{on_screen or ''}"
    for pattern, label in OTHER_GAMES:
        match = re.search(pattern, blob, re.I)
        if match:
            return False, f"footage is {label}, not {GAME_LABEL} (matched {match.group(0)!r})"

    on_screen_hit = GTA_MARKERS.search(on_screen or "")
    meta_hit = GTA_MARKERS.search(meta_text or "")

    if on_screen_hit:
        return True, f"confirmed on screen ({on_screen_hit.group(0)!r})"
    if require_screen_text:
        if not ocr_available:
            return False, "on-screen check unavailable, and this source needs it"
        return False, f"no {GAME_LABEL} marker on screen"
    if meta_hit:
        return True, f"source metadata names {GAME_LABEL} ({meta_hit.group(0)!r}) and no other game"
    return False, f"could not confirm {GAME_LABEL} footage"


def verify_clip(video_path, require_screen_text: bool = False):
    """(ok, reason) for a downloaded clip. Fail-closed."""
    path = Path(video_path)
    if not path.is_file() or path.stat().st_size < 1000:
        return False, "clip missing or empty"
    available = can_read_screen_text()
    ok, reason = classify(
        metadata_text(path),
        screen_text(path) if available else "",
        ocr_available=available,
        require_screen_text=require_screen_text,
    )
    return ok, reason
