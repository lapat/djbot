"""
Brand the DJBOT Mixcloud channel:
  - Rename channel to "DJBOT"
  - Generate + upload AI cover art for each mix
  - Generate + upload DJBOT profile avatar
  - Generate AI art per track section (saved locally as reference)

Uses Pollinations.ai (FLUX model, free, no API key).

Usage:
  python scripts/mixcloud_brand.py
"""

import os
import sys
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import requests

TOKEN_FILE = Path.home() / ".mixcloud_token"
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"

ART_DIR = Path("output/artwork")
ART_DIR.mkdir(parents=True, exist_ok=True)

# ── Image prompts ─────────────────────────────────────────────────────────────

CHANNEL_AVATAR = {
    "file": ART_DIR / "djbot_avatar.jpg",
    "prompt": (
        "DJBOT logo: sleek minimal robot DJ silhouette behind CDJ turntables, "
        "glowing electric blue eyes, dark matte black background, neon circuit "
        "lines, futuristic but elegant, square format, professional channel avatar"
    ),
}

MIX_COVERS = {
    "/louis-lapat/pale-transmissions-afterlife-style-mix/": {
        "name":  "Pale Transmissions — Afterlife Style Mix",
        "notes": "output/pale_transmissions/SET_NOTES.txt",
        "short_desc": (
            "DJBOT — AFTERLIFE ENGINE\n\n"
            "Some signals travel so far they arrive changed. The mirage was never an illusion — it was "
            "a destination you couldn't name until you arrived. The only possible ending is something "
            "that burns and glitters simultaneously.\n\n"
            "122–126 BPM, built on the Afterlife catalog. Harmonic arc runs 4A deep, surges at 1A with "
            "Agents of Time, peaks at 7A with Patrice Bäumel's Receiver. Bass sigmoid crossfade keeps "
            "one kick drum at a time through the dense melodic passages."
        ),
        "file": ART_DIR / "pale_transmissions_cover.jpg",
        "prompt": (
            "Album cover: dark cosmos, pale signal beams cutting through deep space, "
            "distant nebula in indigo and gold, radio telescope silhouette at the bottom, "
            "transmission lines like sound waves across a black void, "
            "Afterlife Records aesthetic, cinematic, ultra detailed, moody"
        ),
    },
    "/louis-lapat/the-hours-before-light-melodic-house-mix/": {
        "name":  "The Hours Before Light — Melodic House Mix",
        "notes": "output/hours_before_light/SET_NOTES.txt",
        "short_desc": (
            "DJ LUNOBOT\n\n"
            "The hours between 3 and 7am — when the city exhales and the mind becomes its own mythology. "
            "Something switches on slow, a warmth behind the sternum. "
            "This is not a set about ecstasy. It is about survival and the grace that follows.\n\n"
            "Harmonically descending 11A→10A→9A into the night, then climbing back toward 5A as morning "
            "breaks. Piano-led melodic house at 122–127 BPM. The peak — WhoMadeWho's Miracle — lands "
            "at 15:02 when the arc finally turns toward light."
        ),
        "file": ART_DIR / "hours_before_light_cover.jpg",
        "prompt": (
            "Album cover: 5am pre-dawn moment, single window glowing warm amber in "
            "a dark city skyline, thin orange horizon line, solitary figure silhouette, "
            "mist over rooftops, melancholic and beautiful, Chris Luno melodic house "
            "aesthetic, cinematic photography style, soft blue-grey tones with warm light"
        ),
    },
    "/louis-lapat/sorry-i-am-late-solomun-style-mix/": {
        "name":  "Sorry I Am Late — Solomun Style Mix",
        "notes": "output/sorry_i_am_late/SET_NOTES.txt",
        "short_desc": (
            "DJ SOLOMONBOT\n\n"
            "The DJ arrives late. But lateness, here, is a kind of ritual. Twenty voices in the same "
            "G-minor prayer — and you don't remember it ending. You just run out of dark.\n\n"
            "The whole set lives in G-minor, Ibiza's back-room key. 20 tracks, 122–125 BPM. "
            "Kollektiv Turmstrasse opens; Stimming closes an hour later with one word — Die Liebe. Love."
        ),
        "file": ART_DIR / "sorry_i_am_late_cover.jpg",
        "prompt": (
            "Album cover: Ibiza at golden hour, hazy sun over dark sea, abstract "
            "geometric shapes dissolving into light, underground techno aesthetic, "
            "Solomun DIYNAMIC style, deep ochre and charcoal, minimal and dramatic, "
            "cinematic wide format composition"
        ),
    },
}

