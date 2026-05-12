import re


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
ABBREVIATIONS = {
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "prof.",
    "sr.",
    "jr.",
    "st.",
    "vs.",
    "etc.",
    "e.g.",
    "i.e.",
    "u.s.",
    "u.k.",
}


def _ends_with_abbreviation(text: str) -> bool:
    words = text.lower().split()
    if not words:
        return False
    last = words[-1].strip('"\'')
    return last in ABBREVIATIONS


def _ends_with_decimal(text: str) -> bool:
    return bool(re.search(r"\d+\.\d+$", text.strip()))


def is_sentence_complete(text: str) -> bool:
    """
    Return True when the buffer appears to end with a complete sentence.
    Keeps tiny fragments, abbreviations, decimals, and open quotes out of TTS.
    """
    text = text.strip()
    if len(text) < 10:
        return False
    if _ends_with_abbreviation(text) or _ends_with_decimal(text):
        return False
    return bool(re.search(r'[.!?]["\')\]]?(\s|$)', text))


def extract_complete_sentence(buffer: str) -> tuple[str, str]:
    """
    Return the first complete sentence and the remaining buffer.
    If the buffer itself is one complete sentence, the remainder is empty.
    """
    buffer = buffer.strip()
    if not buffer:
        return "", ""

    parts = SENTENCE_SPLIT.split(buffer, maxsplit=1)
    if len(parts) == 1:
        return (buffer, "") if is_sentence_complete(buffer) else ("", buffer)

    first, remainder = parts[0].strip(), parts[1].strip()
    if is_sentence_complete(first):
        return first, remainder
    return "", buffer
