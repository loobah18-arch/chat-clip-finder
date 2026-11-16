# 🎬 The Chat Clip Finder

> **Let Twitch chat find the best moments of a stream, then cut them into vertical 9:16 clips.**  
> No paid AI subscription. 100% free and open-source.

---

## 💡 The Idea: Chat Knows Where the Clip Is

When something crazy happens on a stream, chat explodes: hundreds of `"LMAO"`, `"KEKW"`, or `"NO WAY"` flood in within seconds. That burst is the moment worth clipping.

Instead of watching six hours of raw footage, **The Chat Clip Finder** reads the full chat log, computes chat velocity relative to its local baseline, and cuts vertical TikTok/Reels/Shorts clips directly from the spikes.

```
💬 Grab the chat       📈 Find the spikes           ✂️ Cut the clips
   Every message with  -> Messages per 10s       -> 30s vertical 9:16
   timestamp              compared to 5m baseline   1080x1920
```

### 🧠 The Trick
> **Chat reacts AFTER the moment.** People see something happen, then type.  
> The tool starts every clip **20 seconds before the spike** and ends it **10 seconds after**. You capture the buildup and the moment itself—not just the aftermath.

### 🎯 The Smart Part (Local Baseline)
A busy stream has a high chat volume all the time. The tool compares each 10-second slice to the **5 minutes before and after it** using a moving median. It detects moments that are unusually explosive relative to their surroundings, not just the busiest hour of the stream.

---

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

## ☁️ Cloud Runner (GitHub Actions — No Local Install Needed)

Don't want to install FFmpeg or download heavy video files to your computer or phone? Run the clipper entirely in GitHub's cloud runners:

1. Fork or open this repo on GitHub.
2. Go to **Actions** → **Clip Twitch Stream (Cloud Runner)**.
3. Click **Run workflow**:
   - Paste the **Twitch VOD URL** (e.g. `https://www.twitch.tv/videos/1234567890`)
   - (Optional) Enter opening hook text (e.g. `Wait for it 😳`)
4. Download the ready-to-post vertical 9:16 `.mp4` clips directly from the workflow artifacts!

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

### Step 8 · Add Captions & Hook (Step 9 of Guide)
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
| `--layout <mode>` | 9:16 layout: `blur` (ambient fill with full 16:9 stream) or `crop` (center zoom) | `blur` |
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
- Built based on the original Chat Clip Finder guide by [@ai.with.raiyan](https://www.instagram.com/ai.with.raiyan/).
- Uses [TwitchDownloader](https://github.com/lay295/TwitchDownloader) by `lay295` (MIT) and [FFmpeg](https://ffmpeg.org).
- License: [MIT](LICENSE)
