"""Mythree's server.

It serves the home page and Mythree's senses. The ears are here; the
brain, eyes and voice are added one milestone at a time.
"""

import asyncio
import hashlib
import hmac
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
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
        # On Modal every file is dated 1 January 1970, so a phone asking "changed since then?" was told
        # "no" and kept running old code. Without a date, phones compare the file's fingerprint instead.
        if "last-modified" in response.headers:
            del response.headers["last-modified"]
    return response


def page(name: str) -> HTMLResponse:
    """A page whose scripts and pictures carry a fingerprint of their content (phone.js?v=3f2a…),
    so a phone always loads the newest code after an update, never an old copy."""
    html = (STATIC / name).read_text()

    def fingerprinted(found: re.Match) -> str:
        file = STATIC / found.group(2)
        mark = hashlib.md5(file.read_bytes()).hexdigest()[:10] if file.exists() else "0"
        return f'{found.group(1)}="/static/{found.group(2)}?v={mark}"'
    return HTMLResponse(re.sub(r'(src|href)="/static/([\w.-]+)"', fingerprinted, html))


# Online, Mythree's senses need a passcode (set as the MYTHREE_PASSCODE secret), and each
# visitor gets a fair number of requests per minute, so strangers can't use up the credits.
REQUESTS_PER_MINUTE = 40
recent: dict[str, deque] = defaultdict(deque)
# Guessing the passcode: after WRONG_TRIES wrong passcodes in an hour, a visitor is refused until the hour is up.
WRONG_TRIES = 10
wrong: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def guard(request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    visitor = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    if request.url.path.startswith("/api/try/") and try_closed():
        return JSONResponse({"detail": TRY_CLOSED}, status_code=410)
    passcode = secret("MYTHREE_PASSCODE")
    if passcode and not request.url.path.startswith("/api/try/"):   # the Try page is open to everyone
        misses, now = wrong[visitor], time.monotonic()
        while misses and now - misses[0] > 3600:
            misses.popleft()
        if len(misses) >= WRONG_TRIES:
            return JSONResponse({"detail": "Too many wrong passcodes. Please try again in an hour. "
                                           "· చాలాసార్లు తప్పు పాస్‌కోడ్. గంట తర్వాత ప్రయత్నించండి."}, status_code=429)
        typed = request.headers.get("x-mythree-passcode", "")
        if not hmac.compare_digest(typed, passcode) and not await invited(request):
            if typed:   # a wrong guess (an empty one is just a page asking whether a passcode is needed)
                misses.append(now)
            return JSONResponse({"detail": "Passcode needed · పాస్‌కోడ్ కావాలి"}, status_code=401)
    times, now = recent[visitor], time.monotonic()
    while times and now - times[0] > 60:
        times.popleft()
    if len(times) >= REQUESTS_PER_MINUTE:
        return JSONResponse({"detail": "Too many requests. Please wait a minute. · ఒక నిమిషం ఆగండి."}, status_code=429)
    times.append(now)
    return await call_next(request)


async def invited(request) -> bool:
    """Someone who opened a call's link (with its hidden key) may take part in that one call without
    the passcode: the caller, who has the passcode, invited them. A grandmother never types a passcode."""
    found = re.match(r"^/api/calls/(\d{4})(/(join|heard|said|speak))?$", request.url.path)
    key = request.headers.get("x-mythree-call-key", "")
    if not found or not key:
        return False
    try:
        room = await rooms.find(found.group(1))
    except rooms.RoomError:
        return False
    return bool(room.key) and hmac.compare_digest(room.key, key)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def home():
    """The page the grandson opens on his laptop."""
    return page("index.html")


@app.get("/demo")
def demo():
    """Two phones side by side on one screen, for testing alone (each side is the real phone app)."""
    return page("demo.html")


# The free Try page is open for the hackathon week only: it closes by itself at the submission deadline,
# Wednesday 4 November 2026, 8 PM in Dallas (Central Standard Time, 2 AM on 5 November in UTC).
TRY_OPEN_UNTIL = 1793844000   # 2026-11-05 02:00 UTC
TRY_CLOSED = "Try Mythree was open during the hackathon week, and it is closed now. Thank you for trying it! 🦚"


def try_closed() -> bool:
    return time.time() >= TRY_OPEN_UNTIL


# --- Who is trying Mythree: numbers only, never words, voices or names ------------
# Per Dallas day: {"voices": visitors who lent their voice, "sentences": sentences spoken,
# "languages": {language chosen: sentences}}. Online they are kept in a small Modal store,
# so they survive restarts; locally and in tests, in memory.
stats_store = None          # online: a modal.Dict (set by modal_app.py)
stats_days: dict[str, dict] = {}


def dallas_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 6 * 3600))   # Dallas, near enough for counting


