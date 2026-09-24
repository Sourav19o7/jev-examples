"""The gate is deterministic code, not a probability."""

import re

WAKE_WORD = "computer"


def strip_wake_word(text: str, wake_word: str = WAKE_WORD) -> str | None:
    """Return the command after the wake word, or None if it was not addressed."""
    # Whisper varies casing and appends sentence punctuation, so match loosely
    # at the front and keep the remainder verbatim for slot extraction.
    pattern = rf"^\s*{re.escape(wake_word)}\b[\s,.:!-]*"
    match = re.match(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    command = text[match.end():].strip().rstrip(".!?,")
    return command.strip() or None
