# Audio Computer Use Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speak a wake word and a browser command; the machine carries it out in Chrome.

**Architecture:** Mic → Silero VAD segments utterances → MLX Whisper transcribes → deterministic wake gate → deterministic slot extraction → one Jev request (5 parallel typed questions) → policy applies confidence tiers → AppleScript acts on Chrome. Code extracts literal strings because Jev returns only probability distributions; Jev judges meaning, context-dependence, and trust.

**Tech Stack:** Python 3.10+, `typesafe-sdk` 0.7.1, `mlx-whisper` 0.4.3, `silero-vad` 6.2.3, `sounddevice` 0.5.6, `rich`, `python-dotenv`, `pytest`. macOS + Apple Silicon. AppleScript via `osascript`.

**Spec:** `docs/superpowers/specs/2026-09-24-audio-computer-use-design.md`

## Global Constraints

- All work happens in `audio-computer-use/`. Delete the empty `audio-computer-user/` directory.
- Python `>=3.10`. Package layout and `pyproject.toml` mirror `email-organiser/`.
- Follow the sibling project's idiom: **code owns control flow, Jev only judges.**
- Jev returns `Choice` / `Score` / `Noul` only — never request a string from Jev.
- All five questions ride in **one** `system_one` request per utterance.
- `actuator/` is the only package permitted to mutate browser state.
- Never act on an errored judgement.
- Every value interpolated into AppleScript is escaped via `applescript.escape()`.
- Thresholds are named module-level constants in `policy.py`, never inline literals.
- Comments follow the repo norm: explain *why*, never narrate *what*. `email-organiser` carries almost none; match that.
- No network calls in tests. No microphone in tests. No real Chrome mutation in tests.

## Review Focus

Verified empirically during planning; each line's test is assigned to the owning task.

1. **Whisper returns varied casing and trailing punctuation** — measured: `"Computer, Open Chrome."` and `"computer close time."`. The wake gate must match case-insensitively and tolerate a comma or period after the wake word. *(Task 3)*
2. **Short verbs are misheard** — measured: `"close tab"` → `"close time"`. Slot extraction must not crash on an unknown verb, and policy must route low confidence to confirm/ignore rather than act. *(Tasks 4, 7)*
3. **VAD emits `start` with no matching `end`** — measured: speech running to the end of the buffer yields `{'start': 0.0}` only. The capture loop must also close an utterance on a silence timeout, or the final command hangs forever. *(Task 2)*
4. **First Whisper call costs ~52s** (model download and load), warm calls 0.09s for `small.en`. The model must load once at startup; a per-utterance load makes the first command look broken. *(Task 12)*
5. **A transcribed query may contain AppleScript metacharacters.** A quote in the query must not terminate the string literal or inject script. *(Task 8)*

---

## Task 1: Project scaffold

**Files:**
- Create: `audio-computer-use/pyproject.toml`, `audio-computer-use/.env.example`, `audio-computer-use/.gitignore`
- Create: `audio-computer-use/acu/__init__.py`, `acu/listener/__init__.py`, `acu/intent/__init__.py`, `acu/actuator/__init__.py`
- Create: `audio-computer-use/tests/__init__.py`
- Delete: `audio-computer-user/` (empty directory)

**Interfaces:**
- Consumes: nothing
- Produces: importable package `acu`; console script `listen` → `acu.session:main`

- [ ] **Step 1: Remove the stale directory and create the tree**

```bash
cd /Users/souravdey/Projects/jev-examples
rmdir audio-computer-user
mkdir -p audio-computer-use/acu/{listener,intent,actuator} audio-computer-use/tests
cd audio-computer-use
touch acu/__init__.py acu/listener/__init__.py acu/intent/__init__.py acu/actuator/__init__.py tests/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "audio-computer-use"
version = "0.1.0"
description = "Voice-driven browser control with TypeSafe Jev typed decisions"
requires-python = ">=3.10"
dependencies = [
    "typesafe-sdk",
    "mlx-whisper",
    "silero-vad",
    "sounddevice",
    "numpy",
    "rich",
    "python-dotenv",
]

[project.optional-dependencies]
dev = ["pytest"]

[project.scripts]
listen = "acu.session:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["acu*"]
```

- [ ] **Step 3: Write `.env.example` and `.gitignore`**

```bash
cat > .env.example <<'EOF'
TYPESAFE_API_KEY=
EOF
cat > .gitignore <<'EOF'
.venv/
__pycache__/
*.egg-info/
.env
EOF
```

- [ ] **Step 4: Create the venv and install**