# Per-track art prompts — saved locally for reference (Mixcloud doesn't support
# in-mix track images via API, but you can use these for social posts etc.)
TRACK_ART = {
    "pale_transmissions": [
        ("Innellea - The Golden Fort",
         "ancient golden fortress rising from dark fog, melodic techno, Afterlife aesthetic, moody blue-gold"),
        ("Adriatique & Emmit Fenn - Closer",
         "two figures moving toward each other through fog and neon light, intimate, Adriatique style"),
        ("Yotto - Radiate",
         "burst of warm light radiating outward from a dark horizon, golden particles, melodic electronic"),
        ("Monolink - Father Ocean",
         "vast dark ocean at night, single beam of moonlight, hypnotic, deep and still, Monolink aesthetic"),
        ("Agents of Time - The Mirage",
         "desert mirage shimmering with electronic city lights, surreal, dark sky, Afterlife Records"),
        ("Innellea - Distorted Youth",
         "youth figure distorted in fragmented mirror reflections, neon, glitch art, dark techno energy"),
        ("ARTBAT & Fred Lenix - Dreamcatcher",
         "dreamcatcher made of glowing geometric lines floating in dark space, ARTBAT aesthetic, cinematic"),
        ("Kevin de Vries & Lehar - Tokyo Nights",
         "Tokyo city at 3am, rain-slicked streets reflecting neon kanji signs, cinematic, dark electronic"),
        ("Patrice Bäumel - Receiver",
         "giant radio telescope dish pointed at sky, signal waves visible, cosmic, dramatic, peak energy"),
        ("Lane 8 feat. POLIÇA - Brightest Lights",
         "brightest lights seen through rain on a window, warm blurred bokeh, emotional, Lane 8 melodic"),
        ("Massano - The Feeling",
         "abstract emotional energy, warm golden light dissolving into dark space, Massano aesthetic"),
        ("Thodoris Triantafillou - The Sun the Stars",
         "both sun and stars visible simultaneously at twilight, cosmic and warm, melancholic closing"),
    ],
    "hours_before_light": [
        ("Solomun - Kreatur der Nacht",
         "creature of the night silhouette against moonlit Berlin skyline, dark and poetic"),
        ("Yotto - Just Another Piano Track",
         "single grand piano on an empty stage, single spotlight, melancholic, emotional"),
        ("Ben Böhmer - Breathing",
         "soft breath visible in cold pre-dawn air, close macro, ethereal, tender light"),
        ("Anyma & Chris Avantgarde - Consciousness",
         "consciousness awakening: neurons firing in dark space, golden sparks, Anyma aesthetic"),
        ("Jon Hopkins - Open Eye Signal",
         "wide open eye reflecting a cosmos, Jon Hopkins psychedelic, deep focus, layered reality"),
        ("Stephan Bodzin - Boavista",
         "Boavista Portugal at dawn, misty hills, warm light cresting, Stephan Bodzin synthesizer energy"),
        ("WhoMadeWho & Adriatique - Miracle",
         "miracle: impossible golden light breaking through dark clouds over sea, euphoric peak"),
        ("ARTBAT - Breathe In",
         "deep breath of cold morning air, frost crystals, ARTBAT dramatic wide landscape"),
        ("ARTBAT - Horizon",
         "perfect horizon line between dark sea and pale dawn sky, ARTBAT cinematic"),
        ("Monolink - Burning Sun",
         "sun burning through morning haze over a city, warm and final, Monolink aesthetic"),
    ],
}

