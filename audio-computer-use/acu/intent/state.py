"""Named fields so relationships between parts stay explicit."""

from dataclasses import asdict

from acu.intent.slots import Slots

# Jev's accuracy drops when state carries irrelevant bulk, and older commands
# stop being evidence quickly.
RECENT_COMMAND_LIMIT = 3


def build_state(command: str, slots: Slots, screen: dict, recent: list[str]) -> dict:
    state: dict = {"utterance": command, "screen": screen}

    populated = {k: v for k, v in asdict(slots).items() if v is not None}
    if populated:
        state["slots"] = populated

    if recent:
        state["recent_commands"] = recent[-RECENT_COMMAND_LIMIT:]

    return state
