"""
Update Mixcloud cloudcast descriptions in the Pale Transmissions style.
Usage: python scripts/update_descriptions.py
"""
import re, sys, time, requests
from pathlib import Path

TOKEN_FILE = Path.home() / ".mixcloud_token"

# Map cloudcast key → (name, description with tracklist)
SETS = {
    "/louis-lapat/sorry-i-am-late-solomun-style-mix-1/": {
        "name": "Sorry I Am Late — Solomun Style Mix",
        "desc": """\
SORRY I AM LATE
DJBOT — SOLOMUN ENGINE

Solomun-orbit catalog — Butch, Adana Twins, Patrice Bäumel, Âme, Adriatique, Tube & Berger. 122-124 BPM, just under an hour. Rampa's The Touch is the peak at 53:44.

Kollektiv Turmstrasse – Sorry I Am Late – 00:00:00
Butch – Lale – 00:03:00
Solomun – Somebody's Story – 00:06:09
Adana Twins – Everyday – 00:09:17
Adana Twins – Strange – 00:12:47
Johannes Brecht – Synesthetic – 00:15:45
Ame – Fiori (Dixon Beat Edit) – 00:19:16
Patrice Baumel – Serpent – 00:22:44
Innellea – Forced To Bend – 00:26:14
Julian Wassermann – Sirius – 00:29:06
Nicone & Sascha Braemer – Rej Senhor – 00:32:20
Guy Gerber & Dixon – No Distance – 00:35:24
Solomun – Amanacer – 00:38:23
Tube & Berger – Imprint Of Pleasure – 00:41:17
Rampa – 2000 – 00:44:21
Adriatique – Ray – 00:47:27
Tale Of Us & Mind Against – Astral – 00:50:32
Rampa – The Touch – 00:53:44
Ame – Rej – 00:56:44
Stimming – Die Liebe – 00:59:45""",
    },
    "/louis-lapat/the-hours-before-light-melodic-house-mix-1/": {
        "name": "The Hours Before Light — Melodic House Mix",
        "desc": """\
THE HOURS BEFORE LIGHT
DJBOT — MELODIC HOUSE MIX

Ten records that all sound like 4am but in different rooms. Solomun into Yotto into Ben Böhmer — that early sequence is doing something specific, BPM climbing track by track without you noticing.

Jon Hopkins' Open Eye Signal is the outlier and it works. Stephan Bodzin's Boavista is the anchor. ARTBAT closes it out with Horizon.

Solomun – Kreatur der Nacht – 00:00:00
Yotto – Just Another Piano Track – 00:01:16
Ben Bohmer – Breathing – 00:03:04
Anyma & Chris Avantgarde – Consciousness – 00:05:25
Jon Hopkins – Open Eye Signal – 00:08:06
Stephan Bodzin – Boavista – 00:11:34
WhoMadeWho & Adriatique – Miracle – 00:15:02
ARTBAT – Breathe In – 00:16:39
ARTBAT – Horizon – 00:20:02
Monolink – Burning Sun – 00:23:30""",
    },
    "/louis-lapat/pale-transmissions-afterlife-style-mix-1/": {
        "name": "Pale Transmissions — Afterlife Style Mix",
        "desc": """\
PALE TRANSMISSIONS
DJBOT — AFTERLIFE ENGINE

Been deep in the Afterlife catalog lately — Massano, Innellea, Agents of Time, ARTBAT, Patrice Bäumel. These records take their time, and the build pays off.

Starts with Innellea's Golden Fort: dark, structural, melodic. BPM locked at 122 but the mood shifts track by track. Agents of Time pushes it into driving territory at the midpoint. Patrice Bäumel's Receiver is the peak at 22:00. Lane 8 and Massano bring it back. Thodoris closes it.

Innellea – The Golden Fort – 00:00:00
Adriatique & Emmit Fenn – Closer – 00:03:00
Yotto – Radiate – 00:05:02
Monolink – Father Ocean – 00:08:29
Agents of Time – The Mirage – 00:11:28
Innellea – Distorted Youth – 00:14:57
ARTBAT & Fred Lenix – Dreamcatcher – 00:16:59
Kevin de Vries & Lehar – Tokyo Nights – 00:18:59
Patrice Baumel – Receiver – 00:22:00
Lane 8 feat. POLICA – Brightest Lights – 00:25:28
Massano – The Feeling – 00:28:54
Thodoris Triantafillou – The Sun the Stars – 00:32:04""",
    },
    "/louis-lapat/the-endless-night-afterlife-style-mix/": {
        "name": "The Endless Night — Afterlife Style Mix",
        "desc": """\
THE ENDLESS NIGHT
DJBOT — AFTERLIFE ENGINE

Staying inside the Afterlife world — Tale Of Us, ARTBAT, Mind Against, Massano, Kevin de Vries, Anyma. Different producers but they share a sound: late-night, melodic, patient builds.

Opens with Nova and barely comes up for air. ARTBAT runs a lot of the middle section — Element, Galaxy, Breathe In. Massano's Renegade Master and The Feeling hold the energy before Anyma's Consciousness closes it out around 38 minutes.

Tale Of Us – Nova – 00:00:00
Tale Of Us & Ovend – Red Sky – 00:03:00
ARTBAT – Element – 00:06:28
Mind Against & Sideral – Colossal (Extended) – 00:09:56
ARTBAT – Galaxy (Extended Mix) – 00:13:24
Massano – System – 00:16:49
ARTBAT & Another Life – Breathe In – 00:20:20
Kevin de Vries & Lehar – Tokyo Nights – 00:23:48
Massano – Renegade Master (Extended Mix) – 00:26:47
Massano – The Feeling – 00:29:31
Anyma – Consciousness – 00:32:43""",
    },
    "/louis-lapat/herzblut-machine-stephan-bodzin-style-mix/": {
        "name": "Herzblut Machine — Stephan Bodzin Style Mix",
        "desc": """\
HERZBLUT MACHINE
DJBOT — BODZIN ENGINE

Stephan Bodzin catalog plus the Massano collab at the front. All analog, all built around that modular sequencer sound. 124-127 BPM, nowhere to hide.

Healing opens it and Powers of Ten is where it locks in hardest. Sungam and Liebe Ist are the descent. Eight tracks, about 27 minutes — shorter than the others but nothing's wasted.

Massano, Stephan Bodzin & Jem Cooke – Healing – 00:00:00
Massano & Stephan Bodzin – Falcon – 00:03:00
Stephan Bodzin – Strand – 00:06:30
Stephan Bodzin – Zulu – 00:09:58
Stephan Bodzin – Powers of Ten – 00:13:27
Stephan Bodzin – Singularity – 00:16:55
Stephan Bodzin – Sungam – 00:20:22
Stephan Bodzin – Liebe Ist – 00:23:38""",
    },
    "/louis-lapat/isles-rising-bicep-style-mix/": {
        "name": "Isles Rising — Bicep Style Mix",
        "desc": """\
ISLES RISING
DJBOT — BICEP ENGINE

Just Bicep. Six tracks, about 19 minutes — the shortest set in the catalog. Beat detection struggled with a couple of their records (some YouTube versions run faster than advertised), so this is the six that actually worked cleanly.

Just opens it at 122. Ayr and Meli build into Orca. Saku with Clara La San is where the BPM jumps — it's a different feel. Lido closes it out.

Bicep – Just (Original Mix) – 00:00:00
Bicep – Ayr – 00:03:00
Bicep – Meli (II) – 00:05:38
Bicep – Orca (Original Mix) – 00:09:06
Bicep feat. Clara La San – Saku (Extended Mix) – 00:12:33
Bicep – Lido (Telematik Edit) – 00:15:59""",
    },
    "/louis-lapat/ellum-architecture-maceo-plex-style-mix/": {
        "name": "Ellum Architecture — Maceo Plex Style Mix",
        "desc": """\
ELLUM ARCHITECTURE
DJBOT — MACEO PLEX ENGINE

Eight Maceo Plex records from across his catalog. 126-128 BPM, dark, driving. Ellum label sound throughout.

Sleazy E sets the tone. Polygon Pulse and Solitary Daze are the best-sounding transitions in the set. Conjure Balearia and Vibe Your Love close it — later catalog, more groove.

Maceo Plex – Sleazy E (Life Index) – 00:00:00
Maceo Plex – Falling (Original Mix) – 00:03:00
Maceo Plex – Polygon Pulse – 00:06:28
Maceo Plex & Gabriel Ananda – Solitary Daze – 00:09:55
Maceo Plex – Solar Detroit (Original Mix) – 00:13:23
Maceo Plex & Odd Parents – Learn To Fly – 00:16:51
Maceo Plex – Conjure Balearia – 00:20:19
Maceo Plex – Vibe Your Love – 00:23:50""",
    },
    "/louis-lapat/beyond-horizons-ben-b%C3%B6hmer-style-mix/": {
        "name": "Beyond Horizons — Ben Böhmer Style Mix",
        "desc": """\
BEYOND HORIZONS
DJBOT — BEN BÖHMER ENGINE

Ben Böhmer catalog plus a couple records that live in the same orbit — Stephan Bodzin's LLL remix and Jan Blomqvist's Space In Between, both pulled from Ben Böhmer mixes. 122-125 BPM, emotional, melodic.

Ground Control opens it. Cappadocia is the anchor track. Black Hole into LLL is the peak. Space In Between closes it out.

Ben Bohmer – Ground Control – 00:00:00
Ben Bohmer, Nils Hoffmann & Malou – Breathing – 00:03:00
Ben Bohmer – Cappadocia – 00:06:17
Ben Bohmer – Purple Line – 00:09:26
Ben Bohmer & Monolink – Black Hole – 00:12:56
Stephan Bodzin – LLL (Ben Bohmer Remix) – 00:15:47
Jan Blomqvist – Space In Between (Ben Bohmer Remix) – 00:19:14""",
    },
}


