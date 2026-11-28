# 🎬 Chat Clip Finder

[![Auto-Clip](https://github.com/loobah18-arch/chat-clip-finder/actions/workflows/auto_clip.yml/badge.svg)](https://github.com/loobah18-arch/chat-clip-finder/actions/workflows/auto_clip.yml) ← tap, then **Run workflow** to clip now

> **Two autonomous pipelines for GTA 6 Shorts. Runs fully in the cloud on GitHub Actions — no hardware needed.**

---

## Pipeline Overview

| | Mode A — Stream Highlight | Mode B — Viceprint |
|---|---|---|
| **What it makes** | Clip-reaction Shorts from live Twitch/YouTube streams | Narrated "GTA 6 Secrets" Shorts from raw gameplay VODs |
| **Source** | Twitch streams + YouTube VODs with active chat | Twitch VODs tagged `Grand Theft Auto VI` with strict gameplay filter |
| **Layout** | Streamer webcam (top) + gameplay (bottom), kinetic captions | Multi-scene 3.2 s jump-cuts, full-bleed gameplay, no facecam |
| **Audio** | Original stream audio, word-timed captions | Edge-TTS narration + sidechain-ducked BGM |
| **Trigger** | `--mode a` or omit flag | `--mode b` |

---

## Mode A — Stream Highlight Clips

Finds the **highest chat-reaction moments** in a Twitch or YouTube stream and auto-crops them to 9:16.

### How it works
1. **Discovery** — searches YouTube for today's most-watched GTA 6 gameplay streams (skips news, leaks, countdowns, GTA 5/RP and Shorts). Checks Twitch for live/recent GTA 6 streams. Creators in `streamers.txt` are always checked first.
2. **Chat analysis** — downloads timestamped chat with TwitchDownloaderCLI or yt-dlp, counts reactions per 10 s bucket, picks the top spikes.
3. **Rendering** — for each spike, downloads only the ±30 s segment. YuNet face detector finds the webcam; if found, stacks cam (top) + gameplay (bottom). No cam → zoomed gameplay over a blurred copy. Whisper transcribes every word; captions appear 1–2 words at a time, active word highlights yellow.
4. **Hook** — 3.5 s black-on-white hook title at the start (chosen per clip based on chat reaction type).
5. **Output** — 1080×1920, 30 fps, –14 LUFS, `@streamer` credit, `clips/posts.json` with title + hashtags.

### Candle Gate (algorithm protection)
Scheduled auto-runs are suppressed when the YouTube algorithm is in a "distribution window" (Candle Gate, same logic as `auto-clipper-shorts`). Prevents posting into dead zones.

---

## Mode B — Viceprint (Narrated GTA 6 Secrets)

Produces **standalone narrated Shorts** in the style of a "GTA 6 secrets/guide" video — no streamer, no facecam, pure gameplay footage with voiceover.

### What Mode B produces
- **Multi-scene jump-cuts** — 4 × 3.2 s segments from different timestamps in the same VOD, round-robined so the shot variety looks like a produced edit.
- **Edge-TTS narration** — a "secret tip" or "guide" script (~90–120 words) is generated for the topic, synthesised with `edge-tts` (Microsoft's free neural TTS) at a slightly elevated rate.
- **Ducked BGM** — an instrumental gaming BGM track plays under the narration, sidechained so the music drops 12 dB whenever speech is present.
- **Borderless active-box crop** — `ffprobe cropdetect` auto-detects the letterbox/pillarbox bounds of the source clip and crops to the true gameplay area before squaring to 1080×1920. No black bars.
- **Kinetic captions** — Whisper aligns the generated script word-by-word against the TTS audio; captions appear 2 words at a time (Montserrat Black, 96 px, yellow highlight on the spoken word).

### Where Mode B gets its clips
1. **Twitch VOD discovery** — calls the Twitch Helix API for top VODs under category `Grand Theft Auto VI`.
2. **Strict content filter (`is_viceprint_twitch_candidate`)** — rejects VODs whose title matches `TWITCH_EXCLUDE_RE` (react, trailer, kai vs, counting down, watch party, movie, etc.). Requires `TWITCH_GAMEPLAY_RE` keywords (play, gameplay, day, grind, run, session, hours, full, stream, live, drops) in strict mode.
3. **Multi-burst download** — picks 4 non-overlapping 15 s windows spread across the VOD (skipping the first/last 5 % to avoid intros/outros) and downloads each with yt-dlp.
4. **Segment validation (`validate_gameplay_segment`)** — each burst is checked:
   - **Facecam rejection**: runs `ccf.facecam.detect()`. If the detected face box is centered (x within 24–76 % of frame width) or oversized (> 45 % wide / > 55 % tall), the segment is rejected as a reaction/facecam segment.
   - **Letterbox rejection**: if `cropdetect` returns ultra-wide (< 56 % of frame height) the segment is rejected as a cinema trailer.
5. **Path A — dense guide speech detected** (`_is_dense_guide_speech`): if the VOD already contains a dense narration track (≥ 115 WPM, first word within 3.5 s, no gap > 4.5 s, silence at end < 6 s), that audio is used directly; Whisper transcribes it for captions.
6. **Path B — synthesised narration** (default): `produce_viceprint_short()` generates a "GTA 6 secrets" script for the detected topic, synthesises it with edge-tts, and builds the Short from the validated burst segments.

### Audio pipeline
```
edge-tts narration ──► align_script_words (Whisper) ──► captions
                   └──► mix_viceprint_audio ──────────── BGM sidechain-duck ──► final mix
```

---

## CI/CD — GitHub Actions

**Workflow**: `.github/workflows/auto_clip.yml`  
**Schedule**: daily at **4 PM ET** (21:00 UTC)  
**Manual trigger**: Repository → Actions → Auto-Clip → Run workflow

### Required Secrets

| Secret | What it's for |
|---|---|
| `CLIENT_ID` | Google OAuth client ID (YouTube Data API) |
| `CLIENT_SECRET` | Google OAuth client secret |
| `REFRESH_TOKEN` | OAuth refresh token for the channel |
| `YOUTUBE_COOKIES` | Netscape-format cookies for yt-dlp (export from browser) |
| `TWITCH_CLIENT_ID` | Twitch Helix API app client ID (free at dev.twitch.tv) |
| `TWITCH_CLIENT_SECRET` | Twitch Helix API app client secret |

### Optional Secrets / Variables

| Name | Default | Purpose |
|---|---|---|
| `YOUTUBE_PROXY` | — | Proxy URL if GitHub runner IP is blocked |
| `AUTO_UPLOAD` | `false` | Set repo variable to `true` to auto-upload clips |
| `AUTO_PRIVACY` | `private` | Privacy level of auto-uploaded videos |

### System dependencies installed by the workflow
```
ffmpeg python3-pip yt-dlp fonts-montserrat fontconfig
```

---

## CLI Usage

```bash
# Mode A — stream highlights (default)
python3 auto_clips.py --mode a --count 2 --top 3

# Mode B — Viceprint narrated Short
python3 auto_clips.py --mode b --topic "secret_workout"

# List what the auto-clipper would pick without rendering
python3 auto_clips.py --list

# Single stream, full control
python3 chat_clips.py --url "https://www.twitch.tv/videos/1234567890" --top 5 --emotes
python3 chat_clips.py --url "https://www.youtube.com/watch?v=..." --no-chat
```

### `auto_clips.py` flags

| Flag | Default | Description |
|---|---|---|
| `--mode` | `a` | Pipeline: `a` = stream highlights, `b` = Viceprint narrated |
| `--topic` | auto-detected | Topic slug for Mode B script generation |
| `--count` | `1` | Number of Shorts to produce |
| `--top` | `5` | Candidate streams/VODs to evaluate |
| `--list` | — | Print candidates without rendering |

### `chat_clips.py` flags (Mode A, single stream)

| Flag | Default | Description |
|---|---|---|
| `--url` | — | Twitch or YouTube stream URL |
| `--top` | `5` | Number of clips to cut |
| `--before` | `20` | Seconds of lead-in before chat spike |
| `--after` | `10` | Seconds after spike |
| `--gap` | `90` | Minimum gap between clips (seconds) |
| `--layout` | `auto` | `auto`, `stack`, `gameplay`, `blur`, `crop` |
| `--game` | `gta6` | `gta6` or `none` |
| `--captions` | `on` | Word-by-word captions |
| `--no-chat` | off | Use loudness spikes instead of chat |
| `--video` | — | Cut from a local video file |
| `--dry-run` | false | Analyze only, don't cut video |

---

## `streamers.txt` Format

One Twitch or YouTube handle per line. Checked before generic discovery.

```
# Twitch handles (no @)
kaicenat
xQc

# YouTube channel IDs or handles
UCxxxxxxxxxxxxxxxxxx
@SomeGTAChannel
```

---

## State & Deduplication

`state/processed.json` stores every source ID that has been clipped (YouTube video ID or `tw:<vod_id>`). The auto-clipper skips already-processed sources.

---

## Running Tests

```bash
python3 -m unittest discover -p "test_*.py" -v
# Expected: 62 tests, all pass
```

Tests cover: chat spike detection, facecam detection, Candle Gate logic, Viceprint Twitch filter, Path A density gate, segment validation, script alignment, BGM mix, and render graph.

---

## Project Structure

```
chat-clip-finder/
├── auto_clips.py          # Orchestrator — Mode A & B, discovery, dedup, upload
├── chat_clips.py          # Single-stream Mode A CLI
├── ccf/
│   ├── viceprint.py       # Mode B: Twitch discovery, segment validation, TTS, BGM mix
│   ├── render.py          # FFmpeg filtergraph builder (stack, gameplay, viceprint)
│   ├── captions.py        # Whisper word-timing + ASS subtitle builder
│   ├── facecam.py         # YuNet face detector
│   └── candle_gate.py     # Algorithm protection gate
├── assets/
│   └── audio/
│       └── viceprint_bgm.mp3   # Instrumental BGM for Mode B (90 s)
├── state/
│   └── processed.json          # Dedup store
├── streamers.txt               # Priority creator list
├── test_chat_clips.py          # 62 unit tests
└── .github/workflows/
    └── auto_clip.yml           # Daily CI/CD + manual trigger
```

---

## Troubleshooting

| Error | Fix |
|---|---|
| Mode B picks Avengers / reaction content | `TWITCH_EXCLUDE_RE` should catch it; check that `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` secrets are set so the strict Twitch filter runs |
| Black bars inside the 1:1 frame | `detect_active_box()` uses cropdetect — ensure ffmpeg is installed on the runner |
| No narration audio | `edge-tts` requires outbound internet; check runner firewall |
| Montserrat font missing | Workflow installs `fonts-montserrat` + `fc-cache`; run locally with `sudo apt install fonts-montserrat fontconfig && sudo fc-cache -f` |
| `state/processed.json` blocks re-run | Delete the file or remove the specific source ID from it |
| Cookies expired | Re-export from browser with "Get cookies.txt LOCALLY" extension, update `YOUTUBE_COOKIES` secret |

---

## Credits & Etiquette

- **Only use VODs from creators who allow clipping.** `@streamer` credit is added on screen automatically.
- Facecam detection based on [ClipKaro](https://github.com/allthingsaman/ClipKaro) by Aman Upadhyay (MIT).
- Uses [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org), [Whisper](https://github.com/openai/whisper), [edge-tts](https://github.com/rany2/edge-tts).
- License: [MIT](LICENSE)
