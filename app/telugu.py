"""Small Telugu helpers."""

# Hindi (Devanagari) and Telugu letters sit in the same order in Unicode,
# 0x300 apart, so a letter can be moved from one script to the other.
DEVANAGARI = range(0x0900, 0x0980)
TO_TELUGU = 0x0C00 - 0x0900


def language_of(text: str) -> str | None:
    """"te" if the words are written in Telugu letters, "en" if in English letters, None if unclear."""
    telugu = sum(0x0C00 <= ord(ch) <= 0x0C7F for ch in text)
    latin = sum(ch.isascii() and ch.isalpha() for ch in text)
    if telugu > latin * 0.3:   # Telugu speech often has a few English words in it
        return "te"
    if latin:
        return "en"
    return None


def devanagari_to_telugu(text: str) -> str:
    """Meta's ears sometimes write the first Telugu words in Hindi letters (నమస్తే → नमस्ते).

    Move those letters back into Telugu script. The full stop (।) becomes a normal one.
    """
    out = []
    for ch in text:
        code = ord(ch)
        if ch in "।॥":
            out.append(".")
        elif code in DEVANAGARI:
            out.append(chr(code + TO_TELUGU))
        else:
            out.append(ch)
    return "".join(out)
