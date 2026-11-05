# Mythree

**A video call where a grandparent and a grandchild who don't share a language truly talk**, each in their own language and their own voice.

A grandfather in India speaks only Telugu. His grandson in the US speaks only English. Until now, all they could say to each other was "Hi Babu, how are you?" and "Hi Grandpa." With Mythree, they see each other on their phones, grandpa speaks Telugu, and his grandson hears it in English, in grandpa's own voice. The grandson answers in English, and grandpa hears Telugu, in the grandson's voice.

Built by **Vijaya Meda** for the Meta Global AI Developer Hackathon (26 Oct – 4 Nov 2026).

▶️ **3-minute demo video:** https://www.youtube.com/watch?v=0NtLBp79Ots (both phones of the same real call, side by side, in sync)

> **Judges: how to try Mythree**
>
> **Mythree is the video call.** It needs two phones (Safari on iPhone, Chrome on Android), ideally in two rooms:
> 1. On the first phone, open **[https://vijaya-meda--mythree-web.us-east.modal.run/phone](https://vijaya-meda--mythree-web.us-east.modal.run/phone)**. Choose who you are and your language (Telugu or English), and who you're calling and their language. *(Optional: **Record my voice**, so the other phone hears you in your own voice.)* Tap **Start a call**.
> 2. Send the link to the second phone (or type the 4-digit call code there), and tap the green **Join** button.
> 3. Tap **Video**, tap the green mic, and speak one short sentence. In a few seconds the other phone reads and hears it in its own language. Tap **End** when you're done.
>
> *Testing alone, without Telugu?* Set yourself to English and the other phone to Telugu. Speak English into the first phone, and the second phone says it in Telugu, in your voice if you recorded it.
>
> **Only one phone? A 1-minute taste:** **[https://mythreyi.in](https://mythreyi.in)** shows the heart of the call (hearing, translating, your own voice) without the call, in 102 languages. Choose **I speak** and **Hear it in**, tap the **green button**, say a sentence, and tap the **red button**. Then try **🎤 Use my own voice**, and tap **Done: delete my voice** at the end.

The free **Try page** ([https://mythreyi.in](https://mythreyi.in), the same as [https://vijaya-meda--mythree-web.us-east.modal.run/try](https://vijaya-meda--mythree-web.us-east.modal.run/try)) lets anyone speak any of **102 languages** (all 22 of India's, and 80 more) and hear it in any other, in a ready-made voice or, after 20 seconds of recording, in their own. 94 of them can be spoken; the other 8 Indian languages are shown in writing. The list is in `app/languages.py`. To keep costs safe, visitors' voices may use about 3,800 ElevenLabs characters a day (about 60 sentences); after that, the phone's own voice speaks until the next day. It is open for the hackathon and its judging. It closes by itself when judging ends, at midnight ET at the end of 9 November 2026, also when you run your own copy. The phone call stays open.

## Built during the hackathon

Everything in this repository was written during the hackathon, starting on 27 October 2026. Before that, Mythree was only an idea. The commit history shows each step.

## Where Meta's models are used

Every sentence goes through two Meta models: one **hears** it, one **translates** it.

| Part | Meta model (ID) | Where in the code | What it does |
|---|---|---|---|
| **Ears, live** | Muse Voice Transcribe (`muse-voice-transcribe-1.0`), realtime websocket `wss://api.meta.ai/v1/asr/realtime` | `app/meta.py` → `LiveEars`; used by `/api/calls/{code}/live` in `app/main.py` | Hears each person **while they are still talking**. The phone streams its sound through Mythree's server (the key never reaches the phone), and the words are ready about 0.3 s after the speaker pauses. |
| **Ears, one sentence** | Muse Voice Transcribe (`muse-voice-transcribe-1.0`), `POST https://api.meta.ai/v1/asr/transcribe` | `app/meta.py` → `transcribe()`; used by `/api/calls/{code}/heard` and the Try page `/api/try/heard` | The backup when the live line can't open. On the Try page it hears any of 102 languages, or finds the visitor's language by itself. |
| **Interpreter** | **Muse Spark Open**, Meta's open-weights model (`meta-models/muse-spark-open-1026`), on Baseten | `app/meta.py` → `chat()`; prompts in `app/brain.py` → `translate()` (calls) and `to_language()` (Try page) | Translates like a family interpreter, not a dictionary: knows who is the elder and speaks respectfully to them (మీరు, -అండి), keeps pet names as they are (Babu, Kanna), remembers the last 6 sentences of the call, follows the family's private phrase book, and quietly fixes speech-recognition slips. |
| **Backup interpreter** | Muse Spark 1.3 (`muse-spark-1.3`, Standard), `https://api.meta.ai/v1/chat/completions` | `app/meta.py` → `chat()` | Takes over by itself if Baseten can't answer, so the call never stops. |

**You can see Meta working, on every sentence.** Under each sentence, both phones show which Meta model heard it and which translated it, and how long each took:

```
👂 Meta · Muse Voice Transcribe · heard live in 0.3 s
🧠 Meta · Muse Spark Open on Baseten · translated in 1.3 s
```

**And in the server's log**, every call to a Meta model is one line with its model ID, where it ran, the answer's ID and the time taken. The family's words are never logged. A real example (31 Oct 2026):

```
[Meta] muse-voice-transcribe-1.0 · https://api.meta.ai/v1/asr/transcribe · 200 OK, heard 9 words · 1.3 s
[Meta] meta-models/muse-spark-open-1026 · https://inference.baseten.co/v1/chat/completions · 200 OK, answer chatcmpl-80d3d4d650c54016a82d4f7be4601bd1 · 1.3 s
```

### The parts that are not Meta

| Part | What | Why |
|---|---|---|
| Voice | ElevenLabs (Eleven v4 Turbo), each person's own cloned voice (only with their consent); Sarvam as backup; the browser's standard voice last | Meta has no public text-to-speech model. The organizers confirmed on 27 Oct that non-Meta models may be used alongside Meta's. |
| Seeing each other | The video travels straight between the phones (WebRTC, a web standard), with Cloudflare's relay when a network blocks a direct path | Not an AI model. |

Nothing is saved for long: a call lives only in memory (and a short-lived copy, so it survives an update) and is forgotten a few hours after it ends. Keys stay on the server.

## Run it with your own keys

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then add your keys (see below)
.venv/bin/uvicorn app.main:app --reload
```

Open http://localhost:8000/phone in **two browser tabs**: start a call in one, and join with the 4-digit code in the other. Each `[Meta]` line appears in the terminal as you talk.

| Key in `.env` | Needed? | What it turns on |
|---|---|---|
| `MODEL_API_KEY` | **Yes** | Your Meta Model API key (dev.meta.ai): the ears, and Muse Spark 1.3 as the interpreter. This alone is enough to run Mythree. |
| `BASETEN_API_KEY` | Optional | Muse Spark Open on Baseten becomes the interpreter (Muse Spark 1.3 stays the backup). |
| `ELEVENLABS_API_KEY`, `SARVAM_API_KEY` | Optional | Own voices. Without them, the browser's standard voice speaks. |
| `TURN_KEY_ID`, `TURN_KEY_API_TOKEN` | Optional | Cloudflare's relay for video across networks. Without it, video works when the two can reach each other directly. |

Real phones need https for the microphone and camera: use the live link above, or deploy your own copy with `modal deploy modal_app.py` (keys go into a Modal secret named `mythree-secrets`).

## Tests

```bash
.venv/bin/pytest
```
