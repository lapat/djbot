"""
ElevenLabs text-to-speech for DJ Kyoko's spoken track intros — Louis's own
cloned voice, mixed in ducked under each track's quiet musical intro (see
mixer/set_builder.py's _duck_and_overlay_voice). Best-effort throughout:
this returns None (or raises, which callers catch) rather than ever being
allowed to fail the mix itself — the audio mix is the product, the DJ voice
intro is garnish, same philosophy as mixer/story.py's AI images.

djbot did not have any ElevenLabs integration before this — added fresh
here. The voice ID below is Louis's existing cloned voice on the SAME
ElevenLabs account already used and confirmed working by the (separate,
private) digitaltwin project — see digitaltwin/code/server.js,
ELEVENLABS_VOICE_ID / generateSpeech(). Reused deliberately; this file does
not create a new voice clone.
"""
import requests

ELEVENLABS_VOICE_ID = "eI9XqqmKgBT5w2huzvgD"
_TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"


def generate_track_intro_audio(text: str, elevenlabs_key: str, timeout: int = 45) -> bytes | None:
    """Synthesize one short spoken DJ intro via ElevenLabs TTS, in Louis's
    cloned voice. Returns raw mp3 bytes, or None if there's no text or the
    API returned no audio. Raises on a hard request failure (network error,
    bad key, rate limit, etc.) — callers are expected to catch this and
    treat the whole thing as best-effort (see _generate_voice_intros in
    webapp/job_runner.py), the same pattern mixer/story.py uses for its
    Replicate calls."""
    if not text or not text.strip():
        return None
    resp = requests.post(
        _TTS_URL,
        headers={"xi-api-key": elevenlabs_key, "Content-Type": "application/json"},
        json={
            "text": text.strip(),
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {
                "stability": 0.30, "similarity_boost": 0.80,
                "style": 0.25, "use_speaker_boost": False,
            },
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.content or None
