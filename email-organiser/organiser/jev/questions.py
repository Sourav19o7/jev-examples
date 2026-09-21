"""The question set. This is the only place decisions are defined."""

from typesafe_sdk import Choice, Noul, Score

CATEGORIES = {
    "personal": "A human wrote this specifically to the recipient. Friends, family, one-to-one conversation.",
    "work": "Colleagues, clients, collaborators, or project discussion tied to the recipient's job.",
    "recruiter": "An approach about a job opening, hiring, or candidate sourcing.",
    "transactional": "Receipt, invoice, order confirmation, shipping notice, booking, or payment record.",
    "security": "Login alert, password reset, verification code, or account security notice.",
    "newsletter": "Recurring editorial or marketing content sent to a subscriber list.",
    "notification": "Automated update from a service the recipient uses, such as a social or app alert.",
    "promotional": "Advertising, discounts, or sales campaigns from a business.",
    "spam": "Unsolicited bulk mail, phishing, or fraud.",
}

URGENCY_LEVELS = [
    "No action ever needed. Safe to archive unread.",
    "Purely informational. Read whenever convenient.",
    "Worth reading this week. No deadline attached.",
    "Needs attention in the next day or two, or has a soft deadline.",
    "Time-critical. A hard deadline, outage, or consequence lands within roughly 24 hours.",
]


def build_questions() -> dict:
    """One request, four independent judgements, evaluated in parallel."""
    return {
        "category": Choice(
            instructions=(
                "Classify this email into exactly one category, judging by who sent it "
                "and why, not by how it is formatted."
            ),
            criteria=CATEGORIES,
        ),
        "urgency": Score(
            instructions=(
                "How soon must the recipient act on this email? Judge the consequence of "
                "ignoring it for a week. Marketing that claims urgency is not urgent."
            ),
            criteria=URGENCY_LEVELS,
        ),
        "needs_reply": Noul(
            instructions=(
                "Is this email waiting on a written reply from the recipient personally?"
            ),
            criteria={
                "true": "A person asked the recipient a question, made a request, or is awaiting a decision.",
                "false": "Automated mail, bulk mail, or a message that is purely informational or already resolved.",
            },
        ),
        "bulk_archivable": Noul(
            instructions=(
                "Is this bulk mail that the recipient can safely archive without reading?"
            ),
            criteria={
                "true": "Mass-sent newsletter, promotion, or routine automated notice with no personal obligation.",
                "false": "Written by a person to the recipient, or carries a record, deadline, or security matter worth keeping visible.",
            },
        ),
    }