async def count_visit(what: str, language: str = ""):
    day = dallas_day()
    try:
        counts = (await stats_store.get.aio(day) if stats_store is not None else stats_days.get(day)) or {}
        counts[what] = counts.get(what, 0) + 1
        if what == "sentences":
            languages = counts.setdefault("languages", {})
            name = language or "Found by itself"
            languages[name] = languages.get(name, 0) + 1
        if stats_store is not None:
            await stats_store.put.aio(day, counts)
        else:
            stats_days[day] = counts
    except Exception:   # counting must never spoil a visitor's try
        pass


@app.get("/api/stats")
async def stats():
    """For Vijaya (behind the passcode): how many people tried Mythree, today and all week."""
    if stats_store is not None:
        days = {day: await stats_store.get.aio(day) async for day in stats_store.keys.aio()}
    else:
        days = dict(stats_days)
    week = {"voices": 0, "sentences": 0, "languages": {}}
    for counts in days.values():
        week["voices"] += counts.get("voices", 0)
        week["sentences"] += counts.get("sentences", 0)
        for name, n in counts.get("languages", {}).items():
            week["languages"][name] = week["languages"].get(name, 0) + n
    try:
        in_use = len(await run_in_threadpool(voice.try_voices))
        left = await run_in_threadpool(voice.characters_left)
    except voice.VoiceError:
        in_use, left = None, None
    return {"today": days.get(dallas_day(), {}), "week": week, "voices_in_use": in_use, "voice_places": TRY_MAX_VOICES,
            "characters_left": left, "family_reserve": FAMILY_CHARACTERS, "open_until": TRY_OPEN_UNTIL}


@app.get("/stats")
def stats_page():
    """Vijaya's private page: who is trying Mythree (numbers only)."""
    return page("stats.html")


@app.get("/try")
def try_page():
    """For hackathon visitors: speak your own language, hear yourself speak English."""
    if try_closed():
        return page("try-closed.html")
    return page("try.html")


@app.get("/phone")
def phone():
    """Mythree as its own call: each person on their own phone, in their own language."""
    return page("phone.html")


@app.get("/api/hello")
def hello():
    """The page checks here first, so it can ask for the passcode before anyone talks."""
    return {"ok": True}


@app.get("/health")
def health():
    """A quick "are you alive?" check for the hosting service."""
    return {"status": "ok", "name": "Mythree"}


@app.post("/api/hear")
async def hear(audio: UploadFile = File(...), lang: str = Form(...), sure: bool = Form(False)):
    """Ears: one spoken sentence (WAV) in, the words out.

    The page sends a sentence each time the speaker pauses. Nothing is saved.
    `sure`: the phone app hears only its own person, so the ears are told their language.
    The laptop page hears both people through one microphone, so there the ears are told
    "Telugu or English", which still stops Urdu, Gujarati or Chinese letters.
    """
    if lang not in LANGUAGES:
        raise HTTPException(400, "Unknown language")
    wav = await audio.read(MAX_SENTENCE_BYTES + 1)
    if len(wav) > MAX_SENTENCE_BYTES:
        raise HTTPException(413, "That sentence is too long. Please pause a little more often.")
    if not wav.startswith(b"RIFF"):
        raise HTTPException(400, "Not a WAV sound file")
    try:
        expect = [brain.LANGUAGE_NAMES[lang]] if sure else list(brain.LANGUAGE_NAMES.values())
        text = await run_in_threadpool(meta.transcribe, wav, expect)  # don't block other requests while Meta listens
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


