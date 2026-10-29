"""Copy Mythree's private settings into Modal's secret store ("mythree-secrets").

Run it yourself, from the project folder:
    .venv/bin/python deploy/make_modal_secret.py

It reads the keys from .env, the voice IDs from private/voices.json and the
phrase book from private/phrasebook.md, asks for a passcode (hidden as you
type), and sends them all to Modal. It prints only the names, never a value.
"""

import getpass
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ["MODEL_API_KEY", "BASETEN_API_KEY", "SARVAM_API_KEY", "ELEVENLABS_API_KEY"]

env = {}
for line in (ROOT / ".env").read_text().splitlines():
    name, _, value = line.partition("=")
    env[name.strip()] = value.strip()

settings = {name: env[name] for name in KEYS if env.get(name)}
missing = [name for name in KEYS if name not in settings]
if missing:
    print("Not found in .env (Mythree will use its backups):", ", ".join(missing))

settings["MYTHREE_VOICES"] = (ROOT / "private" / "voices.json").read_text()
settings["MYTHREE_PHRASEBOOK"] = (ROOT / "private" / "phrasebook.md").read_text()

while True:
    passcode = getpass.getpass("Choose a passcode for Mythree (hidden as you type): ").strip()
    if len(passcode) < 6:
        print("Please use at least 6 characters.")
    elif getpass.getpass("Type it again: ").strip() != passcode:
        print("They didn't match. Let's try again.")
    else:
        break
settings["MYTHREE_PASSCODE"] = passcode

# A private temporary file, deleted right after Modal reads it.
fd, path = tempfile.mkstemp(suffix=".json")
try:
    with os.fdopen(fd, "w") as f:
        json.dump(settings, f)
    done = subprocess.run([str(ROOT / ".venv" / "bin" / "modal"), "secret", "create",
                           "mythree-secrets", "--from-json", path, "--force"],
                          capture_output=True, text=True)
finally:
    os.remove(path)

if done.returncode != 0:
    print("Modal couldn't save the secret:", done.stderr.strip()[-300:])
    sys.exit(1)
print("Saved in Modal as mythree-secrets:", ", ".join(sorted(settings)))
