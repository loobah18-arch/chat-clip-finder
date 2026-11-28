"""Viceprint Formula Engine (Unbranded).

Implements the high-retention @viceprintgta-style vertical Shorts formula:
1. Visuals: Borderless 1:1 Square (1080x1080) centered in vertical 9:16 (1080x1920) over rich blurred fill.
2. Subtitles: High-contrast 1-2 word popping kinetic captions in Montserrat Black uppercase.
3. Unbranded: Zero channel watermarks, zero handle badges, zero corner stage clutter.
4. Discovery + Adaptation: Discovers fresh GTA 6 secret/trick/easter-egg/gameplay videos from
   YouTube and verified GTA 6 Twitch playthroughs (strictly rejecting non-GTA6, trailers, and
   react/talking-head segments), extracts multi-scene gameplay bursts, strips letterbox bars,
   and layers fast ~180 WPM voiceover + ducked BGM over dynamic 3.2s jump-cuts.
"""

import asyncio
import difflib
import os
import re
import statistics
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from . import captions, discover, facecam, render

DEFAULT_BGM_PATH = Path(__file__).resolve().parent.parent / "assets" / "audio" / "viceprint_bgm.mp3"

VICEPRINT_QUERIES = [
    "gta 6 secret",
    "gta 6 hidden details",
    "gta 6 tips and tricks",
    "gta 6 easter egg",
    "gta 6 secrets gameplay",
    "gta 6 gameplay no commentary",
]

VICEPRINT_SEARCH_URLS = [
    "https://www.youtube.com/results?search_query={q}&sp=EgIQAQ%253D%253D",
]

EXCLUDE_TALK_RE = re.compile(
    r"\b(news|leak(s|ed)?|rumor(s|ed)?|trailer|countdown|count\s?down|release\s+(date|time)|"
    r"pre-?order|pc\s+port|specs|requirements|unboxing|collector'?s\s+edition|podcast|"
    r"reaction\s+to\s+(the\s+)?trailer)\b",
    re.I,
)

TWITCH_EXCLUDE_RE = re.compile(
    r"\b(react(s|ing|ion)?|trailer|just\s+chatting|podcast|sleeping|sleep\s+stream|"
    r"subathon|marry|kai\s+vs|vs\s+speed|waiting\s+room|countdown|irl|tier\s?list|"
    r"ranking\s+movies|watching\s+videos|music\s+review|drama)\b",
    re.I,
)