```bash
python3 -m venv .venv
.venv/bin/pip install -q -e ".[dev]"
.venv/bin/python -c "import acu, typesafe_sdk, mlx_whisper, silero_vad, sounddevice; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 5: Commit**

```bash
cd /Users/souravdey/Projects/jev-examples
git add -A audio-computer-use
git commit -m "Scaffold audio-computer-use package"
```

---

## Task 2: Utterance segmentation (VAD)

Splits a continuous audio stream into discrete utterances. Pure function over frames so it is testable without a microphone.

**Files:**
- Create: `acu/listener/segmenter.py`
- Test: `tests/test_segmenter.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `FRAME_SAMPLES: int = 512`, `SAMPLE_RATE: int = 16000`
  - `class Segmenter(silence_timeout_frames: int = 16)`
  - `Segmenter.push(frame: np.ndarray, is_speech: bool) -> np.ndarray | None` — returns the completed utterance's samples, else `None`
  - `Segmenter.flush() -> np.ndarray | None`

- [ ] **Step 1: Write the failing tests**

The third test pins Review Focus #3: speech that never falls silent must still close.

```python
# tests/test_segmenter.py
import numpy as np
from acu.listener.segmenter import Segmenter, FRAME_SAMPLES


def frame(value: float = 0.0) -> np.ndarray:
    return np.full(FRAME_SAMPLES, value, dtype=np.float32)


def test_silence_alone_produces_no_utterance():
    seg = Segmenter(silence_timeout_frames=2)
    assert seg.push(frame(), is_speech=False) is None
    assert seg.push(frame(), is_speech=False) is None


def test_speech_then_silence_emits_utterance():
    seg = Segmenter(silence_timeout_frames=2)
    assert seg.push(frame(0.5), is_speech=True) is None
    assert seg.push(frame(), is_speech=False) is None
    out = seg.push(frame(), is_speech=False)
    assert out is not None
    assert len(out) == FRAME_SAMPLES * 3


def test_speech_running_to_end_is_recovered_by_flush():
    seg = Segmenter(silence_timeout_frames=2)
    seg.push(frame(0.5), is_speech=True)
    seg.push(frame(0.5), is_speech=True)
    out = seg.flush()
    assert out is not None
    assert len(out) == FRAME_SAMPLES * 2


def test_flush_with_no_speech_returns_none():
    assert Segmenter().flush() is None


def test_segmenter_resets_between_utterances():
    seg = Segmenter(silence_timeout_frames=1)
    seg.push(frame(0.5), is_speech=True)
    first = seg.push(frame(), is_speech=False)
    assert first is not None
    seg.push(frame(0.5), is_speech=True)
    second = seg.push(frame(), is_speech=False)
    assert second is not None
    assert len(second) == FRAME_SAMPLES * 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_segmenter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acu.listener.segmenter'`

- [ ] **Step 3: Implement**

```python
# acu/listener/segmenter.py
"""Group frames into utterances. No audio device here, so this stays testable."""

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512


class Segmenter:
    def __init__(self, silence_timeout_frames: int = 16):
        self._silence_timeout = silence_timeout_frames
        self._frames: list[np.ndarray] = []
        self._silent_run = 0

    def push(self, frame: np.ndarray, is_speech: bool) -> np.ndarray | None:
        if is_speech:
            self._frames.append(frame)
            self._silent_run = 0
            return None

        if not self._frames:
            return None

        self._frames.append(frame)
        self._silent_run += 1
        if self._silent_run >= self._silence_timeout:
            return self._take()
        return None

    def flush(self) -> np.ndarray | None:
        """Silero emits a start without an end when speech runs to the buffer's
        edge, so the final utterance is only recoverable this way."""
        return self._take() if self._frames else None

    def _take(self) -> np.ndarray:
        utterance = np.concatenate(self._frames)
        self._frames = []
        self._silent_run = 0
        return utterance
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_segmenter.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/listener/segmenter.py audio-computer-use/tests/test_segmenter.py
git commit -m "Close an utterance on silence or on end of stream"
```

---

## Task 3: Wake-word gate

**Files:**
- Create: `acu/listener/wake.py`
- Test: `tests/test_wake.py`

**Interfaces:**
- Consumes: nothing
- Produces: `WAKE_WORD: str = "computer"`, `strip_wake_word(text: str, wake_word: str = WAKE_WORD) -> str | None`

- [ ] **Step 1: Write the failing tests**

These pin Review Focus #1 with the exact strings Whisper produced during planning.

