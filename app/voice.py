"""Mythree's voice: speaks a translation in the speaker's own (cloned) voice, using Sarvam.

Each person's words, translated, are spoken in that person's own voice:
a grandfather's Telugu becomes English in his voice, his grandson's English
becomes Telugu in the grandson's voice. Each voice is cloned only with that
person's consent.

The sound is streamed: the first words play while the rest is still being
made (first sound after about 2.5 s instead of 4.7 s, tested 28 Oct).
"""

from collections.abc import Iterator

import httpx

from app.settings import secret, voice_id

API = "https://api.sarvam.ai"
LANGUAGE_CODES = {"te": "te-IN", "en": "en-IN"}
PACE = "0.9"  # Vijaya: the default felt too fast; 0.9 is about 15% slower (tested 28 Oct)


class VoiceError(Exception):
    """The voice service could not speak (no key, no voice, network, or an error reply)."""


def speak(text: str, lang: str, person: str) -> Iterator[bytes]:
    """Start saying the text in language lang ("te" or "en"), in person "a" or "b"'s voice.

    Returns the MP3 sound piece by piece. Problems found before the first
    piece raise VoiceError, so the page can switch to the standard voice.
    """
    key, voice = secret("SARVAM_API_KEY"), voice_id(person)
    if not key or not voice:
        raise VoiceError("No Sarvam key or cloned voice yet")
    client = httpx.Client(timeout=30)
    request = client.build_request(
        "POST", f"{API}/voices/clone/stream",
        headers={"api-subscription-key": key},
        data={"voice_id": voice, "text": text, "language_code": LANGUAGE_CODES[lang],
              "output_audio_codec": "mp3", "pace": PACE},
    )
    try:
        reply = client.send(request, stream=True)
    except httpx.HTTPError as e:
        client.close()
        raise VoiceError(f"Could not reach Sarvam: {e.__class__.__name__}") from e
    if reply.status_code != 200:
        reply.close()
        client.close()
        raise VoiceError(f"Sarvam replied {reply.status_code}")

    def pieces():
        try:
            yield from reply.iter_bytes()
        finally:
            reply.close()
            client.close()
    return pieces()
