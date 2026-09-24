from typesafe_sdk import Choice, Noul, Score
from acu.intent.questions import VERBS, build_questions


def test_five_questions_ride_in_one_request():
    q = build_questions()
    assert set(q) == {
        "command", "addressed_to_computer",
        "continues_context", "target_is_site", "ambiguity",
    }


def test_primitive_types_match_the_design():
    q = build_questions()
    assert isinstance(q["command"], Choice)
    assert isinstance(q["ambiguity"], Score)
    for name in ("addressed_to_computer", "continues_context", "target_is_site"):
        assert isinstance(q[name], Noul)


def test_eight_verbs_are_offered():
    assert set(VERBS) == {
        "open_app", "search", "new_tab", "close_tab",
        "switch_tab", "back", "scroll", "goto_site",
    }


def test_every_verb_carries_criteria_text():
    assert all(text.strip() for text in VERBS.values())