```python
# tests/test_wake.py
from acu.listener.wake import strip_wake_word


def test_plain_prefix():
    assert strip_wake_word("computer search global warming") == "search global warming"


def test_transcriber_casing_and_comma():
    assert strip_wake_word("Computer, Open Chrome.") == "Open Chrome"


def test_trailing_period_only():
    assert strip_wake_word("computer close tab.") == "close tab"


def test_missing_wake_word_is_rejected():
    assert strip_wake_word("search global warming") is None


def test_wake_word_mid_sentence_is_rejected():
    assert strip_wake_word("ask the computer to search") is None


def test_wake_word_alone_is_rejected():
    assert strip_wake_word("Computer.") is None


def test_embedded_in_longer_word_is_rejected():
    assert strip_wake_word("computerised records") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_wake.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# acu/listener/wake.py
"""The gate is deterministic code, not a probability."""

import re

WAKE_WORD = "computer"


def strip_wake_word(text: str, wake_word: str = WAKE_WORD) -> str | None:
    """Return the command after the wake word, or None if it was not addressed."""
    # Whisper varies casing and appends sentence punctuation, so match loosely
    # at the front and keep the remainder verbatim for slot extraction.
    pattern = rf"^\s*{re.escape(wake_word)}\b[\s,.:!-]*"
    match = re.match(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    command = text[match.end():].strip().rstrip(".!?,")
    return command.strip() or None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_wake.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/listener/wake.py audio-computer-use/tests/test_wake.py
git commit -m "Gate commands on a wake word the transcriber may punctuate"
```

---

## Task 4: Slot extraction

Jev cannot return strings, so literal spans come from rules here.

**Files:**
- Create: `acu/intent/slots.py`
- Test: `tests/test_slots.py`

**Interfaces:**
- Consumes: nothing
- Produces: `@dataclass Slots(query: str | None = None, site: str | None = None, app: str | None = None, ordinal: int | None = None)`, `extract(command: str) -> Slots`

- [ ] **Step 1: Write the failing tests**

`test_unknown_verb_is_not_an_error` pins Review Focus #2.

```python
# tests/test_slots.py
from acu.intent.slots import extract


def test_search_query():
    assert extract("search global warming").query == "global warming"


def test_search_for_query():
    assert extract("search for global warming").query == "global warming"


def test_open_app():
    assert extract("open chrome").app == "chrome"


def test_goto_site():
    assert extract("go to github.com").site == "github.com"


def test_bare_site_name():
    assert extract("go to github").site == "github"


def test_switch_tab_ordinal_digit():
    assert extract("switch to tab 3").ordinal == 3


def test_switch_tab_ordinal_word():
    assert extract("switch to the second tab").ordinal == 2


def test_verbless_command_has_no_slots():
    slots = extract("back")
    assert slots.query is None and slots.app is None and slots.site is None


def test_unknown_verb_is_not_an_error():
    slots = extract("close time")
    assert slots.query is None


def test_empty_string_is_safe():
    assert extract("").query is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_slots.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# acu/intent/slots.py
"""Literal spans come from rules. Jev returns distributions, never text."""

import re
from dataclasses import dataclass

ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "last": -1,
}

_SEARCH = re.compile(r"^(?:search|google|look up)\s+(?:for\s+)?(.+)$", re.I)
_OPEN = re.compile(r"^(?:open|launch|start)\s+(?:the\s+)?(.+?)(?:\s+app)?$", re.I)
_GOTO = re.compile(r"^(?:go to|goto|navigate to|visit)\s+(.+)$", re.I)
_TAB_DIGIT = re.compile(r"\btab\s+(\d+)\b|\b(\d+)(?:st|nd|rd|th)?\s+tab\b", re.I)
_TAB_WORD = re.compile(rf"\b({'|'.join(ORDINAL_WORDS)})\s+tab\b", re.I)


@dataclass
class Slots:
    query: str | None = None
    site: str | None = None
    app: str | None = None
    ordinal: int | None = None


def extract(command: str) -> Slots:
    text = command.strip()
    if not text:
        return Slots()

    slots = Slots()

    if match := _SEARCH.match(text):
        slots.query = match.group(1).strip()
    elif match := _GOTO.match(text):
        slots.site = match.group(1).strip()
    elif match := _OPEN.match(text):
        slots.app = match.group(1).strip()

    if match := _TAB_DIGIT.search(text):
        slots.ordinal = int(match.group(1) or match.group(2))
    elif match := _TAB_WORD.search(text):
        slots.ordinal = ORDINAL_WORDS[match.group(1).lower()]

    return slots
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_slots.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/intent/slots.py audio-computer-use/tests/test_slots.py
git commit -m "Extract literal command slots in code, not in Jev"
```

