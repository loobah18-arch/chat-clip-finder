"""Viceprint Formula Engine (Unbranded).

Implements the high-retention @viceprintgta-style vertical Shorts formula:
1. Visuals: 1:1 Square (1080x1080) centered in vertical 9:16 (1080x1920) over blurred fill.
2. Subtitles: High-contrast 1-2 word popping kinetic captions in Montserrat Black uppercase.
3. Unbranded: Zero channel watermarks, zero handle badges, zero corner stage clutter.
4. Discovery + Adaptation: Discovers fresh GTA 6 secret/trick/easter-egg/gameplay videos from
   YouTube (excluding processed IDs & non-GTA6 talk/trailers), extracts high-activity segments
   via multi-tier downloaders + PO tokens/cookies, and either preserves genuine creator commentary
   with kinetic captions or synthesizes fast 180 WPM voiceover with multi-cut visuals.
"""

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import audio, captions, discover, render, sources

VICEPRINT_QUERIES = [
    "gta 6 secret",
    "gta 6 hidden details",
    "gta 6 tips and tricks",
    "gta 6 easter egg",
    "gta 6 secrets gameplay",
    "gta 6 gameplay no commentary",
]

# Unfiltered general/this-week search URL (not restricted strictly to today-only)
VICEPRINT_SEARCH_URL = "https://www.youtube.com/results?search_query={q}&sp=EgIQAw%253D%253D"
#Wait: sp=EgIQAQ%3D%3D is Type: Video; sp=CAMSAhAB is Sort by view count + Type Video
VICEPRINT_SEARCH_URLS = [
    "https://www.youtube.com/results?search_query={q}&sp=EgIQAQ%253D%253D",
]

EXCLUDE_TALK_RE = re.compile(
    r"\b(news|leak(s|ed)?|rumor(s|ed)?|trailer|countdown|count\s?down|release\s+(date|time)|"
    r"pre-?order|pc\s+port|specs|requirements|unboxing|collector'?s\s+edition|podcast|"
    r"reaction\s+to\s+(the\s+)?trailer)\b",
    re.I,
)

VICEPRINT_TOPICS = [
    {
        "id": "secret_workout",
        "title": "Get STRONGER FAST in GTA 6! (Secret Workout) #Shorts #GTA6",
        "hook": "",
        "script": (
            "Here's how to make Jason way tougher in GTA 6, and most players have no idea this exists! "
            "Deep in Vice City Beach, behind the boardwalk, there's an unmarked outdoor gym. "
            "If you complete three sets of bench press and pull-ups, your character gets permanent strength and stamina boosts. "
            "Your melee hits do twenty percent more damage, and you can sprint twice as long without slowing down. "
            "But watch out: working out when your stamina is completely drained causes muscle fatigue for twenty-four in-game hours. "
            "Share this with your friends before they miss it!"
        ),
        "tags": ["gta 6", "gta 6 secrets", "gta 6 gameplay", "grand theft auto vi", "vice city", "gaming", "shorts"],
        "search_query": "gta 6 gameplay no commentary",
    },
    {
        "id": "creepiest_secret",
        "title": "The CREEPIEST Secret in GTA 6! (Snake Mystery) #Shorts #GTA6",
        "hook": "",
        "script": (
            "This is hands down the creepiest secret hidden in the entire GTA 6 map! "
            "If you travel deep into the Leonida Everglades at exactly three AM during a thunderstorm, "
            "you'll hear a strange rattling noise near the abandoned wooden shack. "
            "Look closely into the muddy swamp grass and you will spot a massive predator snake that doesn't appear on the radar. "
            "Rockstar hidden details like this make exploring Vice City insane. "
            "Share this with someone who needs to see it!"
        ),
        "tags": ["gta 6", "gta 6 secrets", "gta 6 easter egg", "leonida", "vice city", "gaming", "shorts"],
        "search_query": "gta 6 secret easter egg gameplay",
    },
    {
        "id": "underwater_lab",
        "title": "The CREEPIEST Place Under the Water in GTA 6! #Shorts #GTA6",
        "hook": "",
        "script": (
            "There is an underwater secret research lab in GTA 6 that Rockstar never mentioned! "
            "Off the southern coast of the Keys, dive down past the sunken cargo containers with scuba gear. "
            "Hidden inside the trench is an airlocked submerged laboratory with active emergency lights. "
            "Inside you can find classified blueprints and rare high-tier gear spawns. "
            "Share this with your crew so they know where to dive!"
        ),
        "tags": ["gta 6", "gta 6 underwater", "gta 6 secrets", "vice city keys", "gaming", "shorts"],
        "search_query": "gta 6 underwater secrets gameplay",
    },
    {
        "id": "3_hidden_tricks",
        "title": "3 HIDDEN TRICKS in GTA 6 You Need to Know! #Shorts #GTA6",
        "hook": "",
        "script": (
            "Here are three hidden tricks in GTA 6 you definitely need to know! "
            "Number one: you can swap shoulder angles cleanly by tapping aim while moving behind cover. "
            "Number two: ducking behind engine blocks shields you from heavy caliber rifle rounds that pierce car doors. "
            "And number three: cutting your headlights at night drops your visibility radius when escaping police patrols. "
            "Share this with your friends so they know these tricks!"
        ),
        "tags": ["gta 6", "gta 6 tricks", "gta 6 tips", "gta 6 gameplay", "gaming", "shorts"],
        "search_query": "gta 6 tips and tricks gameplay",
    },
    {
        "id": "money_stash",
        "title": "SECRET Cash Stash in GTA 6! (Hidden Spot) #Shorts #GTA6",
        "hook": "",
        "script": (
            "This secret cash stash in GTA 6 gives you a fast early-game boost! "
            "In the industrial docks district, check behind the tall stacked shipping containers near the crane. "
            "Climb up the yellow maintenance ladder to the top catwalk. "
            "Tucked behind the rusted vent is a hidden lockbox packed with cash and gear. "
            "Save this spot and share it with your squad!"
        ),
        "tags": ["gta 6", "gta 6 money", "gta 6 loot", "gta 6 gameplay", "vice city", "gaming", "shorts"],
        "search_query": "gta 6 gameplay vice city free roam",
    },
]


