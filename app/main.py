"""Mythree's server.

It serves the home page and Mythree's senses: ears, brain and voice.
"""

import asyncio
import difflib
import hashlib
import hmac
import re
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import brain, languages, meta, rooms, voice
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


# Mythree is open to everyone: no passcode (Vijaya took it out on 30 Oct; it kept getting in the
# way). Each call is still protected by its hidden key, and each visitor gets a fair number of
# requests per minute, so strangers can't use up the credits. Only Vijaya's Visitors numbers
# (/api/stats) need the passcode (the MYTHREE_PASSCODE secret).
REQUESTS_PER_MINUTE = 40
recent: dict[str, deque] = defaultdict(deque)
# A call's "anything new?", its video notes and its relay pass cost no credits, and two phones on one
# Wi-Fi (one address) on a video call ask them 40-60 times a minute. They aren't counted: refusing them
# lost the video notes (30 Oct). Each call's notes have their own limit (rooms.MAX_NOTES).
NOT_COUNTED = re.compile(r"^/api/calls/\d+(/video|/ice)?$")
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
    if passcode and request.url.path == "/api/stats":
        misses, now = wrong[visitor], time.monotonic()
        while misses and now - misses[0] > 3600:
            misses.popleft()
        if len(misses) >= WRONG_TRIES:
            return JSONResponse({"detail": "Too many wrong passcodes. Please try again in an hour. "
                                           "· చాలాసార్లు తప్పు పాస్‌కోడ్. గంట తర్వాత ప్రయత్నించండి."}, status_code=429)
        typed = request.headers.get("x-mythree-passcode", "")
        if not hmac.compare_digest(typed, passcode):
            if typed:   # a wrong guess (an empty one is just a page asking whether a passcode is needed)
                misses.append(now)
            return JSONResponse({"detail": "Passcode needed · పాస్‌కోడ్ కావాలి"}, status_code=401)
    if NOT_COUNTED.match(request.url.path):
        return await call_next(request)
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
    return page("index.html")


@app.get("/demo")
def demo():
    """Two phones side by side on one screen, for testing alone (each side is the real phone app)."""
    return page("demo.html")


# The free Try page is open for the hackathon and its judging: it closes by itself when judging ends,
# Monday 9 November 2026, midnight in New York (Eastern Standard Time, 5 AM on 10 November in UTC).
TRY_OPEN_UNTIL = 1794286800   # 2026-11-10 05:00 UTC
TRY_CLOSED = "Try Mythree was open during the hackathon week, and it is closed now. Thank you for trying it! 🦚"


def try_closed() -> bool:
    return time.time() >= TRY_OPEN_UNTIL


# --- Who is trying Mythree: numbers only, never words, voices or names ------------
# Per Dallas day: {"voices": visitors who lent their voice, "sentences": sentences spoken,
# "languages": {language spoken: sentences}, "heard_in": {language chosen to hear: sentences},
# "characters": ElevenLabs characters the visitors' voices used}. Online they are kept in a small Modal store,
# so they survive restarts; locally and in tests, in memory.
stats_store = None          # online: a modal.Dict (set by modal_app.py)
stats_days: dict[str, dict] = {}


def dallas_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 6 * 3600))   # Dallas, near enough for counting


async def counts_of(day: str) -> dict:
    return (await stats_store.get.aio(day) if stats_store is not None else stats_days.get(day)) or {}


async def count_visit(what: str, language: str = "", to: str = "", amount: int = 1):
    day = dallas_day()
    try:
        counts = await counts_of(day)
        counts[what] = counts.get(what, 0) + amount
        if what == "sentences":
            languages = counts.setdefault("languages", {})
            name = language or "Found by itself"
            languages[name] = languages.get(name, 0) + 1
            heard_in = counts.setdefault("heard_in", {})
            heard_in[to] = heard_in.get(to, 0) + 1
        if stats_store is not None:
            await stats_store.put.aio(day, counts)
        else:
            stats_days[day] = counts
    except Exception:   # counting must never spoil a visitor's try
        pass