---

## Task 5: The question set

The only place decisions are defined.

**Files:**
- Create: `acu/intent/questions.py`
- Test: `tests/test_questions.py`

**Interfaces:**
- Consumes: nothing
- Produces: `VERBS: dict[str, str]`, `AMBIGUITY_LEVELS: list[str]`, `build_questions() -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_questions.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_questions.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# acu/intent/questions.py
"""The question set. This is the only place decisions are defined."""

from typesafe_sdk import Choice, Noul, Score

VERBS = {
    "open_app": "Launch or focus an application, such as Chrome itself.",
    "search": "Search the web for a phrase the speaker supplied.",
    "goto_site": "Navigate to a named website or URL.",
    "new_tab": "Open a new, empty browser tab.",
    "close_tab": "Close the tab that is currently active.",
    "switch_tab": "Move to a different already-open tab.",
    "back": "Return to the previous page in history.",
    "scroll": "Scroll the current page up or down.",
}

AMBIGUITY_LEVELS = [
    "Unmistakable. The words name one action and one target plainly.",
    "Clear. A competent listener would agree on the action without hesitating.",
    "Mostly clear, but the phrasing or a mis-heard word leaves some doubt.",
    "Genuinely ambiguous. Two different actions fit the words equally well.",
    "Unintelligible as a command. The words do not form a browser instruction.",
]


def build_questions() -> dict:
    """One request, five independent judgements, evaluated in parallel."""
    return {
        "command": Choice(
            instructions=(
                "Which browser action is the speaker asking for? Judge by what they "
                "want to happen, not by the exact words they used."
            ),
            criteria=VERBS,
        ),
        "addressed_to_computer": Noul(
            instructions=(
                "Is the speaker instructing this computer, rather than talking to "
                "another person within earshot?"
            ),
            criteria={
                "true": "An instruction directed at a machine, phrased as a command.",
                "false": "Conversation, thinking aloud, or speech aimed at another person.",
            },
        ),
        "continues_context": Noul(
            instructions=(
                "Does this command depend on what is already on screen to make sense?"
            ),
            criteria={
                "true": "It omits its target and only resolves against the focused app or tab.",
                "false": "It names its own target and stands alone.",
            },
        ),
        "target_is_site": Noul(
            instructions=(
                "Is the target a specific website to visit, rather than a phrase to "
                "search for?"
            ),
            criteria={
                "true": "A domain, a URL, or a well-known site the speaker wants to open.",
                "false": "A topic, question, or phrase the speaker wants results about.",
            },
        ),
        "ambiguity": Score(
            instructions=(
                "How clear is this as a browser command? Judge how confidently a "
                "listener could carry it out without asking."
            ),
            criteria=AMBIGUITY_LEVELS,
        ),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_questions.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/intent/questions.py audio-computer-use/tests/test_questions.py
git commit -m "Define the five typed questions behind every utterance"
```

---

## Task 6: State builder

**Files:**
- Create: `acu/intent/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `acu.intent.slots.Slots`
- Produces: `RECENT_COMMAND_LIMIT: int = 3`, `build_state(command: str, slots: Slots, screen: dict, recent: list[str]) -> dict`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_state.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# acu/intent/state.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_state.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/intent/state.py audio-computer-use/tests/test_state.py
git commit -m "Build the state Jev judges from the utterance and the screen"
```

---

## Task 7: Policy

**Files:**
- Create: `acu/intent/judgement.py`, `acu/policy.py`
- Test: `tests/test_policy.py`

**Interfaces:**
- Consumes: nothing (`Judgement` is defined here and reused by Task 9)
- Produces:
  - `@dataclass Judgement(command, command_confidence, command_probabilities, addressed, continues_context, target_is_site, ambiguity, ambiguity_legend=None, input_tokens=0, error=None)`
  - `ACT_FLOOR`, `CONFIRM_FLOOR`, `ADDRESSED_FLOOR`, `CONTEXT_FLOOR`, `SITE_FLOOR`
  - `@dataclass Decision(action: str, verb: str | None, reason: str, alternatives: list[tuple[str, float]])` where `action ∈ {"act", "confirm", "ignore"}`
  - `decide(judgement: Judgement, slots: Slots, screen: dict) -> Decision`

- [ ] **Step 1: Write the failing tests**

`test_low_command_confidence_confirms` pins Review Focus #2.

