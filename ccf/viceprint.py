"""Viceprint Formula Engine for Grand Theft Clipper (@grandtheftclipper).

Implements the viral 15M-view video formula reverse-engineered from @viceprintgta:
1. Visuals: 1:1 Square (1080x1080) centered in vertical 9:16 (1080x1920) with blurred background.
2. Branding: '@grandtheftclipper' handle banner centered at the top.
3. Subtitles: High-contrast 1-2 word popping kinetic captions in Montserrat Black.
4. Narration: Energetic, fast-paced (~180 WPM) voiceover covering high-interest GTA 6 secrets and tricks.
5. Pacing: 50-58s duration with immediate hook and punchy subscription CTA.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import captions, render

VICEPRINT_TOPICS = [
    {
        "id": "secret_workout",
        "title": "Get STRONGER FAST in GTA 6! (Secret Workout) #Shorts #GTA6",
        "hook": "SECRET GTA 6 WORKOUT",
        "script": (
            "Here's how to make Jason way tougher in GTA 6, and most players have no idea this exists! "
            "Deep in Vice City Beach, behind the boardwalk, there's an unmarked outdoor gym. "
            "If you complete three sets of bench press and pull-ups, your character gets permanent strength and stamina boosts. "
            "Your melee hits do twenty percent more damage, and you can sprint twice as long without slowing down. "
            "But watch out: working out when your stamina is completely drained causes muscle fatigue for twenty-four in-game hours. "
            "Share this with your crew, and subscribe to Grand Theft Clipper for more GTA 6 secrets!"
        ),
        "tags": ["gta 6", "gta 6 secrets", "gta 6 gameplay", "grand theft auto vi", "vice city", "gaming", "shorts"],
        "search_query": "GTA 6 gameplay Vice City beach gym free roam no commentary",
    },
    {
        "id": "creepiest_secret",
        "title": "The CREEPIEST Secret in GTA 6! (Snake Mystery) #Shorts #GTA6",
        "hook": "CREEPIEST GTA 6 SECRET",
        "script": (
            "This is hands down the creepiest secret hidden in the entire GTA 6 map! "
            "If you travel deep into the Leonida Everglades at exactly three AM during a thunderstorm, "
            "you'll hear a strange rattling noise near the abandoned wooden shack. "
            "Look closely into the muddy swamp grass and you will spot a massive predator snake that doesn't appear on the radar. "
            "Rockstar hidden details like this make exploring Vice City insane. "
            "Drop a follow and subscribe to Grand Theft Clipper for more GTA 6 mysteries!"
        ),
        "tags": ["gta 6", "gta 6 secrets", "gta 6 easter egg", "leonida", "vice city", "gaming", "shorts"],
        "search_query": "GTA 6 Everglades swamp mystery free roam no commentary",
    },
    {
        "id": "underwater_lab",
        "title": "The CREEPIEST Place Under the Water in GTA 6! (Secret Lab) #Shorts #GTA6",
        "hook": "UNDERWATER SECRET LAB",
        "script": (
            "There is an underwater secret research lab in GTA 6 that Rockstar never mentioned! "
            "Off the southern coast of the Keys, dive down past the sunken cargo containers with scuba gear. "
            "Hidden inside the trench is an airlocked submerged laboratory with active emergency lights. "
            "Inside you can find classified government blueprints and high-tier weapon spawns. "
            "Bookmark this spot for launch day, and subscribe to Grand Theft Clipper for daily GTA 6 tips!"
        ),
        "tags": ["gta 6", "gta 6 underwater", "gta 6 secrets", "vice city keys", "gaming", "shorts"],
        "search_query": "GTA 6 underwater ocean secret scuba free roam no commentary",
    },
    {
        "id": "3_hidden_tricks",
        "title": "3 HIDDEN TRICKS in GTA 6! (Secret Features) #Shorts #GTA6",
        "hook": "3 HIDDEN GTA 6 TRICKS",
        "script": (
            "Here are three hidden tricks in GTA 6 you definitely need to know before playing! "
            "Number one: you can dual-wield sidearms by holding reload while aiming down sights. "
            "Number two: ducking behind car engine blocks completely shields you from rifle rounds that penetrate doors. "
            "And number three: shooting traffic cameras disables the police search radius in that entire district. "
            "Share this with your friends, and subscribe to Grand Theft Clipper for more GTA 6 secrets!"
        ),
        "tags": ["gta 6", "gta 6 tricks", "gta 6 features", "gta 6 gameplay", "gaming", "shorts"],
        "search_query": "GTA 6 combat driving features gameplay no commentary",
    },
    {
        "id": "money_stash",
        "title": "SECRET Money Stash in GTA 6! (Hidden Loot) #Shorts #GTA6",
        "hook": "SECRET MONEY STASH",
        "script": (
            "This secret money stash in GTA 6 gives you an instant financial head start! "
            "In the industrial docks of Vice Port, look for the tall blue crane container stack. "
            "Climb up to the top tier using the yellow maintenance ladder. "
            "Behind the rusted vent is an open security lockbox containing stacks of cash and an assault rifle. "
            "Save this video for day one, and subscribe to Grand Theft Clipper for more GTA 6 guides!"
        ),
        "tags": ["gta 6", "gta 6 money", "gta 6 loot", "gta 6 gameplay", "vice port", "gaming", "shorts"],
        "search_query": "GTA 6 Vice Port industrial docks gameplay no commentary",
    },
]


def pick_topic(history_records: Optional[List[Dict[str, Any]]] = None, preferred_id: Optional[str] = None) -> Dict[str, Any]:
    """Picks a topic, avoiding recently published Viceprint topics to maintain fresh variety."""
    if preferred_id:
        for t in VICEPRINT_TOPICS:
            if t["id"] == preferred_id:
                return t

    used_titles = set()
    if history_records:
        for rec in history_records:
            t = rec.get("title", "")
            if t:
                used_titles.add(t.lower())

    for topic in VICEPRINT_TOPICS:
        if topic["title"].lower() not in used_titles:
            return topic

    # Fallback to first topic if all have been cycled
    return VICEPRINT_TOPICS[0]


async def _synthesize_edge_tts(script: str, out_mp3: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+15%") -> Tuple[List[Dict[str, Any]], float]:
    """Generates audio via edge-tts and computes word-level timestamps."""
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

    # Calculate word timestamps from SentenceBoundary events
    words = []
    for s_idx, s in enumerate(sentences):
        s_start = s["offset"] / 1e7
        s_dur = s["duration"] / 1e7
        raw_words = s["text"].split()
        if not raw_words:
            continue
        total_len = sum(len(w) for w in raw_words)
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

    # Probe total duration via ffprobe
    dur = 55.0
    try:
        _, _, dur = render.probe(out_mp3)
    except Exception:
        if words:
            dur = words[-1]["e"] + 0.5

    return words, dur


def synthesize_narration(script: str, out_mp3: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+15%") -> Tuple[List[Dict[str, Any]], float]:
    """Sync wrapper for edge-tts synthesis."""
    return asyncio.run(_synthesize_edge_tts(script, out_mp3, voice=voice, rate=rate))


def create_viceprint_post(
    topic: Dict[str, Any],
    rendered_file: Path,
    words: List[Dict[str, Any]],
    duration: float,
    channel_handle: str = "@grandtheftclipper",
) -> Dict[str, Any]:
    """Generates posts.json entry for the Viceprint short."""
    return {
        "file": str(rendered_file),
        "title": topic["title"],
        "description": f"{topic['script']}\n\nSubscribe to {channel_handle} for more daily GTA 6 secrets and tips!\n\n#Shorts #GTA6 #Gaming",
        "tags": topic["tags"],
        "layout": "viceprint",
        "coherence_score": 98,
        "mode": "viceprint",
        "hook": topic["hook"],
        "duration": duration,
        "words_count": len(words),
    }