@app.get("/api/stats")
async def stats():
    """For Vijaya (the only thing behind the passcode): how many people tried Mythree, today and all week."""
    if stats_store is not None:
        days = {day: await stats_store.get.aio(day) async for day in stats_store.keys.aio()}
    else:
        days = dict(stats_days)
    week = {"voices": 0, "sentences": 0, "languages": {}, "heard_in": {}}
    for counts in days.values():
        week["voices"] += counts.get("voices", 0)
        week["sentences"] += counts.get("sentences", 0)
        for kind in ("languages", "heard_in"):
            for name, n in counts.get(kind, {}).items():
                week[kind][name] = week[kind].get(name, 0) + n
    try:
        in_use = len(await run_in_threadpool(voice.try_voices))
        left = await run_in_threadpool(voice.characters_left)
    except voice.VoiceError:
        in_use, left = None, None
    return {"today": days.get(dallas_day(), {}), "week": week, "voices_in_use": in_use, "voice_places": TRY_MAX_VOICES,
            "characters_left": left, "family_reserve": FAMILY_CHARACTERS, "open_until": TRY_OPEN_UNTIL,
            "characters_per_day": TRY_CHARACTERS_PER_DAY}


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
    """A quick check that the page can reach Mythree."""
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
    """Who the caller is calling, so that person only taps one big Answer button (no choosing)."""
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
    gone = await voice_gone(me.voice)
    try:
        room = rooms.start(me.who or "One person", me.lang, "" if gone else me.voice)
    except rooms.RoomError as e:
        raise HTTPException(503, str(e))
    if me.them:
        room.invite = me.them.model_dump()
        rooms.save(room)
    return {"code": room.code, "person": "a", "key": room.key, "voice_gone": gone}


async def voice_gone(voice_id: str) -> bool:
    """The phone sent a recorded voice that ElevenLabs no longer has: the call uses the standard
    voice, and the phone is told, so it forgets that voice and can ask its person to record again."""
    return bool(voice_id) and not await run_in_threadpool(voice.still_there, voice_id)


@app.post("/api/calls/{code}/join")
async def join_call(code: str, me: Person, key: str = CallKey):
    """Join a call with its code: you are person "b"."""
    room = await room_or_404(code, key)
    invited = bool(me.answer and room.invite)
    if invited:   # the invited person tapped Answer: the caller already chose for them
        me.who, me.lang = room.invite["who"], room.invite["lang"]
    if me.lang not in LANGUAGES:
        raise HTTPException(400, "Unknown language")
    free = room.free_places()   # empty, or freed by a phone that has gone
    if not free:
        raise HTTPException(409, rooms.FULL)
    # (only "b" can be free, so this checks that the two languages differ)
    place = next((p for p in free if (room.other(p) or {}).get("lang") != me.lang), None)
    if not place:
        raise HTTPException(400, "You both chose the same language. Please choose the other one.")
    gone = await voice_gone(me.voice)
    person = rooms.join(room, place, me.who or "the other person", me.lang, "" if gone else me.voice)
    return {"code": room.code, "person": person, "key": room.key, "voice_gone": gone}


class Leaving(BaseModel):
    person: str = Field(pattern=r"^[ab]$")


@app.post("/api/calls/{code}/leave")
async def leave_call(code: str, who: Leaving, key: str = CallKey):
    """End: the call ends for both phones; the other phone is told at once."""
    room = await room_or_404(code, key)
    if who.person in room.people:
        rooms.end(room)
    return {"ok": True}


@app.get("/api/calls/{code}")
async def call_news(code: str, after: int = 0, known: int = 0, person: str = "", notes: int = 0,
                    key: str = CallKey):
    """Wait for news: who is on the call, the sentences after number `after`, and the video notes
    for `person` after number `notes`."""
    return await rooms.wait(await room_or_404(code, key), after, known, person, notes)


# --- Seeing each other (video) ----------------------------------------------------
# The picture and the real voice travel straight from phone to phone (WebRTC), not through Mythree.
# Mythree only passes on the notes the two phones need to find each other: "my camera is ready",
# then an offer and an answer ("how to reach me"). No model is involved in the video.