class Invite(BaseModel):
    """Who the caller is calling, so that person only taps one big Answer button (no choosing, no passcode)."""
    who: str = Name                                # e.g. "the grandmother"
    lang: str                                      # the language they speak
    caller: str = Field(default="", max_length=80) # how their screen names the caller, in their language: "మీ మనవడు"


class Person(BaseModel):
    who: str = Name   # e.g. "Ravi, the grandson"
    lang: str = ""
    voice: str = VoiceId   # the voice this person recorded in the app ("" = none yet)
    them: Invite | None = None   # starting a call: who you are calling
    answer: bool = False         # joining: "I am the person you invited", so who and lang come from the invite


class Line(BaseModel):
    person: str
    text: str = Field(min_length=1, max_length=1000)


# Each call has a hidden key in its link, sent by the phones in this header. Without the right
# key a call looks the same as a call that doesn't exist, so guessing 4-digit codes finds nothing.
CallKey = Header(default="", alias="X-Mythree-Call-Key", max_length=40)


async def room_or_404(code: str, key: str) -> rooms.Room:
    try:
        room = await rooms.find(code)
    except rooms.RoomError as e:
        raise HTTPException(404, str(e))
    if not room.key or not hmac.compare_digest(room.key, key):
        raise HTTPException(404, rooms.ENDED)
    return room


@app.post("/api/calls")
async def start_call(me: Person):
    """Start a call: you are person "a", and you get the code to share."""
    if me.lang not in LANGUAGES:
        raise HTTPException(400, "Unknown language")
    if me.them and (me.them.lang not in LANGUAGES or me.them.lang == me.lang):
        me.them = None   # not a usable invitation: the other person chooses for themselves
    try:
        room = rooms.start(me.who or "One person", me.lang, me.voice)
    except rooms.RoomError as e:
        raise HTTPException(503, str(e))
    if me.them:
        room.invite = me.them.model_dump()
        rooms.save(room)
    return {"code": room.code, "person": "a", "key": room.key}


@app.post("/api/calls/{code}/join")
async def join_call(code: str, me: Person, key: str = CallKey):
    """Join a call with its code: you are person "b"."""
    room = await room_or_404(code, key)
    if me.answer and room.invite:   # the invited person tapped Answer: the caller already chose for them
        me.who, me.lang = room.invite["who"], room.invite["lang"]
    if me.lang not in LANGUAGES:
        raise HTTPException(400, "Unknown language")
    if me.lang == room.people["a"]["lang"]:
        raise HTTPException(400, "You both chose the same language. Please choose the other one.")
    try:
        person = rooms.join(room, me.who or "the other person", me.lang, me.voice)
    except rooms.RoomError as e:
        raise HTTPException(409, str(e))
    return {"code": room.code, "person": person, "key": room.key}


@app.get("/api/calls/{code}")
async def call_news(code: str, after: int = 0, known: int = 0, key: str = CallKey):
    """Wait for news: who is on the call, and the sentences after number `after`."""
    return await rooms.wait(await room_or_404(code, key), after, known)


@app.post("/api/calls/{code}/said")
async def said_in_call(code: str, line: Line, key: str = CallKey):
    """One person's sentence (already words): Mythree translates it for the other person and shares it."""
    room = await room_or_404(code, key)
    the_two(room, line.person)
    return await share(room, line.person, line.text)


