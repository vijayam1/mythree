"""Mythree calls: two phones, each person in their own language.

One person starts a call and gets a short code (like 4821). The other person
joins with that code. Each phone listens to its own person; Mythree translates
each sentence and the other phone speaks it, in the speaker's own voice.

Rooms live in the server's memory. Online, each room is also copied into a small
Modal store ("mythree-calls"), so a call survives when Mythree is updated or restarts.
A room is forgotten (in memory and in the store) a few hours after its last use.
"""

import asyncio
import secrets
import time

ROOM_HOURS = 3      # a room nobody has used for this long is forgotten
MAX_ROOMS = 100     # enough for testers and judges; stops strangers filling the memory
WAIT_SECONDS = 25   # a phone waits this long for news before asking again
KEEP_SOUNDS = 6     # voices kept for the newest sentences only
MAX_NOTES = 40      # video notes per person per call (a handful is normal); stops a runaway phone
GONE_SECONDS = 60   # a phone in a call asks for news at least every WAIT_SECONDS: silent this long, it has gone

store = None        # online: a modal.Dict, set by modal_app.py. Locally and in tests: memory only.
saving: set = set() # copies being written to the store right now


ENDED = ("This call has ended. Ask for a new link, or start a new call above. · "
         "ఈ కాల్ ముగిసింది. కొత్త లింక్ అడగండి, లేదా పైన కొత్త కాల్ మొదలుపెట్టండి.")


class RoomError(Exception):
    """The room can't do that (full, unknown, too many rooms)."""


class Sound:
    """One sentence's voice, made as soon as its translation is ready, before the other phone asks.
    (Kept in memory only, never in the store: after a restart an old voice is simply made again.)"""

    def __init__(self):
        self.pieces: list[bytes] = []
        self.done = False
        self.standard = False   # Mythree's standard voice, not the speaker's own
        self.news = asyncio.Event()

    def changed(self):
        self.news.set()
        self.news = asyncio.Event()


class Room:
    def __init__(self, code: str):
        self.code = code
        self.key = secrets.token_urlsafe(9)  # the hidden secret in the call's link: the 4-digit code alone is not enough
        self.invite: dict | None = None      # who the caller is calling: {"who", "lang", "caller"}
        self.people: dict[str, dict] = {}    # "a" started the call, "b" joined it
        self.voices: dict[str, str] = {}     # each person's own voice (its ID), never sent to the phones
        self.messages: list[dict] = []
        self.sounds: dict[int, Sound] = {}   # sentence number → its voice, made early
        self.tasks: set = set()              # voices being made right now
        self.notes: dict[str, list] = {"a": [], "b": []}   # video notes waiting for each person (memory only)
        self.news = asyncio.Event()          # set whenever something changes, to wake waiting phones
        self.seen: dict[str, float] = {}     # when each person's phone last asked for news (memory only)
        self.ended = False                   # someone tapped End: the call is over for both
        self.talking: dict[str, str] = {}    # "speaking" or "translating" right now, for the other phone's sign
        self.used = time.monotonic()
        self.dirty = False                   # changed since the last copy to the store

    def other(self, person: str) -> dict | None:
        return self.people.get("b" if person == "a" else "a")

    def here(self, person: str) -> bool:
        """Is this person still in the call? Not if their phone stopped asking for news (closed, lost,
        out of battery). 31 Oct: nobody could join again after one person's phone was gone."""
        return person in self.people and time.monotonic() - self.seen.get(person, 0) < GONE_SECONDS

    def free_places(self) -> list[str]:
        """The places a newcomer may take: "b" if it is empty or its person's phone has gone. Never "a":
        a caller's phone is often quiet for a while, sending the invitation in WhatsApp."""
        return [] if self.here("b") else ["b"]

    def changed(self):
        """Wake every phone that is waiting, then get ready for the next change."""
        self.wake()
        save(self)

    def wake(self):
        self.used = time.monotonic()
        self.news.set()
        self.news = asyncio.Event()

    def new_notes(self, person: str, seen: int) -> list[dict]:
        """The video notes for `person` after number `seen`. After a restart the list starts again
        from 1, so a phone that has seen more than there are gets them all."""
        box = self.notes.get(person, [])
        return box[seen:] if seen <= len(box) else box

    def state(self, after: int = 0, person: str = "", seen: int = 0) -> dict:
        return {"code": self.code, "people": self.people, "invite": self.invite, "messages": self.messages[after:],
                "notes": self.new_notes(person, seen), "away": [p for p in self.people if not self.here(p)], "ended": self.ended,
                "talking": {p: what for p, what in self.talking.items() if what}}


rooms: dict[str, Room] = {}


# --- The store: a copy of each room that outlives the server -----------------
# Copies are written in the background, so no phone waits for them. Each room has
# at most one writer at a time, so the newest copy always lands last.

def save(room: Room):
    if store is None:
        return
    room.dirty = True
    if any(task.get_name() == room.code for task in saving):
        return   # its writer is already busy and will write this change too
    task = asyncio.get_running_loop().create_task(_write(room), name=room.code)
    saving.add(task)
    task.add_done_callback(saving.discard)


