# 🎬 The Chat Clip Finder

> **Let chat find the best moments of a Twitch or YouTube stream, then turn them into ready-to-post Shorts, Reels and TikToks.**
> Tuned for **GTA 6** streams and gameplay. Free, open-source, runs on GitHub Actions from your phone.

## 🆕 v2: modern Shorts, YouTube streams, GTA 6 mode

| | What you get |
|---|---|
| 🎙️ **Word-by-word captions** | Whisper (free, CPU) times every word. 1-3 words on screen, ALL CAPS, heavy outline, the spoken word pops in yellow. Whisper's made-up words during music / explosions are dropped. |
| 📱 **Streamer layout** | Webcam found automatically (YuNet face detector) -> cam on top, gameplay below, captions on the seam. No cam (gameplay uploads, trailers) -> zoomed gameplay over a blurred copy. |
| 🪝 **Hook title** | Black-on-white hook for the first 3.5 s (Instagram style), picked per clip from how chat reacted ("WAIT... WHAT JUST HAPPENED?", "5 STARS IN 10 SECONDS"). |
| ✅ **Platform-ready** | 1080x1920, 30 fps, -14 LUFS loudness, progress bar, faststart, key content kept out of the apps' button areas, `@streamer` credit on screen. |
| ▶️ **YouTube streams** | Paste a YouTube video / past live-stream link. Chat replay + only the needed segments are downloaded with yt-dlp, using your cookies file (ClipKaro-style lookup) and optional proxy. |
| 🚔 **GTA 6 mode** (`--game gta6`, default) | Chat reactions like WASTED, BUSTED, 5 STAR, VICE CITY, cops, chase count extra; GTA 6 titles + hashtags; every clip gets its own title. |
| 🔊 **No chat? No problem** | `--no-chat` finds moments from loudness spikes (crashes, explosions, screaming) for gameplay videos and trailers. |
| 🧹 **Skips dead air** | Ignores the first 2 min ("Starting soon") and last minute of a stream. |

```
python3 chat_clips.py --url "https://www.youtube.com/watch?v=..." --emotes --top 5
python3 chat_clips.py --url "https://www.twitch.tv/videos/123..." --emotes
python3 chat_clips.py --url "https://youtu.be/..." --no-chat          # GTA 6 gameplay upload, no chat
```
Install once: `pip install -r requirements.txt` + FFmpeg. Finished clips land in `clips/`, with a title,
description and hashtags for each one in `clips/posts.json`.

### YouTube cookies
YouTube asks GitHub's servers to sign in. Export your cookies (any "Get cookies.txt" browser extension,
while logged in to a **throwaway** Google account), then save the file's text (or base64) as the repo
secret `YOUTUBE_COOKIES`. Locally, just put it next to the script as `youtube_cookies.txt`.
Optional: `YOUTUBE_PROXY` secret if the runner is still blocked. Cookies expire, so re-export when
downloads start failing.

