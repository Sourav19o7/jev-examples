import asyncio
from types import SimpleNamespace

import pytest
from typesafe_sdk import TypeSafeError

from acu.intent import classify
from acu.intent.slots import Slots

SCREEN = {"frontmost_app": "Google Chrome", "chrome_running": True,
          "active_tab_title": "New Tab", "tab_count": 1}


class FakeResponse:
    choices = {"command": SimpleNamespace(
        choice="search", confidence=0.93,
        probabilities={"search": 0.93, "goto_site": 0.07})}
    scores = {"ambiguity": SimpleNamespace(
        score=1.2, confidence=0.8, legend={"0": "clear"}, probabilities={})}
    nouls = {
        "addressed_to_computer": SimpleNamespace(noul=0.97),
        "continues_context": SimpleNamespace(noul=0.88),
        "target_is_site": SimpleNamespace(noul=0.04),
    }
    usage = SimpleNamespace(input_tokens=412)


class FakeClient:
    def __init__(self, response=None, error=None):
        self._response, self._error = response, error

    async def system_one(self, state, questions, model=None):
        if self._error:
            raise self._error
        return self._response


def test_judgement_carries_every_answer(monkeypatch):
    monkeypatch.setattr(classify, "_client", lambda: FakeClient(FakeResponse()))
    j = asyncio.run(classify.judge("search global warming",
                                   Slots(query="global warming"), SCREEN, []))
    assert j.command == "search"
    assert j.command_confidence == pytest.approx(0.93)
    assert j.addressed == pytest.approx(0.97)
    assert j.target_is_site == pytest.approx(0.04)
    assert j.input_tokens == 412
    assert j.error is None


def test_api_failure_becomes_an_errored_judgement(monkeypatch):
    monkeypatch.setattr(
        classify, "_client", lambda: FakeClient(error=TypeSafeError("boom")))
    j = asyncio.run(classify.judge("search x", Slots(query="x"), SCREEN, []))
    assert j.error is not None
    assert j.command == "unknown"
