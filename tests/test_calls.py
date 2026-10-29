from fastapi.testclient import TestClient

from app import rooms
from app.main import app

client = TestClient(app)


def no_passcode(monkeypatch):
    monkeypatch.setattr("app.main.secret", lambda name: None)


def test_phone_page_opens():
    assert client.get("/phone").status_code == 200


def test_two_phones_talk(monkeypatch):
    no_passcode(monkeypatch)
    heard = {}

    def fake_translate(text, lang, to, speaker, listener, history):
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