```python
# tests/test_policy.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_policy.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `judgement.py` then `policy.py`**

```python
# acu/intent/judgement.py
"""What Jev returned about one utterance."""

from dataclasses import dataclass, field


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
```

```python
# acu/policy.py
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
        return Decision(
            "ignore", None, f"not addressed ({judgement.addressed:.2f})"
        )

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_policy.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/intent/judgement.py audio-computer-use/acu/policy.py audio-computer-use/tests/test_policy.py
git commit -m "Tier actions by confidence and refuse to act on errors"
```

---

## Task 8: AppleScript actuation

**Files:**
- Create: `acu/actuator/applescript.py`, `acu/actuator/chrome.py`
- Test: `tests/test_applescript.py`, `tests/test_chrome.py`

**Interfaces:**
- Consumes: `acu.intent.slots.Slots`
- Produces:
  - `applescript.escape(value: str) -> str`
  - `applescript.run(script: str) -> str`
  - `chrome.read_context() -> dict`
  - `chrome.build(verb: str, slots: Slots) -> str`
  - `chrome.perform(verb: str, slots: Slots, dry_run: bool = False) -> str`

- [ ] **Step 1: Write the failing tests**

`test_quote_cannot_escape_the_literal` pins Review Focus #5.

```python
# tests/test_applescript.py
from acu.actuator.applescript import escape, run


def test_plain_text_is_unchanged():
    assert escape("global warming") == "global warming"


def test_quote_is_escaped():
    assert escape('say "hi"') == 'say \\"hi\\"'


def test_backslash_is_escaped_before_quotes():
    assert escape(r"a\b") == r"a\\b"


def test_quote_cannot_escape_the_literal():
    hostile = 'x" & (do shell script "echo PWNED") & "y'
    assert run(f'return "{escape(hostile)}"').strip() == hostile
```

```python
# tests/test_chrome.py
import pytest
from acu.actuator.chrome import build
from acu.intent.slots import Slots


def test_search_builds_an_encoded_google_url():
    script = build("search", Slots(query="global warming"))
    assert "google.com/search?q=global+warming" in script


def test_search_query_with_quotes_is_escaped():
    script = build("search", Slots(query='say "hi"'))
    assert '\\"' not in script.split("google.com")[0]
    assert "%22hi%22" in script


def test_bare_site_gets_a_scheme():
    assert "https://github.com" in build("goto_site", Slots(site="github"))


def test_site_with_scheme_is_left_alone():
    assert "https://github.com" in build("goto_site", Slots(site="https://github.com"))


def test_targetless_verbs_build():
    for verb in ("new_tab", "close_tab", "back", "scroll"):
        assert build(verb, Slots()).strip()


def test_unknown_verb_is_rejected():
    with pytest.raises(ValueError):
        build("teleport", Slots())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_applescript.py tests/test_chrome.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# acu/actuator/applescript.py
"""Every value crossing into a script is transcribed speech, so escape it."""

import subprocess


def escape(value: str) -> str:
    # Backslash first: escaping quotes first would double-escape its output.
    return value.replace("\\", "\\\\").replace('"', '\\"')


def run(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "osascript failed")
    return result.stdout
```

```python
# acu/actuator/chrome.py
"""The only module that mutates the browser."""

import urllib.parse

from acu.actuator.applescript import escape, run
from acu.intent.slots import Slots

_CONTEXT_SCRIPT = """
set appName to ""
tell application "System Events"
  set appName to name of first process whose frontmost is true
  set chromeRunning to (exists process "Google Chrome")
end tell
if chromeRunning then
  tell application "Google Chrome"
    if (count of windows) = 0 then
      return appName & "\t" & "true" & "\t" & "" & "\t" & "0"
    end if
    return appName & "\t" & "true" & "\t" & (title of active tab of front window) ¬
      & "\t" & (count of tabs of front window)
  end tell
else
  return appName & "\t" & "false" & "\t" & "" & "\t" & "0"
end if
"""


def read_context() -> dict:
    """Read-only. Runs before Jev so the screen becomes evidence."""
    try:
        parts = run(_CONTEXT_SCRIPT).strip().split("\t")
    except (RuntimeError, OSError):
        return {"frontmost_app": "unknown", "chrome_running": False,
                "active_tab_title": "", "tab_count": 0}
    app, running, title, count = (parts + ["", "", "", "0"])[:4]
    return {
        "frontmost_app": app,
        "chrome_running": running == "true",
        "active_tab_title": title,
        "tab_count": int(count or 0),
    }


