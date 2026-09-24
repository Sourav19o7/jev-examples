from acu.intent.judgement import Judgement
from acu.intent.slots import Slots
from acu.policy import decide

SCREEN = {"frontmost_app": "Google Chrome", "chrome_running": True,
          "active_tab_title": "New Tab", "tab_count": 1}


def judgement(**kw) -> Judgement:
    base = dict(
        command="search", command_confidence=0.95,
        command_probabilities={"search": 0.95, "goto_site": 0.05},
        addressed=0.95, continues_context=0.9, target_is_site=0.1, ambiguity=1.0,
    )
    base.update(kw)
    return Judgement(**base)


def test_confident_command_acts():
    d = decide(judgement(), Slots(query="global warming"), SCREEN)
    assert d.action == "act" and d.verb == "search"


def test_jev_error_is_never_acted_on():
    d = decide(judgement(error="TypeSafeAPIError: boom"), Slots(), SCREEN)
    assert d.action == "ignore"
    assert "error" in d.reason


def test_speech_not_addressed_to_computer_is_ignored():
    d = decide(judgement(addressed=0.2), Slots(query="x"), SCREEN)
    assert d.action == "ignore"


def test_low_command_confidence_confirms():
    d = decide(
        judgement(command_confidence=0.62,
                  command_probabilities={"close_tab": 0.62, "search": 0.38}),
        Slots(), SCREEN,
    )
    assert d.action == "confirm"
    assert d.alternatives[0][0] == "close_tab"


def test_very_low_confidence_is_ignored_silently():
    d = decide(
        judgement(command_confidence=0.30,
                  command_probabilities={"close_tab": 0.30, "scroll": 0.28}),
        Slots(), SCREEN,
    )
    assert d.action == "ignore"


def test_missing_target_rescued_by_screen_context():
    d = decide(judgement(continues_context=0.9), Slots(query="global warming"), SCREEN)
    assert d.action == "act"


def test_missing_target_without_context_confirms():
    d = decide(judgement(command="search", continues_context=0.1), Slots(), SCREEN)
    assert d.action == "confirm"


def test_site_target_routes_to_navigation():
    d = decide(
        judgement(command="goto_site", target_is_site=0.9,
                  command_probabilities={"goto_site": 0.95}),
        Slots(site="github.com"), SCREEN,
    )
    assert d.action == "act" and d.verb == "goto_site"


def test_verbs_needing_no_target_act_without_slots():
    for verb in ("back", "new_tab", "close_tab", "scroll"):
        d = decide(
            judgement(command=verb, command_probabilities={verb: 0.95}),
            Slots(), SCREEN,
        )
        assert d.action == "act", verb


def test_ambiguous_reading_confirms_even_when_the_verb_is_confident():
    """Misheard speech picks a near verb confidently; ambiguity is what catches it."""
    d = decide(
        judgement(command="close_tab", command_confidence=0.98,
                  command_probabilities={"close_tab": 0.98}, ambiguity=1.55),
        Slots(), SCREEN,
    )
    assert d.action == "confirm"


def test_clear_reading_still_acts():
    d = decide(
        judgement(command="close_tab", command_confidence=1.0,
                  command_probabilities={"close_tab": 1.0}, ambiguity=0.36),
        Slots(), SCREEN,
    )
    assert d.action == "act"
