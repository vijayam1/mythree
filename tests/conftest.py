import pytest

from app import main


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