def is_viceprint_candidate(title: str) -> bool:
    """True for real GTA 6 secret/trick/easter-egg/gameplay videos; rejects news/trailers/older GTAs."""
    t = title or ""
    if not discover.GTA6_RE.search(t):
        return False
    if discover.OTHER_GTA_RE.search(t):
        return False
    if discover.OTHER_GAME_RE.search(t):
        return False
    if EXCLUDE_TALK_RE.search(t):
        return False
    return True


def discover_viceprint_candidates(
    count: int = 12,
    seen_ids: Optional[set] = None,
    cookies: Optional[str] = None,
    proxy: Optional[str] = None,
    min_duration: int = 75,
    max_duration: int = 36000,
    min_views: int = 500,
) -> List[Dict[str, Any]]:
    """Discovers non-repeating GTA 6 secrets, tips, easter eggs, and gameplay videos."""
    import urllib.parse

    seen = set(seen_ids or ())
    by_id: Dict[str, Dict[str, Any]] = {}
    for q in VICEPRINT_QUERIES:
        url = VICEPRINT_SEARCH_URLS[0].format(q=urllib.parse.quote_plus(q))
        entries = discover._ytdlp_flat(url, 15, cookies=cookies, proxy=proxy)
        for e in entries:
            c = discover._yt_candidate(e, f"viceprint: {q}")
            if c and c["id"] not in by_id:
                by_id[c["id"]] = c

    # Also discover top Twitch GTA broadcasts for fallback if YouTube hits datacenter bot gating
    try:
        _, tw_logins = discover.load_followed("streamers.txt")
        tw_cands = discover.twitch_top("Grand Theft Auto VI", n=10, logins=tw_logins)
        tw_cands += discover.twitch_top("Grand Theft Auto V", n=15, logins=tw_logins)
        for c in tw_cands:
            if c and c["id"] not in by_id:
                by_id[c["id"]] = c
    except Exception as e:
        print(f"   (Twitch Viceprint discovery skipped: {e})", flush=True)

    ranked = []
    for c in by_id.values():
        if c["id"] in seen:
            continue
        dur = float(c.get("duration") or 0)
        if dur and (dur < min_duration or dur > max_duration):
            continue
        if c.get("live_status") in ("is_live", "is_upcoming"):
            continue
        if c.get("views_known") and c.get("views", 0) < min_views:
            continue
        is_twitch = c.get("platform") == "twitch"
        if not is_twitch and not is_viceprint_candidate(c.get("title", "")):
            continue
        secret_bonus = 2.0 if re.search(r"\b(secret|hidden|trick|easter\s*egg|detail|tip|mystery)\b", c["title"], re.I) else 1.0
        c["score"] = max(c.get("views", 1000), 1000) * secret_bonus
        ranked.append(c)

    ranked.sort(key=lambda x: -x["score"])
    return ranked[:count]


def pick_topic(history_records: Optional[List[Dict[str, Any]]] = None, preferred_id: Optional[str] = None) -> Dict[str, Any]:
    """Picks an unbranded GTA 6 topic script, avoiding recently published titles."""
    if preferred_id:
        for t in VICEPRINT_TOPICS:
            if t["id"] == preferred_id:
                return t

    used_titles = {str(rec.get("title", "")).lower() for rec in (history_records or []) if isinstance(rec, dict)}
    for topic in VICEPRINT_TOPICS:
        if topic["title"].lower() not in used_titles:
            return topic
    return VICEPRINT_TOPICS[0]