@app.post("/api/calls/{code}/heard")
async def heard_in_call(code: str, audio: UploadFile = File(...), person: str = Form(...),
                        key: str = CallKey):
    """One spoken sentence, in a single trip: Meta's ears, then the brain, then sharing it.
    (From India, every trip across the world adds time; this saves one.)"""
    room = await room_or_404(code, key)
    me, _ = the_two(room, person)
    wav = await audio.read(MAX_SENTENCE_BYTES + 1)
    if len(wav) > MAX_SENTENCE_BYTES:
        raise HTTPException(413, "That sentence is too long. Please pause a little more often.")
    if not wav.startswith(b"RIFF"):
        raise HTTPException(400, "Not a WAV sound file")
    try:   # this phone hears only its own person, so the ears are told their language
        text = await run_in_threadpool(meta.transcribe, wav, [brain.LANGUAGE_NAMES[me["lang"]]])
    except meta.MetaError:
        raise HTTPException(502, "Mythree couldn't hear that just now. Please say it again. "
                                 "మళ్ళీ ఒకసారి చెప్పండి.")
    text = devanagari_to_telugu(text)
    if not text:
        return {"text": ""}
    return await share(room, person, text)


def the_two(room: rooms.Room, person: str) -> tuple[dict, dict]:
    me, them = room.people.get(person), room.other(person)
    if not me:
        raise HTTPException(400, "Unknown person")
    if not them:
        raise HTTPException(409, "Waiting for the other person to join.")
    return me, them


async def share(room: rooms.Room, person: str, said: str) -> dict:
    """Translate one person's sentence for the other, share it, and start making its voice right away."""
    me, them = the_two(room, person)
    # Each phone hears only its own person, so trust their chosen language, not the letters:
    # the ears sometimes write Telugu in English or Gujarati letters.
    lang, to = me["lang"], them["lang"]
    if lang == to:
        raise HTTPException(400, "Choose two different languages")
    history = [{"who": room.people[m["person"]]["who"], "text": m["text"], "lang": m["lang"]}
               for m in room.messages]
    try:
        text = await run_in_threadpool(brain.translate, said, lang, to, me["who"], them["who"], history)
    except meta.MetaError:
        raise HTTPException(502, "Mythree couldn't translate that just now. Please say it again. "
                                 "మళ్ళీ ఒకసారి చెప్పండి.")
    m = rooms.add(room, {"person": person, "text": said, "lang": lang,
                         "translation": text, "to": to})
    if room.voices.get(person):   # start making the voice now, before the other phone asks for it
        sound = room.sounds[m["n"]] = rooms.Sound()
        room.tasks.add(task := asyncio.create_task(make_voice(sound, text, to, room.voices[person])))
        task.add_done_callback(room.tasks.discard)
    return m


async def make_voice(sound: rooms.Sound, text: str, lang: str, voice_id: str):
    """Fetch the voice piece by piece into `sound`, so the other phone can start playing at once."""
    try:
        pieces = await run_in_threadpool(voice.speak_as, text, lang, voice_id)
        while (piece := await run_in_threadpool(next, pieces, None)) is not None:
            sound.pieces.append(piece)
            sound.changed()
    except voice.VoiceError:
        pass   # no pieces: the phone uses its standard voice
    finally:
        sound.done = True
        sound.changed()


class Heard(BaseModel):
    n: int


@app.post("/api/calls/{code}/speak")
async def speak_in_call(code: str, heard: Heard, key: str = CallKey):
    """Voice: sentence number n, in the voice of the person who said it (MP3, streamed)."""
    room = await room_or_404(code, key)
    if not 1 <= heard.n <= len(room.messages):
        raise HTTPException(404, "No such sentence")
    m = room.messages[heard.n - 1]
    sound = room.sounds.get(heard.n)
    if sound is None:   # no early voice (an older sentence, or after a restart): make it now
        try:
            pieces = await run_in_threadpool(voice.speak_as, m["translation"], m["to"], room.voices.get(m["person"]))
        except voice.VoiceError:
            raise HTTPException(503, "Own voice not available, using the standard voice")
        return StreamingResponse(pieces, media_type="audio/mpeg")
    while not sound.pieces and not sound.done:   # usually already arriving: it started with the translation
        await sound.news.wait()
    if not sound.pieces:
        raise HTTPException(503, "Own voice not available, using the standard voice")

    async def early_pieces():
        sent = 0
        while True:
            if sent < len(sound.pieces):
                yield sound.pieces[sent]
                sent += 1
            elif sound.done:
                return
            else:
                await sound.news.wait()
    return StreamingResponse(early_pieces(), media_type="audio/mpeg")


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


