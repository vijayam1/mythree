"""Private settings: keys and voice IDs.

Keys come from the private .env file (or the environment). They are never
sent to the web page and never go online.
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
VOICES_FILE = ROOT / "private" / "voices.json"


def secret(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip()
    return None


def voice_id(person: str) -> str | None:
    """The cloned voice of person "a" or "b" (made with each person's consent)."""
    if not VOICES_FILE.exists():
        return None
    return json.loads(VOICES_FILE.read_text()).get(person)