### Cloud runner
Actions -> **Clip Stream to Shorts** -> Run workflow -> paste the link. Leave `upload_to_youtube` off to
check the clips first (download them from the run's artifacts); demo runs never upload.

---

## 💡 The Idea: Chat Knows Where the Clip Is

When something crazy happens on a stream, chat explodes. The tool counts messages per 10 seconds,
compares each slice to the 5 minutes around it, and cuts from the spikes. Chat reacts *after* the
moment, so clips start 20 s before the spike and end 10 s after.

## ⚡ Quick Start (3 Commands)

Clone the repository and test the algorithm immediately with the included synthetic 2-hour demo stream:

```bash
git clone https://github.com/loobah18-arch/chat-clip-finder.git
cd chat-clip-finder

# 1. Test spike detector on demo chat (zero setup required)
node chat-clips.mjs demo_chat.json
# or with Python:
python3 chat_clips.py demo_chat.json
```

**Real output:**
```text
💬 13597 chat messages, ⏱ 2:00:00 of stream

▁▁▁▁▁▁▁▁▁▇▁▁▁▁▁▁▁▃▁▁▁▁▁▁▁█▁▁▁▁▁▁▁▁▅▁▁▁▁▁▁▁▁▁▁▁█▁▁▁▁▁▁▁▁▁
0:00:00                                          2:00:00

Top Moments:
#1  0:20:00  120 msgs in 10s  (6.3x normal)  -> clip 0:19:40 to 0:20:10
#2  0:38:20  59 msgs in 10s  (3.1x normal)  -> clip 0:38:00 to 0:38:30
#3  0:55:30  130 msgs in 10s  (6.8x normal)  -> clip 0:55:10 to 0:55:40
#4  1:15:00  85 msgs in 10s  (4.5x normal)  -> clip 1:14:40 to 1:15:10
#5  1:40:10  138 msgs in 10s  (7.3x normal)  -> clip 1:39:50 to 1:40:20

✅ Saved moment data to clips/moments.json.
```

---


---

## 📖 Step-by-Step Guide

### Step 1 · Install Node.js (or Python 3)
- Download and install Node.js (v18+) from [nodejs.org](https://nodejs.org).
- Check: `node --version`

### Step 2 · Install FFmpeg
- **Windows (PowerShell)**: `winget install Gyan.FFmpeg`
- **macOS (Terminal)**: `brew install ffmpeg`
- **Linux / Ubuntu**: `sudo apt install ffmpeg`
- Check: `ffmpeg -version`

### Step 3 · Download TwitchDownloaderCLI
- Download the CLI zip for your OS from [lay295/TwitchDownloader Releases](https://github.com/lay295/TwitchDownloader/releases/latest).
- Extract `TwitchDownloaderCLI` (or `TwitchDownloaderCLI.exe`) into the folder.
- On Mac/Linux: run `chmod +x TwitchDownloaderCLI`.

### Step 4 · Pick a Stream
- On Twitch, go to a streamer's page → **Videos** → **Past Broadcasts**.
- Copy the VOD URL: `https://www.twitch.tv/videos/1234567890`
- *Always clip creators who allow clipping or run clipping campaigns.*

### Step 5 · Grab the Chat
Download the timestamped chat log:
```bash
# Windows
.\TwitchDownloaderCLI.exe chatdownload --id https://www.twitch.tv/videos/1234567890 -o chat.json

# Mac / Linux
./TwitchDownloaderCLI chatdownload --id https://www.twitch.tv/videos/1234567890 -o chat.json
```

### Step 6 · Find the Moments
Inspect the chat spikes and ASCII timeline:
```bash
node chat-clips.mjs chat.json
```

### Step 7 · Cut Vertical 9:16 Clips
Download only the 30-second clips around each spike and auto-crop to 9:16 (1080x1920):
```bash
node chat-clips.mjs chat.json --vod https://www.twitch.tv/videos/1234567890
```
> *If you already downloaded the entire stream video, use `--video stream.mp4` instead of `--vod`.*

### Step 8 · Captions & Hook
v2 adds word-by-word captions and a hook automatically. The old helper still works for one-off edits:
Most users watch Short-form video with the sound muted. Add captions or an opening hook:
- **Built-in Hook Caption**:
  ```bash
  python3 caption_helper.py clips/clip_01.mp4 --text "Wait for it 😳"
  ```
- **Option A**: [OpenShorts](https://openshorts.app) / [github.com/mutonby/openshorts](https://github.com/mutonby/openshorts)
- **Option B**: CapCut (Auto Captions → Bold Style)

---

## 🎛️ Settings Cheat Sheet

Add any of these flags to customize the output:

| Option | Description | Default |
|---|---|---|
| `--top <n>` | How many clips to generate | `5` |
| `--before <s>` | Seconds before the spike to start clip | `20` |
| `--after <s>` | Seconds after the spike to end clip | `10` |
| `--gap <s>` | Minimum seconds between two clips | `90` |
| `--bucket <s>` | Size of each counting slice in seconds | `10` |
| `--layout <mode>` | `auto`, `stack` (cam top), `gameplay` (zoomed, no cam), `blur`, `crop` | `auto` |
| `--cam <pos>` | Webcam position, or `auto` to detect | `auto` |
| `--game <name>` | `gta6` or `none` | `gta6` |
| `--captions on/off` | Word-by-word captions | `on` |
| `--lang <code>` | Spoken language (`en`, `hi`...) | auto |
| `--hook <text>` | Same hook on every clip | per clip |
| `--credit <name>` | Streamer credit | from video |
| `--url <link>` | Twitch or YouTube link | — |
| `--no-chat` | Loudness spikes instead of chat | off |
| `--skip-start / --skip-end` | Ignore intro / outro seconds | `120` / `60` |
| `--out <folder>` | Folder name for the output clips | `clips` |
| `--video <file>` | Cut from a local video file you already have | — |
| `--vod <url/id>` | Cut from Twitch directly via TwitchDownloaderCLI | — |
| `--tdl <path>` | Custom path to TwitchDownloaderCLI binary | auto-detected |
| `--dry-run` | Analyze chat & write moments.json without cutting video | `false` |

**Example (10 clips, 25s lead-in, custom folder):**
```bash
node chat-clips.mjs chat.json --vod https://www.twitch.tv/videos/1234567890 --top 10 --before 25 --out gta-day1
```

---

## 🛠️ Troubleshooting

| Error | Fix |
|---|---|
| `node / ffmpeg is not recognized` | Close terminal and open a new one. Ensure tools are on your PATH. |
| `No chat messages found` | Verify `chat.json` finished downloading and is not empty. |
| `TwitchDownloaderCLI failed` | On Windows, ensure `.exe` is in the folder. On Mac/Linux, run `chmod +x TwitchDownloaderCLI` and pass `--tdl ./TwitchDownloaderCLI`. |
| `Clips start after the action` | Increase lead-in time with `--before 30`. |
| `Moments are all at the start` | The stream was short or chat was quiet. Pick a longer VOD with active chat. |
| `VOD link doesn't work` | Subscriber-only or expired VODs cannot be downloaded. |

---

## ⚖️ Etiquette & Credits

- **Only clip creators who allow it.** Credit the streamer in your caption and on screen (`@streamer`).
- Facecam model, cookies lookup and safe-zone ideas from [ClipKaro](https://github.com/allthingsaman/ClipKaro) by Aman Upadhyay (MIT).
- Built based on the original Chat Clip Finder guide by [@ai.with.raiyan](https://www.instagram.com/ai.with.raiyan/).
- Uses [TwitchDownloader](https://github.com/lay295/TwitchDownloader) by `lay295` (MIT) and [FFmpeg](https://ffmpeg.org).
- License: [MIT](LICENSE)
