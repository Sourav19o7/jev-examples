import asyncio

from acu import session
from acu.intent.judgement import Judgement

SCREEN = {"frontmost_app": "Google Chrome", "chrome_running": True,
          "active_tab_title": "New Tab", "tab_count": 1}


def confident(verb="search"):
    async def _judge(command, slots, screen, recent, model="jev-latest"):
        return Judgement(
            command=verb, command_confidence=0.95,
            command_probabilities={verb: 0.95}, addressed=0.98,
            continues_context=0.9, target_is_site=0.05, ambiguity=1.0,
            input_tokens=300,
        )
    return _judge


def test_confident_command_is_acted_on_in_dry_run(monkeypatch):
    monkeypatch.setattr(session, "judge", confident())
    decision = asyncio.run(
        session.handle("search global warming", [], SCREEN, dry_run=True))
    assert decision.action == "act"


def test_acted_commands_enter_the_context_history(monkeypatch):
    monkeypatch.setattr(session, "judge", confident())
    recent: list[str] = []
    asyncio.run(session.handle("search global warming", recent, SCREEN, True))
    assert recent == ["search"]


def test_ignored_commands_do_not_enter_history(monkeypatch):
    async def _unaddressed(command, slots, screen, recent, model="jev-latest"):
        return Judgement(
            command="search", command_confidence=0.95,
            command_probabilities={"search": 0.95}, addressed=0.1,
            continues_context=0.5, target_is_site=0.1, ambiguity=3.0,
        )
    monkeypatch.setattr(session, "judge", _unaddressed)
    recent: list[str] = []
    asyncio.run(session.handle("mumbling", recent, SCREEN, True))
    assert recent == []


async def _ambiguous(command, slots, screen, recent, model="jev-latest"):
    return Judgement(
        command="close_tab", command_confidence=0.98,
        command_probabilities={"close_tab": 0.98}, addressed=0.9,
        continues_context=0.5, target_is_site=0.1, ambiguity=1.6,
    )


def test_confirm_that_is_accepted_acts(monkeypatch):
    monkeypatch.setattr(session, "judge", _ambiguous)
    performed: list[str] = []
    monkeypatch.setattr(session.chrome, "perform",
                        lambda verb, slots, dry_run=False: performed.append(verb) or "")
    recent: list[str] = []
    asyncio.run(session.handle("close time", recent, SCREEN, True, confirm=lambda d: True))
    assert performed == ["close_tab"]
    assert recent == ["close_tab"]


def test_confirm_that_is_declined_does_nothing(monkeypatch):
    monkeypatch.setattr(session, "judge", _ambiguous)
    performed: list[str] = []
    monkeypatch.setattr(session.chrome, "perform",
                        lambda verb, slots, dry_run=False: performed.append(verb) or "")
    recent: list[str] = []
    asyncio.run(session.handle("close time", recent, SCREEN, True, confirm=lambda d: False))
    assert performed == []
    assert recent == []


def test_confirm_without_a_channel_does_not_act(monkeypatch):
    monkeypatch.setattr(session, "judge", _ambiguous)
    performed: list[str] = []
    monkeypatch.setattr(session.chrome, "perform",
                        lambda verb, slots, dry_run=False: performed.append(verb) or "")
    asyncio.run(session.handle("close time", [], SCREEN, True))
    assert performed == []
