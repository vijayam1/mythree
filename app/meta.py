"""Talking to Meta's models.

The key is read from the private .env file (or the environment) and is
never sent to the web page.
"""

import json

import httpx

from app.settings import secret

BASE = "https://api.meta.ai/v1"
EARS_MODEL = "muse-voice-transcribe-1.0"
BRAIN_MODEL = "muse-spark-1.3"  # Standard model, not "contributor": family talk stays private
# Main brain: Meta's open-weights model, run by Baseten (hackathon inference partner).
OPEN_BRAIN_BASE = "https://inference.baseten.co/v1"
OPEN_BRAIN_MODEL = "meta-models/muse-spark-open-1026"  # the hackathon's model; the credit key only works with it


class MetaError(Exception):
    """Meta's service could not do the job (no key, network, or an error reply)."""


def api_key():
    key = secret("MODEL_API_KEY")
    if not key:
        raise MetaError("No Meta key found in .env")
    return key


def transcribe(wav: bytes, languages: list[str] | None = None) -> str:
    """Ears: send one spoken sentence (a plain WAV file) and get the words back.

    `languages` (["Telugu"], or ["Telugu", "English"]) tells the ears what to expect; without it
    they guess, and sometimes write Telugu in Gujarati, Urdu or English letters."""
    request = {"model": EARS_MODEL, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
    if languages:
        request["languageBias"] = languages
    files = {
        "request": (None, json.dumps(request), "application/json"),
        "audio": ("sentence.wav", wav, "audio/wav"),
    }
    try:
        reply = httpx.post(
            f"{BASE}/asr/transcribe",
            files=files,
            headers={"Authorization": f"Bearer {api_key()}", "Accept": "application/json"},
            timeout=30,
        )
    except httpx.HTTPError as e:
        raise MetaError(f"Could not reach Meta: {e.__class__.__name__}") from e
    if reply.status_code != 200:
        raise MetaError(f"Meta replied {reply.status_code}")
    return reply.json().get("transcript", "").strip()


def chat(messages: list[dict]) -> str:
    """Brain: Meta's open-weights Muse Spark Open (on Baseten) first; Meta's own API if that fails."""
    open_key = secret("BASETEN_API_KEY")
    if open_key:
        try:
            # Muse Spark Open "thinks" before answering, even at the lowest setting (400–650
            # thinking words). Translation doesn't need it: with thinking off, the same
            # translations come in a steady ~1.6 s instead of 1.3–2.7 s (tested 29 Oct).
            return _ask(OPEN_BRAIN_BASE, f"Api-Key {open_key}", OPEN_BRAIN_MODEL, messages,
                        {"chat_template_kwargs": {"enable_thinking": False}})
        except MetaError:
            pass  # fall through to the backup brain
    # Meta's own API: "minimal" thinking gave the same translations in 1–3 s instead of 3–6 s (28 Oct).
    return _ask(BASE, f"Bearer {api_key()}", BRAIN_MODEL, messages, {"reasoning_effort": "minimal"})


def _ask(base: str, auth: str, model: str, messages: list[dict], thinking: dict) -> str:
    try:
        reply = httpx.post(
            f"{base}/chat/completions",
            json={"model": model, "messages": messages, **thinking},
            headers={"Authorization": auth, "Accept": "application/json"},
            timeout=20,
        )
    except httpx.HTTPError as e:
        raise MetaError(f"Could not reach {base}: {e.__class__.__name__}") from e
    if reply.status_code != 200:
        raise MetaError(f"{base} replied {reply.status_code}")
    return reply.json()["choices"][0]["message"]["content"].strip()
