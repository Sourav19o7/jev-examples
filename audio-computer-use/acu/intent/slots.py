"""Literal spans come from rules. Jev returns distributions, never text."""

import re
from dataclasses import dataclass

ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "last": -1,
}

_SEARCH = re.compile(r"^(?:search|google|look up)\s+(?:for\s+)?(.+)$", re.I)
_OPEN = re.compile(r"^(?:open|launch|start)\s+(?:the\s+)?(.+?)(?:\s+app)?$", re.I)
_GOTO = re.compile(r"^(?:go to|goto|navigate to|visit)\s+(.+)$", re.I)
_TAB_DIGIT = re.compile(r"\btab\s+(\d+)\b|\b(\d+)(?:st|nd|rd|th)?\s+tab\b", re.I)
_TAB_WORD = re.compile(rf"\b({'|'.join(ORDINAL_WORDS)})\s+tab\b", re.I)


@dataclass
class Slots:
    query: str | None = None
    site: str | None = None
    app: str | None = None
    ordinal: int | None = None


def extract(command: str) -> Slots:
    text = command.strip()
    if not text:
        return Slots()

    slots = Slots()

    if match := _SEARCH.match(text):
        slots.query = match.group(1).strip()
    elif match := _GOTO.match(text):
        slots.site = match.group(1).strip()
    elif match := _OPEN.match(text):
        slots.app = match.group(1).strip()

    if match := _TAB_DIGIT.search(text):
        slots.ordinal = int(match.group(1) or match.group(2))
    elif match := _TAB_WORD.search(text):
        slots.ordinal = ORDINAL_WORDS[match.group(1).lower()]

    return slots
