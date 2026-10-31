import asyncio

from fastapi.testclient import TestClient

from app import meta, rooms
from app.main import app

client = TestClient(app)


def remember_call_key(response):
    """Like a phone: keep the hidden key of the call just started, and send it with every request."""
    if response.request.method == "POST" and response.request.url.path == "/api/calls":
        response.read()
        if key := response.json().get("key"):
            client.headers["X-Mythree-Call-Key"] = key


client.event_hooks["response"].append(remember_call_key)


def no_passcode(monkeypatch):
    monkeypatch.setattr("app.main.secret", lambda name: None)


def test_phone_page_opens():
    assert client.get("/phone").status_code == 200


def test_two_phones_talk(monkeypatch):
    no_passcode(monkeypatch)
    heard = {}

    def fake_translate(text, lang, to, speaker, listener, history, work):
        heard.update(lang=lang, to=to, speaker=speaker, listener=listener, history=history)
        return "Hello Babu"
    monkeypatch.setattr("app.brain.translate", fake_translate)

    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    assert client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"}).json()["person"] == "b"

    news = client.get(f"/api/calls/{code}?after=0&known=1").json()   # Grandpa's phone learns he joined
    assert news["people"]["b"]["who"] == "Grandson"

    said = client.post(f"/api/calls/{code}/said", json={"person": "a", "text": "నమస్తే బాబు"}).json()
    assert said["translation"] == "Hello Babu" and said["to"] == "en" and said["n"] == 1
    assert heard["speaker"] == "Grandpa" and heard["listener"] == "Grandson"

    news = client.get(f"/api/calls/{code}?after=0&known=2").json()   # the grandson's phone gets it
    assert [m["translation"] for m in news["messages"]] == ["Hello Babu"]


def test_wrong_code_same_language_and_full_call(monkeypatch):
    no_passcode(monkeypatch)
    assert client.post("/api/calls/0000/join", json={"who": "x", "lang": "en"}).status_code == 404
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    assert client.post(f"/api/calls/{code}/join", json={"who": "x", "lang": "te"}).status_code == 400
    assert client.post(f"/api/calls/{code}/join", json={"who": "x", "lang": "en"}).status_code == 200
    assert client.post(f"/api/calls/{code}/join", json={"who": "y", "lang": "en"}).status_code == 409


def test_cannot_talk_before_the_other_person_joins(monkeypatch):
    no_passcode(monkeypatch)
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    assert client.post(f"/api/calls/{code}/said", json={"person": "a", "text": "నమస్తే"}).status_code == 409


def test_old_calls_are_forgotten(monkeypatch):
    room = rooms.start("Grandpa", "te")
    room.used -= rooms.ROOM_HOURS * 3600 + 1
    rooms.tidy()
    assert room.code not in rooms.rooms


# --- Each person's own voice --------------------------------------------------

def wav_of(seconds):
    return b"RIFF" + b"\0" * (40 + 16_000 * 2 * seconds)


def test_learning_a_voice_needs_consent(monkeypatch):
    no_passcode(monkeypatch)
    monkeypatch.setattr("app.voice.learn", lambda name, wav: "newVoice123")
    files = {"audio": ("v.wav", wav_of(30), "audio/wav")}
    assert client.post("/api/voices", files=files, data={"name": "Asha"}).status_code == 400
    reply = client.post("/api/voices", files=files, data={"name": "Asha", "consent": "true"})
    assert reply.json() == {"voice": "newVoice123"}


def test_a_voice_needs_at_least_20_seconds(monkeypatch):
    no_passcode(monkeypatch)
    files = {"audio": ("v.wav", wav_of(5), "audio/wav")}
    assert client.post("/api/voices", files=files, data={"consent": "true"}).status_code == 400


def test_family_voices_cannot_be_deleted_from_the_app(monkeypatch):
    no_passcode(monkeypatch)
    monkeypatch.setattr("app.main.family_voice", lambda person, service: "familyVoice1")
    deleted = []
    monkeypatch.setattr("app.voice.forget", deleted.append)
    assert client.delete("/api/voices/familyVoice1").status_code == 400
    assert client.delete("/api/voices/appVoice123").status_code == 200
    assert deleted == ["appVoice123"]


