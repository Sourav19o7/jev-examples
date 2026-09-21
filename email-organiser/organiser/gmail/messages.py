"""Fetch and decode messages into a shape the judge layer can read."""

import base64
import re
from dataclasses import dataclass
from email.utils import parseaddr

from bs4 import BeautifulSoup


@dataclass
class Email:
    id: str
    thread_id: str
    sender: str
    to: str
    cc: str
    subject: str
    date: str
    body: str
    list_unsubscribe: bool
    reply_to_owner: bool


def _header(payload: dict, name: str) -> str:
    target = name.lower()
    for header in payload.get("headers", []):
        if header.get("name", "").lower() == target:
            return header.get("value", "")
    return ""


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    """Prefer text/plain; fall back to stripped HTML."""
    plain, html = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data:
            if mime == "text/plain":
                plain.append(_decode(data))
            elif mime == "text/html":
                html.append(_decode(data))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)

    if plain:
        return "\n".join(plain)
    if html:
        text = BeautifulSoup("\n".join(html), "html.parser").get_text("\n")
        return re.sub(r"\n{3,}", "\n\n", text)
    return ""


def fetch(service, query: str, limit: int) -> list[Email]:
    listed = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=limit)
        .execute()
        .get("messages", [])
    )

    emails = []
    for stub in listed:
        raw = (
            service.users()
            .messages()
            .get(userId="me", id=stub["id"], format="full")
            .execute()
        )
        payload = raw.get("payload", {})
        emails.append(
            Email(
                id=raw["id"],
                thread_id=raw.get("threadId", ""),
                sender=_header(payload, "From"),
                to=_header(payload, "To"),
                cc=_header(payload, "Cc"),
                subject=_header(payload, "Subject") or "(no subject)",
                date=_header(payload, "Date"),
                body=_extract_body(payload),
                list_unsubscribe=bool(_header(payload, "List-Unsubscribe")),
                reply_to_owner="SENT" in raw.get("labelIds", []),
            )
        )
    return emails


def sender_name(email: Email) -> str:
    name, address = parseaddr(email.sender)
    return name or address
