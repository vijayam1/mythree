from fastapi.testclient import TestClient

from app import brain, meta
from app.main import app

client = TestClient(app)


def test_translate_telugu_for_the_grandson(monkeypatch):
    seen = {}

    def fake_chat(messages):
        seen["messages"] = messages
        return '"Dear, have you eaten?"'
    monkeypatch.setattr(meta, "chat", fake_chat)
    reply = client.post("/api/translate", json={"text": "నాన్నా, భోజనం చేశావా?", "lang": "te", "to": "en", "who": "Grandpa", "listener": "Ravi"})
    assert reply.json() == {"text": "Dear, have you eaten?", "lang": "en"}
    assert "Grandpa (Telugu) says" in seen["messages"][-1]["content"]
    assert "Translate into English, for Ravi" in seen["messages"][-1]["content"]


def test_translate_english_for_the_grandfather(monkeypatch):
    monkeypatch.setattr(meta, "chat", lambda m: "Translation: నమస్తే తాతగారు")
    reply = client.post("/api/translate", json={"text": "Hi Grandpa", "lang": "en", "to": "te"})
    assert reply.json() == {"text": "నమస్తే తాతగారు", "lang": "te"}


def test_earlier_sentences_are_given_as_context(monkeypatch):
    seen = {}
    monkeypatch.setattr(meta, "chat", lambda m: seen.setdefault("m", m) and "ok")
    client.post("/api/translate", json={
        "text": "Yes, I ate", "lang": "en", "to": "te", "who": "Ravi",
        "history": [{"text": "భోజనం చేశావా?", "lang": "te", "who": "Grandpa"}],
    })
    assert "Grandpa: భోజనం చేశావా?" in seen["m"][1]["content"]


def test_rules_keep_respect_for_elders():
    assert "మీరు" in brain.RULES and "తాతగారు" in brain.RULES


def test_names_are_optional(monkeypatch):
    seen = {}
    monkeypatch.setattr(meta, "chat", lambda m: seen.setdefault("m", m) and "ok")
    client.post("/api/translate", json={"text": "hi", "lang": "en", "to": "te"})
    assert "One person (English) says: hi" in seen["m"][-1]["content"]


def test_same_language_twice_is_refused():
    assert client.post("/api/translate", json={"text": "hi", "lang": "en", "to": "en"}).status_code == 400


def test_works_without_a_phrase_book(monkeypatch, tmp_path):
    monkeypatch.setattr(brain, "PHRASEBOOK", tmp_path / "missing.md")
    assert brain.family_examples() == ""


def test_phrase_book_rows_become_examples(monkeypatch, tmp_path):
    book = tmp_path / "book.md"
    book.write_text("| # | Grandson says | Telugu |\n|---|---|---|\n| 1 | Hi | నమస్తే |\n")
    monkeypatch.setattr(brain, "PHRASEBOOK", book)
    assert brain.family_examples().endswith("Hi → నమస్తే")


def test_empty_or_unknown_input_is_refused():
    assert client.post("/api/translate", json={"text": "", "lang": "te", "to": "en"}).status_code == 422
    assert client.post("/api/translate", json={"text": "hi", "lang": "xx", "to": "en"}).status_code == 400


def test_meta_trouble_gives_a_friendly_message(monkeypatch):
    def broken(messages):
        raise meta.MetaError("down")
    monkeypatch.setattr(meta, "chat", broken)
    reply = client.post("/api/translate", json={"text": "hi", "lang": "en", "to": "te"})
    assert reply.status_code == 502
    assert "మళ్ళీ" in reply.json()["detail"]


def test_open_brain_is_tried_first_then_meta_api(monkeypatch):
    calls = []

    def fake_ask(base, auth, model, messages):
        calls.append(model)
        if model == meta.OPEN_BRAIN_MODEL:
            raise meta.MetaError("Baseten down")
        return "Dear, have you eaten?"
    monkeypatch.setattr(meta, "_ask", fake_ask)
    monkeypatch.setattr(meta, "secret", lambda name: "test-key")
    assert meta.chat([{"role": "user", "content": "hi"}]) == "Dear, have you eaten?"
    assert calls == [meta.OPEN_BRAIN_MODEL, meta.BRAIN_MODEL]


def test_pet_names_stay_pet_names():
    assert "Pet names stay pet names" in brain.RULES
    assert 'never "dear", "my boy"' in brain.RULES


def test_telugu_on_an_english_card_is_still_translated_into_english(monkeypatch):
    seen = {}
    monkeypatch.setattr(meta, "chat", lambda m: seen.setdefault("m", m) and "Did you eat?")
    reply = client.post("/api/translate", json={"text": "భోజనం చేశావా?", "lang": "en", "to": "te"})
    assert reply.json()["lang"] == "en"
    assert "Translate into English" in seen["m"][-1]["content"]
