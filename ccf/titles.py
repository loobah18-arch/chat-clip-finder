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


def _tc(text):
    """Title Case without breaking apostrophes (Couldn't, not Couldn'T)."""
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.split())


def make(rank, kind, phrase, streamer="", game="none", fixed_hook="", seed=None):
    rnd = random.Random(seed if seed is not None else rank)
    hook = fixed_hook or rnd.choice(HOOKS.get(kind) or HOOKS[None])
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
    credit_line = f"Credit: {who} (go follow!)" if who else ""
    description = "\n".join(x for x in [title, credit_line, "", " ".join(tags)] if x is not None)
    return {"hook": hook, "title": title, "description": description,
            "tags": [t.lstrip("#") for t in tags], "credit": f"@{who}" if who else ""}