def test_each_person_is_heard_in_their_own_voice(monkeypatch):
    no_passcode(monkeypatch)
    monkeypatch.setattr("app.brain.translate", lambda *a: "Hello Babu")
    used = []
    monkeypatch.setattr("app.voice.speak_as", lambda text, lang, v: used.append((text, lang, v)) or iter([b"mp3"]))
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te", "voice": "grandpaVoice1"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en", "voice": "grandsonVoice1"})
    n = client.post(f"/api/calls/{code}/said", json={"person": "a", "text": "నమస్తే బాబు"}).json()["n"]
    assert client.post(f"/api/calls/{code}/speak", json={"n": n}).content == b"mp3"
    assert used == [("Hello Babu", "en", "grandpaVoice1")]
    news = client.get(f"/api/calls/{code}?after=0&known=2").json()
    assert "grandpaVoice1" not in str(news)   # voice IDs never go to the phones


def test_no_recorded_voice_means_the_standard_voice(monkeypatch):
    no_passcode(monkeypatch)
    monkeypatch.setattr("app.brain.translate", lambda *a: "Hello")
    monkeypatch.setattr("app.voice.secret", lambda name: "key")
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"})
    n = client.post(f"/api/calls/{code}/said", json={"person": "a", "text": "నమస్తే"}).json()["n"]
    assert client.post(f"/api/calls/{code}/speak", json={"n": n}).status_code == 503


def test_the_speakers_chosen_language_wins_over_the_letters(monkeypatch):
    no_passcode(monkeypatch)
    asked = {}
    monkeypatch.setattr("app.brain.translate", lambda text, lang, to, *a: asked.update(lang=lang, to=to) or "Yes or no?")
    code = client.post("/api/calls", json={"who": "Mother", "lang": "te"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Son", "lang": "en"})
    said = client.post(f"/api/calls/{code}/said", json={"person": "a", "text": "Niquea o no"}).json()
    assert asked == {"lang": "te", "to": "en"} and said["to"] == "en"   # Telugu in English letters still goes to English


class FakeStore:
    """Behaves like the Modal store (a modal.Dict), in memory."""

    def __init__(self):
        self.data = {}
        outer = self

        class Call:
            def __init__(self, fn):
                self.aio = fn
        async def put(k, v): outer.data[k] = v
        async def get(k): return outer.data.get(k)
        async def pop(k): return outer.data.pop(k, None)
        async def keys():
            for k in list(outer.data):
                yield k
        self.put, self.get, self.pop, self.keys = Call(put), Call(get), Call(pop), Call(keys)


def test_a_call_survives_a_restart(monkeypatch):
    no_passcode(monkeypatch)
    monkeypatch.setattr(rooms, "store", FakeStore())
    monkeypatch.setattr("app.brain.translate", lambda *a: "Hello Babu")
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"})
    client.post(f"/api/calls/{code}/said", json={"person": "a", "text": "నమస్తే బాబు"})
    del rooms.rooms[code]   # Mythree was updated: its memory is empty
    news = client.get(f"/api/calls/{code}?after=0&known=0").json()
    assert news["people"]["b"]["who"] == "Grandson"
    assert [m["translation"] for m in news["messages"]] == ["Hello Babu"]


def test_old_copies_are_deleted_from_the_store(monkeypatch):
    no_passcode(monkeypatch)
    store = FakeStore()
    store.data["1111"] = {"people": {}, "voices": {}, "messages": [], "saved": 0}   # long ago
    monkeypatch.setattr(rooms, "store", store)
    client.post("/api/calls", json={"who": "Grandpa", "lang": "te"})
    assert "1111" not in store.data
    assert client.post("/api/calls/1111/join", json={"who": "x", "lang": "en"}).status_code == 404


def test_the_phone_tells_the_ears_which_language_to_expect(monkeypatch):
    no_passcode(monkeypatch)
    expected = []
    monkeypatch.setattr("app.meta.transcribe", lambda wav, languages=None: expected.append(languages) or "నమస్తే")
    wav = {"audio": ("s.wav", b"RIFF" + b"\0" * 100, "audio/wav")}
    client.post("/api/hear", data={"lang": "te", "sure": "true"}, files=wav)   # the phone: one person
    client.post("/api/hear", data={"lang": "te"}, files=wav)                   # the laptop: both people
    assert expected == [["Telugu"], ["Telugu", "English"]]


def test_the_voice_is_made_early_once(monkeypatch):
    no_passcode(monkeypatch)
    monkeypatch.setattr("app.brain.translate", lambda *a: "Hello Babu")
    made = []
    monkeypatch.setattr("app.voice.speak_as", lambda text, lang, v: made.append(v) or iter([b"ID3", b"mp3"]))
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te", "voice": "grandpaVoice1"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"})
    n = client.post(f"/api/calls/{code}/said", json={"person": "a", "text": "నమస్తే బాబు"}).json()["n"]
    assert client.post(f"/api/calls/{code}/speak", json={"n": n}).content == b"ID3mp3"
    assert made == ["grandpaVoice1"]   # made once, as soon as the translation was ready


