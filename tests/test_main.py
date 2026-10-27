from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_page_shows_mythree():
    response = client.get("/")
    assert response.status_code == 200
    assert "Mythree" in response.text


def test_health_check():
    assert client.get("/health").json() == {"status": "ok", "name": "Mythree"}
