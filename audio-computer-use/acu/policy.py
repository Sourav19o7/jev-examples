"""Deterministic composition. Jev judged; this decides."""

from dataclasses import dataclass, field

from acu.intent.judgement import Judgement
from acu.intent.slots import Slots

ACT_FLOOR = 0.80
CONFIRM_FLOOR = 0.50
ADDRESSED_FLOOR = 0.60
CONTEXT_FLOOR = 0.50
SITE_FLOOR = 0.60

VERBS_NEEDING_TARGET = {"search", "goto_site", "open_app", "switch_tab"}

# Seam for risk tiering: map a verb to a floor above ACT_FLOOR and consult it in
# decide(). Deliberately unused in v1 — see decision 2 in the design.
RISK_TIERS: dict[str, float] = {}


@dataclass
class Decision:
    action: str
    verb: str | None
    reason: str
    alternatives: list[tuple[str, float]] = field(default_factory=list)


def _ranked(judgement: Judgement) -> list[tuple[str, float]]:
    return sorted(
        judgement.command_probabilities.items(), key=lambda kv: kv[1], reverse=True
    )[:2]


def _has_target(verb: str, slots: Slots) -> bool:
    if verb == "search":
        return slots.query is not None
    if verb == "goto_site":
        return slots.site is not None
    if verb == "open_app":
        return slots.app is not None
    if verb == "switch_tab":
        return slots.ordinal is not None
    return True


def decide(judgement: Judgement, slots: Slots, screen: dict) -> Decision:
    if judgement.error:
        return Decision("ignore", None, f"jev error: {judgement.error}")

    if judgement.addressed < ADDRESSED_FLOOR:
        return Decision("ignore", None, f"not addressed ({judgement.addressed:.2f})")

    ranked = _ranked(judgement)
    contest = " vs ".join(f"{n} {p:.2f}" for n, p in ranked)

    if judgement.command_confidence < CONFIRM_FLOOR:
        return Decision("ignore", None, f"unclear ({contest})", ranked)

    verb = judgement.command

    if judgement.command_confidence < ACT_FLOOR:
        return Decision("confirm", verb, f"low confidence ({contest})", ranked)

    if verb in VERBS_NEEDING_TARGET and not _has_target(verb, slots):
        # An omitted target is only recoverable from what is already on screen.
        if judgement.continues_context < CONTEXT_FLOOR:
            return Decision("confirm", verb, "target missing and no context", ranked)

    return Decision("act", verb, f"confident ({contest})", ranked)
