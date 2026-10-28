"""Talking to Meta's models.

The key is read from the private .env file (or the environment) and is
never sent to the web page.
"""

import json
import os
from pathlib import Path

import httpx

BASE = "https://api.meta.ai/v1"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
EARS_MODEL = "muse-voice-transcribe-1.0"


class MetaError(Exception):
    """Meta's service could not do the job (no key, network, or an error reply)."""


def api_key():
    if os.environ.get("MODEL_API_KEY"):
        return os.environ["MODEL_API_KEY"]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "MODEL_API_KEY":
                return value.strip()
    raise MetaError("No Meta key found in .env")


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