class VideoNote(BaseModel):
    person: str
    kind: str = Field(pattern=r"^(ready|offer|answer|bye)$")
    id: int = Field(default=0, ge=0)                    # which offer an answer belongs to
    reply: bool = False                                 # a "ready" sent back to a "ready" (not answered again)
    sdp: str = Field(default="", max_length=20000)     # the phone's "how to reach me", written by the browser


@app.post("/api/calls/{code}/video")
async def video_note(code: str, note: VideoNote, key: str = CallKey):
    """One phone's video note, kept for the other phone (it collects it with the call's news)."""
    room = await room_or_404(code, key)
    the_two(room, note.person)
    try:
        rooms.note(room, note.person, note.model_dump(exclude={"person"}))
    except rooms.RoomError as e:
        raise HTTPException(429, str(e))
    return {"ok": True}


# When a home or mobile network blocks a direct line between the phones (common on mobile data),
# the video goes through a relay (TURN). Cloudflare's relay is used when its key is in the secrets;
# without it, only direct lines work (fine on the same Wi-Fi). Cost: about $0.05 per GB.
STUN = [{"urls": ["stun:stun.cloudflare.com:3478", "stun:stun.l.google.com:19302"]}]
TURN_URL = "https://rtc.live.cloudflare.com/v1/turn/keys/{}/credentials/generate-ice-servers"
TURN_HOURS = 4


@app.get("/api/calls/{code}/ice")
async def video_routes(code: str, key: str = CallKey):
    """How the phones may reach each other: direct (STUN), and through the relay (TURN) if set up."""
    await room_or_404(code, key)
    turn_id, turn_token = secret("TURN_KEY_ID"), secret("TURN_KEY_API_TOKEN")
    if not (turn_id and turn_token):
        return {"iceServers": STUN}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            reply = await client.post(TURN_URL.format(turn_id), json={"ttl": TURN_HOURS * 3600},
                                      headers={"Authorization": f"Bearer {turn_token}"})
        servers = reply.json()["iceServers"] if reply.status_code in (200, 201) else []
    except (httpx.HTTPError, ValueError, KeyError):
        servers = []
    for server in servers:   # browsers block port 53, and waiting for it only slows the start
        server["urls"] = [u for u in server.get("urls", []) if ":53?" not in u and not u.endswith(":53")]
    return {"iceServers": servers or STUN}


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
    work = []   # which Meta models did the work, shown under the sentence
    try:   # this phone hears only its own person, so the ears are told their language
        with meta.timed(work, "hear", meta.EARS_NAME, ""):
            text = await run_in_threadpool(meta.transcribe, wav, [brain.LANGUAGE_NAMES[me["lang"]]])
    except meta.MetaError:
        raise HTTPException(502, "Mythree couldn't hear that just now. Please say it again. "
                                 "మళ్ళీ ఒకసారి చెప్పండి.")
    text = devanagari_to_telugu(text)
    if not text:
        return {"text": ""}
    return await share(room, person, text, work)


LIVE_SECONDS = 45   # one sentence on the live line: at most 25 s of speech, plus room to spare


@app.websocket("/api/calls/{code}/live")
async def live_in_call(socket: WebSocket, code: str):
    """One spoken sentence, heard while it is being said (Meta's live ears), then translated and shared.

    The phone opens this line when its person starts talking: first {"key", "person"} (a browser
    can't add headers to a websocket), then the sound in small pieces, then {"end": true} after
    the pause. Meanwhile it gets {"partial": words}; at the end, the same reply as /heard.
    On {"error"} the phone sends the whole sentence the old way (/heard), so nothing is lost."""
    await socket.accept()
    try:
        hello = await asyncio.wait_for(socket.receive_json(), 10)
        room = await room_or_404(code, str(hello.get("key", "")))
        person = str(hello.get("person", ""))
        me, _ = the_two(room, person)
        work = []
        async with meta.LiveEars([brain.LANGUAGE_NAMES[me["lang"]]]) as ears:
            text = await asyncio.wait_for(hear_live(socket, ears, work), LIVE_SECONDS)
        text = devanagari_to_telugu(text)
        reply = await share(room, person, text, work) if text else {"text": ""}
    except WebSocketDisconnect:
        return   # the phone went away (the sentence was a cough, or the call ended)
    except HTTPException as e:
        reply = {"error": e.detail}
    except (meta.MetaError, asyncio.TimeoutError, ValueError, KeyError, AttributeError):
        reply = {"error": "Live listening didn't work just now"}
    try:
        await socket.send_json(reply)
        await socket.close()
    except (WebSocketDisconnect, RuntimeError):
        pass   # the phone has already gone