TWITCH_GAMEPLAY_RE = re.compile(
    r"\b(gameplay|playthrough|walkthrough|story\s+mode|100%|secrets?|easter\s*eggs?|"
    r"no\s+commentary|free\s*roam|exploration|missions?|heist|chapter|part\s*\d+|ep\.?\s*\d+)\b",
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
            "If you travel deep into the Leonida Everglades at three AM during a thunderstorm, "
            "you'll hear a strange rattling noise near the abandoned wooden shack. "
            "Look closely into the muddy swamp grass and you will spot a massive predator snake that doesn't show up on your radar. "
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
            "Hidden inside the trench is an airlocked submerged laboratory with flickering emergency lights. "
            "Inside you can find classified blueprints and rare high-tier gear spawns. "
            "Just watch your oxygen tank before diving down. "
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
            "And number three: cutting your headlights at night drops your detection radius when escaping police patrols. "
            "Master these three early and combat gets twice as easy!"
        ),
        "tags": ["gta 6", "gta 6 tricks", "gta 6 tips", "gta 6 gameplay", "gaming", "shorts"],
        "search_query": "gta 6 tips and tricks gameplay",
    },
    {
        "id": "money_stash",
        "title": "SECRET Cash Stash in GTA 6! (Hidden Spot) #Shorts #GTA6",
        "hook": "",
        "script": (
            "This secret cash stash in GTA 6 gives you a huge early-game boost! "
            "Over in the industrial docks district, check behind the tall stacked shipping containers near the crane. "
            "Climb up the yellow maintenance ladder onto the upper catwalk. "
            "Tucked behind the rusted vent is a hidden lockbox packed with cash and rare weapon parts. "
            "Grab this early before spending money on upgrades!"
        ),
        "tags": ["gta 6", "gta 6 money", "gta 6 loot", "gta 6 gameplay", "vice city", "gaming", "shorts"],
        "search_query": "gta 6 gameplay vice city free roam",
    },
    {
        "id": "gator_detail",
        "title": "Insane GATOR Physics Detail in GTA 6! (Secret Detail) #Shorts #GTA6",
        "hook": "",
        "script": (
            "Rockstar put an insane wildlife detail inside the swamps of GTA 6! "
            "If you fire warning shots into the air near the Leonida riverbank, nearby alligators immediately bolt back into the deep water. "
            "Wait thirty seconds without moving, and they slowly stalk right back toward the shoreline watching your noise level. "
            "NPCs walking near the water edge will actually freeze in panic if they spot one lunging. "
            "It's wild how realistic the wildlife AI is!"
        ),
        "tags": ["gta 6", "gta 6 details", "gta 6 wildlife", "gta 6 secrets", "gaming", "shorts"],
        "search_query": "gta 6 hidden details gameplay",
    },
    {
        "id": "motel_safe_code",
        "title": "Crack This Hidden MOTEL SAFE in GTA 6! (Secret Code) #Shorts #GTA6",
        "hook": "",
        "script": (
            "Most players walk straight past this hidden safe inside an abandoned highway motel in GTA 6! "
            "Check inside room number nine near the flickering neon sign off Route Twenty-Seven. "
            "Behind the tilted wall mirror sits a heavy steel wall safe with a faded scratch mark on the dial. "
            "Look on the back of the crumpled diner receipt on the nightstand to find the combination. "
            "Open it up for fast emergency cash and a custom sidearm!"
        ),
        "tags": ["gta 6", "gta 6 secret safe", "gta 6 secrets", "gta 6 gameplay", "gaming", "shorts"],
        "search_query": "gta 6 secret location gameplay",
    },
    {
        "id": "car_trunk_loot",
        "title": "Search CAR TRUNKS in GTA 6 For Rare Gear! #Shorts #GTA6",
        "hook": "",
        "script": (
            "Stop ignoring random parked cars in GTA 6, because Rockstar hid a massive loot system inside car trunks! "
            "Unlike older GTA games where cars are just rides, prying open trunks in affluent Vice Beach neighborhoods can spawn tactical bags, "
            "high-end watches, and extra armor plates you can store straight in your duffel bag. "
            "Watch out for alarmed luxury coupes though, because neighbors actually call the cops on your plate number!"
        ),
        "tags": ["gta 6", "gta 6 trunks", "gta 6 mechanics", "gta 6 gameplay", "gaming", "shorts"],
        "search_query": "gta 6 new mechanics gameplay",
    },
    {
        "id": "guard_dog_trick",
        "title": "SECRET Trick to Calm GUARD DOGS in GTA 6! #Shorts #GTA6",
        "hook": "",
        "script": (
            "Getting spotted by estate guard dogs in GTA 6 ruins stealth missions fast, unless you use this hidden trick! "
            "Before sneaking onto high-security mansions, stop by a late-night convenience store and stock up on meat snacks. "
            "When a patrol dog starts barking through the hedge, toss a snack near the fence and crouch quietly in shadow. "
            "It completely stops barking and lets you slip straight past security cameras!"
        ),
        "tags": ["gta 6", "gta 6 stealth", "gta 6 tips", "gta 6 secret", "gaming", "shorts"],
        "search_query": "gta 6 stealth gameplay",
    },
    {
        "id": "police_witness_system",
        "title": "How GTA 6 POLICE TRACK YOUR CAR! (Must Know) #Shorts #GTA6",
        "hook": "",
        "script": (
            "You can't just respray your ride and vanish in GTA 6 anymore, because police track witness descriptions! "
            "After a chase, witnesses report your exact car model, paint color, and license plate over police dispatch. "
            "If you leave an active scene in that same car, cruisers immediately lock onto you at roadblocks. "
            "Duck into a quiet alley, swap outfits, and steal a low-profile sedan to wipe your heat level clean!"
        ),
        "tags": ["gta 6", "gta 6 police", "gta 6 escape", "gta 6 details", "gaming", "shorts"],
        "search_query": "gta 6 police chase gameplay",
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


def is_viceprint_twitch_candidate(title: str, strict_gameplay: bool = True) -> bool:
    """Filters Twitch VOD titles strictly to GTA 6 gameplay/playthroughs, blocking trailers & react bait."""
    t = title or ""
    if not discover.GTA6_RE.search(t):
        return False
    if discover.OTHER_GTA_RE.search(t):
        return False
    if discover.OTHER_GAME_RE.search(t):
        return False
    if TWITCH_EXCLUDE_RE.search(t):
        return False
    if strict_gameplay and not TWITCH_GAMEPLAY_RE.search(t):
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
    extra_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Discovers non-repeating GTA 6 secrets, tips, easter eggs, and gameplay videos."""
    import urllib.parse

    seen = set(seen_ids or ())
    by_id: Dict[str, Dict[str, Any]] = {}
    queries = ([extra_query] + VICEPRINT_QUERIES) if extra_query else VICEPRINT_QUERIES
    for q in dict.fromkeys(queries):
        url = VICEPRINT_SEARCH_URLS[0].format(q=urllib.parse.quote_plus(q))
        entries = discover._ytdlp_flat(url, 15, cookies=cookies, proxy=proxy)
        for e in entries:
            c = discover._yt_candidate(e, f"viceprint: {q}")
            if c and c["id"] not in by_id:
                by_id[c["id"]] = c

    # Strictly Grand Theft Auto VI on Twitch (enforce GTA 6 exclusive directive until 1 Dec 2026)
    tw_cands: List[Dict[str, Any]] = []
    try:
        _, tw_logins = discover.load_followed("streamers.txt")
        tw_cands = discover.twitch_top("Grand Theft Auto VI", n=25, logins=tw_logins)
    except Exception as e:
        print(f"   (Twitch Viceprint discovery skipped: {e})", flush=True)

    # First keep strict gameplay Twitch VODs; fallback to relaxed GTA6 non-react VODs only if needed
    strict_tw = [c for c in tw_cands if is_viceprint_twitch_candidate(c.get("title", ""), strict_gameplay=True)]
    chosen_tw = strict_tw if strict_tw else [
        c for c in tw_cands if is_viceprint_twitch_candidate(c.get("title", ""), strict_gameplay=False)
    ]
    for c in chosen_tw:
        if c and c["id"] not in by_id:
            by_id[c["id"]] = c

    ranked = []
    for c in by_id.values():
        if c["id"] in seen:
            continue
        dur = float(c.get("duration") or 0)
        if dur and (dur < min_duration or dur > max_duration):
            continue
        if c.get("live_status") in ("is_live", "is_upcoming", "post_live"):
            continue
        if c.get("views_known") and c.get("views", 0) < min_views:
            continue
        is_twitch = c.get("platform") == "twitch"
        if is_twitch:
            if not is_viceprint_twitch_candidate(c.get("title", ""), strict_gameplay=False):
                continue
        elif not is_viceprint_candidate(c.get("title", "")):
            continue

        secret_bonus = 2.0 if re.search(r"\b(secret|hidden|trick|easter\s*egg|detail|tip|mystery)\b", c["title"], re.I) else 1.0
        playthrough_bonus = 1.6 if TWITCH_GAMEPLAY_RE.search(c["title"]) else 1.0
        platform_weight = 0.35 if is_twitch else 1.0
        c["score"] = max(c.get("views", 1000), 1000) * secret_bonus * playthrough_bonus * platform_weight
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
    return VICEPRINT_TOPICS[len(history_records or []) % len(VICEPRINT_TOPICS)]


def align_script_words(script: str, whisper_words: List[Dict[str, Any]], total_dur: float) -> List[Dict[str, Any]]:
    """Maps studio-accurate Whisper word timings back onto exact script typography (preserving GTA 6, numbers)."""
    raw_tokens = [w for w in script.split() if re.sub(r"[^\w']", "", w)]
    if not raw_tokens or not whisper_words or len(whisper_words) < max(6, len(raw_tokens) // 2):
        return []

    norm_s = [re.sub(r"[^\w]", "", w).lower() for w in raw_tokens]
    norm_w = [re.sub(r"[^\w]", "", w.get("w", "")).lower() for w in whisper_words]

    sm = difflib.SequenceMatcher(None, norm_s, norm_w, autojunk=False)
    mapped: List[Optional[Tuple[float, float]]] = [None] * len(raw_tokens)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                mapped[i1 + k] = (float(whisper_words[j1 + k]["s"]), float(whisper_words[j1 + k]["e"]))
        elif tag == "replace" and (i2 - i1) > 0 and (j2 - j1) > 0:
            span_s = float(whisper_words[j1]["s"])
            span_e = float(whisper_words[j2 - 1]["e"])
            step = max(0.08, (span_e - span_s) / (i2 - i1))
            for k in range(i2 - i1):
                mapped[i1 + k] = (span_s + k * step, span_s + (k + 1) * step)

    # Interpolate any unmatched words smoothly between matched anchors
    anchors = [idx for idx, val in enumerate(mapped) if val is not None]
    if len(anchors) < max(5, len(raw_tokens) // 3):
        return []

    for i, val in enumerate(mapped):
        if val is not None:
            continue
        prev_idx = max((a for a in anchors if a < i), default=None)
        next_idx = min((a for a in anchors if a > i), default=None)
        if prev_idx is not None and next_idx is not None:
            t0 = mapped[prev_idx][1]
            t1 = mapped[next_idx][0]
            frac0 = (i - prev_idx) / (next_idx - prev_idx + 1)
            frac1 = (i - prev_idx + 1) / (next_idx - prev_idx + 1)
            mapped[i] = (t0 + frac0 * max(0.08, t1 - t0), t0 + frac1 * max(0.08, t1 - t0))
        elif next_idx is not None:
            t1 = mapped[next_idx][0]
            step = t1 / max(1, next_idx)
            mapped[i] = (i * step, (i + 1) * step)
        elif prev_idx is not None:
            t0 = mapped[prev_idx][1]
            tail = max(0.15, total_dur - t0) / max(1, len(raw_tokens) - prev_idx)
            k = i - prev_idx - 1
            mapped[i] = (t0 + k * tail, t0 + (k + 1) * tail)

    out = []
    for tok, span in zip(raw_tokens, mapped):
        w_clean = re.sub(r"[^\w'%!?.]", "", tok).upper()
        if w_clean and span:
            s_t = max(0.0, round(span[0], 2))
            e_t = max(s_t + 0.08, round(span[1], 2))
            out.append({"w": w_clean, "s": s_t, "e": e_t})
    return out


async def _synthesize_edge_tts(
    script: str, out_mp3: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+18%"
) -> Tuple[List[Dict[str, Any]], float]:
    """Generates crisp fast-paced voiceover audio via edge-tts and derives tight word timestamps."""
    import edge_tts

    try:
        comm = edge_tts.Communicate(script, voice=voice, rate=rate, boundary="WordBoundary")
    except TypeError:
        comm = edge_tts.Communicate(script, voice=voice, rate=rate)

    word_events = []
    sentences = []
    audio_bytes = bytearray()

    async for chunk in comm.stream():
        chunk_type = chunk.get("type")
        if chunk_type == "audio":
            audio_bytes.extend(chunk.get("data", b""))
        elif chunk_type == "WordBoundary":
            word_events.append({
                "offset": chunk["offset"],
                "duration": chunk["duration"],
                "text": chunk["text"],
            })
        elif chunk_type == "SentenceBoundary":
            sentences.append({
                "offset": chunk["offset"],
                "duration": chunk["duration"],
                "text": chunk["text"],
            })

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    out_mp3.write_bytes(audio_bytes)

    dur = 52.0
    try:
        _, _, dur = render.probe(out_mp3)
    except Exception:
        pass

    words: List[Dict[str, Any]] = []
    if word_events:
        for we in word_events:
            w_clean = re.sub(r"[^\w'%]", "", we.get("text", "")).upper()
            if w_clean:
                s_t = round(we["offset"] / 1e7, 2)
                e_t = round((we["offset"] + max(we["duration"], 800000)) / 1e7, 2)
                words.append({"w": w_clean, "s": s_t, "e": e_t})
    else:
        for s in sentences:
            s_start = s["offset"] / 1e7
            s_dur = max(0.2, (s["duration"] / 1e7) * 0.92)
            raw_words = s["text"].split()
            if not raw_words:
                continue
            total_len = sum(len(w) for w in raw_words) or 1
            cur_t = s_start
            for w in raw_words:
                w_span = (len(w) / total_len) * s_dur
                w_clean = re.sub(r"[^\w'%]", "", w)
                if w_clean:
                    words.append({
                        "w": w_clean.upper(),
                        "s": round(cur_t, 2),
                        "e": round(cur_t + w_span, 2),
                    })
                cur_t += w_span

    if dur <= 0 and words:
        dur = words[-1]["e"] + 0.4

    # Try exact Whisper audio-waveform alignment mapped onto clean script tokens
    try:
        w_words = captions.transcribe(out_mp3, model_size="small")
        aligned = align_script_words(script, w_words, dur)
        if aligned:
            words = aligned
    except Exception:
        pass

    return words, dur


def synthesize_narration(
    script: str, out_mp3: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+18%"
) -> Tuple[List[Dict[str, Any]], float]:
    """Sync wrapper for edge-tts synthesis."""
    return asyncio.run(_synthesize_edge_tts(script, out_mp3, voice=voice, rate=rate))


def pick_best_segment(video_url: str, duration: float, work_dir: Path, target_len: float = 54.0,
                      cookies: Optional[str] = None, proxy: Optional[str] = None) -> Tuple[float, float]:
    """Picks an in-action segment skipping stream intros and trail-offs."""
    dur = float(duration or 0)
    if dur <= 0:
        return 20.0, 20.0 + target_len
    if dur > 1800.0:
        skip_start = round(dur * 0.30, 2)
    elif dur > 600.0:
        skip_start = round(dur * 0.25, 2)
    elif dur > 120.0:
        skip_start = 20.0
    elif dur > 80.0:
        skip_start = 10.0
    else:
        skip_start = 0.0
    start = min(skip_start, max(0.0, dur - target_len))
    return round(start, 2), round(min(dur, start + target_len), 2)


def pick_best_segments(
    duration: float, n_segments: int = 4, seg_len: float = 16.0
) -> List[Tuple[float, float]]:
    """Returns spread-out timestamps across long VODs/videos (skipping Twitch intros/react segments)."""
    dur = float(duration or 0)
    if dur <= 0:
        return [(20.0, 20.0 + seg_len)]
    if dur < 140.0:
        skip = 10.0 if dur > 80.0 else 0.0
        s = min(skip, max(0.0, dur - 54.0))
        return [(round(s, 2), round(min(dur, s + 54.0), 2))]

    # Sample well past streamer intro (~28% to ~80% across VOD)
    ratios = [0.28, 0.45, 0.62, 0.78, 0.36, 0.54]
    windows: List[Tuple[float, float]] = []
    for r in ratios:
        s = round(max(12.0, min(dur - seg_len - 5.0, dur * r)), 2)
        e = round(min(dur, s + seg_len), 2)
        if e - s >= 6.0 and all(abs(s - ws) >= seg_len for ws, _ in windows):
            windows.append((s, e))
        if len(windows) >= n_segments + 2:
            break
    return windows or [pick_best_segment("", dur, Path("."))]


def detect_active_box(
    video_path: Path, src_w: Optional[int] = None, src_h: Optional[int] = None
) -> Tuple[int, int, int, int]:
    """Uses ffmpeg cropdetect on 3 sample points to detect and strip black letterbox/pillarbox bars."""
    video_path = Path(video_path)
    if src_w is None or src_h is None:
        src_w, src_h, dur = render.probe(video_path)
    else:
        _, _, dur = render.probe(video_path)

    crops: List[Tuple[int, int, int, int]] = []
    sample_times = [max(0.2, min(dur * 0.25, dur - 0.5)), max(0.5, min(dur * 0.55, dur - 0.5))] if dur > 2.0 else [0.0]
    for st in sample_times:
        cmd = [
            "ffmpeg", "-hide_banner", "-ss", f"{st:.2f}", "-i", str(video_path),
            "-vframes", "8", "-vf", "cropdetect=24:2:0", "-f", "null", "-",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        for m in re.finditer(r"crop=(\d+):(\d+):(\d+):(\d+)", res.stderr or ""):
            cw, ch, cx, cy = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
            if cw >= 200 and ch >= 200 and cw <= src_w and ch <= src_h:
                crops.append((cw, ch, cx, cy))

    if not crops:
        return 0, 0, int(src_w) // 2 * 2, int(src_h) // 2 * 2

    cw = int(statistics.median(c[0] for c in crops)) // 2 * 2
    ch = int(statistics.median(c[1] for c in crops)) // 2 * 2
    cx = max(0, int(statistics.median(c[2] for c in crops)) // 2 * 2)
    cy = max(0, int(statistics.median(c[3] for c in crops)) // 2 * 2)

    cw = min(cw, src_w - cx) // 2 * 2
    ch = min(ch, src_h - cy) // 2 * 2

    # Snap near-full dims back to exact frame size to avoid micro 2-4px trims
    if cw >= src_w * 0.96 and cx <= src_w * 0.03:
        cx, cw = 0, int(src_w) // 2 * 2
    if ch >= src_h * 0.96 and cy <= src_h * 0.03:
        cy, ch = 0, int(src_h) // 2 * 2
    return cx, cy, max(2, cw), max(2, ch)


def validate_gameplay_segment(video_path: Path) -> Tuple[bool, str, Optional[Tuple[int, int, int, int]]]:
    """Rejects movie trailers (ultrawide letterbox), static black frames, and centered talking-head cams."""
    video_path = Path(video_path)
    src_w, src_h, dur = render.probe(video_path)
    if dur < 3.5:
        return False, f"duration {dur:.1f}s too short", None
    if src_h < 360 or src_w < 480:
        return False, f"resolution {src_w}x{src_h} < 360p", None

    ax, ay, aw, ah = detect_active_box(video_path, src_w, src_h)
    if aw < 360 or ah < 360:
        return False, f"active frame {aw}x{ah} too small (heavy letterboxing)", None

    # Reject cinema/movie trailers (e.g. 2.39:1 bars eating top/bottom > 22% inside 16:9)
    if ah < src_h * 0.78 and (aw / max(1, ah)) >= 2.02:
        return False, f"ultrawide cinema letterbox detected ({aw}x{ah} in {src_w}x{src_h})", None

    # Reject centered or fullscreen facecam / talking-head react layouts
    cam = facecam.detect(video_path)
    if cam:
        cx, _cy, cw, ch = cam
        cam_mid_x = (cx + cw / 2.0) / max(1, src_w)
        if 0.24 <= cam_mid_x <= 0.76 or cw > 0.45 * src_w or ch > 0.55 * src_h:
            return False, f"centered/dominant facecam reaction detected at x={cx}..{cx+cw}", None

    return True, "ok", (ax, ay, aw, ah)


def _has_audio_stream(video_path: Path) -> bool:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type",
         "-of", "default=nw=1", str(video_path)],
        capture_output=True, text=True,
    )
    return "codec_type=audio" in (res.stdout or "")


def build_viceprint_jumpcuts(
    src_videos: Union[Path, Sequence[Path]],
    target_duration: float,
    out_path: Path,
    cut_sec: float = 3.2,
    keep_audio: bool = False,
) -> Path:
    """Slices gameplay into dynamic multi-scene jump-cuts (~3.2s rhythm) normalized to border-free 1920x1080."""
    paths = [Path(src_videos)] if isinstance(src_videos, (str, Path)) else [Path(p) for p in src_videos]
    if not paths:
        raise RuntimeError("No gameplay clips provided to build_viceprint_jumpcuts")

    infos = []
    for p in paths:
        w, h, dur = render.probe(p)
        if dur <= 0.5:
            continue
        ax, ay, aw, ah = detect_active_box(p, w, h)
        has_aud = keep_audio and _has_audio_stream(p)
        infos.append({"path": p, "dur": dur, "box": (ax, ay, aw, ah), "has_aud": has_aud})

    if not infos:
        raise RuntimeError("Invalid gameplay duration across source clips")

    all_have_aud = keep_audio and all(x["has_aud"] for x in infos)
    n_cuts = max(1, int(round(target_duration / cut_sec)))

    ffmpeg_inputs: List[str] = []
    filter_parts: List[str] = []
    v_labels: List[str] = []
    a_labels: List[str] = []

    for idx, info in enumerate(infos):
        ffmpeg_inputs += ["-i", str(info["path"])]

    pos = 0.0
    per_src_idx = [0] * len(infos)
    # Round-robin across bursts so consecutive cuts are genuinely different scenes
    for c_i in range(n_cuts):
        src_idx = c_i % len(infos)
        info = infos[src_idx]
        s_dur = info["dur"]
        local_turn = per_src_idx[src_idx]
        per_src_idx[src_idx] += 1

        if len(infos) == 1:
            # Spread cuts widely across single video
            usable = max(0.5, s_dur - cut_sec - 4.0)
            start = round(min(s_dur - 1.0, 2.0 + (c_i * max(cut_sec, usable / max(1, n_cuts))) % max(0.5, usable)), 2)
        else:
            stride = max(cut_sec + 0.3, (s_dur - cut_sec) / max(1, (n_cuts // len(infos)) + 1))
            start = round((local_turn * stride) % max(0.1, s_dur - cut_sec), 2)

        seg_dur = round(min(cut_sec, max(0.5, target_duration - pos)), 2)
        if seg_dur <= 0.15:
            break
        if start + seg_dur > s_dur:
            start = round(max(0.0, s_dur - seg_dur), 2)

        ax, ay, aw, ah = info["box"]
        # Strip black borders and standardize dimensions/fps so concat always succeeds cleanly
        v_filter = (
            f"[{src_idx}:v]trim=start={start:.2f}:duration={seg_dur:.2f},setpts=PTS-STARTPTS,"
            f"crop={aw}:{ah}:{ax}:{ay},"
            f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            f"setsar=1,fps=30,format=yuv420p[v{c_i}]"
        )
        filter_parts.append(v_filter)
        v_labels.append(f"[v{c_i}]")

        if all_have_aud:
            a_filter = (
                f"[{src_idx}:a]atrim=start={start:.2f}:duration={seg_dur:.2f},"
                f"asetpts=PTS-STARTPTS,aresample=48000[a{c_i}]"
            )
            filter_parts.append(a_filter)
            a_labels.append(f"[a{c_i}]")
        pos += seg_dur

    if all_have_aud:
        paired = "".join(f"{v}{a}" for v, a in zip(v_labels, a_labels))
        fc = ";".join(filter_parts) + f";{paired}concat=n={len(v_labels)}:v=1:a=1[vout][aout]"
        maps = ["-map", "[vout]", "-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
    else:
        fc = ";".join(filter_parts) + f";{''.join(v_labels)}concat=n={len(v_labels)}:v=1:a=0[vout]"
        maps = ["-map", "[vout]"]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", *ffmpeg_inputs,
        "-filter_complex", fc, *maps,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        str(out_path),
    ], check=True)
    return out_path


def mix_viceprint_audio(
    jumpcut_vid: Path,
    narration_mp3: Path,
    out_path: Path,
    duration: float,
    bgm_path: Optional[Path] = None,
    keep_game_audio: bool = False,
) -> Path:
    """Combines studio narration + sidechain-ducked BGM (+ optional non-vocal game SFX)."""
    bgm = Path(bgm_path) if bgm_path else DEFAULT_BGM_PATH
    has_bgm = bgm.is_file()
    has_game = keep_game_audio and _has_audio_stream(jumpcut_vid)

    inputs = ["-i", str(jumpcut_vid), "-i", str(narration_mp3)]
    if has_bgm:
        inputs += ["-stream_loop", "-1", "-i", str(bgm)]

    if has_bgm and has_game:
        af = (
            "[1:a]aresample=48000,volume=1.05,asplit=3[narr_sc1][narr_sc2][narr_mix];"
            "[2:a]aresample=48000,volume=0.14[bgm_raw];"
            "[bgm_raw][narr_sc1]sidechaincompress=threshold=0.05:ratio=6:attack=20:release=250[bgm_duck];"
            "[0:a]aresample=48000,volume=0.13[game_raw];"
            "[game_raw][narr_sc2]sidechaincompress=threshold=0.05:ratio=5:attack=20:release=250[game_duck];"
            "[narr_mix][bgm_duck][game_duck]amix=inputs=3:duration=first:normalize=0[aout]"
        )
    elif has_bgm:
        af = (
            "[1:a]aresample=48000,volume=1.05,asplit=2[narr_sc][narr_mix];"
            "[2:a]aresample=48000,volume=0.15[bgm_raw];"
            "[bgm_raw][narr_sc]sidechaincompress=threshold=0.05:ratio=6:attack=20:release=250[bgm_duck];"
            "[narr_mix][bgm_duck]amix=inputs=2:duration=first:normalize=0[aout]"
        )
    elif has_game:
        af = (
            "[1:a]aresample=48000,volume=1.05,asplit=2[narr_sc][narr_mix];"
            "[0:a]aresample=48000,volume=0.15[game_raw];"
            "[game_raw][narr_sc]sidechaincompress=threshold=0.05:ratio=5:attack=20:release=250[game_duck];"
            "[narr_mix][game_duck]amix=inputs=2:duration=first:normalize=0[aout]"
        )
    else:
        af = "[1:a]aresample=48000,volume=1.05[aout]"

    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", *inputs,
        "-filter_complex", af, "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.2f}", str(out_path),
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