# --- The Try page: speak any language, hear yourself in English ----------------
# For hackathon visitors. Meta's ears find the language by themselves (about 25 languages), the brain
# turns it into English, and ElevenLabs says it in the visitor's own voice. A visitor's voice copy is
# deleted after TRY_MINUTES, so nobody's voice stays and the voice slots free up again.
TRY_MINUTES = 60
SHARE_AFTER_MINUTES = 10   # when all voice places are taken, a visitor voice this old may make room
# Protecting the family's own Mythree (Vijaya, her husband, her son, and her demo video):
TRY_MAX_VOICES = 7           # visitors hold at most 7 of ElevenLabs' 10 voice places; 3 stay for the family
FAMILY_CHARACTERS = 20_000   # below this many characters left this month, visitors hear a standard voice
VOICES_FULL = ("So many people are trying Mythree right now that all of its own-voice places are in use. 🙏 "
                                     "Everything else works: speak, and you'll read and hear it in English in a standard voice. "
                                     "Come back in about 10 minutes and tap \"Try my own voice again\".")
STANDARD_VOICE = ("Today Mythree's own voices are saved for the family that built it, so you'll hear a standard "
                  "voice. Everything else works the same!")


async def family_characters_safe() -> bool:
    try:
        return await run_in_threadpool(voice.characters_left) > FAMILY_CHARACTERS
    except voice.VoiceError:
        return False


async def tidy_try_voices(make_room: bool = False):
    """Delete visitors' voices older than TRY_MINUTES. With make_room (all ElevenLabs voice places taken),
    also the oldest one if it is older than SHARE_AFTER_MINUTES: that visitor has most likely finished.
    Someone still testing keeps their voice; the newcomer then hears a standard voice.
    Family voices are never touched: only voices named "Mythree · Try visitor" are visitors'."""
    try:
        visitors = await run_in_threadpool(voice.try_voices)
    except voice.VoiceError:
        return
    now = time.time()
    old = [v for v, made in visitors.items() if now - made > TRY_MINUTES * 60]
    if make_room and not old and visitors:
        oldest = min(visitors, key=visitors.get)
        if now - visitors[oldest] > SHARE_AFTER_MINUTES * 60:
            old = [oldest]
    for v in old:
        try:
            await run_in_threadpool(voice.forget, v)
        except voice.VoiceError:
            continue


# The Try page is free for everyone, so it has a daily limit too (on top of each service's own spending limit).
TRY_PER_DAY = 500
try_today = {"day": "", "count": 0}


def count_a_try():
    today = time.strftime("%Y-%m-%d")
    if try_today["day"] != today:
        try_today.update(day=today, count=0)
    if try_today["count"] >= TRY_PER_DAY:
        raise HTTPException(503, "Mythree's free tries for today are used up. Please come back tomorrow!")
    try_today["count"] += 1


async def visitor_voice(voice_id: str) -> str:
    """The free Try page may greet or delete only a visitor's voice, never a family voice."""
    try:
        visitors = await run_in_threadpool(voice.try_voices)
    except voice.VoiceError:
        raise HTTPException(503, "Your voice isn't ready just now.")
    if voice_id not in visitors:
        raise HTTPException(404, "Unknown voice")
    return voice_id


@app.post("/api/try/hello/{voice_id}")
async def try_hello(voice_id: str):
    """The first wow: "Hello! This is my voice in Mythree." in the visitor's own voice."""
    try:
        sound = await run_in_threadpool(voice.speak_as, HELLO["en"], "en", await visitor_voice(voice_id))
    except voice.VoiceError:
        raise HTTPException(503, "Your voice isn't ready just now.")
    return StreamingResponse(sound, media_type="audio/mpeg")


