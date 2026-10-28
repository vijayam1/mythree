"""Small Telugu helpers."""

# Hindi (Devanagari) and Telugu letters sit in the same order in Unicode,
# 0x300 apart, so a letter can be moved from one script to the other.
DEVANAGARI = range(0x0900, 0x0980)
TO_TELUGU = 0x0C00 - 0x0900


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
