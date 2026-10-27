"""Mythree's server.

For now it only serves the home page. The ears, brain, eyes and voice
are added one milestone at a time.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Mythree")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def home():
    """The page the grandson opens on his laptop."""
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    """A quick "are you alive?" check for the hosting service."""
    return {"status": "ok", "name": "Mythree"}
