"""Small Telugu helpers."""

# India's scripts (Hindi, Bengali, Gujarati, Tamil, Kannada…) sit side by side in Unicode,
# each in a block of 0x80 letters in the same order, so a letter can be moved into Telugu.
OTHER_INDIC = [b for b in range(0x0900, 0x0D80, 0x80) if b != 0x0C00]
TELUGU = 0x0C00


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
    """Meta's ears sometimes write Telugu in Hindi or Gujarati letters (నమస్తే → नमस्ते, હું).

    Move those letters back into Telugu script. The full stop (।) becomes a normal one.
    """
    out = []
    for ch in text:
        code = ord(ch)
        if ch in "।॥":
            out.append(".")
        elif any(block <= code < block + 0x80 for block in OTHER_INDIC):
            out.append(chr(TELUGU + code % 0x80))
        else:
            out.append(ch)
    return "".join(out)