def test_one_trip_hears_translates_and_shares(monkeypatch):
    no_passcode(monkeypatch)
    told = []
    monkeypatch.setattr("app.meta.transcribe", lambda wav, languages=None: told.append(languages) or "नमस्ते బాబు")
    monkeypatch.setattr("app.brain.translate", lambda *a: "Hello Babu")
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"})
    m = client.post(f"/api/calls/{code}/heard", data={"person": "a"},
                    files={"audio": ("s.wav", b"RIFF" + b"\0" * 100, "audio/wav")}).json()
    assert (m["text"], m["translation"], m["to"]) == ("నమస్తే బాబు", "Hello Babu", "en")
    assert told == [["Telugu"]]
    news = client.get(f"/api/calls/{code}?after=0&known=0").json()   # the grandson's phone gets it
    assert [x["translation"] for x in news["messages"]] == ["Hello Babu"]


def test_a_call_needs_its_hidden_key(monkeypatch):
    no_passcode(monkeypatch)
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    for wrong in ({"X-Mythree-Call-Key": "guess"}, {"X-Mythree-Call-Key": ""}):
        assert client.post(f"/api/calls/{code}/join", json={"who": "x", "lang": "en"}, headers=wrong).status_code == 404
        assert client.get(f"/api/calls/{code}?after=0&known=0", headers=wrong).status_code == 404
    assert client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"}).status_code == 200


def test_the_invited_person_answers_with_one_tap(monkeypatch):
    no_passcode(monkeypatch)
    reply = client.post("/api/calls", json={
        "who": "Sam, the grandson", "lang": "en",
        "them": {"who": "the grandmother", "lang": "te", "caller": "సామ్"}}).json()
    code, key = reply["code"], reply["key"]
    grandma = {"X-Mythree-Call-Key": key}   # she has only the link
    news = client.get(f"/api/calls/{code}?after=0&known=0", headers=grandma).json()
    assert news["invite"]["caller"] == "సామ్" and "b" not in news["people"]
    joined = client.post(f"/api/calls/{code}/join", headers=grandma, json={"answer": True})
    assert joined.status_code == 200
    assert client.get(f"/api/calls/{code}?after=0&known=0", headers=grandma).json()["people"]["b"] == \
        {"who": "the grandmother", "lang": "te"}
    # without the link's key, nobody can read the call
    assert client.get(f"/api/calls/{code}?after=0&known=0", headers={"X-Mythree-Call-Key": "wrong"}).status_code == 404


def test_pages_always_load_the_newest_code():
    html = client.get("/phone").text
    assert 'src="/static/phone.js?v=' in html and 'href="/static/mythree-logo.svg?v=' in html
    assert "last-modified" not in client.get("/static/phone.js").headers   # no 1970 date for phones to trust


# --- The Try page ---------------------------------------------------------------

def test_try_page_any_language_into_english_in_your_own_voice(monkeypatch):
    no_passcode(monkeypatch)
    assert client.get("/try").status_code == 200
    monkeypatch.setattr("app.meta.transcribe", lambda wav, languages=None: "मेरा नाम प्रिया है")
    monkeypatch.setattr("app.brain.to_english", lambda text, work=None: "My name is Priya")
    m = client.post("/api/try/heard", files={"audio": ("s.wav", b"RIFF" + b"\0" * 100, "audio/wav")}).json()
    assert (m["text"], m["english"]) == ("मेरा नाम प्रिया है", "My name is Priya")   # Hindi stays Hindi here
    assert [w["model"] for w in m["meta"]] == ["Muse Voice Transcribe"]   # shown under the sentence
    spoken = []
    monkeypatch.setattr("app.voice.speak_as", lambda text, lang, v: spoken.append((text, lang, v)) or iter([b"mp3"]))
    assert client.post("/api/try/speak", json={"text": "My name is Priya", "voice": "visitorVoice1"}).content == b"mp3"
    assert spoken == [("My name is Priya", "en", "visitorVoice1")]


def test_try_voices_are_deleted_after_an_hour(monkeypatch):
    no_passcode(monkeypatch)
    import time
    forgotten, learned = [], []
    monkeypatch.setattr("app.voice.forget", forgotten.append)
    monkeypatch.setattr("app.voice.try_voices", lambda: {"oldVisitor1": 0, "newVisitor0": time.time()})
    monkeypatch.setattr("app.voice.learn", lambda name, wav: learned.append(name) or "newVisitor1")
    files = {"audio": ("v.wav", wav_of(25), "audio/wav")}
    assert client.post("/api/try/voice", files=files, data={"consent": "true"}).json() == {"voice": "newVisitor1"}
    assert forgotten == ["oldVisitor1"] and learned == ["Try visitor"]   # the recent visitor keeps their voice