async def hear_live(socket: WebSocket, ears: meta.LiveEars, work: list) -> str:
    """Pass the phone's sound on to Meta while Meta's words come back; returns the final words.
    How long Meta took after the pause is added to `work`."""
    paused = {}

    async def pass_on():
        size = 0
        while True:
            message = await socket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()
            if message.get("bytes"):
                size += len(message["bytes"])
                if size > MAX_SENTENCE_BYTES:
                    raise HTTPException(413, "That sentence is too long. Please pause a little more often.")
                await ears.hear(message["bytes"])
            elif message.get("text"):   # {"end": true}: the speaker paused
                paused["at"] = time.monotonic()
                await ears.end()
                return

    async def listen():
        async for words, final in ears.words():
            if final:
                waited = time.monotonic() - paused.get("at", time.monotonic())
                work.append({"job": "hear", "model": meta.EARS_NAME, "where": "live", "s": round(waited, 1)})
                return words
            await socket.send_json({"partial": devanagari_to_telugu(words)})

    passing, listening = asyncio.create_task(pass_on()), asyncio.create_task(listen())
    try:   # stop at once if either side fails; otherwise wait for the final words
        await asyncio.wait({passing, listening}, return_when=asyncio.FIRST_EXCEPTION)
        if passing.done() and passing.exception():
            raise passing.exception()
        return await listening
    finally:
        passing.cancel()
        listening.cancel()


def the_two(room: rooms.Room, person: str) -> tuple[dict, dict]:
    me, them = room.people.get(person), room.other(person)
    if not me:
        raise HTTPException(400, "Unknown person")
    if not them:
        raise HTTPException(409, "Waiting for the other person to join.")
    return me, them


async def share(room: rooms.Room, person: str, said: str, work: list | None = None) -> dict:
    """Translate one person's sentence for the other, share it, and start making its voice right away.
    `work`: the Meta models that have already worked on it (the ears); the brain is added."""
    me, them = the_two(room, person)
    # Each phone hears only its own person, so trust their chosen language, not the letters:
    # the ears sometimes write Telugu in English or Gujarati letters.
    lang, to = me["lang"], them["lang"]
    if lang == to:
        raise HTTPException(400, "Choose two different languages")
    if echo(room, said):   # the phone heard a voice it already played: drop it quietly, before translating
        return {"text": "", "translation": "", "echo": True}
    history =[{"who": room.people[m["person"]]["who"], "text": m["text"], "lang": m["lang"]}
               for m in room.messages]
    work = list(work or [])
    try:
        text = await run_in_threadpool(brain.translate, said, lang, to, me["who"], them["who"], history, work)
    except meta.MetaError:
        raise HTTPException(502, "Mythree couldn't translate that just now. Please say it again. "
                                 "మళ్ళీ ఒకసారి చెప్పండి.")
    m = rooms.add(room, {"person": person, "text": said, "lang": lang,
                         "translation": text, "to": to, "at": time.time(), "meta": work})
    # start making the voice now, before the other phone asks for it
    sound = room.sounds[m["n"]] = rooms.Sound()
    room.tasks.add(task := asyncio.create_task(make_voice(sound, text, to, *voices_of(room, person))))
    task.add_done_callback(room.tasks.discard)
    return m


def voices_of(room: rooms.Room, person: str) -> tuple[str, str]:
    """The voices to speak this person's translations in: their own (if recorded), then a standard one."""
    return room.voices.get(person) or "", voice.standard_voice(room.people[person]["who"])


# Echoes: a phone's microphone can hear a voice played a moment ago (the other phone in the same room,
# or its own speaker) and send it again as new words, round and round (30 Oct: the same sentence
# 5 times). A sentence of 4 words or more that closely matches something said or played in the last
# ECHO_SECONDS is dropped. Short ones ("how are you?") are kept: real replies often repeat them.
ECHO_SECONDS = 30
ECHO_LIKENESS = 0.75