def _url_for(slots: Slots) -> str:
    if slots.site:
        site = slots.site.strip()
        return site if "://" in site else f"https://{site}"
    query = urllib.parse.quote_plus(slots.query or "")
    return f"https://www.google.com/search?q={query}"


def build(verb: str, slots: Slots) -> str:
    if verb in ("search", "goto_site"):
        url = escape(_url_for(slots))
        return (
            'tell application "Google Chrome"\n'
            " activate\n"
            " if (count of windows) = 0 then make new window\n"
            f' set URL of active tab of front window to "{url}"\n'
            "end tell"
        )
    if verb == "open_app":
        app = escape((slots.app or "Google Chrome").strip())
        return f'tell application "{app}" to activate'
    if verb == "new_tab":
        return (
            'tell application "Google Chrome"\n'
            " activate\n"
            " if (count of windows) = 0 then\n"
            "  make new window\n"
            " else\n"
            "  tell front window to make new tab\n"
            " end if\n"
            "end tell"
        )
    if verb == "close_tab":
        return 'tell application "Google Chrome" to close active tab of front window'
    if verb == "switch_tab":
        index = slots.ordinal or 1
        if index == -1:
            return (
                'tell application "Google Chrome" to tell front window to '
                "set active tab index to (count of tabs)"
            )
        return (
            'tell application "Google Chrome" to tell front window to '
            f"set active tab index to {int(index)}"
        )
    if verb == "back":
        return (
            'tell application "Google Chrome" to tell active tab of front window to '
            "go back"
        )
    if verb == "scroll":
        return (
            'tell application "Google Chrome" to tell active tab of front window to '
            'execute javascript "window.scrollBy(0, window.innerHeight * 0.8)"'
        )
    raise ValueError(f"unknown verb: {verb}")


def perform(verb: str, slots: Slots, dry_run: bool = False) -> str:
    script = build(verb, slots)
    if dry_run:
        return script
    run(script)
    return script
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd audio-computer-use
.venv/bin/pytest tests/test_applescript.py tests/test_chrome.py -v
```

Expected: 10 passed

- [ ] **Step 5: Verify context reading against the real machine**

```bash
.venv/bin/python -c "
from acu.actuator.chrome import read_context
print(read_context())"
```

Expected: a dict naming the frontmost app, e.g. `{'frontmost_app': 'Google Chrome', 'chrome_running': True, ...}`

- [ ] **Step 6: Commit**

```bash
git add audio-computer-use/acu/actuator audio-computer-use/tests/test_applescript.py audio-computer-use/tests/test_chrome.py
git commit -m "Drive Chrome through escaped AppleScript"
```

---

## Task 9: The Jev client

**Files:**
- Create: `acu/intent/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Consumes: `build_questions`, `build_state`, `Judgement`, `Slots`
- Produces: `async judge(command: str, slots: Slots, screen: dict, recent: list[str], model: str = "jev-latest") -> Judgement`

- [ ] **Step 1: Write the failing tests**

Tests use a fake client, so no network call happens.

```python
# tests/test_classify.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_classify.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# acu/intent/classify.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_classify.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/intent/classify.py audio-computer-use/tests/test_classify.py
git commit -m "Ask Jev five questions about each utterance in one request"
```

---

## Task 10: Reporting

**Files:**
- Create: `acu/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `Judgement`, `Decision`
- Produces: `console`, `render_decision(command, judgement, decision) -> None`, `format_usd(amount) -> str`, `cost_usd(tokens) -> float`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report.py
from acu.report import cost_usd, format_usd


def test_sub_cent_runs_are_not_rounded_away():
    assert format_usd(cost_usd(1000)) != "$0.00"


def test_zero_is_plain():
    assert format_usd(0) == "$0"


def test_cost_tracks_the_published_rate():
    assert cost_usd(1_000_000) == 0.042
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# acu/report.py
"""Terminal feedback. The numbers here are what you tune thresholds against."""

from rich.console import Console
from rich.table import Table

from acu.intent.judgement import Judgement
from acu.policy import Decision

console = Console()

USD_PER_MILLION_INPUT_TOKENS = 0.042

_STYLES = {"act": "green", "confirm": "yellow", "ignore": "dim"}


def cost_usd(input_tokens: int) -> float:
    return input_tokens / 1_000_000 * USD_PER_MILLION_INPUT_TOKENS


def format_usd(amount: float) -> str:
    if amount == 0:
        return "$0"
    if amount < 0.01:
        return f"{amount * 100:.3f}¢"
    return f"${amount:.4f}"


def render_decision(command: str, judgement: Judgement, decision: Decision) -> None:
    style = _STYLES.get(decision.action, "white")
    console.print(f'\n[bold]"{command}"[/bold]')

    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_row("verb", f"[{style}]{decision.verb or '—'}[/{style}]")
    table.add_row("action", f"[{style}]{decision.action}[/{style}]")
    table.add_row("reason", decision.reason)
    if not judgement.error:
        table.add_row("addressed", f"{judgement.addressed:.2f}")
        table.add_row("context", f"{judgement.continues_context:.2f}")
        table.add_row("cost", format_usd(cost_usd(judgement.input_tokens)))
    console.print(table)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_report.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/report.py audio-computer-use/tests/test_report.py
git commit -m "Show the judgement behind every decision"
```

