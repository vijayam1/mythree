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
    key, voice = secret("ELEVENLABS_API_KEY"), voice_id(person, "elevenlabs")
    if not key or not voice:
        raise VoiceError("No ElevenLabs key or cloned voice yet")
    return _stream("ElevenLabs", "POST", f"{ELEVENLABS}/text-to-speech/{voice}/stream",
                   headers={"xi-api-key": key}, params={"output_format": "mp3_44100_128"},
                   json={"text": text, "model_id": ELEVENLABS_MODEL, "language_code": lang})


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
