"""Mythree's server.

It serves the home page and Mythree's senses. The ears are here; the
brain, eyes and voice are added one milestone at a time.
"""

import hmac
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import brain, meta, rooms, voice
from app.settings import secret, voice_id as family_voice
from app.telugu import devanagari_to_telugu, language_of

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_SENTENCE_BYTES = 2_000_000  # about 60 seconds of speech at 16 kHz
LANGUAGES = {"te", "en"}
PEOPLE = {"a", "b"}  # the two people on the call

app = FastAPI(title="Mythree")


@app.middleware("http")
async def always_fresh(request, call_next):
    """Browsers must always check for the newest page and code, never use an old copy."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# Online, Mythree's senses need a passcode (set as the MYTHREE_PASSCODE secret), and each
# visitor gets a fair number of requests per minute, so strangers can't use up the credits.
REQUESTS_PER_MINUTE = 40
recent: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def guard(request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    passcode = secret("MYTHREE_PASSCODE")
    if passcode and not hmac.compare_digest(request.headers.get("x-mythree-passcode", ""), passcode):
        return JSONResponse({"detail": "Passcode needed · పాస్‌కోడ్ కావాలి"}, status_code=401)
    visitor = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    times, now = recent[visitor], time.monotonic()
    while times and now - times[0] > 60:
        times.popleft()
    if len(times) >= REQUESTS_PER_MINUTE:
        return JSONResponse({"detail": "Too many requests. Please wait a minute. · ఒక నిమిషం ఆగండి."}, status_code=429)
    times.append(now)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def home():
    """The page the grandson opens on his laptop."""
    return FileResponse(STATIC / "index.html")


@app.get("/phone")
def phone():
    """Mythree as its own call: each person on their own phone, in their own language."""
    return FileResponse(STATIC / "phone.html")


@app.get("/api/hello")
def hello():
    """The page checks here first, so it can ask for the passcode before anyone talks."""
    return {"ok": True}


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


# --- Calls: two phones -------------------------------------------------------
# Each phone listens to its own person. Its sentence goes to /api/hear (words), then here:
# Mythree translates it and the other phone, which is waiting for news, speaks it.

VoiceId = Field(default="", max_length=40, pattern=r"^[A-Za-z0-9]*$")


class Person(BaseModel):
    who: str = Name   # e.g. "Ravi, the grandson"
    lang: str
    voice: str = VoiceId   # the voice this person recorded in the app ("" = none yet)


class Line(BaseModel):
    person: str
    text: str = Field(min_length=1, max_length=1000)


def room_or_404(code: str) -> rooms.Room:
    try:
        return rooms.find(code)
    except rooms.RoomError as e:
        raise HTTPException(404, str(e))


@app.post("/api/calls")
async def start_call(me: Person):
    """Start a call: you are person "a", and you get the code to share."""
    if me.lang not in LANGUAGES:
        raise HTTPException(400, "Unknown language")
    try:
        room = rooms.start(me.who or "One person", me.lang, me.voice)
    except rooms.RoomError as e:
        raise HTTPException(503, str(e))
    return {"code": room.code, "person": "a"}


@app.post("/api/calls/{code}/join")
async def join_call(code: str, me: Person):
    """Join a call with its code: you are person "b"."""
    room = room_or_404(code)
    if me.lang not in LANGUAGES:
        raise HTTPException(400, "Unknown language")
    if me.lang == room.people["a"]["lang"]:
        raise HTTPException(400, "You both chose the same language. Please choose the other one.")
    try:
        person = rooms.join(room, me.who or "the other person", me.lang, me.voice)
    except rooms.RoomError as e:
        raise HTTPException(409, str(e))
    return {"code": room.code, "person": person}


@app.get("/api/calls/{code}")
async def call_news(code: str, after: int = 0, known: int = 0):
    """Wait for news: who is on the call, and the sentences after number `after`."""
    return await rooms.wait(room_or_404(code), after, known)


@app.post("/api/calls/{code}/said")
async def said_in_call(code: str, line: Line):
    """One person's sentence: Mythree translates it for the other person and shares it."""
    room = room_or_404(code)
    me = room.people.get(line.person)
    them = room.other(line.person)
    if not me:
        raise HTTPException(400, "Unknown person")
    if not them:
        raise HTTPException(409, "Waiting for the other person to join.")
    lang = language_of(line.text) or me["lang"]   # trust the words over the setting
    to = them["lang"] if lang != them["lang"] else me["lang"]
    if lang == to:
        raise HTTPException(400, "Choose two different languages")
    history = [{"who": room.people[m["person"]]["who"], "text": m["text"], "lang": m["lang"]}
               for m in room.messages]
    try:
        text = await run_in_threadpool(brain.translate, line.text, lang, to, me["who"], them["who"], history)
    except meta.MetaError:
        raise HTTPException(502, "Mythree couldn't translate that just now. Please say it again. "
                                 "మళ్ళీ ఒకసారి చెప్పండి.")
    return rooms.add(room, {"person": line.person, "text": line.text, "lang": lang,
                            "translation": text, "to": to})