---

## Task 11: Session loop and `--text` mode

Wires the pipeline and holds context. `--text` runs everything except audio.

**Files:**
- Create: `acu/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: everything above
- Produces: `async handle(command: str, recent: list[str], screen: dict, dry_run: bool) -> Decision`, `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# acu/session.py
"""Entry point. Code owns the control flow; Jev only judges."""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from acu.actuator import chrome
from acu.intent.classify import judge
from acu.intent.slots import extract
from acu.listener.wake import WAKE_WORD, strip_wake_word
from acu.policy import decide
from acu.report import console, render_decision


async def handle(
    command: str, recent: list[str], screen: dict, dry_run: bool
) -> "object":
    slots = extract(command)
    judgement = await judge(command, slots, screen, recent)
    decision = decide(judgement, slots, screen)
    render_decision(command, judgement, decision)

    if decision.action == "act" and decision.verb:
        try:
            script = chrome.perform(decision.verb, slots, dry_run=dry_run)
        except (RuntimeError, ValueError) as exc:
            console.print(f"[red]actuation failed:[/red] {exc}")
            return decision
        if dry_run:
            console.print(f"[dim]{script}[/dim]")
        recent.append(decision.verb)

    return decision


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="listen", description="Voice-driven browser control with TypeSafe Jev."
    )
    parser.add_argument(
        "--text", nargs="*", help="run typed commands instead of listening"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print AppleScript instead of running it"
    )
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument(
        "--wake-word", default=WAKE_WORD, help="prefix that marks a command"
    )
    return parser.parse_args(argv)


async def _run_text(commands: list[str], dry_run: bool) -> int:
    recent: list[str] = []
    screen = chrome.read_context()
    for raw in commands:
        await handle(raw, recent, screen, dry_run)
        screen = chrome.read_context()
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if not os.environ.get("TYPESAFE_API_KEY"):
        console.print("[red]TYPESAFE_API_KEY is not set.[/red] Add it to .env")
        return 1

    if args.text is not None:
        return asyncio.run(_run_text(args.text, args.dry_run))

    from acu.listener.loop import listen

    return listen(args.wake_word, args.dry_run, args.model)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_session.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/session.py audio-computer-use/tests/test_session.py
git commit -m "Wire the pipeline and let commands be typed as well as spoken"
```

---

## Task 12: Transcription and the live listening loop

The only task needing a microphone. Everything above is already testable without one.

**Files:**
- Create: `acu/listener/transcribe.py`, `acu/listener/loop.py`
- Test: `tests/test_transcribe.py`

**Interfaces:**
- Consumes: `Segmenter`, `strip_wake_word`, `handle`
- Produces: `Transcriber(model=DEFAULT_MODEL).transcribe(samples) -> str`, `DEFAULT_MODEL`, `listen(wake_word, dry_run, model) -> int`

- [ ] **Step 1: Write the failing test**

Generates its own audio with `say`, so it needs no microphone. It is skipped when the model is not cached, keeping the suite fast and offline.

```python
# tests/test_transcribe.py
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from acu.listener.transcribe import Transcriber


@pytest.mark.skipif(not shutil.which("say"), reason="macOS say unavailable")
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg unavailable")
def test_spoken_command_is_transcribed(tmp_path: Path):
    aiff, wav = tmp_path / "s.aiff", tmp_path / "s.wav"
    subprocess.run(["say", "-o", str(aiff), "open chrome"], check=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(aiff),
         "-ar", "16000", "-ac", "1", str(wav)], check=True)

    with wave.open(str(wav)) as handle:
        samples = np.frombuffer(
            handle.readframes(handle.getnframes()), dtype=np.int16
        ).astype(np.float32) / 32768.0

    text = Transcriber().transcribe(samples).lower()
    assert "chrome" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_transcribe.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# acu/listener/transcribe.py