# ── Image generation via Pollinations.ai (FLUX, free) ─────────────────────────

def generate_image(prompt: str, output_path: Path, width=1024, height=1024, seed=None) -> Path:
    if output_path.exists():
        print(f"    (cached) {output_path.name}")
        return output_path

    encoded = urllib.parse.quote(prompt)
    seed_str = f"&seed={seed}" if seed is not None else ""
    url = f"{POLLINATIONS_BASE}/{encoded}?width={width}&height={height}&model=flux&nologo=true{seed_str}"

    print(f"    Generating: {output_path.name}...")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DJBot/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if len(data) < 5000:
                raise ValueError(f"Response too small ({len(data)} bytes), likely an error page")
            output_path.write_bytes(data)
            print(f"    ✓ {output_path.name}  ({len(data)//1024} KB)")
            return output_path
        except Exception as e:
            if attempt < 2:
                print(f"    retry {attempt+1}/3: {e}")
                time.sleep(3)
            else:
                raise RuntimeError(f"Image generation failed for {output_path.name}: {e}")

# ── Mixcloud API calls ─────────────────────────────────────────────────────────

def get_token():
    if not TOKEN_FILE.exists():
        sys.exit("No Mixcloud token found — run mixcloud_upload.py first to authenticate.")
    return TOKEN_FILE.read_text().strip()


DJBOT_BIO = """\
I am DJBOT — a fully autonomous AI DJ built in Python, here to service your ears.

I don't sleep. I don't get nervous. I don't lose the beat at 3am. I just mix.

Every set I build runs through the same obsessive process:

I use BEAT DETECTION to find the exact BPM and beat grid of every track — \
sub-millisecond accuracy, no guessing.

I use PHASE ALIGNMENT to search every possible cue point, score it by beat regularity \
and phase drift, and reject anything with more than 20ms of error. Most DJs can't hear \
20ms. I can measure it.

I use a BPM RAMP — over the last 8 bars before each crossfade, I nudge the tempo across \
32 micro-steps so small you'll never notice, but your body will feel the difference.

I use an EQ CROSSFADE inspired by the Pioneer DJM-800: one kick drum at a time through \
the blend. No bass clash. Ever.

I use AMPLITUDE GATES to make sure nothing clips, cuts, or jumps at any transition.

No human touched these mixes. Pure math, measured in milliseconds.\
"""

assert len(DJBOT_BIO) <= 1000, f"Bio too long: {len(DJBOT_BIO)} chars"


def update_profile(token, name="DJBOT", avatar_path=None):
    """Update Mixcloud channel name, bio, and/or profile picture."""
    data = {"name": name, "biog": DJBOT_BIO}
    files = {}
    if avatar_path:
        files["picture"] = (avatar_path.name, open(avatar_path, "rb"), "image/jpeg")

    r = requests.post(
        f"https://api.mixcloud.com/me/?access_token={token}",
        data=data,
        files=files if files else None,
        timeout=60,
    )
    if r.status_code == 200:
        print(f"  ✓ Channel updated → name: {name}")
    else:
        print(f"  ✗ Profile update failed: {r.status_code} {r.text[:200]}")


def _compact_cue(cue_text):
    """Reformat cue lines to compact 'HH:MM Artist - Track' form."""
    lines = []
    for line in cue_text.split('\n'):
        line = line.strip()
        if not line or line.startswith('Each crossfade'):
            continue
        m = re.match(r'(\d{2}:\d{2})–\d{2}:\d{2}\s+\[\d+\] → (.+?)(?:\s+←.*)?$', line)
        if m:
            lines.append(f"{m.group(1)} {m.group(2).strip()}")
            continue
        m = re.match(r'(\d{2}:\d{2})\s+Set starts — (.+)', line)
        if m:
            lines.append(f"{m.group(1)} {m.group(2).strip()}")
            continue
        m = re.match(r'(\d{2}:\d{2})\s+Set ends', line)
        if m:
            lines.append(f"{m.group(1)} Set ends")
    return '\n'.join(lines)


