"""Deterministic composition. Jev judged; this decides."""

from dataclasses import dataclass, field

from organiser.jev.classify import Judgement

LABEL_PREFIX = "Jev"

# Confidence below this means the distribution was spread: don't act unattended.
ROUTING_CONFIDENCE_FLOOR = 0.6
# Archiving hides mail from the inbox, so it needs a firmer signal than labelling.
ARCHIVE_CONFIDENCE_FLOOR = 0.85
ARCHIVE_PROBABILITY_FLOOR = 0.85
NEEDS_REPLY_FLOOR = 0.7
URGENT_SCORE_FLOOR = 3.0

# Categories where a wrong archive costs the user something irreversible.
NEVER_ARCHIVE = {"personal", "work", "security", "transactional"}


@dataclass
class Plan:
    judgement: Judgement
    add_labels: list[str] = field(default_factory=list)
    archive: bool = False
    review_reasons: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)

    @property
    def subject(self) -> str:
        return self.judgement.email.subject


def decide(judgement: Judgement) -> Plan:
    plan = Plan(judgement=judgement)

    if judgement.error:
        plan.review_reasons.append(f"jev error: {judgement.error}")
        return plan

    if judgement.category_confidence < ROUTING_CONFIDENCE_FLOOR:
        ranked = sorted(
            judgement.category_probabilities.items(), key=lambda kv: kv[1], reverse=True
        )[:2]
        contest = " vs ".join(f"{name} {prob:.2f}" for name, prob in ranked) or (
            f"{judgement.category} {judgement.category_confidence:.2f}"
        )
        plan.review_reasons.append(f"category unclear ({contest})")
    else:
        plan.add_labels.append(f"{LABEL_PREFIX}/{judgement.category}")

    if judgement.needs_reply >= NEEDS_REPLY_FLOOR:
        plan.add_labels.append(f"{LABEL_PREFIX}/needs-reply")

    if judgement.urgency >= URGENT_SCORE_FLOOR:
        plan.add_labels.append(f"{LABEL_PREFIX}/urgent")

    plan.archive = (
        judgement.bulk_archivable >= ARCHIVE_PROBABILITY_FLOOR
        and judgement.category not in NEVER_ARCHIVE
        and judgement.category_confidence >= ARCHIVE_CONFIDENCE_FLOOR
        and judgement.needs_reply < NEEDS_REPLY_FLOOR
        and judgement.urgency < URGENT_SCORE_FLOOR
    )

    return plan


def plan_all(judgements: list[Judgement]) -> list[Plan]:
    return [decide(j) for j in judgements]
