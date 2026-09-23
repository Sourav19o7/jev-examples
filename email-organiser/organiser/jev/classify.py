"""The judge layer: one Jev request per email, four questions in parallel."""

import asyncio
from dataclasses import dataclass

from typesafe_sdk import AsyncTypeSafeClient, TypeSafeError

from organiser.gmail.messages import Email
from organiser.jev.questions import build_questions
from organiser.jev.state import build_state


@dataclass
class Judgement:
    email: Email
    category: str
    category_confidence: float
    category_probabilities: dict
    urgency: float
    urgency_confidence: float
    needs_reply: float
    owner_must_act: float
    bulk_archivable: float
    urgency_legend: dict | None = None
    input_tokens: int = 0
    error: str | None = None

    @property
    def urgency_normalised(self) -> float:
        """Score returns a probability-weighted level index, not a 0-1 value."""
        if not self.urgency_legend or len(self.urgency_legend) < 2:
            return 0.0
        return self.urgency / (len(self.urgency_legend) - 1)


async def _judge_one(client, email: Email, owner: str, model: str) -> Judgement:
    questions = build_questions()
    try:
        response = await client.system_one(
            build_state(email, owner), questions, model=model
        )
    except TypeSafeError as exc:
        return Judgement(
            email=email,
            category="unknown",
            category_confidence=0.0,
            category_probabilities={},
            urgency=0.0,
            urgency_confidence=0.0,
            needs_reply=0.0,
            owner_must_act=0.0,
            bulk_archivable=0.0,
            error=f"{exc.__class__.__name__}: {exc}",
        )

    category = response.choices["category"]
    urgency = response.scores["urgency"]
    return Judgement(
        email=email,
        category=category.choice,
        category_confidence=category.confidence,
        category_probabilities=dict(category.probabilities),
        urgency=urgency.score,
        urgency_confidence=urgency.confidence,
        urgency_legend=dict(urgency.legend) if urgency.legend else None,
        needs_reply=response.nouls["needs_reply"].noul,
        owner_must_act=response.nouls["owner_must_act"].noul,
        bulk_archivable=response.nouls["bulk_archivable"].noul,
        input_tokens=response.usage.input_tokens or 0,
    )


async def judge_all(
    emails: list[Email], owner: str, model: str, concurrency: int = 8
) -> list[Judgement]:
    """Each email is its own request because each carries different state."""
    semaphore = asyncio.Semaphore(concurrency)

    async with AsyncTypeSafeClient() as client:

        async def bounded(email: Email) -> Judgement:
            async with semaphore:
                return await _judge_one(client, email, owner, model)

        return await asyncio.gather(*(bounded(email) for email in emails))
