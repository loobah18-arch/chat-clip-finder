#!/usr/bin/env node
/**
 * chat-clips: find the best moments of a Twitch stream from its chat, and cut them as vertical clips.
 *
 * 1. Get the chat:   TwitchDownloaderCLI chatdownload --id <VOD> -o chat.json
 * 2. Find + cut:     node chat-clips.mjs chat.json --vod <VOD>        (downloads only the clip pieces)
 *              or:   node chat-clips.mjs chat.json --video vod.mp4    (cuts from a video you already have)
 *              or:   node chat-clips.mjs chat.json                    (just lists the moments)
 *
 * Needs: Node 18+, ffmpeg on PATH (for cutting), TwitchDownloaderCLI on PATH or --tdl <path> (for --vod).
 * Free, MIT. Only clip creators who allow it.
 */

import { readFileSync, mkdirSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] !== undefined ? args[i + 1] : def;
};
const hasFlag = (name) => args.includes(`--${name}`);

const chatFile = args.find((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--')));
if (!chatFile || hasFlag('help') || hasFlag('h')) {
  console.log(`
The Chat Clip Finder 🎬
Let Twitch chat find the best moments of a stream, then cut them into vertical 9:16 clips.

Usage:
  node chat-clips.mjs <chat.json> [options]

Options:
  --vod <URL|ID>      Twitch VOD URL or ID (downloads only the 30s clips needed)
  --video <file.mp4>  Cut from a local video file you already downloaded
  --top <number>      Number of clips to make (default: 5)
  --before <seconds>  Seconds before spike to start clip (default: 20)
  --after <seconds>   Seconds after spike to end clip (default: 10)
  --gap <seconds>     Minimum seconds between two clips (default: 90)
  --bucket <seconds>  Window size for counting chat messages (default: 10)
  --out <dir>         Output directory for clips and metadata (default: clips)
  --tdl <path>        Path to TwitchDownloaderCLI executable
  --dry-run           Only find moments and save moments.json, do not cut video
  --help, -h          Show this help message

Examples:
  node chat-clips.mjs chat.json
  node chat-clips.mjs chat.json --vod https://www.twitch.tv/videos/1234567890
  node chat-clips.mjs chat.json --video stream.mp4 --top 10 --before 25 --out highlights
`);
  process.exit(chatFile ? 0 : 1);
}

const BUCKET = Number(opt('bucket', 10)); // seconds per slice
const TOP = Number(opt('top', 5));        // how many clips
const BEFORE = Number(opt('before', 20)); // chat reacts AFTER the moment, so start earlier
const AFTER = Number(opt('after', 10));
const GAP = Number(opt('gap', 90));       // min seconds between two clips
const OUT = opt('out', 'clips');
const VOD = opt('vod');
const VIDEO = opt('video');
const LAYOUT = opt('layout', 'blur');     // 'blur' (ambient fill, full HUD/facecam) or 'crop' (center zoom)
const DRY_RUN = hasFlag('dry-run');

// Smart binary detection for TwitchDownloaderCLI
const resolveTDL = () => {
  const custom = opt('tdl');
  if (custom) return custom;
  if (existsSync('./TwitchDownloaderCLI')) return './TwitchDownloaderCLI';
  if (existsSync('./TwitchDownloaderCLI.exe')) return './TwitchDownloaderCLI.exe';
  if (process.platform === 'win32') return 'TwitchDownloaderCLI.exe';
  return 'TwitchDownloaderCLI';
};
const TDL = resolveTDL();

// --- 1. Read chat (TwitchDownloader JSON: comments[].content_offset_seconds) ---
if (!existsSync(chatFile)) {
  console.error(`Error: Chat file not found: ${chatFile}`);
  process.exit(1);
}

let chat;
try {
  chat = JSON.parse(readFileSync(chatFile, 'utf8'));
} catch (err) {
  console.error(`Error parsing JSON from ${chatFile}: ${err.message}`);
  process.exit(1);
}

const comments = Array.isArray(chat) ? chat : (chat.comments ?? []);
const times = comments
  .map((c) => (typeof c === 'number' ? c : c.content_offset_seconds))
  .filter((t) => typeof t === 'number' && !isNaN(t) && t >= 0);

if (times.length === 0) {
  console.error('Error: No chat messages found. Is this a TwitchDownloader chat .json file?');
  process.exit(1);
}

// --- 2. Count messages per bucket ---
const length = Math.max(...times, chat.video?.length ?? 0);
const totalBuckets = Math.ceil(length / BUCKET) + 1;
const counts = new Array(totalBuckets).fill(0);
for (const t of times) {
  const idx = Math.floor(t / BUCKET);
  if (idx < totalBuckets) counts[idx]++;
}

// --- 3. Score = how much louder than the chat around it (local median) ---
// Compares each moment to 5 minutes (300s) before and after
const median = (arr) => {
  if (arr.length === 0) return 0;
  const s = [...arr].sort((x, y) => x - y);
  return s[Math.floor(s.length / 2)] ?? 0;
};

const AROUND = Math.max(1, Math.round(300 / BUCKET)); // 5 minutes on each side
const score = counts.map((n, i) => {
  const windowSlice = counts.slice(Math.max(0, i - AROUND), i + AROUND + 1);
  const baseline = median(windowSlice);
  return n / (baseline + 1);
});

// --- 4. Pick the top spikes, keep them apart ---
const order = score.map((s, i) => i).sort((a, b) => score[b] - score[a]);
const peaks = [];
for (const i of order) {
  if (peaks.length >= TOP) break;
  const t = i * BUCKET;
  if (counts[i] < 5) continue; // Minimum 5 messages in spike to filter tiny noise
  if (peaks.some((p) => Math.abs(p.t - t) < GAP)) continue;
  peaks.push({
    t,
    msgs: counts[i],
    score: +score[i].toFixed(1),
  });
}
peaks.sort((a, b) => a.t - b.t);

// --- 5. Show ASCII visualization and summary ---
const hms = (s) => {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600);
  const m = Math.floor(s / 60) % 60;
  const sec = s % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
};

const bars = ' ▁▂▃▄▅▆▇█';
const W = 60;
const per = Math.max(1, Math.ceil(counts.length / W));
const cols = Array.from({ length: Math.ceil(counts.length / per) }, (_, k) =>
  Math.max(...counts.slice(k * per, (k + 1) * per))
);
const topVal = Math.max(...cols, 1);

console.log(`\n💬 ${times.length} chat messages, ⏱ ${hms(length)} of stream\n`);
console.log(cols.map((c) => bars[Math.min(8, Math.round((c / topVal) * 8))]).join(''));
const endHms = hms(length);
const spacing = Math.max(1, cols.length - endHms.length - 7);
console.log(`0:00:00${' '.repeat(spacing)}${endHms}\n`);

console.log('Top Moments:');
peaks.forEach((p, k) => {
  const clipStart = Math.max(0, p.t - BEFORE);
  const clipEnd = p.t + AFTER;
  console.log(
    `#${k + 1}  ${hms(p.t)}  ${p.msgs} msgs in ${BUCKET}s  (${p.score}x normal)  -> clip ${hms(clipStart)} to ${hms(clipEnd)}`
  );
});

mkdirSync(OUT, { recursive: true });
const momentsData = peaks.map((p, k) => {
  const start = Math.max(0, p.t - BEFORE);
  const end = p.t + AFTER;
  return {
    rank: k + 1,
    t: p.t,
    timestamp: hms(p.t),
    msgs: p.msgs,
    score: p.score,
    start,
    end,
    clipStart: hms(start),
    clipEnd: hms(end),
    duration: end - start,
    clipFile: `clip_${String(k + 1).padStart(2, '0')}.mp4`,
  };
});

writeFileSync(join(OUT, 'moments.json'), JSON.stringify(momentsData, null, 2));

if (DRY_RUN || (!VOD && !VIDEO)) {
  console.log(`\n✅ Saved moment data to ${join(OUT, 'moments.json')}.`);
  console.log('To render clips, add --vod <ID/URL> or --video <file.mp4>');
  process.exit(0);
}

// --- 6. Cut vertical clips (9:16 format) ---
const run = (cmd, cmdArgs) => {
  const r = spawnSync(cmd, cmdArgs, { stdio: 'inherit' });
  if (r.status !== 0) {
    throw new Error(`Command failed: ${cmd} ${cmdArgs.join(' ')}`);
  }
};

// 9:16 layout filters: 'blur' (ambient fill with full 16:9 content) or 'crop' (center zoom)
const getFilterArgs = () => {
  if (LAYOUT === 'crop') {
    return [
      '-vf',
      'crop=w=floor(ih*9/16/2)*2:h=ih:x=(iw-ow)/2:y=0,scale=1080:1920,setsar=1',
    ];
  }
  return [
    '-filter_complex',
    '[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.15[bg];[0:v]scale=1080:-1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1',
  ];
};

const CODEC_OPTS = [
  '-c:v', 'libx264',
  '-preset', 'veryfast',
  '-crf', '20',
  '-c:a', 'aac',
  '-b:a', '192k',
];

momentsData.forEach((p) => {
  const out = join(OUT, p.clipFile);
  console.log(`\n✂️ Cutting #${p.rank} -> ${out} (${p.clipStart} to ${p.clipEnd}, ${p.duration}s, layout: ${LAYOUT})`);

  if (VIDEO) {
    run('ffmpeg', [
      '-y',
      '-loglevel', 'error',
      '-ss', String(p.start),
      '-t', String(p.duration),
      '-i', VIDEO,
      ...getFilterArgs(),
      ...CODEC_OPTS,
      out,
    ]);
  } else {
    const piece = join(OUT, `piece_${p.rank}.mp4`);
    console.log(`  Downloading stream segment with ${TDL}...`);
    run(TDL, [
      'videodownload',
      '--id', VOD,
      '-b', p.clipStart,
      '-e', p.clipEnd,
      '-o', piece,
    ]);
    console.log(`  Rendering 9:16 vertical 1080x1920 (${LAYOUT}) with ffmpeg...`);
    run('ffmpeg', [
      '-y',
      '-loglevel', 'error',
      '-i', piece,
      ...getFilterArgs(),
      ...CODEC_OPTS,
      out,
    ]);
    rmSync(piece, { force: true });
  }
});

console.log(`\n✨ Done! ${momentsData.length} vertical clips generated in ./${OUT}/`);
console.log('Drop them into CapCut, OpenShorts, or use caption_tool.py to add captions.');
