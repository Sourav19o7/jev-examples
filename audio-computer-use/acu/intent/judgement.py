"""What Jev returned about one utterance."""

from dataclasses import dataclass


@dataclass
class Judgement:
    command: str
    command_confidence: float
    command_probabilities: dict
    addressed: float
    continues_context: float
    target_is_site: float
    ambiguity: float
    ambiguity_legend: dict | None = None
    input_tokens: int = 0
    error: str | None = None
