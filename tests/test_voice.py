import json

from fastapi.testclient import TestClient

from app import settings, voice
from app.main import app

client = TestClient(app)


def test_speak_streams_the_sound(monkeypatch):
    monkeypatch.setattr(voice, "speak", lambda text, lang, person: iter([b"ID3", b"...", b"mp3"]))
    reply = client.post("/api/speak", json={"text": "Dear, have you eaten?", "lang": "en", "person": "a"})
    assert reply.status_code == 200
    assert reply.headers["content-type"] == "audio/mpeg"
    assert reply.content == b"ID3...mp3"


def test_the_speakers_own_voice_is_used_elevenlabs_first(monkeypatch):
    asked = []
    monkeypatch.setattr(voice, "voice_id", lambda person, service: asked.append((person, service)))
    try:
        voice.speak("hi", "en", "b")
    except voice.VoiceError:
        pass
    assert asked == [("b", "elevenlabs"), ("b", "sarvam")]


def test_sarvam_takes_over_when_elevenlabs_fails(monkeypatch):
    def broken(text, lang, person):
        raise voice.VoiceError("ElevenLabs replied 401")
    monkeypatch.setattr(voice, "_elevenlabs", broken)
    monkeypatch.setattr(voice, "_sarvam", lambda text, lang, person: iter([b"sarvam"]))
    assert list(voice.speak("hi", "te", "a")) == [b"sarvam"]


def test_unknown_person_is_refused():
    assert client.post("/api/speak", json={"text": "hi", "lang": "en", "person": "z"}).status_code == 400


def test_no_own_voice_tells_the_page_to_use_the_standard_voice(monkeypatch):
    def broken(text, lang, person):
        raise voice.VoiceError("no voice")
    monkeypatch.setattr(voice, "speak", broken)
    assert client.post("/api/speak", json={"text": "hi", "lang": "en", "person": "a"}).status_code == 503


def test_unknown_language_is_refused():
    assert client.post("/api/speak", json={"text": "hi", "lang": "xx", "person": "a"}).status_code == 400


def test_voice_ids_come_from_the_private_file(monkeypatch, tmp_path):
    voices = tmp_path / "voices.json"
    voices.write_text(json.dumps({"a": {"elevenlabs": "el-1", "sarvam": "svc-1"}}))
    monkeypatch.setattr(settings, "VOICES_FILE", voices)
    assert settings.voice_id("a", "elevenlabs") == "el-1"
    assert settings.voice_id("a", "sarvam") == "svc-1"
    assert settings.voice_id("b", "elevenlabs") is None


def test_missing_voice_is_a_voice_error(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "voice_id", lambda person, service: None)
    try:
        voice.speak("hi", "en", "a")
        assert False, "should have failed"
    except voice.VoiceError:
        pass
