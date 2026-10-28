"""Mythree's server.

It serves the home page and Mythree's senses. The ears are here; the
brain, eyes and voice are added one milestone at a time.
"""

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import brain, meta, voice
from app.telugu import devanagari_to_telugu, language_of

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_SENTENCE_BYTES = 2_000_000  # about 60 seconds of speech at 16 kHz
LANGUAGES = {"te", "en"}
PEOPLE = {"a", "b"}  # the two people on the call

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
    text = devanagari_to_telugu(text)   # only Telugu and English for now, so Hindi letters are Telugu
    return {"text": text, "lang": language_of(text) or lang}   # trust the words over the card


Name = Field(default="", max_length=80)  # e.g. "Ravi, the grandson"


class Said(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    lang: str
    who: str = Name  # the speaker's name, as typed on the page


class Translate(Said):
    to: str
    listener: str = Name
    history: list[Said] = Field(default=[], max_length=20)  # earlier sentences, kept only by the page


@app.post("/api/translate")
async def translate(said: Translate):
    """Brain: one person's sentence, in the other person's language. Nothing is saved."""
    if said.lang not in LANGUAGES or said.to not in LANGUAGES or said.lang == said.to:
        raise HTTPException(400, "Choose two different languages")
    # If the card's language is wrong (Telugu said on an "English" card), go by the words themselves.
    spoken = language_of(said.text)
    if spoken and spoken != said.lang:
        said.lang, said.to = spoken, said.lang
    history = [h.model_dump() for h in said.history if h.lang in LANGUAGES]
    try:
        text = await run_in_threadpool(brain.translate, said.text, said.lang, said.to,
                                       said.who or "One person", said.listener or "the other person", history)
    except meta.MetaError:
        raise HTTPException(502, "Mythree couldn't translate that just now. Please say it again. "
                                 "మళ్ళీ ఒకసారి చెప్పండి.")
    return {"text": text, "lang": said.to}


class Speak(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    lang: str
    person: str  # "a" or "b": whose voice to use (the person who said the original words)


@app.post("/api/speak")
async def speak(said: Speak):
    """Voice: a translation in, its sound in the speaker's own voice out (MP3, streamed).

    If the own voice can't be made, the page falls back to the browser's standard voice.
    """
    if said.lang not in LANGUAGES or said.person not in PEOPLE:
        raise HTTPException(400, "Unknown language or person")
    try:
        sound = await run_in_threadpool(voice.speak, said.text, said.lang, said.person)
    except voice.VoiceError:
        raise HTTPException(503, "Own voice not available, using the standard voice")
    return StreamingResponse(sound, media_type="audio/mpeg")
