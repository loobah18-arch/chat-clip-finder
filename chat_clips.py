#!/usr/bin/env python3
"""
chat-clips: let chat (or the audio) find the best moments of a stream, then turn them into
ready-to-post vertical Shorts / Reels / TikToks: word-by-word captions, hook title, facecam stack.

Usage:
    python3 chat_clips.py <chat.json | Twitch URL | YouTube URL> [options]

Sources:
    chat.json                 TwitchDownloader chat file, or a yt-dlp *.live_chat.json (YouTube)
    --url <link>              Twitch VOD or YouTube video / past live stream: chat and clips are
                              downloaded automatically (YouTube uses your cookies file)
    --vod <ID/URL>            (old name for --url, Twitch)
    --video <file.mp4>        Cut from a local video you already have
    --no-chat                 Find moments from loudness spikes instead (gameplay videos, trailers)
    --cookies <file>          YouTube cookies (default: youtube_cookies.txt / cookies.txt here)
    --proxy <url>             Proxy for YouTube (or $YOUTUBE_PROXY)

Finding moments:
    --game <gta6|none>        Game-tuned reactions & titles (default: gta6)
    --emotes                  Count only reaction messages (LMAO, KEKW, 💀, WTF, WASTED...), weighted
    --min-score <n>           Minimum spike multiplier (default 1.0)
    --top <n>                 Number of clips (default 5)
    --before / --after <s>    Seconds before / after the spike (default 20 / 10)
    --gap <s>                 Minimum seconds between clips (default 90)
    --bucket <s>              Counting window (default 10)
    --skip-start / --skip-end <s>  Ignore "Starting soon" / ending screen (default 120 / 60)

Making the Short:
    --layout <auto|stack|gameplay|blur|crop>   (default auto: stack if a webcam is found, else gameplay)
    --cam <auto|top-left|top-right|bottom-left|bottom-right>   Webcam position (default auto-detect)
    --captions <on|off>       Word-by-word captions with Whisper (default on)
    --whisper-model <name>    tiny / base / small / medium (default small)
    --lang <code>             Spoken language, e.g. en, hi (default: auto-detect)
    --hook <text>             Fixed hook title for every clip (default: picked per clip from chat)
    --credit <name>           Streamer name shown on screen and in the description
    --out <dir>               Output folder (default clips)
    --tdl <path>              TwitchDownloaderCLI path
    --dry-run                 Only find moments and write moments.json
"""

import argparse
import json
import math
import sys
from pathlib import Path

from ccf import chat as chatmod
from ccf import sources, titles
from ccf.timefmt import hms


def format_hms(seconds):
    return hms(seconds)