def test_when_all_voice_places_are_taken_the_oldest_visitor_voice_makes_room(monkeypatch):
    no_passcode(monkeypatch)
    import time
    from app import voice
    forgotten, tries = [], []
    monkeypatch.setattr("app.voice.forget", forgotten.append)
    monkeypatch.setattr("app.voice.try_voices", lambda: {"visitorA": time.time() - 900, "visitorB": time.time() - 30})

    def learn(name, wav):   # ElevenLabs is full the first time
        tries.append(name)
        if len(tries) == 1:
            raise voice.VoiceError("ElevenLabs replied 400")
        return "newVisitor1"
    monkeypatch.setattr("app.voice.learn", learn)
    files = {"audio": ("v.wav", wav_of(25), "audio/wav")}
    assert client.post("/api/try/voice", files=files, data={"consent": "true"}).json() == {"voice": "newVisitor1"}
    assert forgotten == ["visitorA"]   # only the oldest visitor's voice, never a family voice


def test_try_page_tells_the_ears_the_visitors_language(monkeypatch):
    no_passcode(monkeypatch)
    told = []
    monkeypatch.setattr("app.meta.transcribe", lambda wav, languages=None: told.append(languages) or "ಮಂಚಿತನ")
    monkeypatch.setattr("app.brain.to_english", lambda text, work=None: "goodness")
    wav = {"audio": ("s.wav", b"RIFF" + b"\0" * 100, "audio/wav")}
    m = client.post("/api/try/heard", files=wav, data={"language": "Telugu"}).json()
    assert told == [["Telugu"]] and m["text"] == "మంచితన"   # Kannada letters that slipped through → Telugu
    assert client.post("/api/try/heard", files=wav, data={"language": "Klingon"}).status_code == 400


def test_visitors_still_testing_keep_their_voice_and_the_newcomer_hears_a_standard_voice(monkeypatch):
    no_passcode(monkeypatch)
    import time
    from app import voice
    forgotten = []
    monkeypatch.setattr("app.voice.forget", forgotten.append)
    monkeypatch.setattr("app.voice.try_voices", lambda: {"visitorA": time.time() - 120})   # still testing
    monkeypatch.setattr("app.voice.learn", lambda name, wav: (_ for _ in ()).throw(voice.VoiceError("full")))
    files = {"audio": ("v.wav", wav_of(25), "audio/wav")}
    reply = client.post("/api/try/voice", files=files, data={"consent": "true"})
    assert reply.status_code == 503 and "standard voice" in reply.json()["detail"]
    assert forgotten == []


def test_no_passcode_is_asked_for_calls_or_the_try_page(monkeypatch):
    monkeypatch.setattr("app.main.secret", lambda name: "family-passcode" if name == "MYTHREE_PASSCODE" else None)
    monkeypatch.setattr("app.meta.transcribe", lambda wav, languages=None: "Hola")
    monkeypatch.setattr("app.brain.to_english", lambda text, work=None: "Hello")
    wav = {"audio": ("s.wav", b"RIFF" + b"\0" * 100, "audio/wav")}
    assert client.post("/api/try/heard", files=wav).json()["english"] == "Hello"
    assert client.post("/api/calls", json={"who": "x", "lang": "te"}).status_code == 200


def test_the_free_page_can_greet_or_delete_only_visitor_voices(monkeypatch):
    no_passcode(monkeypatch)
    forgotten = []
    monkeypatch.setattr("app.voice.try_voices", lambda: {"visitorVoice1": 0})
    monkeypatch.setattr("app.voice.forget", forgotten.append)
    monkeypatch.setattr("app.voice.speak_as", lambda text, lang, v: iter([b"mp3"]))
    assert client.delete("/api/try/voice/familyVoice123").status_code == 404
    assert client.post("/api/try/hello/familyVoice123").status_code == 404
    assert client.post("/api/try/hello/visitorVoice1").content == b"mp3"
    assert client.delete("/api/try/voice/visitorVoice1").status_code == 200 and forgotten == ["visitorVoice1"]


