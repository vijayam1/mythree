import json

from fastapi.testclient import TestClient

from app import settings, voice
from app.main import app

client = TestClient(app)


def test_speak_streams_the_sound(monkeypatch):
    monkeypatch.setattr(voice, "speak", lambda text, lang: iter([b"ID3", b"...", b"mp3"]))
    reply = client.post("/api/speak", json={"text": "Dear, have you eaten?", "lang": "en"})
    assert reply.status_code == 200
    assert reply.headers["content-type"] == "audio/mpeg"
    assert reply.content == b"ID3...mp3"


def test_english_is_spoken_in_the_grandfathers_voice():
    assert voice.owner("en") == "grandfather"
    assert voice.owner("te") == "grandson"


def test_no_own_voice_tells_the_page_to_use_the_standard_voice(monkeypatch):
    def broken(text, lang):
        raise voice.VoiceError("no voice")
    monkeypatch.setattr(voice, "speak", broken)
    assert client.post("/api/speak", json={"text": "hi", "lang": "en"}).status_code == 503


def test_unknown_language_is_refused():
    assert client.post("/api/speak", json={"text": "hi", "lang": "xx"}).status_code == 400


def test_voice_ids_come_from_the_private_file(monkeypatch, tmp_path):
    voices = tmp_path / "voices.json"
    voices.write_text(json.dumps({"grandfather": "svc-1"}))
    monkeypatch.setattr(settings, "VOICES_FILE", voices)
    assert settings.voice_id("grandfather") == "svc-1"
    assert settings.voice_id("grandson") is None


def test_missing_voice_is_a_voice_error(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "voice_id", lambda person: None)
    try:
        voice.speak("hi", "en")
        assert False, "should have failed"
    except voice.VoiceError:
        pass
