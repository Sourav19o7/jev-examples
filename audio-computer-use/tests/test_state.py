from acu.intent.slots import Slots
from acu.intent.state import RECENT_COMMAND_LIMIT, build_state

SCREEN = {"frontmost_app": "Google Chrome", "chrome_running": True,
          "active_tab_title": "New Tab", "tab_count": 1}


def test_command_and_screen_are_named_fields():
    state = build_state("search global warming", Slots(query="global warming"), SCREEN, [])
    assert state["utterance"] == "search global warming"
    assert state["screen"]["frontmost_app"] == "Google Chrome"


def test_only_populated_slots_are_sent():
    state = build_state("search x", Slots(query="x"), SCREEN, [])
    assert state["slots"] == {"query": "x"}


def test_empty_slots_are_omitted_entirely():
    assert "slots" not in build_state("back", Slots(), SCREEN, [])


def test_recent_commands_are_capped():
    recent = ["a", "b", "c", "d", "e"]
    state = build_state("back", Slots(), SCREEN, recent)
    assert state["recent_commands"] == recent[-RECENT_COMMAND_LIMIT:]


def test_no_recent_commands_key_when_history_empty():
    assert "recent_commands" not in build_state("back", Slots(), SCREEN, [])
