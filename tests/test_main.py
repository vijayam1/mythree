from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_page_shows_mythree():
    response = client.get("/")
    assert response.status_code == 200
    assert "Mythree" in response.text


def test_health_check():
    assert client.get("/health").json() == {"status": "ok", "name": "Mythree"}


def test_page_and_code_are_never_stale():
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert client.get("/static/ears.js").headers["cache-control"] == "no-cache"


def test_no_passcode_needed_when_none_is_set(monkeypatch):
    monkeypatch.delenv("MYTHREE_PASSCODE", raising=False)
    monkeypatch.setattr("app.main.secret", lambda name: None)
    assert client.get("/api/hello").json() == {"ok": True}


def test_only_the_visitors_numbers_need_the_passcode(monkeypatch):
    monkeypatch.setattr("app.main.secret", lambda name: "kokila" if name == "MYTHREE_PASSCODE" else None)
    assert client.get("/api/hello").status_code == 200   # Mythree itself is open to everyone
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/stats", headers={"X-Mythree-Passcode": "wrong"}).status_code == 401
    assert client.get("/").status_code == 200


def test_too_many_requests_are_slowed_down(monkeypatch):
    from app import main
    monkeypatch.setattr("app.main.secret", lambda name: None)
    monkeypatch.setattr(main, "REQUESTS_PER_MINUTE", 3)
    main.recent.clear()
    codes = [client.get("/api/hello").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    main.recent.clear()


def test_a_calls_news_and_video_notes_are_not_counted(monkeypatch):
    # Two phones on one Wi-Fi share an address: their "anything new?" and video notes mustn't use up the limit.
    from app import main
    monkeypatch.setattr("app.main.secret", lambda name: None)
    monkeypatch.setattr(main, "REQUESTS_PER_MINUTE", 3)
    main.recent.clear()
    paths = ["/api/calls/1234", "/api/calls/1234/ice"] * 5
    assert all(client.get(p).status_code != 429 for p in paths)
    assert client.post("/api/calls/1234/video", json={}).status_code != 429
    assert [client.get("/api/hello").status_code for _ in range(4)] == [200, 200, 200, 429]   # the rest still are
    main.recent.clear()


def test_voices_and_phrase_book_can_come_from_secrets(monkeypatch):
    from app import brain, settings
    monkeypatch.setenv("MYTHREE_VOICES", '{"a": {"elevenlabs": "el-9"}}')
    monkeypatch.setenv("MYTHREE_PHRASEBOOK", "| 1 | Hi | నమస్తే |")
    assert settings.voice_id("a", "elevenlabs") == "el-9"
    assert brain.family_examples().endswith("Hi → నమస్తే")