"""Whisper via MLX. The model is loaded once; a per-utterance load costs ~50s."""

import mlx_whisper
import numpy as np

DEFAULT_MODEL = "mlx-community/whisper-small.en-mlx"


class Transcriber:
    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model
        self._warm = False

    def warm_up(self) -> None:
        """Pay the load cost before the first real command, not during it."""
        if not self._warm:
            self.transcribe(np.zeros(16000, dtype=np.float32))
            self._warm = True

    def transcribe(self, samples: np.ndarray) -> str:
        result = mlx_whisper.transcribe(
            samples, path_or_hf_repo=self._model, language="en",
            condition_on_previous_text=False,
        )
        self._warm = True
        return result["text"].strip()
```

```python
# acu/listener/loop.py
"""Microphone in, decisions out."""

import asyncio

import numpy as np
import sounddevice as sd
import torch
from silero_vad import VADIterator, load_silero_vad

from acu.actuator import chrome
from acu.listener.segmenter import FRAME_SAMPLES, SAMPLE_RATE, Segmenter
from acu.listener.transcribe import DEFAULT_MODEL, Transcriber
from acu.listener.wake import strip_wake_word
from acu.report import console
from acu.session import handle


def listen(wake_word: str, dry_run: bool, model: str) -> int:
    transcriber = Transcriber(DEFAULT_MODEL)
    with console.status("Loading the speech model…"):
        transcriber.warm_up()

    vad_model = load_silero_vad()
    vad = VADIterator(vad_model, sampling_rate=SAMPLE_RATE, min_silence_duration_ms=400)
    segmenter = Segmenter()
    recent: list[str] = []

    console.print(f'Listening. Say "[bold]{wake_word}[/bold], open chrome". Ctrl-C to stop.')

    speaking = False
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=FRAME_SAMPLES
        ) as stream:
            while True:
                block, _ = stream.read(FRAME_SAMPLES)
                frame = block[:, 0].copy()

                event = vad(torch.from_numpy(frame), return_seconds=True)
                if event:
                    if "start" in event:
                        speaking = True
                    if "end" in event:
                        speaking = False

                utterance = segmenter.push(frame, is_speech=speaking)
                if utterance is None:
                    continue

                text = transcriber.transcribe(utterance)
                if not text:
                    continue

                command = strip_wake_word(text, wake_word)
                if command is None:
                    console.print(f"[dim]ignored: {text}[/dim]")
                    continue

                screen = chrome.read_context()
                asyncio.run(handle(command, recent, screen, dry_run))
    except KeyboardInterrupt:
        console.print("\nStopped.")
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_transcribe.py -v`
Expected: 1 passed (first run downloads the model and is slow)

- [ ] **Step 5: Commit**

```bash
git add audio-computer-use/acu/listener/transcribe.py audio-computer-use/acu/listener/loop.py audio-computer-use/tests/test_transcribe.py
git commit -m "Transcribe utterances and drive the loop from the microphone"
```

---

## Task 13: README and full verification

**Files:**
- Create: `audio-computer-use/README.md`

- [ ] **Step 1: Run the whole suite**

```bash
cd audio-computer-use
.venv/bin/pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Verify the pipeline end to end without audio**

Requires `TYPESAFE_API_KEY` in `.env`. Prints the AppleScript rather than running it.

```bash
.venv/bin/listen --dry-run --text \
  "open chrome" \
  "search global warming" \
  "go to github.com" \
  "close time"
```

Expected: the first three decide `act`; `"close time"` (the real misrecognition measured during planning) decides `confirm` or `ignore`, never `act`.

- [ ] **Step 3: Write the README**

Cover: what it does; the `code extracts / Jev judges` architecture and why Jev cannot return text; the layer table from the spec; setup (venv, `TYPESAFE_API_KEY`, microphone permission); usage for both `--text` and voice; the five thresholds in `policy.py` and how to tune them; the eight verbs; cost per utterance; and the v1 limits from the spec's "Out of scope" section, including the risk-blind tiering decision.

- [ ] **Step 4: Commit**

```bash
git add audio-computer-use/README.md
git commit -m "Document setup, tuning, and the limits of v1"
```

- [ ] **Step 5: Live microphone check (requires the user)**

This is the one step that cannot be automated: microphone access needs a granted
permission and a real voice.

```bash
.venv/bin/listen --dry-run
```

Say: *"computer, open chrome"*, then *"computer, search global warming"*.
Expected: each utterance prints a transcript, a verb, confidences, and the
AppleScript it would run. Report what the second command decides — it is the
context-resolution case from the design.