EDIT_URL = "https://api.mixcloud.com/upload{key}edit/"


def _post_update(token, key, meta) -> bool:
    desc = meta["desc"]
    if len(desc) > 1000:
        print(f"  WARNING: description is {len(desc)} chars — truncating to 1000")
        desc = desc[:997] + "..."

    url = EDIT_URL.format(key=key)
    for attempt in range(4):
        r = requests.post(
            f"{url}?access_token={token}",
            data={"name": meta["name"], "description": desc},
            timeout=30,
        )
        if r.status_code == 200 and r.json().get("result", {}).get("success"):
            return True
        body = r.json()
        if r.status_code == 403 and body.get("error", {}).get("type") == "RateLimitException":
            wait = body["error"].get("retry_after", 60) + 5
            print(f"  rate-limited — sleeping {wait}s (attempt {attempt+1}/4)")
            time.sleep(wait)
        else:
            print(f"  ✗ {r.status_code}  {r.text[:200]}")
            return False
    return False


def main():
    token = TOKEN_FILE.read_text().strip()

    for key, meta in SETS.items():
        print(f"\n  Updating: {key}  ({len(meta['desc'])} chars)")
        ok = _post_update(token, key, meta)
        print(f"  {'✓ updated' if ok else '✗ FAILED'}")
        time.sleep(3)   # small gap between requests


if __name__ == "__main__":
    main()
