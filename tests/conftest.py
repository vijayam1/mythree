import pytest

from app import main, voice


@pytest.fixture(autouse=True)
def fresh_request_counts():
    """Every test starts with a clean per-minute request count."""
    main.recent.clear()
    main.wrong.clear()
    yield
    main.recent.clear()
    main.wrong.clear()


@pytest.fixture(autouse=True)
def plenty_of_characters(monkeypatch):
    """Tests never ask ElevenLabs how many characters are left: there are always plenty."""
    monkeypatch.setattr("app.voice.characters_left", lambda: 30_000)


@pytest.fixture(autouse=True)
def recorded_voices_are_still_there(monkeypatch):
    """Tests never ask ElevenLabs whether a recorded voice still exists: it does."""
    monkeypatch.setattr("app.voice.still_there", lambda voice_id: bool(voice_id))


@pytest.fixture(autouse=True)
def no_real_voices(monkeypatch):
    """Tests never make a real voice at ElevenLabs (it costs characters): every call now gets a voice,
    the standard one if nobody recorded theirs. A test that needs a voice pretends to be ElevenLabs."""
    def offline(name, *a, **k):
        raise voice.VoiceError(f"Tests don't reach {name}")
    monkeypatch.setattr("app.voice._stream", offline)
