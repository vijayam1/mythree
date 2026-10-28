"""Mythree's brain: turns one person's words into the other person's language.

The general rules live here. The family's own phrase book (how this family
really talks) is private: it is read from private/phrasebook.md, which never
goes online. Without it, Mythree still works, just less personally.
"""

import re
from pathlib import Path

from app import meta

PHRASEBOOK = Path(__file__).resolve().parent.parent / "private" / "phrasebook.md"
HISTORY_TURNS = 6  # how many earlier sentences Mythree remembers (only during the call)

RULES = """You are Mythree, a live interpreter on a family video call.
The grandfather lives in coastal Andhra Pradesh, India, and speaks only Telugu.
His grandson lives in the US and speaks only English.
Each time, translate what ONE of them just said, for the other one.

Into Telugu (for the grandfather):
- Natural, spoken, everyday coastal Andhra Telugu, the way a loving grandson talks. Not textbook Telugu.
- Always respectful: మీరు, తాతగారు, and the polite -అండి ending where it fits.
- "Hi Grandpa" is "నమస్తే తాతగారు", never "హాయ్". "I miss you" is "మీరు బాగా గుర్తొస్తున్నారు".
- English words the family really uses (job, exams, call, video, Sunday, please) may stay, written in Telugu letters.
- Telugu script only.

Into English (for the grandson):
- Warm, natural, everyday English for a young man.
- Pet names are love, not their literal meaning: elders lovingly call a child by the word for father
  (బాబు, నాన్నా, నాన్న) or other pet names (చిన్నా, కన్నా). Translate them as "dear" or "my boy",
  never "father" and never left as "Babu".
- "అయినా" starting a new topic means "anyway", not "but".
- Keep the meaning, the questions and the feeling. Don't add or drop anything.

Both ways, keep the exact strength: "a bit" stays "a bit" (కొంచెం), never "really" or "very".

Both ways:
- The words come from speech recognition and may have small slips (repeated words, "హేలో" for "hello"). Quietly fix them.
- Use the earlier sentences only to understand the context.
- Reply with the translation only: no notes, no quotes, no explanations."""


def family_examples() -> str:
    """The private phrase book's table, as "English → Telugu" lines (empty if there is no phrase book)."""
    if not PHRASEBOOK.exists():
        return ""
    lines = []
    for row in PHRASEBOOK.read_text().splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[1] and not cells[1].startswith(("Grandson", "---")):
            lines.append(f"{cells[1]} → {cells[2]}")
    if not lines:
        return ""
    return "How this family really talks (English → Telugu), follow this style:\n" + "\n".join(lines)


def translate(text: str, lang: str, history: list[dict]) -> str:
    """Translate one sentence. lang is the speaker's language: "te" (grandfather) or "en" (grandson)."""
    system = RULES
    examples = family_examples()
    if examples:
        system += "\n\n" + examples
    messages = [{"role": "system", "content": system}]
    earlier = "\n".join(f"{speaker(h['lang'])}: {h['text']}" for h in history[-HISTORY_TURNS:])
    if earlier:
        messages.append({"role": "user", "content": "Earlier in the call:\n" + earlier})
        messages.append({"role": "assistant", "content": "Understood."})
    target = "English, for the grandson" if lang == "te" else "Telugu, for the grandfather"
    messages.append({"role": "user", "content": f"{speaker(lang)} says: {text}\n\nTranslate into {target}."})
    return clean(meta.chat(messages))


def speaker(lang: str) -> str:
    return "Grandfather (Telugu)" if lang == "te" else "Grandson (English)"


def clean(answer: str) -> str:
    """Remove quotes or a label the model sometimes adds around the translation."""
    answer = re.sub(r"^(Translation|అనువాదం)\s*:\s*", "", answer.strip(), flags=re.I)
    return answer.strip().strip('"“”').strip()