def echo(room: rooms.Room, said: str) -> bool:
    words = lambda text: " ".join(re.findall(r"\w+", text.lower()))
    new = words(said)
    if len(new.split()) < 4:
        return False
    for m in room.messages[-6:]:
        if time.time() - m.get("at", 0) > ECHO_SECONDS:
            continue
        for old in (words(m["text"]), words(m["translation"])):
            if new in old or difflib.SequenceMatcher(None, new, old).ratio() >= ECHO_LIKENESS:
                return True
    return False


async def make_voice(sound: rooms.Sound, text: str, lang: str, own: str, standard: str):
    """Fetch the voice piece by piece into `sound`, so the other phone can start playing at once."""
    try:
        pieces = await run_in_threadpool(start_voice, text, lang, own, standard)
        sound.standard = pieces.standard
        while (piece := await run_in_threadpool(next, pieces, None)) is not None:
            sound.pieces.append(piece)
            sound.changed()
    except voice.VoiceError:   # no pieces: the phone uses its own voice (already in the logs)
        pass
    finally:
        sound.done = True
        sound.changed()


class Spoken:
    """The pieces of a voice, and whether it is the standard one (the phone says so under the line)."""

    def __init__(self, pieces, standard: bool):
        self.pieces, self.standard = pieces, standard

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.pieces)


def start_voice(text: str, lang: str, own: str, standard: str) -> Spoken:
    """The person's own voice if they recorded one; otherwise, or if it fails, Mythree's standard voice."""
    if own:
        try:
            return Spoken(voice.speak_as(text, lang, own), False)
        except voice.VoiceError as e:
            # Say why in the logs (31 Oct: one person's every sentence fell back, and nothing said why)
            print(f"Own voice failed ({lang}), the standard voice is used: {e}")
    try:
        return Spoken(voice.speak_as(text, lang, standard), True)
    except voice.VoiceError as e:
        print(f"Standard voice failed ({lang}), the phone's own voice is used: {e}")
        raise


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
            pieces = await run_in_threadpool(start_voice, m["translation"], m["to"], *voices_of(room, m["person"]))
        except voice.VoiceError:
            raise HTTPException(503, "No voice available, using the phone's own voice")
        return StreamingResponse(pieces, media_type="audio/mpeg", headers=voice_kind(pieces.standard))
    while not sound.pieces and not sound.done:   # usually already arriving: it started with the translation
        await sound.news.wait()
    if not sound.pieces:
        raise HTTPException(503, "No voice available, using the phone's own voice")

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
    return StreamingResponse(early_pieces(), media_type="audio/mpeg", headers=voice_kind(sound.standard))


def voice_kind(standard: bool) -> dict:
    return {"X-Mythree-Voice": "standard" if standard else "own"}


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
                                     "Everything else works: speak, and you'll read and hear it in a standard voice. "
                                     "Come back in about 10 minutes and tap \"Try my own voice again\".")
STANDARD_VOICE = ("Today Mythree's own voices are saved for the family that built it, so you'll hear a standard "
                  "voice. Everything else works the same!")


async def family_characters_safe() -> bool:
    try:
        return await run_in_threadpool(voice.characters_left) > FAMILY_CHARACTERS
    except voice.VoiceError:
        return False


# The visitors' voices may use only so many characters a day, so a busy evening (a post going viral) can't
# spend the whole month at once: judges trying Mythree on the last day still hear the real voices.
TRY_CHARACTERS_PER_DAY = 1_200   # about 20 sentences; after that, the phone's own voice until tomorrow
VOICES_REST_TODAY = ("Mythree's voices have spoken a lot today, so for the rest of the day you'll hear your phone's "
                     "own voice. Everything else works the same! Come back tomorrow for the real voice.")


