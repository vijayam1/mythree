"""Mythree's server.

It serves the home page and Mythree's senses. The ears are here; the
brain, eyes and voice are added one milestone at a time.
"""

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app import meta
from app.telugu import devanagari_to_telugu

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_SENTENCE_BYTES = 2_000_000  # about 60 seconds of speech at 16 kHz
LANGUAGES = {"te", "en"}

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


@app.post("/api/hear")
async def hear(audio: UploadFile = File(...), lang: str = Form(...)):
    """Ears: one spoken sentence (WAV) in, the words out.

    The page sends a sentence each time the speaker pauses. Nothing is saved.
    """
    if lang not in LANGUAGES:
        raise HTTPException(400, "Unknown language")
    wav = await audio.read(MAX_SENTENCE_BYTES + 1)
    if len(wav) > MAX_SENTENCE_BYTES:
        raise HTTPException(413, "That sentence is too long. Please pause a little more often.")
    if not wav.startswith(b"RIFF"):
        raise HTTPException(400, "Not a WAV sound file")
    try:
        text = await run_in_threadpool(meta.transcribe, wav)  # don't block other requests while Meta listens
    except meta.MetaError:
        raise HTTPException(502, "Mythree couldn't hear that just now. Please say it again. "
                                 "మళ్ళీ ఒకసారి చెప్పండి.")
    if lang == "te":
        text = devanagari_to_telugu(text)
    return {"text": text, "lang": lang}