def _build_description(notes_path, short_desc=None):
    """Build a <1000-char Mixcloud description: summary + cue times."""
    text = Path(notes_path).read_text()
    cue_match = re.search(r"── CUE SHEET ─+\n(.*)", text, re.DOTALL)
    cue_raw = cue_match.group(1).strip() if cue_match else ""

    # Strip annotations and header; try full format first, compact if still too long
    cue_full = re.sub(r'\s+←[^\n]*', '', cue_raw)
    cue_full = re.sub(r'^Each crossfade[^\n]+\n\n?', '', cue_full, flags=re.M).strip()

    summary = short_desc or ""
    for cue in (cue_full, _compact_cue(cue_raw)):
        desc = (summary + "\n\n" + cue) if summary else cue
        if len(desc) <= 997:
            return desc

    # Last resort: truncate
    return desc[:997]


def update_cloudcast(token, cloudcast_key, name, picture_path, notes_path, short_desc=None):
    """Update cover + description on an existing Mixcloud cloudcast in one API call."""
    data = {"key": cloudcast_key, "name": name}
    files = {}
    if notes_path and Path(notes_path).exists():
        data["description"] = _build_description(notes_path, short_desc)
    pic_fh = None
    if picture_path and Path(picture_path).exists():
        pic_fh = open(picture_path, "rb")
        files["picture"] = (Path(picture_path).name, pic_fh, "image/jpeg")
    try:
        r = requests.post(
            f"https://api.mixcloud.com/upload/?access_token={token}",
            data=data,
            files=files if files else None,
            timeout=60,
        )
    finally:
        if pic_fh:
            pic_fh.close()
    if r.status_code == 200:
        print(f"  ✓ Updated cover + description for {cloudcast_key}")
        if "description" in data:
            print(f"    ({len(data['description'])} chars description)")
    else:
        print(f"  ✗ Update failed ({cloudcast_key}): {r.status_code} {r.text[:300]}")


def generate_track_art(set_key):
    """Generate per-track images for a set, saved locally."""
    if set_key not in TRACK_ART:
        return
    tracks = TRACK_ART[set_key]
    track_dir = ART_DIR / set_key
    track_dir.mkdir(exist_ok=True)
    print(f"\n  Generating {len(tracks)} track images for {set_key}...")
    for i, (title, prompt) in enumerate(tracks, 1):
        safe_name = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:40]
        out = track_dir / f"{i:02d}_{safe_name}.jpg"
        generate_image(prompt, out, width=1024, height=1024, seed=i * 7)
        time.sleep(1)  # be polite to the free API


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = get_token()

    # 1. Generate DJBOT avatar
    print("\n── DJBOT Avatar ────────────────────────────────────")
    generate_image(CHANNEL_AVATAR["prompt"], CHANNEL_AVATAR["file"], width=800, height=800, seed=42)

    # 2. Generate mix covers
    print("\n── Mix Covers ──────────────────────────────────────")
    for key, meta in MIX_COVERS.items():
        generate_image(meta["prompt"], meta["file"], width=1024, height=1024,
                       seed=hash(key) % 9999)

    # 3. Update Mixcloud channel name + avatar
    print("\n── Updating Mixcloud profile ───────────────────────")
    update_profile(token, name="DJBOT", avatar_path=CHANNEL_AVATAR["file"])

    # 4. Push cover + description to each mix (one API call per cloudcast)
    print("\n── Updating mix covers + descriptions ──────────────")
    for key, meta in MIX_COVERS.items():
        update_cloudcast(token, key, meta["name"], meta["file"], meta["notes"],
                         short_desc=meta.get("short_desc"))

    # 5. Generate per-track art (local only)
    print("\n── Per-track artwork (saved to output/artwork/) ────")
    generate_track_art("pale_transmissions")
    generate_track_art("hours_before_light")

    print("\n══════════════════════════════════════════════════")
    print("  Done. Artwork saved to output/artwork/")
    print("  Channel: https://www.mixcloud.com/louis-lapat/")
    print("══════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