def test_the_free_page_has_a_daily_limit(monkeypatch):
    no_passcode(monkeypatch)
    from app import main
    monkeypatch.setattr("app.meta.transcribe", lambda wav, languages=None: "Hola")
    monkeypatch.setattr("app.brain.to_english", lambda text, work=None: "Hello")
    monkeypatch.setattr(main, "try_today", {"day": __import__("time").strftime("%Y-%m-%d"), "count": main.TRY_PER_DAY})
    wav = {"audio": ("s.wav", b"RIFF" + b"\0" * 100, "audio/wav")}
    reply = client.post("/api/try/heard", files=wav)
    assert reply.status_code == 503 and "tomorrow" in reply.json()["detail"]


def test_family_characters_are_kept_for_the_family(monkeypatch):
    no_passcode(monkeypatch)
    monkeypatch.setattr("app.voice.characters_left", lambda: 19_000)   # under the family's reserve
    spoken = []
    monkeypatch.setattr("app.voice.speak_as", lambda *a: spoken.append(a) or iter([b"mp3"]))
    reply = client.post("/api/try/speak", json={"text": "Hello", "voice": "visitorVoice1"})
    assert reply.status_code == 503 and "standard voice" in reply.json()["detail"] and spoken == []
    files = {"audio": ("v.wav", wav_of(25), "audio/wav")}
    assert client.post("/api/try/voice", files=files, data={"consent": "true"}).status_code == 503


def test_visitors_hold_at_most_seven_voice_places(monkeypatch):
    no_passcode(monkeypatch)
    import time
    learned = []
    monkeypatch.setattr("app.voice.try_voices", lambda: {f"visitor{i}": time.time() - 60 for i in range(7)})
    monkeypatch.setattr("app.voice.forget", lambda v: None)
    monkeypatch.setattr("app.voice.learn", lambda name, wav: learned.append(name) or "newVisitor1")
    files = {"audio": ("v.wav", wav_of(25), "audio/wav")}
    reply = client.post("/api/try/voice", files=files, data={"consent": "true"})
    assert reply.status_code == 503 and learned == []   # all 7 visitors are still testing: a standard voice
    assert "Try my own voice again" in reply.json()["detail"]


def test_guessing_the_passcode_is_stopped_after_ten_wrong_tries(monkeypatch):
    monkeypatch.setattr("app.main.secret", lambda name: "family-passcode" if name == "MYTHREE_PASSCODE" else None)
    for i in range(10):
        assert client.get("/api/stats", headers={"X-Mythree-Passcode": f"guess{i}"}).status_code == 401
    # the 11th try is refused, even with the right passcode, until the hour is up
    assert client.get("/api/stats", headers={"X-Mythree-Passcode": "family-passcode"}).status_code == 429
    assert client.get("/api/hello").status_code != 429   # the rest of Mythree is never locked


def test_a_page_asking_without_a_passcode_is_not_a_wrong_guess(monkeypatch):
    monkeypatch.setattr("app.main.secret", lambda name: "family-passcode" if name == "MYTHREE_PASSCODE" else None)
    monkeypatch.setattr("app.voice.try_voices", lambda: {})
    monkeypatch.setattr("app.voice.characters_left", lambda: 0)
    for _ in range(15):
        assert client.get("/api/stats", headers={"X-Mythree-Passcode": ""}).status_code == 401
    assert client.get("/api/stats", headers={"X-Mythree-Passcode": "family-passcode"}).status_code != 401


def test_the_try_page_closes_by_itself_after_the_hackathon_week(monkeypatch):
    no_passcode(monkeypatch)
    from app import main
    assert "Lend Mythree your voice" in client.get("/try").text
    monkeypatch.setattr(main, "TRY_OPEN_UNTIL", 0)   # the deadline has passed
    assert "Thank you for trying Mythree" in client.get("/try").text
    reply = client.post("/api/try/heard", files={"audio": ("s.wav", b"RIFF" + b"\0" * 100, "audio/wav")})
    assert reply.status_code == 410 and "closed" in reply.json()["detail"]


def test_the_visitors_page_counts_numbers_only(monkeypatch):
    no_passcode(monkeypatch)
    from app import main
    main.stats_days.clear()
    monkeypatch.setattr("app.meta.transcribe", lambda wav, languages=None: "నమస్తే")
    monkeypatch.setattr("app.brain.to_english", lambda text, work=None: "Hello")
    monkeypatch.setattr("app.voice.try_voices", lambda: {"visitor1": 0})
    wav = {"audio": ("s.wav", b"RIFF" + b"\0" * 100, "audio/wav")}
    client.post("/api/try/heard", files=wav, data={"language": "Telugu"})
    client.post("/api/try/heard", files=wav)
    s = client.get("/api/stats").json()
    assert s["today"]["sentences"] == 2 and s["week"]["languages"] == {"Telugu": 1, "Found by itself": 1}
    assert s["voices_in_use"] == 1 and s["characters_left"] == 30_000
    assert "నమస్తే" not in str(s) and "Hello" not in str(s)   # never the words


