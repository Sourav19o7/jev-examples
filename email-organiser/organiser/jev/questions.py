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
    "Purely informational, or the only deadline is one an automated system resolves by itself. Read whenever convenient.",
    "Worth reading this week. Any deadline is soft, or missing it costs the recipient nothing they would mind.",
    "The recipient must personally do something within a few days, and missing it has a real cost.",
    "The recipient must personally act within about a day to avoid losing money, access, or an opportunity they cannot recover.",
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
        "owner_must_act": Noul(
            instructions=(
                "Must the recipient personally do something, beyond reading, for this "
                "to be resolved?"
            ),
            criteria={
                "true": "It stays unresolved, or something is lost, unless the recipient takes an action themselves.",
                "false": "A system, sender, or deadline resolves it on its own, or it merely reports something that already happened.",
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