def calculate_median(arr):
    if not arr:
        return 0
    s = sorted(arr)
    return s[len(s) // 2]


def parse_args(argv=None):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("source", nargs="?")
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("--url"); p.add_argument("--vod"); p.add_argument("--video")
    p.add_argument("--no-chat", action="store_true")
    p.add_argument("--cookies"); p.add_argument("--proxy")
    p.add_argument("--game", default="gta6")
    p.add_argument("--emotes", "--filter-emotes", action="store_true")
    p.add_argument("--min-score", type=float, default=1.0)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--before", type=int, default=20)
    p.add_argument("--after", type=int, default=10)
    p.add_argument("--gap", type=int, default=90)
    p.add_argument("--bucket", type=int, default=10)
    p.add_argument("--skip-start", type=int, default=120)
    p.add_argument("--skip-end", type=int, default=60)
    p.add_argument("--layout", default="stack", choices=["auto", "stack", "gameplay", "blur", "crop"])
    p.add_argument("--require-cam", action="store_true", default=True, help="skip candidate if no webcam detected")
    p.add_argument("--no-require-cam", dest="require_cam", action="store_false")
    p.add_argument("--cam", default="auto", choices=["auto", "top-left", "top-right", "bottom-left", "bottom-right"])
    p.add_argument("--captions", default="on", choices=["on", "off"])
    p.add_argument("--whisper-model", default="small")
    p.add_argument("--lang")
    p.add_argument("--hook", default="")
    p.add_argument("--credit", default="")
    p.add_argument("--out", default="clips")
    p.add_argument("--tdl")
    p.add_argument("--dry-run", action="store_true")
    a, unknown = p.parse_known_args(argv)
    if a.help or (not a.source and not a.url and not a.vod and not (a.no_chat and a.video)):
        print(__doc__)
        sys.exit(0 if a.help else 1)
    if unknown:
        print(f"Error: unknown option(s): {' '.join(unknown)}  (see --help)", file=sys.stderr)
        sys.exit(2)
    a.url = a.url or a.vod
    if a.source and sources.kind_of(a.source) in ("youtube", "twitch") and not Path(a.source).exists():
        a.url, a.source = a.url or a.source, None
    return a


def resolve_tdl(custom_path=None):
    import os
    if custom_path:
        return custom_path
    for p in ("./TwitchDownloaderCLI", "./TwitchDownloaderCLI.exe"):
        if os.path.exists(p):
            return p
    return "TwitchDownloaderCLI.exe" if sys.platform == "win32" else "TwitchDownloaderCLI"


def bucket_counts(a, messages, length):
    nb = math.ceil(length / a.bucket) + 1
    counts = [0] * nb
    use_weights = a.emotes
    for m in messages:
        i = int(m["t"] // a.bucket)
        if i >= nb:
            continue
        if use_weights:
            w, _ = chatmod.classify(m["text"], a.game)
            counts[i] += w
        else:
            counts[i] += 1
    if use_weights:
        counts = [round(c, 2) for c in counts]
    return counts


def find_peaks(a, counts):
    nb = len(counts)
    around = max(1, round(300 / a.bucket))
    scores = []
    for i in range(nb):
        base = calculate_median(counts[max(0, i - around): min(nb, i + around + 1)])
        scores.append(counts[i] / (base + 1.0))
    first_ok = math.ceil(a.skip_start / a.bucket) if nb * a.bucket > (a.skip_start + a.skip_end) * 3 else 0
    last_ok = nb - 1 - (math.ceil(a.skip_end / a.bucket) if first_ok else 0)
    peaks = []
    for idx in sorted(range(nb), key=lambda i: scores[i], reverse=True):
        if len(peaks) >= a.top:
            break
        if counts[idx] < 5 or scores[idx] < a.min_score or not (first_ok <= idx <= last_ok):
            continue
        t = idx * a.bucket
        if any(abs(p["t"] - t) < a.gap for p in peaks):
            continue
        msgs = counts[idx]
        peaks.append({"t": t, "msgs": int(msgs) if float(msgs).is_integer() else msgs, "score": round(scores[idx], 1)})
    peaks.sort(key=lambda p: p["t"])
    return peaks


def ascii_graph(counts, total_length):
    bars = " ▁▂▃▄▅▆▇█"
    per = max(1, math.ceil(len(counts) / 60))
    cols = [max(counts[k * per:(k + 1) * per] or [0]) for k in range(math.ceil(len(counts) / per))]
    top = max(cols) if cols and max(cols) > 0 else 1
    g = "".join(bars[min(8, round(c / top * 8))] for c in cols)
    end = hms(total_length)
    return f"{g}\n0:00:00{' ' * max(1, len(cols) - len(end) - 7)}{end}"


def main(argv=None):
    a = parse_args(argv)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tdl = resolve_tdl(a.tdl)
    info = {"title": "", "channel": "", "duration": 0.0}

    # 1. Signal: chat (file or downloaded) or loudness
    messages, length, chat_file = [], 0.0, None
    if a.source:
        chat_file = Path(a.source)
        if not chat_file.exists():
            print(f"Error: Chat file not found: {chat_file}", file=sys.stderr)
            sys.exit(1)
    elif a.url and not a.no_chat:
        print(f"💬 Downloading chat replay for {a.url} ...", flush=True)
        chat_file = sources.fetch_chat(a.url, out_dir, a.cookies, a.proxy, tdl)
        if not chat_file:
            print("   ! This video has no chat replay. Falling back to loudness spikes (--no-chat).", flush=True)
            a.no_chat = True

    if chat_file and not a.no_chat:
        try:
            messages, length = chatmod.load_chat(chat_file)
        except Exception as e:
            print(f"Error reading chat from {chat_file}: {e}", file=sys.stderr)
            sys.exit(1)
        if a.emotes:
            messages_used = [m for m in messages if chatmod.classify(m["text"], a.game)[0] > 0]
        else:
            messages_used = messages
        if not messages_used:
            print("Error: No messages matched reaction emotes/keywords. Try without --emotes." if a.emotes
                  else "Error: No chat messages found. Is this a TwitchDownloader / YouTube live-chat file?",
                  file=sys.stderr)
            sys.exit(1)
        counts = bucket_counts(a, messages_used, length)
        label = f"{len(messages_used)} chat messages" + (" (reaction filter active)" if a.emotes else "")
    else:
        from ccf import audio
        src = a.video or a.url
        if not src:
            print("Error: --no-chat needs --video or --url", file=sys.stderr)
            sys.exit(1)
        print("🔊 Finding moments from loudness spikes ...", flush=True)
        aud = sources.download_audio(src, out_dir / "audio", a.cookies, a.proxy)
        counts = audio.loudness_buckets(aud, a.bucket)
        length = len(counts) * a.bucket
        label = "audio loudness (no chat)"

    peaks = find_peaks(a, counts)
    print(f"\n💬 {label}, ⏱ {hms(length)} of stream\n")
    print(ascii_graph(counts, length) + "\n")
    if not peaks:
        print(f"No moments reached the minimum multiplier threshold of {a.min_score}x. Try lowering --min-score.")
        sys.exit(0)

    # 2. Name things
    streamer = a.credit or (chatmod.streamer_name(chat_file) if chat_file else "")
    if not streamer and a.url and not a.dry_run:
        info = sources.video_info(a.url, a.cookies, a.proxy)
        streamer = info.get("channel", "")

    print("Top Moments:")
    moments = []
    for i, p in enumerate(peaks):
        start = max(0, p["t"] - a.before)
        end = p["t"] + a.after
        kind, phrase = chatmod.top_reaction(messages, p["t"] - 5, p["t"] + a.bucket + 10, a.game) if messages else (None, "")
        meta = titles.make(i + 1, kind, phrase, streamer, a.game, a.hook)
        clip_file = f"clip_{i + 1:02d}.mp4"
        print(f"#{i + 1}  {hms(p['t'])}  {p['msgs']} msgs in {a.bucket}s  ({p['score']}x normal)  "
              f"-> clip {hms(start)} to {hms(end)}" + (f"  [{kind}]" if kind else ""))
        moments.append({"rank": i + 1, "t": p["t"], "timestamp": hms(p["t"]), "msgs": p["msgs"],
                        "score": p["score"], "start": start, "end": end, "clipStart": hms(start),
                        "clipEnd": hms(end), "duration": end - start, "clipFile": clip_file,
                        "reaction": kind, "chatPhrase": phrase, **meta})

    with open(out_dir / "moments.json", "w", encoding="utf-8") as f:
        json.dump(moments, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved moment data to {out_dir / 'moments.json'}.")

    if a.dry_run:
        print("Dry run requested; skipping video cutting.")
        sys.exit(0)
    if not a.url and not a.video:
        print("To cut video clips, provide --url <Twitch/YouTube link> or --video <local.mp4>")
        sys.exit(0)

    # 3. Cut + render
    from ccf import captions, render
    posts = []
    for m in moments:
        out_path = out_dir / m["clipFile"]
        piece = out_dir / f"piece_{m['rank']}.mp4"
        print(f"\n✂️  #{m['rank']} {m['clipStart']} -> {m['clipEnd']}  \"{m['hook']}\"", flush=True)
        if a.video:
            sources.download_section(a.video, m["start"], m["end"], piece)
        else:
            sources.download_section(a.url, m["start"], m["end"], piece, a.cookies, a.proxy, tdl)

        # Early check for webcam if required to avoid wasted whisper and render time
        if a.require_cam:
            src_w, src_h, _ = render.probe(piece)
            layout, cam = render.choose_layout(a.layout, a.cam, piece, src_w, src_h, require_cam=True)
            if not layout:
                print(f"   ! skipping candidate: no webcam detected (require-cam active)", flush=True)
                piece.unlink(missing_ok=True)
                sys.exit(3)

        words = captions.transcribe(piece, a.whisper_model, a.lang) if a.captions == "on" else []
        r = render.render(piece, out_path, a.layout, a.cam, words, m["hook"], m["credit"], require_cam=a.require_cam)
        piece.unlink(missing_ok=True)
        if not r or not r.get("layout"):
            print(f"   ! skipping candidate: render failed or no webcam detected", flush=True)
            sys.exit(3)
        print(f"   ✅ {out_path}  ({r['layout']} layout, {len(words)} caption words)")
        posts.append({"file": str(out_path), "title": m["title"], "description": m["description"],
                      "tags": m["tags"], "layout": r["layout"]})

    with open(out_dir / "posts.json", "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)
    print(f"\n🎉 Finished! {len(posts)} Shorts in {out_dir}/ (titles + captions in posts.json)")


if __name__ == "__main__":
    main()