@app.delete("/api/try/voice/{voice_id}")
async def try_forget(voice_id: str):
    """Done: delete the visitor's voice copy."""
    try:
        await run_in_threadpool(voice.forget, await visitor_voice(voice_id))
    except voice.VoiceError:
        raise HTTPException(502, "Mythree couldn't delete your voice just now. It will be deleted within the hour.")
    return {"ok": True}


@app.post("/api/try/voice")
async def try_learn_voice(audio: UploadFile = File(...), consent: bool = Form(False)):
    """A visitor's voice, for one hour at most."""
    if not await family_characters_safe():
        raise HTTPException(503, STANDARD_VOICE)
    await tidy_try_voices()
    try:
        visitors = await run_in_threadpool(voice.try_voices)
    except voice.VoiceError:
        visitors = {}
    if len(visitors) >= TRY_MAX_VOICES:   # visitors' share is full: free a finished one, or use a standard voice
        await tidy_try_voices(make_room=True)
        if len(await run_in_threadpool(voice.try_voices)) >= TRY_MAX_VOICES:
            raise HTTPException(503, VOICES_FULL)
    try:
        learned = await learn_voice(audio, voice.TRY_NAME.removeprefix("Mythree · "), consent)
        await count_visit("voices")
        return learned
    except HTTPException as e:
        if e.status_code != 502:
            raise
    await tidy_try_voices(make_room=True)   # probably all 10 voice places are taken: free one and try again
    await audio.seek(0)
    try:
        learned = await learn_voice(audio, voice.TRY_NAME.removeprefix("Mythree · "), consent)
        await count_visit("voices")
        return learned
    except HTTPException as e:
        if e.status_code != 502:
            raise
    raise HTTPException(503, VOICES_FULL)


# The languages a visitor may pick (all accepted by Meta's ears, tested 29 Oct). Without a pick the
# ears guess, and sometimes write Telugu in Kannada letters, because the two sound alike.
TRY_LANGUAGES = {"Telugu", "Hindi", "Kannada", "Tamil", "Malayalam", "Bengali", "Marathi", "Gujarati", "Punjabi",
                 "Urdu", "English", "Spanish", "French", "German", "Portuguese", "Italian", "Arabic", "Chinese",
                 "Japanese", "Korean", "Russian", "Indonesian", "Vietnamese", "Turkish", "Thai"}


@app.post("/api/try/heard")
async def try_heard(audio: UploadFile = File(...), language: str = Form("")):
    """One sentence in any language: what was said, and the same in English.
    `language` (optional) is the visitor's own language, told to the ears."""
    count_a_try()
    if language and language not in TRY_LANGUAGES:
        raise HTTPException(400, "Unknown language")
    wav = await audio.read(MAX_SENTENCE_BYTES + 1)
    if len(wav) > MAX_SENTENCE_BYTES:
        raise HTTPException(413, "That's a bit long. Please say one or two sentences at a time.")
    if not wav.startswith(b"RIFF"):
        raise HTTPException(400, "Not a WAV sound file")
    try:
        said = await run_in_threadpool(meta.transcribe, wav, [language] if language else None)
        if language == "Telugu":
            said = devanagari_to_telugu(said)   # any Kannada or Hindi letters that slipped through → Telugu
        english = await run_in_threadpool(brain.to_english, said) if said else ""
    except meta.MetaError:
        raise HTTPException(502, "Mythree couldn't hear that just now. Please try again.")
    await count_visit("sentences", language)
    return {"text": said, "english": english}


class TrySpeak(BaseModel):
    text: str = Field(max_length=600)
    voice: str = VoiceId


@app.post("/api/try/speak")
async def try_speak(line: TrySpeak):
    """The English, in the visitor's own voice."""
    if not await family_characters_safe():
        raise HTTPException(503, STANDARD_VOICE)
    try:
        sound = await run_in_threadpool(voice.speak_as, line.text, "en", own_voice_id(line.voice))
    except voice.VoiceError:
        raise HTTPException(503, "Your voice isn't ready, so you'll hear a standard voice.")
    return StreamingResponse(sound, media_type="audio/mpeg")


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