def test_the_visitors_page_needs_the_passcode(monkeypatch):
    monkeypatch.setattr("app.main.secret", lambda name: "family-passcode" if name == "MYTHREE_PASSCODE" else None)
    assert client.get("/api/stats", headers={"X-Mythree-Passcode": ""}).status_code == 401


class PretendLiveEars:
    """Meta's live ears, pretend: hears the pieces, says the words so far, and the final words at the end."""
    heard: list = []
    fail = False

    def __init__(self, languages):
        self.languages, self.ended = languages, asyncio.Event()
        PretendLiveEars.told = languages

    async def __aenter__(self):
        if PretendLiveEars.fail:
            raise meta.MetaError("Meta is down")
        return self

    async def __aexit__(self, *_):
        pass

    async def hear(self, pcm):
        PretendLiveEars.heard.append(pcm)

    async def end(self):
        self.ended.set()

    async def words(self):
        yield "नमस्ते", False
        await self.ended.wait()
        yield "नमस्ते బాబు", True


def live_call(monkeypatch):
    no_passcode(monkeypatch)
    PretendLiveEars.heard, PretendLiveEars.fail = [], False
    monkeypatch.setattr("app.meta.LiveEars", PretendLiveEars)
    monkeypatch.setattr("app.brain.translate", lambda *a: "Hello Babu")
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"})
    return code, client.headers["X-Mythree-Call-Key"]


def test_live_listening_hears_while_speaking(monkeypatch):
    code, key = live_call(monkeypatch)
    with client.websocket_connect(f"/api/calls/{code}/live") as line:
        line.send_json({"key": key, "person": "a"})
        line.send_bytes(b"\1\0" * 1280)
        assert line.receive_json() == {"partial": "నమస్తే"}   # the words so far, while still talking
        line.send_bytes(b"\2\0" * 1280)
        line.send_json({"end": True})
        m = line.receive_json()
    assert (m["text"], m["translation"], m["to"]) == ("నమస్తే బాబు", "Hello Babu", "en")
    assert PretendLiveEars.told == ["Telugu"] and len(PretendLiveEars.heard) == 2
    news = client.get(f"/api/calls/{code}?after=0&known=0").json()   # the grandson's phone gets it
    assert [x["translation"] for x in news["messages"]] == ["Hello Babu"]


def test_both_phones_see_which_meta_models_did_the_work(monkeypatch):
    code, key = live_call(monkeypatch)

    def translate(*a):
        a[-1].append({"job": "translate", "model": "Muse Spark Open", "where": "on Baseten", "s": 1.3})
        return "Hello Babu"
    monkeypatch.setattr("app.brain.translate", translate)
    with client.websocket_connect(f"/api/calls/{code}/live") as line:
        line.send_json({"key": key, "person": "a"})
        line.receive_json()
        line.send_json({"end": True})
        m = line.receive_json()
    assert [(w["model"], w["where"]) for w in m["meta"]] == [("Muse Voice Transcribe", "live"),
                                                             ("Muse Spark Open", "on Baseten")]
    news = client.get(f"/api/calls/{code}?after=0&known=0").json()   # the grandson's phone sees the same
    assert news["messages"][0]["meta"] == m["meta"]


def test_live_listening_needs_the_hidden_key(monkeypatch):
    code, _ = live_call(monkeypatch)
    with client.websocket_connect(f"/api/calls/{code}/live") as line:
        line.send_json({"key": "guess", "person": "a"})
        assert "error" in line.receive_json()
    assert PretendLiveEars.heard == []


def test_when_live_listening_fails_the_phone_is_told_to_use_the_old_way(monkeypatch):
    code, key = live_call(monkeypatch)
    PretendLiveEars.fail = True
    with client.websocket_connect(f"/api/calls/{code}/live") as line:
        line.send_json({"key": key, "person": "a"})
        assert "error" in line.receive_json()
    assert client.get(f"/api/calls/{code}?after=0&known=0").json()["messages"] == []


# --- Seeing each other (video) --------------------------------------------------------

def video_call(monkeypatch):
    no_passcode(monkeypatch)
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"})
    return code


