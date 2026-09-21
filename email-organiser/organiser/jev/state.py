"""Turn a fetched message into the state object Jev judges."""

import re

from organiser.gmail.messages import Email

# Jev allows 32k tokens for state, but accuracy drops when the state carries
# large irrelevant content, so we send the part that carries the intent.
BODY_CHAR_BUDGET = 4000

_QUOTED_REPLY = re.compile(
    r"^(On .{0,120}wrote:|-{2,}\s*Original Message|_{5,}|From:\s)", re.MULTILINE
)


def _trim_body(body: str) -> str:
    """Drop quoted history: it describes an older message, not this one."""
    match = _QUOTED_REPLY.search(body)
    if match:
        body = body[: match.start()]
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if len(body) > BODY_CHAR_BUDGET:
        body = body[:BODY_CHAR_BUDGET] + "\n[truncated]"
    return body


def build_state(email: Email, owner: str) -> dict:
    """Named fields so relationships between parts stay explicit."""
    state = {
        "mailbox_owner": owner,
        "email": {
            "from": email.sender,
            "to": email.to,
            "subject": email.subject,
            "date": email.date,
            "body": _trim_body(email.body),
        },
    }
    if email.cc:
        state["email"]["cc"] = email.cc
    if email.list_unsubscribe:
        # Presence of this header is strong evidence of bulk mail.
        state["email"]["has_list_unsubscribe_header"] = True
    if email.reply_to_owner:
        state["thread"] = {"owner_has_replied_before": True}
    return state