class Heard(BaseModel):
    n: int


@app.post("/api/calls/{code}/speak")
async def speak_in_call(code: str, heard: Heard):
    """Voice: sentence number n, in the voice of the person who said it (MP3, streamed)."""
    room = room_or_404(code)
    if not 1 <= heard.n <= len(room.messages):
        raise HTTPException(404, "No such sentence")
    m = room.messages[heard.n - 1]
    try:
        sound = await run_in_threadpool(voice.speak_as, m["translation"], m["to"], room.voices.get(m["person"]))
    except voice.VoiceError:
        raise HTTPException(503, "Own voice not available, using the standard voice")
    return StreamingResponse(sound, media_type="audio/mpeg")


# --- Each person's own voice, recorded in the app -----------------------------
MAX_VOICE_BYTES = 4_000_000                 # about 2 minutes at 16 kHz
MIN_VOICE_BYTES = 44 + 16_000 * 2 * 20      # about 20 seconds
VOICE_ID = re.compile(r"^[A-Za-z0-9]{8,40}$")
HELLO = {"te": "నమస్తే! ఇది మైత్రిలో నా గొంతు.", "en": "Hello! This is my voice in Mythree."}


def own_voice_id(voice_id: str) -> str:
    """Only voices recorded in the app may be used or deleted here, never the family's own voices."""
    family = {family_voice(p, "elevenlabs") for p in PEOPLE}
    if not VOICE_ID.match(voice_id) or voice_id in family:
        raise HTTPException(400, "Unknown voice")
    return voice_id


@app.post("/api/voices")
async def learn_voice(audio: UploadFile = File(...), name: str = Form("", max_length=80),
                      consent: bool = Form(False)):
    """Learn one person's voice from about a minute of them talking. Only with their consent."""
    if not consent:
        raise HTTPException(400, "Please tick the box to agree first. · ముందు అంగీకరించండి.")
    wav = await audio.read(MAX_VOICE_BYTES + 1)
    if len(wav) > MAX_VOICE_BYTES:
        raise HTTPException(413, "That recording is too long. About one minute is enough.")
    if not wav.startswith(b"RIFF"):
        raise HTTPException(400, "Not a WAV sound file")
    if len(wav) < MIN_VOICE_BYTES:
        raise HTTPException(400, "Please talk for at least 20 seconds. · కనీసం 20 సెకన్లు మాట్లాడండి.")
    try:
        new = await run_in_threadpool(voice.learn, name or "someone", wav)
    except voice.VoiceError:
        raise HTTPException(502, "Mythree couldn't learn your voice just now. Please try again.")
    return {"voice": new}


@app.post("/api/voices/{voice_id}/hello")
async def hello_in_my_voice(voice_id: str, lang: str = "en"):
    """A short greeting in a newly recorded voice, so the person can hear how it sounds."""
    if lang not in LANGUAGES:
        raise HTTPException(400, "Unknown language")
    try:
        sound = await run_in_threadpool(voice.speak_as, HELLO[lang], lang, own_voice_id(voice_id))
    except voice.VoiceError:
        raise HTTPException(503, "Your voice isn't ready just now.")
    return StreamingResponse(sound, media_type="audio/mpeg")


@app.delete("/api/voices/{voice_id}")
async def forget_voice(voice_id: str):
    """Delete a voice recorded in the app, whenever its owner wants."""
    try:
        await run_in_threadpool(voice.forget, own_voice_id(voice_id))
    except voice.VoiceError:
        raise HTTPException(502, "Mythree couldn't delete it just now. Please try again.")
    return {"ok": True}
