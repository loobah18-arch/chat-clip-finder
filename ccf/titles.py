"""Hook text, title, caption and hashtags for each clip, from what chat reacted with.

Every clip gets its own title (identical titles look like spam to YouTube) and credits the streamer."""
import random

HOOKS = {
    "laugh": ["CHAT COULDN'T STOP LAUGHING", "I CAN'T BREATHE", "THIS IS SO DUMB", "HE DIDN'T SEE IT COMING"],
    "hype": ["THIS IS INSANE", "WAIT FOR IT...", "CLEANEST PLAY EVER?", "CHAT WENT CRAZY"],
    "shock": ["WAIT... WHAT JUST HAPPENED?", "NO WAY THIS HAPPENED", "HE WAS NOT READY", "WATCH TILL THE END"],
    "game": ["13 YEARS WAS WORTH IT", "GTA 6 PHYSICS ARE UNREAL", "VICE CITY IS NOT SAFE",
             "5 STARS IN 10 SECONDS"],
    None: ["WAIT FOR IT...", "WATCH TILL THE END", "CHAT LOST IT HERE"],
}

GTA6_TAGS = ["#GTA6", "#GTAVI", "#GrandTheftAuto6", "#ViceCity", "#Shorts", "#Gaming", "#Rockstar"]
GENERIC_TAGS = ["#Shorts", "#Gaming", "#Twitch", "#Streamer", "#Clips"]

IG_COMMENTS = {
    "laugh": [
        "the way he laughed had me crying 😭😭",
        "bro's laugh took 5 business days 💀",
        "ain't no way bro started crying of laughter 😭💀",
        "bro really thought he could survive Vice City 💀",
        "his soul completely left his body 💀",
        "nah this is the funniest GTA 6 clip so far 💀",
        "he's fighting for his life not to laugh 😭",
    ],
    "shock": [
        "bro was NOT ready for GTA 6 💀",
        "Vice City police do NOT play around 😭🚔",
        "bro paused the game in real life 💀",
        "ain't no way that just happened on stream 😳",
        "Rockstar really made NPCs ruthless 💀",
        "he really thought he could escape 5 stars 💀🚔",
        "my jaw actually dropped watching this 😳",
    ],
    "hype": [
        "he is actually him bro 🐐🔥",
        "cleanest play in Vice City history 🔥",
        "bro pulled off the impossible 🤯",
        "nah that timing was actually cinematic 🔥",
        "13 years of waiting was worth this clip 🐐",
    ],
    "game": [
        "13 years of waiting for this exact moment 💀",
        "GTA 6 physics are on another level 😭",
        "Rockstar did not have to make the graphics this insane 🤯",
        "Florida in a nutshell honestly 💀",
        "bro got folded by Vice City physics 😭💀",
    ],
    None: [
        "bro was NOT ready for GTA 6 💀",
        "ain't no way that just happened 😭",
        "nah Vice City is totally out of pocket 💀",
    ]
}

IG_USERNAMES = [
    "vicecity_daily", "gta6_clips", "floridaman_live", "gaminghub",
    "rockstar_central", "clipcity", "vicecitycops", "gta6memes"
]
IG_TIMES = ["1h", "2h", "4h", "8h", "1d"]
IG_LIKES = ["18.4K", "24.8K", "38.2K", "49.6K", "61.3K", "82.5K"]


def _tc(text):
    """Title Case without breaking apostrophes (Couldn't, not Couldn'T)."""
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.split())


def make(rank, kind, phrase, streamer="", game="none", fixed_hook="", seed=None):
    rnd = random.Random(seed if seed is not None else rank)
    hook = fixed_hook or rnd.choice(HOOKS.get(kind) or HOOKS[None])
    ig_comment = {
        "text": rnd.choice(IG_COMMENTS.get(kind) or IG_COMMENTS[None]),
        "username": rnd.choice(IG_USERNAMES),
        "time": rnd.choice(IG_TIMES),
        "likes": rnd.choice(IG_LIKES),
    }
    who = streamer.strip()
    if game in ("gta6", "gta"):
        base = {
            "laugh": f"{who or 'Streamer'} can't stop laughing in GTA 6",
            "hype": f"{who or 'Streamer'} pulled this off in GTA 6",
            "shock": f"{who or 'Streamer'} was NOT ready for GTA 6",
            "game": f"GTA 6 did WHAT to {who or 'this streamer'}",
        }.get(kind, f"Best GTA 6 moment from {who or 'stream'}")
        tags = GTA6_TAGS
    else:
        base = f"{who + ': ' if who else ''}{_tc(hook)}"
        tags = GENERIC_TAGS
    if phrase and len(base) + len(phrase) < 70 and rnd.random() < 0.5:
        base = f"{base} ({_tc(phrase)})"
    emoji = {"laugh": " 💀", "hype": " 🔥", "shock": " 😳", "game": " 🚨"}.get(kind, "")
    title = (base + emoji)[:90]
    handle = who.lstrip("@") if who else ""
    credit_line = f"Credit: @{handle} (go follow!)" if handle else ""
    description = "\n".join(x for x in [title, credit_line, "", " ".join(tags)] if x is not None)
    return {"hook": hook, "title": title, "description": description,
            "tags": [t.lstrip("#") for t in tags], "credit": f"@{handle}" if handle else "",
            "ig_comment": ig_comment}
