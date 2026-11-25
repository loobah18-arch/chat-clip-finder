# Project Memory & Constraints

## Active Directives
- **Game Priority:** Prioritize **GTA 6** (`gta6`) exclusively for all clipping and uploads until **1 December 2026**.
- **Shorts Layout:** Strictly enforce `stack` layout (`1080x700` top corner streamer webcam, `1080x1220` bottom gameplay). Never fallback to gameplay-only or blurred background layouts.
- **Webcam Enforcement:** Strictly require a detected facecam in one of the 4 corners (`--require-cam` active by default). Automatically skip streams without a webcam.
- **Upload Target:** Automated uploads publish to the connected YouTube channel (`grandtheftclipper`).
- **Exact-Due Auto-Restart:** If Candle Gate Layer 0 spacing holds the run, the workflow must calculate remaining seconds, sleep until the exact due time (+60s), and automatically re-dispatch the workflow instead of waiting for tomorrow's cron.
