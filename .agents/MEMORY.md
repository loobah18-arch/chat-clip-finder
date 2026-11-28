# Project Memory & Constraints

## Active Directives
- **Game Priority:** Prioritize **GTA 6** (`gta6`) exclusively for all clipping and uploads until **1 December 2026**.
- **Shorts Layout:** Strictly enforce `stack` layout (`1080x700` top corner streamer webcam, `1080x1220` bottom gameplay). Never fallback to gameplay-only or blurred background layouts.
- **Webcam Enforcement:** Strictly require a detected facecam in one of the 4 corners (`--require-cam` active by default). Automatically skip streams without a webcam.
- **Upload Target:** Automated uploads publish to the connected YouTube channel (`grandtheftclipper`).
- **Exact-Due Auto-Restart:** If Candle Gate Layer 0 spacing holds the run, the workflow must calculate remaining seconds, sleep until the exact due time (+60s), and automatically re-dispatch the workflow instead of waiting for tomorrow's cron.
- **Dual Mode (Streamer Stack + Viceprint Formula):** Supports both Mode A (Streamer Stack with required facecam) and Mode B (Viceprint formula: unbranded 1:1 square centered in 9:16 blurred background, no channel watermark or HUD badges, 1-2 word bold kinetic popping captions, fast-paced voiceover/narration on GTA 6 secrets, tips & gameplay). Automatically alternates modes via `upload_history.json` (`mode`) and falls back to Viceprint if no live streamer with a facecam is found.

- **High-Intelligence Token Optimization (ALWAYS ON):** Permanently enforce token saving protocols across all sessions and turns (~/.agents/rules/token-saving.md). Eliminate pleasantries, filler, and trailing summaries; enforce surgical diffs, line-scoped reads, aggressive batching, and /handoff compaction.