async def _write(room: Room):
    while room.dirty:
        room.dirty = False
        if room.ended:   # no copy of an ended call is kept: its words are forgotten at once
            try:
                await store.pop.aio(room.code)
            except Exception:
                pass
            return
        copy = {"key": room.key, "invite": room.invite, "people": room.people, "voices": room.voices, "messages": room.messages,
                "saved": time.time()}
        try:
            await store.put.aio(room.code, copy)
        except Exception:   # the store is only a backup: the call goes on from memory
            return


async def _forget_old_copies():
    try:
        async for code in store.keys.aio():
            copy = await store.get.aio(code)
            if not copy or time.time() - copy["saved"] > ROOM_HOURS * 3600:
                await store.pop.aio(code)
    except Exception:
        pass


async def _from_store(code: str) -> Room | None:
    try:
        copy = await store.get.aio(code)
    except Exception:
        return None
    if not copy or time.time() - copy["saved"] > ROOM_HOURS * 3600:
        return None
    room = rooms[code] = Room(code)
    room.key, room.people, room.voices, room.messages = copy.get("key", ""), copy["people"], copy["voices"], copy["messages"]
    room.invite = copy.get("invite")
    room.seen = dict.fromkeys(room.people, time.monotonic())   # after a restart, give both phones time to ask again
    return room


def tidy():
    old = [code for code, room in rooms.items() if time.monotonic() - room.used > ROOM_HOURS * 3600]
    for code in old:
        del rooms[code]
    if store is not None:   # the store's old copies too, so no words stay longer than ROOM_HOURS
        saving.add(task := asyncio.get_running_loop().create_task(_forget_old_copies()))
        task.add_done_callback(saving.discard)


def start(who: str, lang: str, voice: str = "") -> Room:
    tidy()
    if len(rooms) >= MAX_ROOMS:
        raise RoomError("Mythree is busy right now. Please try again later.")
    code = f"{secrets.randbelow(9000) + 1000}"
    while code in rooms:
        code = f"{secrets.randbelow(9000) + 1000}"
    room = rooms[code] = Room(code)
    room.people["a"] = {"who": who, "lang": lang}
    room.voices["a"] = voice
    room.seen["a"] = time.monotonic()
    save(room)
    return room


async def find(code: str) -> Room:
    code = code.strip()
    room = rooms.get(code)
    if not room and store is not None:   # Mythree restarted: the call may be in the store
        room = await _from_store(code)
    if not room or room.ended:
        raise RoomError(ENDED)
    return room


FULL = "This call already has two people. · ఈ కాల్‌లో ఇద్దరు ఉన్నారు."


def join(room: Room, place: str, who: str, lang: str, voice: str = "") -> str:
    """Take place `place` (from free_place): a new person, or someone coming back after leaving."""
    room.people[place] = {"who": who, "lang": lang}
    room.voices[place] = voice
    room.notes[place] = []   # an earlier phone's video notes are not for this one
    room.seen[place] = time.monotonic()
    room.changed()
    return place


def talking(room: Room, person: str, what: str = ""):
    """What this person is doing right now: "speaking", "translating", or "" (done). The other phone
    shows a sign, so a wait feels like waiting for an interpreter, not like a broken call (1 Nov).
    Memory only: not worth a copy in the store."""
    if room.talking.get(person, "") != what:
        room.talking[person] = what
        room.wake()


def end(room: Room):
    """Someone tapped End: the call ends for both phones (Vijaya, 1 Nov), and its words are forgotten.
    (The room stays in memory a while, marked ended, so a late request hears "the call has ended".)"""
    room.ended = True
    room.changed()   # the other phone, waiting for news, hears it at once


def add(room: Room, message: dict) -> dict:
    message["n"] = len(room.messages) + 1
    room.messages.append(message)
    for n in [n for n in room.sounds if n <= message["n"] - KEEP_SOUNDS]:
        del room.sounds[n]
    room.changed()
    return message


def note(room: Room, person: str, note: dict):
    """A video note (how to reach my phone) from `person`, kept for the other person to collect."""
    box = room.notes["b" if person == "a" else "a"]
    if len(box) >= MAX_NOTES:
        raise RoomError("Too many video notes for this call.")
    box.append({**note, "n": len(box) + 1})
    room.wake()   # not copied to the store: after a restart the phones simply say hello again


async def wait(room: Room, after: int, known: int, person: str = "", seen: int = 0) -> dict:
    """Answer as soon as there is news (a message after number `after`, more than `known` people,
    or a video note for `person` after number `seen`), or after WAIT_SECONDS."""
    if person in room.people:
        room.seen[person] = time.monotonic()   # this phone is still in the call
    if len(room.messages) <= after and len(room.people) <= known and not room.new_notes(person, seen):
        try:
            await asyncio.wait_for(room.news.wait(), WAIT_SECONDS)
        except TimeoutError:
            pass
    if person in room.people:
        room.seen[person] = time.monotonic()
    return room.state(after, person, seen)
