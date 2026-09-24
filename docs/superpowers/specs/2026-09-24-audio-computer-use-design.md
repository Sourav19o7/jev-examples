# Audio Computer Use — Design

Voice-driven browser control. Speak a wake word and a command; the machine
carries it out in Chrome.

Built on [TypeSafe Jev](https://docs.typesafe.ai), following the same principle as
the sibling `email-organiser` project: **code owns control flow, Jev only judges.**

## The problem this design solves

A naive reading of "voice controls the computer" suggests: transcribe speech, hand
the text to a model, let the model act. That shape cannot be built with Jev, and
the reason is the central constraint of this design.

Jev exposes exactly three primitives — `Choice`, `Score`, `Noul` — and all three
return **probability distributions over options defined in advance**. None returns
free-form text.

So for the utterance *"search global warming"*:

- *Which action is this?* — `Choice` over known verbs. Jev is excellent at this.
- *What is the query string?* — the literal text `"global warming"`. **Jev
  structurally cannot return this.** No prompt design extracts a string from a
  distribution.

The architecture follows directly: **code extracts, Jev judges.** A deterministic
slot extractor pulls literal spans out of the transcript; Jev decides what the
utterance *means*, whether it was addressed to the computer at all, and how much
to trust the reading. Jev is never asked a question it cannot answer with a
probability.

### Why Jev is load-bearing and not decorative

A regex table could map `"open chrome"` to an action. It could not do these, all of
which are genuinely hard and all of which decide whether the system is usable:

- **Is this even a command?** The microphone hears everything, including speech to
  other people. A `Noul` gates it.
- **Which of several plausible readings?** `"go to github"` (navigate) versus
  `"search github"` (query) differ in intent, not in surface form.
- **Does this depend on what is on screen?** `"search global warming"` means
  *search in Chrome* only because Chrome is focused. Said cold, it is ambiguous.
- **How much should we trust this?** Speech-to-text mishears. Calibrated confidence
  is what separates acting, confirming, and staying quiet.

## Architecture

```text
mic ──> VAD ──> Whisper ──> wake gate ──> slots ──> JEV ──> policy ──> AppleScript
       (segment) (text)    (deterministic) (extract) (judge)  (decide)   (act)
                                                       │
                                                   session
                                                   context
```

| Layer | Module | Responsibility |
| --- | --- | --- |
| Listen | `listener/capture.py` | Mic stream, Silero VAD, emit utterance audio |
| Transcribe | `listener/transcribe.py` | MLX Whisper, utterance → text |
| Gate | `listener/wake.py` | Wake-word prefix check; strip it, discard the rest |
| Context | `intent/context.py` | Read frontmost app and Chrome tab state |
| Slots | `intent/slots.py` | Extract literal query/site/ordinal from text |
| Questions | `intent/questions.py` | The typed question set — the only place decisions are defined |
| Judge | `intent/classify.py` | One Jev request per utterance, questions in parallel |
| Policy | `policy.py` | Confidence tiers → act / confirm / ignore |
| Act | `actuator/chrome.py` | The only module that touches the browser |
| Loop | `session.py` | Wires the stages, holds context, runs the confirm cycle |

Two boundaries carry the weight.

**`slots.py` extracts, Jev judges.** Literal strings come from rules, never from the
model, because the model cannot produce them.

**`policy.py` decides, `chrome.py` acts.** Jev returns judgements; policy converts
them to actions under explicit thresholds; a single module mutates anything. This
mirrors `email-organiser`, where `labels.py` is the sole mutation point.

**`context.py` is read-only and runs before Jev**, so frontmost-app and tab facts
enter the state as named fields. This is what makes context resolution possible:
Jev judges `frontmost_app: "Google Chrome"` as evidence. It never queries the
screen itself.

## Decisions taken

Five decisions were settled during design. Each is recorded with its rejected
alternatives, because the alternatives are reasonable and may be revisited.

### 1. Context-aware, not stateless

The session tracks the frontmost application and recent commands, so
*"search global warming"* resolves against Chrome-in-focus.

*Rejected:* stateless commands, where every utterance fully specifies its target
(*"search Google for global warming"*). Simpler and more predictable, but more
verbose to speak, and it leaves so little ambiguity that Jev would be reduced to a
lookup table.

*Cost accepted:* context can be stale or wrong. Confidence gating is the mitigation,
which makes it load-bearing rather than a nicety.

### 2. Confidence tiers, risk-blind

One confidence dimension, three tiers: act, confirm, ignore. All commands are
governed by the same thresholds.

*Rejected:* tiering by consequence, where destructive verbs always confirm
regardless of confidence — the analogue of `NEVER_ARCHIVE` in `email-organiser`.

*Known risk, accepted deliberately:* `"open Chrome"` and a destructive command sit
behind the same threshold. The concern is not that Jev is often wrong; it is that
the cost of a rare miss is unbounded, and short verbs are exactly what speech-to-text
most often confuses. This was raised during design and the risk-blind choice was
reaffirmed for v1, where every additional confirmation is friction.

*Seam left in place:* a `RISK_TIERS` mapping and one added condition in `decide()`.
Adding risk tiering later is a policy-layer edit, not a restructure. The v1
vocabulary is read-mostly, which bounds the exposure.

### 3. Browser-focused vocabulary

Eight verbs, Chrome only, every one AppleScript-native: `open`, `search`,
`new_tab`, `close_tab`, `switch_tab`, `back`, `scroll`, `goto_site`.

*Rejected:* general computer use across arbitrary applications. That requires the
Accessibility API for UI-tree traversal, granted permissions, and a two-stage
`Choice` decomposition to stop probability mass spreading across near-synonymous
verbs. It is a substantially larger project and the natural successor to this one,
but it needs a working pipeline beneath it first.

*Also rejected:* a two-verb minimum (`open`, `search`). Too thin to exercise the
context resolution that decision 1 commits to.

### 4. Wake word

Commands are prefixed: *"computer, search global warming."* The gate is a
deterministic prefix check in code, before Jev is called.

*Rejected:* push-to-talk (not hands-free, undercuts the premise) and always-on with
a Jev `Noul` gate (highest risk, bills a request for every stray sentence in the
room, and a probabilistic gate eventually lets background speech through).

*Consistent with the rest of the design:* the gate sits in code, not in a
probability. It also bounds cost, since Jev is only consulted for plausible
commands.

*Composable later:* the `addressed_to_computer` question already exists as a second
check behind the wake word. Always-on is a later configuration change, not a
rewrite.

### 5. Terminal feedback, voice replies

Prompts and results print to the console with `rich`. Confirmations are answered by
voice through the same VAD and Whisper loop.

*Rejected:* spoken prompts via macOS `say`, and an always-on-top overlay.

*Reasoning:* early use is mostly threshold tuning, which means reading
distributions and confidences. The terminal shows them; a voice-only channel hides
exactly the numbers needed. `report.py` follows the precedent already set in
`email-organiser`. Speech output is a single function if silent prompts prove
annoying in practice.

## The question set

Five questions ride in **one request per utterance**, evaluated in parallel — the
pattern the Jev documentation recommends and that `email-organiser` already uses.

| Question | Primitive | Returns |
| --- | --- | --- |
| `command` | `Choice` over 8 verbs | verb + full distribution + confidence |
| `addressed_to_computer` | `Noul` | probability 0–1 |
| `continues_context` | `Noul` | probability 0–1 |
| `target_is_site` | `Noul` | probability 0–1 |
| `ambiguity` | `Score` over 5 levels | weighted position + confidence |

`command` is the workhorse. `continues_context` is what makes the motivating
example work. `target_is_site` separates `"go to github"` from `"search github"`, a
distinction slots cannot make. `ambiguity` measures how confident the overall
reading is; it is **not** risk tiering, which decision 2 excluded.

Kept deliberately out of Jev's remit, following its documented weak spots: no
arithmetic, no date comparison, and no question whose answer would have to be a
string.

## State

Named fields, so relationships stay explicit — the shape `email-organiser/jev/state.py`
uses:

```python
{
  "utterance": "search global warming",
  "slots": {"query": "global warming"},
  "screen": {
      "frontmost_app": "Google Chrome",
      "chrome_running": True,
      "active_tab_title": "New Tab",
      "tab_count": 1,
  },
  "recent_commands": ["open_app"],   # most recent last, capped
}
```

`recent_commands` is capped at a small window. Unbounded history would grow state
without improving judgement, and Jev's accuracy degrades when state carries
irrelevant bulk.

## Policy

Named constants at module top, the tuning surface:

```python
ACT_FLOOR       = 0.80   # carry it out
CONFIRM_FLOOR   = 0.50   # ask first; below this, ignore silently
ADDRESSED_FLOOR = 0.60   # not addressed to the computer → drop before anything else
CONTEXT_FLOOR   = 0.50   # resolve an underspecified target against screen context
SITE_FLOOR      = 0.60   # treat the slot as a site rather than a search query
```

Order of evaluation in `decide()`:

1. Jev error → ignore and log. **Never act on an errored judgement.**
2. `addressed_to_computer` below `ADDRESSED_FLOOR` → ignore. Speech that leaked past
   the wake word.
3. `command` confidence below `CONFIRM_FLOOR` → ignore, log the contested pair.
4. Confidence between floors → confirm, showing the top two candidates.
5. Above `ACT_FLOOR` → resolve target, act.

Target resolution: a command needing a target but lacking a slot is rescued by
context when `continues_context` clears `CONTEXT_FLOOR`; otherwise it drops to
confirm. `target_is_site` above `SITE_FLOOR` routes to navigation, else to search.

## Speech-to-text

**Local MLX Whisper, with Silero VAD segmentation.** Chosen for this hardware
(Apple Silicon, `mlx` present, `ffmpeg` installed).

**Utterance-segmented, not token-streaming.** This is deliberate. Commands are
short, and VAD provides a clean "speaker stopped" boundary — a better trigger than
partial hypotheses needing debouncing. VAD also solves Whisper's documented
tendency to hallucinate text during silence, since silence never reaches the model.

*Alternatives weighed:* Parakeet is streaming-native but benchmarks roughly 2.6×
slower than Whisper on Apple Silicon; Moonshine is the strongest edge option but
weaker on general vocabulary. Neither advantage applies to short command phrases on
this machine.

## Actuation

**AppleScript via `osascript`**, verified working on the target machine — reading
Chrome's active tab URL succeeded with no permission prompt. Chrome ships a
scripting dictionary covering every v1 verb natively.

*Rejected:* PyAutoGUI, which needs an Accessibility grant and synthesises input
rather than driving the application.

`actuator/applescript.py` holds script templates and the subprocess call;
`actuator/chrome.py` maps intents to them. **All interpolated values are escaped**,
never formatted into script text raw — a search query is arbitrary transcribed
speech and must not be able to terminate a string literal and inject script.

## Failure modes

Every stage fails independently, and each degrades alone rather than cascading:

| Stage | Failure | Behaviour |
| --- | --- | --- |
| VAD | Silence, noise | No utterance emitted; no-op |
| Whisper | Garbled transcript | Wake gate rejects it; no Jev call |
| Wake gate | Wake word misheard | Utterance dropped; user repeats |
| Jev | API error, timeout | Ignore and log; **never act** |
| Policy | Low confidence | Confirm or ignore by tier |
| Actuator | AppleScript error, Chrome absent | Report; do not retry |

Retrying a failed actuation is explicitly rejected: a partially applied browser
action is not safely repeatable without knowing how far it got.

## Testing

The pipeline is testable without a microphone and without a browser:

- `wake.py`, `slots.py`, `policy.py` — pure functions, plain unit tests, no I/O
- `intent/` — transcript strings plus fabricated context dicts
- `actuator/` — `--dry-run` prints the AppleScript instead of executing it
- `session.py` — `--text` accepts typed commands, exercising everything but audio

Threshold tuning therefore needs no audio at all, and each failure mode above is
reachable in a test.

## Layout

```text
audio-computer-use/
  pyproject.toml          # console script: listen
  README.md
  .env.example
  listener/    capture.py  transcribe.py  wake.py
  intent/      context.py  slots.py  questions.py  classify.py
  actuator/    applescript.py  chrome.py
  policy.py    session.py  report.py
  tests/
```

Dependencies: `typesafe-sdk`, `mlx-whisper`, `silero-vad`, `sounddevice`, `rich`,
`python-dotenv`.

## Out of scope for v1

Recorded here so the boundary is explicit, not forgotten:

- Applications other than Chrome; the Accessibility API; arbitrary UI clicking
- Risk tiering by consequence (seam left; see decision 2)
- Always-on listening without a wake word (question already exists; see decision 4)
- Spoken prompts and on-screen overlay (see decision 5)
- Multi-step commands in one utterance ("open Chrome and search X")

## Tuning

Start in `intent/questions.py`. The verb criteria and the ambiguity rubric are plain
text, and rewording a criterion is the highest-leverage change available — the same
guidance `email-organiser` gives for its categories.

Read the confidence column before editing questions. A spread distribution usually
means the utterance was genuinely ambiguous, not that the model misfired.
