# Mythree

**A live interpreter that joins a family's video call**, so people who speak different Indian languages can finally talk, starting with Telugu, English and Hindi.

A grandfather in India who speaks only Telugu calls his grandson in the US, who speaks only English. Mythree runs on the grandson's laptop next to the call, listens, and speaks each person's words in the other's language, with the respect a grandfather deserves. When the grandfather holds a letter up to the camera, Mythree reads it and explains it in Telugu.

Built by team **Mythreyi** for the Meta Global AI Developer Hackathon (26 Oct – 4 Nov 2026).

## Built during the hackathon

Everything in this repository was written during the hackathon, starting on 27 October 2026. The commit history shows each step.

## How it works

| Part | Job | Model |
|---|---|---|
| Ears | Speech → text | Meta Muse Voice Transcribe |
| Brain | Translates with respect and context, checks itself | Meta Muse Spark Open / Muse Spark |
| Eyes | Reads letters, highlights dates and amounts | Meta Muse Spark + SAM 3.1 |
| Voice | Speaks the translation | Google Text-to-Speech |

## Run it on your computer

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then add your own keys
.venv/bin/uvicorn app.main:app --reload
```

Then open http://localhost:8000.

## Tests

```bash
.venv/bin/pytest
```
