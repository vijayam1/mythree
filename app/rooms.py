"""Mythree calls: two phones, each person in their own language.

One person starts a call and gets a short code (like 4821). The other person
joins with that code. Each phone listens to its own person; Mythree translates
each sentence and the other phone speaks it, in the speaker's own voice.

Rooms live only in the server's memory. Nothing is written to disk, and a room
is forgotten a few hours after its last use.
"""

import asyncio
import secrets
import time

ROOM_HOURS = 3      # a room nobody has used for this long is forgotten
MAX_ROOMS = 100     # enough for testers and judges; stops strangers filling the memory
WAIT_SECONDS = 25   # a phone waits this long for news before asking again


class RoomError(Exception):
    """The room can't do that (full, unknown, too many rooms)."""


class Room:
    def __init__(self, code: str):
        self.code = code
        self.people: dict[str, dict] = {}    # "a" started the call, "b" joined it
        self.voices: dict[str, str] = {}     # each person's own voice (its ID), never sent to the phones
        self.messages: list[dict] = []
        self.news = asyncio.Event()          # set whenever something changes, to wake waiting phones
        self.used = time.monotonic()

    def other(self, person: str) -> dict | None:
        return self.people.get("b" if person == "a" else "a")

    def changed(self):
        """Wake every phone that is waiting, then get ready for the next change."""
        self.used = time.monotonic()
        self.news.set()
        self.news = asyncio.Event()

    def state(self, after: int = 0) -> dict:
        return {"code": self.code, "people": self.people, "messages": self.messages[after:]}


rooms: dict[str, Room] = {}


def tidy():
    old = [code for code, room in rooms.items() if time.monotonic() - room.used > ROOM_HOURS * 3600]
    for code in old:
        del rooms[code]


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
    return room


def find(code: str) -> Room:
    room = rooms.get(code.strip())
    if not room:
        raise RoomError("No call with that code. Please check the number.")
    return room


def join(room: Room, who: str, lang: str, voice: str = "") -> str:
    if "b" in room.people:
        raise RoomError("This call already has two people.")
    room.people["b"] = {"who": who, "lang": lang}
    room.voices["b"] = voice
    room.changed()
    return "b"


def add(room: Room, message: dict) -> dict:
    message["n"] = len(room.messages) + 1
    room.messages.append(message)
    room.changed()
    return message


async def wait(room: Room, after: int, known: int) -> dict:
    """Answer as soon as there is news (a message after number `after`, or more than `known` people),
    or after WAIT_SECONDS."""
    if len(room.messages) <= after and len(room.people) <= known:
        try:
            await asyncio.wait_for(room.news.wait(), WAIT_SECONDS)
        except TimeoutError:
            pass
    return room.state(after)