async def visitors_may_speak(characters: int):
    """Refuse (503) when the family's reserve or today's visitor share would be used up."""
    if not await family_characters_safe():
        raise HTTPException(503, STANDARD_VOICE)
    used = (await counts_of(dallas_day())).get("characters", 0)
    if used + characters > TRY_CHARACTERS_PER_DAY:
        raise HTTPException(503, VOICES_REST_TODAY)


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
    await visitors_may_speak(len(HELLO["en"]))
    try:
        sound = await run_in_threadpool(voice.speak_as, HELLO["en"], "en", await visitor_voice(voice_id))
    except voice.VoiceError:
        raise HTTPException(503, "Your voice isn't ready just now.")
    await count_visit("characters", amount=len(HELLO["en"]))
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
    await visitors_may_speak(1)   # no point copying a voice that can't speak today
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


# The languages a visitor may speak and hear (app/languages.py): India's 22, and the world's. Telling the ears
# the language helps: without it they guess, and sometimes write Telugu in Kannada letters, because the two sound alike.
TRY_LANGUAGES = languages.VOICE_CODE


@app.get("/api/try/languages")
def try_languages():
    return languages.for_the_page()


@app.post("/api/try/heard")
async def try_heard(audio: UploadFile = File(...), language: str = Form(""), to: str = Form("English")):
    """One sentence in any language: what was said, and the same in the language the visitor chose to hear.
    `language` (optional) is the visitor's own language, told to the ears."""
    count_a_try()
    if (language and language not in TRY_LANGUAGES) or to not in TRY_LANGUAGES:
        raise HTTPException(400, "Unknown language")
    wav = await audio.read(MAX_SENTENCE_BYTES + 1)
    if len(wav) > MAX_SENTENCE_BYTES:
        raise HTTPException(413, "That's a bit long. Please say one or two sentences at a time.")
    if not wav.startswith(b"RIFF"):
        raise HTTPException(400, "Not a WAV sound file")
    work = []   # which Meta models did the work, shown under the sentence
    try:
        with meta.timed(work, "hear", meta.EARS_NAME, ""):
            said = await run_in_threadpool(meta.transcribe, wav, [language] if language else None)
        if language == "Telugu":
            said = devanagari_to_telugu(said)   # any Kannada or Hindi letters that slipped through → Telugu
        translation = await run_in_threadpool(brain.to_language, said, to, work) if said else ""
    except meta.MetaError:
        raise HTTPException(502, "Mythree couldn't hear that just now. Please try again.")
    await count_visit("sentences", language, to)
    return {"text": said, "translation": translation, "to": to, "meta": work}


class TrySpeak(BaseModel):
    text: str = Field(max_length=600)
    voice: str = VoiceId          # empty: the visitor hasn't lent a voice, so a ready-made voice speaks
    language: str = Field(default="English", max_length=40)


@app.post("/api/try/speak")
async def try_speak(line: TrySpeak):
    """The translation, in the visitor's own voice (or a ready-made one), in the language they chose."""
    code = TRY_LANGUAGES.get(line.language, "unknown")
    if code == "unknown":
        raise HTTPException(400, "Unknown language")
    if code is None:
        raise HTTPException(404, f"Mythree has no voice for {line.language} yet. Read it above!")
    await visitors_may_speak(len(line.text))
    speaker = own_voice_id(line.voice) if line.voice else voice.STANDARD_VOICES["anyone"]
    try:
        sound = await run_in_threadpool(voice.speak_as, line.text, code, speaker)
    except voice.VoiceError:
        raise HTTPException(503, "Your voice isn't ready, so you'll hear a standard voice.")
    await count_visit("characters", amount=len(line.text))
    return StreamingResponse(sound, media_type="audio/mpeg")


@app.post("/api/voices/{voice_id}/hello")
async def hello_in_my_voice(voice_id: str, lang: str = "en"):
    """A short greeting in a newly recorded voice, so the person can hear how it sounds."""
    if lang not in LANGUAGES:
        raise HTTPException(400, "Unknown language")
    try:
        sound = await run_in_threadpool(voice.speak_as, HELLO[lang], lang, own_voice_id(voice_id))
    except voice.VoiceError as e:
        print(f"Hear it failed: {e}")
        if await voice_gone(voice_id):   # deleted since: the phone forgets it and asks to record again
            raise HTTPException(410, "Your recorded voice is gone. Please record it again.")
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
