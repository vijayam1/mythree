from fastapi.testclient import TestClient

from app import meta
from app.main import MAX_SENTENCE_BYTES, app
from app.telugu import devanagari_to_telugu

client = TestClient(app)
WAV = b"RIFF" + b"\0" * 100  # enough to look like a sound file; Meta is replaced below


def send(wav=WAV, lang="te"):
    return client.post("/api/hear", files={"audio": ("s.wav", wav, "audio/wav")}, data={"lang": lang})


def test_hindi_letters_become_telugu():
    assert devanagari_to_telugu("नमस्ते, నా పేరు విజయ।") == "నమస్తే, నా పేరు విజయ."


def test_telugu_and_english_are_left_alone():
    assert devanagari_to_telugu("ఎలా ఉన్నారు? I miss you.") == "ఎలా ఉన్నారు? I miss you."


def test_hear_returns_telugu_words(monkeypatch):
    monkeypatch.setattr(meta, "transcribe", lambda wav, languages=None: "नमस्ते తాతయ్య గారు")
    reply = send()
    assert reply.status_code == 200
    assert reply.json() == {"text": "నమస్తే తాతయ్య గారు", "lang": "te"}


def test_english_is_not_changed(monkeypatch):
    monkeypatch.setattr(meta, "transcribe", lambda wav, languages=None: "Hi Grandpa")
    assert send(lang="en").json()["text"] == "Hi Grandpa"


def test_the_words_decide_the_language_not_the_card(monkeypatch):
    monkeypatch.setattr(meta, "transcribe", lambda wav, languages=None: "నాన్నా, భోజనం చేశావా? Dallas లో ఎండలు")
    assert send(lang="en").json()["lang"] == "te"


def test_unknown_language_is_refused():
    assert send(lang="xx").status_code == 400


def test_not_a_sound_file_is_refused():
    assert send(wav=b"hello").status_code == 400


def test_very_long_sentence_is_refused():
    assert send(wav=b"RIFF" + b"\0" * MAX_SENTENCE_BYTES).status_code == 413


def test_meta_trouble_gives_a_friendly_message(monkeypatch):
    def broken(wav, languages=None):
        raise meta.MetaError("down")
    monkeypatch.setattr(meta, "transcribe", broken)
    reply = send()
    assert reply.status_code == 502
    assert "మళ్ళీ" in reply.json()["detail"]


def test_gujarati_letters_become_telugu():
    assert devanagari_to_telugu("અને") == "అనే"   # the ears wrote Telugu "అనే" in Gujarati letters