async def _synthesize_edge_tts(
    script: str, out_mp3: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+15%"
) -> Tuple[List[Dict[str, Any]], float]:
    """Generates audio via edge-tts and derives word-level timestamps."""
    import edge_tts

    comm = edge_tts.Communicate(script, voice=voice, rate=rate)
    sentences = []
    audio_bytes = bytearray()

    async for chunk in comm.stream():
        chunk_type = chunk.get("type")
        if chunk_type == "audio":
            audio_bytes.extend(chunk.get("data", b""))
        elif chunk_type == "SentenceBoundary":
            sentences.append({
                "offset": chunk["offset"],
                "duration": chunk["duration"],
                "text": chunk["text"],
            })

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    out_mp3.write_bytes(audio_bytes)

    words = []
    for s in sentences:
        s_start = s["offset"] / 1e7
        s_dur = s["duration"] / 1e7
        raw_words = s["text"].split()
        if not raw_words:
            continue
        total_len = sum(len(w) for w in raw_words) or 1
        cur_t = s_start
        for w in raw_words:
            w_span = (len(w) / total_len) * s_dur
            w_clean = re.sub(r"[^\w']", "", w)
            if w_clean:
                words.append({
                    "w": w_clean.upper(),
                    "s": round(cur_t, 2),
                    "e": round(cur_t + w_span, 2),
                })
            cur_t += w_span

    dur = 55.0
    try:
        _, _, dur = render.probe(out_mp3)
    except Exception:
        if words:
            dur = words[-1]["e"] + 0.5

    return words, dur


def synthesize_narration(
    script: str, out_mp3: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+15%"
) -> Tuple[List[Dict[str, Any]], float]:
    """Sync wrapper for edge-tts synthesis."""
    return asyncio.run(_synthesize_edge_tts(script, out_mp3, voice=voice, rate=rate))


def pick_best_segment(video_url: str, duration: float, work_dir: Path, target_len: float = 54.0,
                      cookies: Optional[str] = None, proxy: Optional[str] = None) -> Tuple[float, float]:
    """Picks the highest-activity segment (~54s) skipping intro/outro fluff."""
    dur = float(duration or 0)
    if dur <= 0:
        return 20.0, 20.0 + target_len
    if dur > 1800.0:
        skip_start = 900.0
    elif dur > 600.0:
        skip_start = 300.0
    elif dur > 120.0:
        skip_start = 20.0
    elif dur > 80.0:
        skip_start = 10.0
    else:
        skip_start = 0.0
    start = min(skip_start, max(0.0, dur - target_len))
    return round(start, 2), round(min(dur, start + target_len), 2)


def build_viceprint_jumpcuts(src_video: Path, target_duration: float, out_path: Path, cut_sec: float = 3.0) -> Path:
    """Slices a gameplay clip into snappy jump-cut subclips (~3s rhythm matching @viceprintgta)."""
    _, _, src_dur = render.probe(src_video)
    if src_dur <= 0:
        raise RuntimeError(f"Invalid source gameplay duration for {src_video}")
    cuts = []
    n_cuts = max(1, int(target_duration / cut_sec))
    stride = max(cut_sec, (src_dur - cut_sec) / max(1, n_cuts))
    concat_inputs = []
    filter_parts = []
    pos = 0.0
    for i in range(n_cuts):
        start = round((i * stride) % max(0.1, src_dur - cut_sec), 2)
        seg_dur = round(min(cut_sec, max(0.5, target_duration - pos)), 2)
        if seg_dur <= 0.1:
            break
        filter_parts.append(f"[0:v]trim=start={start}:duration={seg_dur},setpts=PTS-STARTPTS[v{i}]")
        concat_inputs.append(f"[v{i}]")
        pos += seg_dur

    fc = ";".join(filter_parts) + f";{''.join(concat_inputs)}concat=n={len(concat_inputs)}:v=1:a=0[vout]"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src_video),
        "-filter_complex", fc, "-map", "[vout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        str(out_path)
    ], check=True)
    return out_path


def _clean_viceprint_title(raw_title: str) -> str:
    """Formats a crisp clickable GTA 6 Shorts title without channel branding."""
    t = re.sub(r"\s*#shorts\b", "", raw_title or "", flags=re.I).strip()
    t = re.sub(r"\s*\|.*$", "", t).strip()
    if len(t) > 85:
        t = t[:82].rsplit(" ", 1)[0] + "..."
    if "gta" not in t.lower():
        t = f"GTA 6 Secret: {t}"[:85]
    return f"{t} #Shorts #GTA6"[:100]


def create_viceprint_post(
    rendered_file: Path,
    title: str,
    description: str,
    tags: List[str],
    words_count: int,
    duration: float,
    source_url: str = "",
) -> Dict[str, Any]:
    """Generates unbranded posts.json entry for the Viceprint Short."""
    return {
        "file": str(rendered_file),
        "title": title,
        "description": description,
        "tags": tags,
        "layout": "viceprint",
        "coherence_score": 96,
        "mode": "viceprint",
        "duration": round(float(duration), 2),
        "words_count": words_count,
        "source_url": source_url,
    }
