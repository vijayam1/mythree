"""Mythree's brain: turns one person's words into the other person's language.

Any two people can talk: a grandfather and grandson, a mother and daughter,
two friends. Each person has a name and a language, chosen on the page.

The general rules live here. The family's own phrase book (how this family
really talks) is private: it is read from private/phrasebook.md, which never
goes online. Without it, Mythree still works, just less personally.
"""

import os
import re
from pathlib import Path

from app import meta

PHRASEBOOK = Path(__file__).resolve().parent.parent / "private" / "phrasebook.md"
HISTORY_TURNS = 6  # how many earlier sentences Mythree remembers (only during the call)
LANGUAGE_NAMES = {"te": "Telugu", "en": "English"}

RULES = """You are Mythree, a live interpreter on a family video call between two people
who don't share a language. Each time, translate what ONE of them just said, for the other one.
Use their names and the conversation to understand who is older and how they are related.

Into Telugu:
- Natural, spoken, everyday coastal Andhra Telugu, the way a loving family talks. Not textbook Telugu.
- When speaking to an elder, or when unsure, be respectful: మీరు and the polite -అండి ending where it fits.
  Grandparents are తాతగారు / అమ్మమ్మ / నానమ్మ, never by name.
- "Hi Grandpa" is "నమస్తే తాతగారు", never "హాయ్". "I miss you" is "మీరు బాగా గుర్తొస్తున్నారు" (to an elder).
- English words families really use (job, exams, call, video, Sunday, please) may stay, written in Telugu letters.
- Telugu script only.

Into English:
- Plain, gentle, warm English, the way a loving grandparent or parent really speaks.
  No slang or trendy words: never "Hey", "What's up", "buddy", "kiddo", "gonna". "హలో" is "Hello".
- Pet names stay pet names: elders lovingly call a child బాబు, నాన్నా, అమ్మా, చిన్నా, కన్నా, బంగారం.
  Keep them exactly, written in English letters (Babu, Nanna, Amma, Chinna, Kanna, Bangaram).
  Don't translate them: never "dear", "my boy", "my girl", "father" or "mother".
  Never add a pet name or a name that wasn't said (ఏరా is just a friendly "Hello", not "Babu").
- "అయినా" starting a new topic means "anyway", not "but".
- Keep the meaning, the questions and the feeling. Don't add or drop anything.

Both ways:
- Keep the exact strength: "a bit" stays "a bit" (కొంచెం), never "really" or "very".
- The words come from speech recognition and may have small slips (repeated words, "హేలో" for "hello"). Quietly fix them.
- Use the earlier sentences only to understand the context.
- Reply with the translation only: no notes, no quotes, no explanations."""


def family_examples() -> str:
    """The private phrase book's table, as "English → Telugu" lines (empty if there is no phrase book).

    Online, the phrase book is kept in the host's secret store (MYTHREE_PHRASEBOOK) instead of a file.
    """
    if os.environ.get("MYTHREE_PHRASEBOOK"):
        book = os.environ["MYTHREE_PHRASEBOOK"]
    elif PHRASEBOOK.exists():
        book = PHRASEBOOK.read_text()
    else:
        return ""
    lines = []
    for row in book.splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[1] and not cells[1].startswith(("Grandson", "---")):
            lines.append(f"{cells[1]} → {cells[2]}")
    if not lines:
        return ""
    return ("How this family really talks (a grandson's English → Telugu for his grandfather), "
            "follow this style:\n" + "\n".join(lines))


def translate(text: str, lang: str, to: str, speaker: str, listener: str, history: list[dict]) -> str:
    """Translate one sentence from lang into to, said by speaker, for listener."""
    system = RULES
    examples = family_examples()
    if examples:
        system += "\n\n" + examples
    messages = [{"role": "system", "content": system}]
    earlier = "\n".join(f"{h['who']}: {h['text']}" for h in history[-HISTORY_TURNS:])
    if earlier:
        messages.append({"role": "user", "content": "Earlier in the call:\n" + earlier})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content":
                     f"{speaker} ({LANGUAGE_NAMES[lang]}) says: {text}\n"
                     f"(Speech recognition wrote this down and sometimes uses the wrong letters, for example "
                     f"English letters for spoken Telugu. Read it as spoken {LANGUAGE_NAMES[lang]}.)\n\n"
                     f"Translate into {LANGUAGE_NAMES[to]}, for {listener}."})
    return clean(meta.chat(messages))


def clean(answer: str) -> str:
    """Remove quotes or a label the model sometimes adds around the translation."""
    answer = re.sub(r"^(Translation|అనువాదం)\s*:\s*", "", answer.strip(), flags=re.I)
    return answer.strip().strip('"“”').strip()


TO_ENGLISH = """You are Mythree, a live interpreter. Someone just spoke, in any language.
Translate what they said into plain, natural, warm spoken English, the way they would say it themselves.
Keep the meaning, the questions and the feeling; don't add or drop anything. If it is already English,
return it with only small speech-recognition slips fixed. Reply with the English only: no notes, no quotes."""


def to_english(text: str) -> str:
    """For the Try page: anything anyone says, in any language, into English."""
    return clean(meta.chat([{"role": "system", "content": TO_ENGLISH}, {"role": "user", "content": text}]))