def test_the_phones_pass_video_notes_through_the_call(monkeypatch):
    code = video_call(monkeypatch)
    client.post(f"/api/calls/{code}/video", json={"person": "b", "kind": "ready"})
    news = client.get(f"/api/calls/{code}?after=0&known=2&person=a&notes=0").json()   # Grandpa's phone
    assert [(n["kind"], n["n"]) for n in news["notes"]] == [("ready", 1)]

    offer = {"person": "a", "kind": "offer", "id": 7, "sdp": "v=0 grandpa"}
    assert client.post(f"/api/calls/{code}/video", json=offer).json() == {"ok": True}
    news = client.get(f"/api/calls/{code}?after=0&known=2&person=b&notes=0").json()   # the grandson's phone
    assert news["notes"][0]["kind"] == "offer" and news["notes"][0]["id"] == 7
    assert news["notes"][0]["sdp"] == "v=0 grandpa"
    # notes already seen are not sent again, and a note never comes back to its own sender
    # (known=1: answer at once, as there is "news" of a second person)
    assert client.get(f"/api/calls/{code}?after=0&known=1&person=b&notes=1").json()["notes"] == []
    assert client.get(f"/api/calls/{code}?after=0&known=1&person=a&notes=1").json()["notes"] == []


def test_a_waiting_phone_wakes_up_for_a_video_note(monkeypatch):
    code = video_call(monkeypatch)
    room = rooms.rooms[code]

    async def wait_and_note():
        waiting = asyncio.create_task(rooms.wait(room, 0, 2, "b", 0))
        await asyncio.sleep(0.05)
        rooms.note(room, "a", {"kind": "ready"})
        return await asyncio.wait_for(waiting, 2)
    assert asyncio.run(wait_and_note())["notes"][0]["kind"] == "ready"


def test_after_a_restart_a_phone_gets_the_new_notes_from_the_start(monkeypatch):
    code = video_call(monkeypatch)
    client.post(f"/api/calls/{code}/video", json={"person": "a", "kind": "ready"})
    # the phone had seen 5 notes before the restart; the new list has only 1
    assert len(client.get(f"/api/calls/{code}?after=0&known=2&person=b&notes=5").json()["notes"]) == 1


def test_video_notes_need_the_hidden_key_and_are_checked(monkeypatch):
    code = video_call(monkeypatch)
    note = {"person": "a", "kind": "ready"}
    assert client.post(f"/api/calls/{code}/video", json=note, headers={"X-Mythree-Call-Key": "wrong"}).status_code == 404
    assert client.post(f"/api/calls/{code}/video", json={**note, "kind": "virus"}).status_code == 422
    assert client.post(f"/api/calls/{code}/video", json={**note, "person": "z"}).status_code == 400
    assert client.post(f"/api/calls/{code}/video", json={**note, "sdp": "x" * 20001}).status_code == 422
    for _ in range(rooms.MAX_NOTES):
        client.post(f"/api/calls/{code}/video", json=note)
    assert client.post(f"/api/calls/{code}/video", json=note).status_code == 429


