"""Mythree's voice: speaks a translation in the speaker's own (cloned) voice.

Each person's words, translated, are spoken in that person's own voice:
a grandfather's Telugu becomes English in his voice, his grandson's English
becomes Telugu in the grandson's voice. Each voice is cloned only with that
person's consent.

ElevenLabs speaks first (Vijaya chose it on 29 Oct: it sounds most like her,
with natural American English); Sarvam takes over automatically if
ElevenLabs can't. The sound is streamed: the first words play while the rest
is still being made.
"""

from collections.abc import Iterator

import httpx

from app.settings import secret, voice_id

ELEVENLABS = "https://api.elevenlabs.io/v1"
ELEVENLABS_MODEL = "eleven_v4_turbo"  # speaks Telugu and English, ~2 s per sentence (tested 29 Oct)
SARVAM = "https://api.sarvam.ai"
SARVAM_LANGUAGES = {"te": "te-IN", "en": "en-IN"}
SARVAM_PACE = "0.9"  # Vijaya: the default felt too fast; 0.9 is about 15% slower (tested 28 Oct)


class VoiceError(Exception):
    """No voice service could speak (no key, no voice, network, or an error reply)."""


def speak(text: str, lang: str, person: str) -> Iterator[bytes]:
    """Start saying the text in language lang ("te" or "en"), in person "a" or "b"'s voice.

    Returns the MP3 sound piece by piece. Problems found before the first
    piece raise VoiceError, so the page can switch to the standard voice.
    """
    problems = []
    for service in (_elevenlabs, _sarvam):
        try:
            return service(text, lang, person)
        except VoiceError as e:
            problems.append(str(e))
    raise VoiceError("; ".join(problems))


def _elevenlabs(text: str, lang: str, person: str) -> Iterator[bytes]:
    return speak_as(text, lang, voice_id(person, "elevenlabs"))


def speak_as(text: str, lang: str, voice: str | None) -> Iterator[bytes]:
    """Say the text in one particular ElevenLabs voice (in calls: the one the speaker recorded in the app)."""
    key = secret("ELEVENLABS_API_KEY")
    if not key or not voice:
        raise VoiceError("No ElevenLabs key or cloned voice yet")
    request = {"text": text, "model_id": ELEVENLABS_MODEL, "language_code": lang}
    if lang == "en":   # Vijaya chose sample "J" (29 Oct): her own voice, a steady American accent, a little slower.
        # Without it the English drifted into a British accent; American grandchildren prefer American English.
        request["text"] = "[American accent] " + text   # a stage direction for the model, not spoken aloud
        request["voice_settings"] = {"stability": 0.75, "similarity_boost": 0.9, "speed": 0.92}
    return _stream("ElevenLabs", "POST", f"{ELEVENLABS}/text-to-speech/{voice}/stream",
                   headers={"xi-api-key": key}, params={"output_format": "mp3_44100_128"}, json=request)


# --- Learning a voice in the app ----------------------------------------------
# Each person records about a minute of themselves talking, after ticking the
# consent box. ElevenLabs makes a copy of the voice and keeps it; Mythree keeps
# only its ID, on that person's own phone. They can delete it at any time.

def learn(name: str, wav: bytes) -> str:
    """Make a copy of someone's voice from their recording. Returns the new voice's ID."""
    key = secret("ELEVENLABS_API_KEY")
    if not key:
        raise VoiceError("No ElevenLabs key")
    try:
        reply = httpx.post(f"{ELEVENLABS}/voices/add", headers={"xi-api-key": key}, timeout=60,
                           data={"name": f"Mythree · {name}"[:100],
                                 "description": "Recorded in the Mythree app, with the speaker's consent."},
                           files={"files": ("voice.wav", wav, "audio/wav")})
    except httpx.HTTPError as e:
        raise VoiceError(f"Could not reach ElevenLabs: {e.__class__.__name__}") from e
    if reply.status_code != 200:
        raise VoiceError(f"ElevenLabs replied {reply.status_code}")
    return reply.json()["voice_id"]


TRY_NAME = "Mythree · Try visitor"


def characters_left() -> int:
    """How many ElevenLabs characters are left this month (shared by family calls and visitors)."""
    key = secret("ELEVENLABS_API_KEY")
    if not key:
        raise VoiceError("No ElevenLabs key")
    try:
        reply = httpx.get(f"{ELEVENLABS}/user/subscription", headers={"xi-api-key": key}, timeout=30)
    except httpx.HTTPError as e:
        raise VoiceError(f"Could not reach ElevenLabs: {e.__class__.__name__}") from e
    if reply.status_code != 200:
        raise VoiceError(f"ElevenLabs replied {reply.status_code}")
    plan = reply.json()
    return plan.get("character_limit", 0) - plan.get("character_count", 0)


def try_voices() -> dict[str, float]:
    """The Try page's visitor voices still kept at ElevenLabs: {voice ID: when it was made (Unix time)}."""
    key = secret("ELEVENLABS_API_KEY")
    if not key:
        raise VoiceError("No ElevenLabs key")
    try:
        reply = httpx.get(f"{ELEVENLABS}/voices", headers={"xi-api-key": key}, timeout=30)
    except httpx.HTTPError as e:
        raise VoiceError(f"Could not reach ElevenLabs: {e.__class__.__name__}") from e
    if reply.status_code != 200:
        raise VoiceError(f"ElevenLabs replied {reply.status_code}")
    return {v["voice_id"]: v.get("created_at_unix") or 0 for v in reply.json().get("voices", [])
            if v.get("name") == TRY_NAME}


def forget(voice: str):
    """Delete a voice someone recorded in the app."""
    key = secret("ELEVENLABS_API_KEY")
    if not key:
        raise VoiceError("No ElevenLabs key")
    try:
        reply = httpx.delete(f"{ELEVENLABS}/voices/{voice}", headers={"xi-api-key": key}, timeout=30)
    except httpx.HTTPError as e:
        raise VoiceError(f"Could not reach ElevenLabs: {e.__class__.__name__}") from e
    if reply.status_code not in (200, 404):   # 404: already gone
        raise VoiceError(f"ElevenLabs replied {reply.status_code}")


def _sarvam(text: str, lang: str, person: str) -> Iterator[bytes]:
    key, voice = secret("SARVAM_API_KEY"), voice_id(person, "sarvam")
    if not key or not voice:
        raise VoiceError("No Sarvam key or cloned voice yet")
    return _stream("Sarvam", "POST", f"{SARVAM}/voices/clone/stream",
                   headers={"api-subscription-key": key},
                   data={"voice_id": voice, "text": text, "language_code": SARVAM_LANGUAGES[lang],
                         "output_audio_codec": "mp3", "pace": SARVAM_PACE})


def _stream(name: str, method: str, url: str, **request) -> Iterator[bytes]:
    """Open a streamed reply; fail before the first piece if the service says no."""
    client = httpx.Client(timeout=30)
    try:
        reply = client.send(client.build_request(method, url, **request), stream=True)
    except httpx.HTTPError as e:
        client.close()
        raise VoiceError(f"Could not reach {name}: {e.__class__.__name__}") from e
    if reply.status_code != 200:
        reply.close()
        client.close()
        raise VoiceError(f"{name} replied {reply.status_code}")

    def pieces():
        try:
            yield from reply.iter_bytes()
        finally:
            reply.close()
            client.close()
    return pieces()
