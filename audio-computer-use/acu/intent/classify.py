"""The judge layer: one Jev request per utterance, five questions in parallel."""

from typesafe_sdk import AsyncTypeSafeClient, TypeSafeError

from acu.intent.judgement import Judgement
from acu.intent.questions import build_questions
from acu.intent.slots import Slots
from acu.intent.state import build_state


def _client():
    return AsyncTypeSafeClient()


def _errored(message: str) -> Judgement:
    return Judgement(
        command="unknown", command_confidence=0.0, command_probabilities={},
        addressed=0.0, continues_context=0.0, target_is_site=0.0,
        ambiguity=0.0, error=message,
    )


async def judge(
    command: str,
    slots: Slots,
    screen: dict,
    recent: list[str],
    model: str = "jev-latest",
) -> Judgement:
    state = build_state(command, slots, screen, recent)
    client = _client()
    try:
        response = await client.system_one(state, build_questions(), model=model)
    except TypeSafeError as exc:
        return _errored(f"{exc.__class__.__name__}: {exc}")

    choice = response.choices["command"]
    ambiguity = response.scores["ambiguity"]
    return Judgement(
        command=choice.choice,
        command_confidence=choice.confidence,
        command_probabilities=dict(choice.probabilities),
        addressed=response.nouls["addressed_to_computer"].noul,
        continues_context=response.nouls["continues_context"].noul,
        target_is_site=response.nouls["target_is_site"].noul,
        ambiguity=ambiguity.score,
        ambiguity_legend=dict(ambiguity.legend) if ambiguity.legend else None,
        input_tokens=response.usage.input_tokens or 0,
    )