def test_an_invited_grandparent_sends_video_notes_without_the_passcode(monkeypatch):
    no_passcode(monkeypatch)
    code = client.post("/api/calls", json={"who": "Grandson", "lang": "en"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandpa", "lang": "te"})
    monkeypatch.setattr("app.main.secret", lambda name: "family-passcode" if name == "MYTHREE_PASSCODE" else None)
    grandpa = {"X-Mythree-Passcode": ""}   # he has only the link, with its hidden key
    assert client.post(f"/api/calls/{code}/video", json={"person": "b", "kind": "ready"}, headers=grandpa).status_code == 200
    assert client.get(f"/api/calls/{code}/ice", headers=grandpa).status_code == 200


def test_without_the_relay_key_the_phones_try_a_direct_line(monkeypatch):
    code = video_call(monkeypatch)
    servers = client.get(f"/api/calls/{code}/ice").json()["iceServers"]
    assert all(u.startswith("stun:") for s in servers for u in s["urls"])


def test_with_the_relay_key_the_phones_get_the_relay_without_port_53(monkeypatch):
    code = video_call(monkeypatch)
    monkeypatch.setattr("app.main.secret", lambda name: {"TURN_KEY_ID": "k", "TURN_KEY_API_TOKEN": "t"}.get(name))
    asked = {}

    class Reply:
        status_code = 201

        def json(self):
            return {"iceServers": [{"urls": ["stun:stun.cloudflare.com:3478", "stun:stun.cloudflare.com:53"]},
                                   {"urls": ["turn:turn.cloudflare.com:3478?transport=udp",
                                             "turn:turn.cloudflare.com:53?transport=udp"],
                                    "username": "u", "credential": "c"}]}

    class Client:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        async def post(self, url, json, headers):
            asked.update(url=url, ttl=json["ttl"], auth=headers["Authorization"])
            return Reply()
    monkeypatch.setattr("app.main.httpx.AsyncClient", Client)
    servers = client.get(f"/api/calls/{code}/ice").json()["iceServers"]
    assert asked["url"].endswith("/keys/k/credentials/generate-ice-servers") and asked["auth"] == "Bearer t"
    assert servers[1]["urls"] == ["turn:turn.cloudflare.com:3478?transport=udp"] and servers[1]["credential"] == "c"
    assert servers[0]["urls"] == ["stun:stun.cloudflare.com:3478"]


def test_an_echo_is_dropped_but_a_real_reply_is_kept(monkeypatch):
    # 30 Oct: the grandson's phone heard the English played on the other phone and sent it again, 5 times.
    no_passcode(monkeypatch)
    english = {"అనుకున్నవన్నీ జరగవు": "Not everything we hope for happens."}
    monkeypatch.setattr("app.brain.translate", lambda text, *rest: english.get(text, "ఇది కొత్త మాట"))
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"})

    first = client.post(f"/api/calls/{code}/said", json={"person": "a", "text": "అనుకున్నవన్నీ జరగవు"}).json()
    assert first["n"] == 1
    # grandpa's phone hears the English played on the grandson's phone: an echo, dropped
    again = client.post(f"/api/calls/{code}/said", json={"person": "a", "text": "not everything we hope for happens"}).json()
    assert again["text"] == "" and again.get("echo")
    # the grandson's phone hears it too: also dropped
    assert client.post(f"/api/calls/{code}/said", json={"person": "b", "text": "Not everything we hoped for happens."}).json()["text"] == ""
    # a real reply, and a short one that repeats words, are kept
    assert client.post(f"/api/calls/{code}/said", json={"person": "b", "text": "Grandpa, that is so true, I miss you"}).json()["n"] == 2
    assert client.post(f"/api/calls/{code}/said", json={"person": "b", "text": "how are you"}).json()["n"] == 3
    news = client.get(f"/api/calls/{code}?after=0&known=2").json()
    assert len(news["messages"]) == 3


def test_an_old_sentence_said_again_later_is_not_an_echo(monkeypatch):
    import time
    no_passcode(monkeypatch)
    monkeypatch.setattr("app.brain.translate", lambda text, *rest: "I will come to India next summer")
    code = client.post("/api/calls", json={"who": "Grandpa", "lang": "te"}).json()["code"]
    client.post(f"/api/calls/{code}/join", json={"who": "Grandson", "lang": "en"})
    client.post(f"/api/calls/{code}/said", json={"person": "b", "text": "I will come to India next summer"})
    later = time.time() + 31
    monkeypatch.setattr("app.main.time.time", lambda: later)
    assert client.post(f"/api/calls/{code}/said", json={"person": "b", "text": "I will come to India next summer"}).json()["n"] == 2


from app.voice import still_there as REAL_STILL_THERE   # (before the tests' stand-in replaces it)


def test_a_voice_that_is_gone_is_not_used_and_the_phone_is_told(monkeypatch):
    # 31 Oct: a phone remembered a voice ElevenLabs no longer had, so every sentence quietly used the standard voice.
    no_passcode(monkeypatch)
    monkeypatch.setattr("app.voice.still_there", lambda v: v != "deletedVoice1")
    start = client.post("/api/calls", json={"who": "Grandpa", "lang": "te", "voice": "grandpaVoice1"}).json()
    assert start["voice_gone"] is False
    joined = client.post(f"/api/calls/{start['code']}/join", json={"who": "Grandson", "lang": "en", "voice": "deletedVoice1"}).json()
    assert joined["voice_gone"] is True
    from app import rooms
    assert rooms.rooms[start["code"]].voices == {"a": "grandpaVoice1", "b": ""}
    no_voice = client.post("/api/calls", json={"who": "Grandma", "lang": "te"}).json()
    assert no_voice["voice_gone"] is False   # nothing recorded is not "gone"


def test_still_there_asks_elevenlabs(monkeypatch):
    from app import voice
    monkeypatch.setattr("app.voice.still_there", REAL_STILL_THERE)   # the real one, not the tests' stand-in
    monkeypatch.setattr("app.voice.secret", lambda name: "key")
    answers = {"live1": 200, "gone1": 400, "busy1": 503}
    monkeypatch.setattr("app.voice.httpx.get", lambda url, **kw: type("R", (), {"status_code": answers[url.rsplit("/", 1)[1]]})())
    assert voice.still_there("live1") and not voice.still_there("gone1") and voice.still_there("busy1")
    assert not voice.still_there("")
