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


def transcribe(wav: bytes) -> str:
    """Ears: send one spoken sentence (a plain WAV file) and get the words back."""
    request = {"model": EARS_MODEL, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
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
            return _ask(OPEN_BRAIN_BASE, f"Api-Key {open_key}", OPEN_BRAIN_MODEL, messages)
        except MetaError:
            pass  # fall through to the backup brain
    return _ask(BASE, f"Bearer {api_key()}", BRAIN_MODEL, messages)


def _ask(base: str, auth: str, model: str, messages: list[dict]) -> str:
    try:
        reply = httpx.post(
            f"{base}/chat/completions",
            # Muse Spark thinks before answering; "minimal" gave the same translations
            # in about 1–2 s instead of 3–6 s (tested 28 Oct).
            json={"model": model, "messages": messages, "reasoning_effort": "minimal"},
            headers={"Authorization": auth, "Accept": "application/json"},
            timeout=20,
        )
    except httpx.HTTPError as e:
        raise MetaError(f"Could not reach {base}: {e.__class__.__name__}") from e
    if reply.status_code != 200:
        raise MetaError(f"{base} replied {reply.status_code}")
    return reply.json()["choices"][0]["message"]["content"].strip()
