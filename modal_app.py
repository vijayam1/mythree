"""Mythree on Modal: the live link for testers and judges.

Keys, the passcode, voice IDs and the phrase book come from the Modal secret
"mythree-secrets" as environment variables, never from files in the code.

Deploy (from the project folder):  .venv/bin/modal deploy modal_app.py
"""

import modal

image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir("static", "/root/static")
    .add_local_python_source("app")
)

app = modal.App("mythree", image=image)


@app.function(
    secrets=[modal.Secret.from_name("mythree-secrets")],
    scaledown_window=600,   # stay awake 10 minutes after the last visitor, then sleep (no cost while asleep)
    max_containers=1,       # one small server is plenty, and keeps the cost low
)
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def web():
    from app import rooms
    from app.main import app as mythree

    # A copy of each call, so calls survive an update or restart (forgotten after a few hours).
    rooms.store = modal.Dict.from_name("mythree-calls", create_if_missing=True)
    # How many people tried the Try page, per day (numbers only).
    import app.main
    app.main.stats_store = modal.Dict.from_name("mythree-try-stats", create_if_missing=True)
    return mythree
