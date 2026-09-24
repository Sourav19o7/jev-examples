# Audio Computer Use

Voice-driven browser control. Say a wake word and a command; it happens in Chrome.

```
"computer, open chrome"
"computer, search global warming"
```

Built on [TypeSafe Jev](https://docs.typesafe.ai), a System One model that returns
typed, calibrated decisions instead of text.

## Architecture

The shape follows TypeSafe's core guidance: **code owns control flow, Jev only judges.**

```
mic ──> VAD ──> Whisper ──> wake gate ──> slots ──> JEV ──> policy ──> AppleScript
       (segment) (text)    (deterministic) (extract) (judge)  (decide)   (act)
                                                       │
                                                   session
                                                   context
```

| Layer | Module | Responsibility |
| --- | --- | --- |
| Listen | `acu/listener/segmenter.py` | Group frames into utterances |
| Transcribe | `acu/listener/transcribe.py` | MLX Whisper, utterance → text |
| Gate | `acu/listener/wake.py` | Wake-word check; strip it, discard the rest |
| Context | `acu/actuator/chrome.py` | Read frontmost app and Chrome tab state |
| Slots | `acu/intent/slots.py` | Extract literal query/site/ordinal from text |
| Questions | `acu/intent/questions.py` | The typed question set — the only place decisions are defined |
| Judge | `acu/intent/classify.py` | One Jev request per utterance, five questions in parallel |
| Policy | `acu/policy.py` | Confidence tiers → act / confirm / ignore |
| Act | `acu/actuator/chrome.py` | The only module that mutates the browser |

### Why Jev cannot simply be handed the transcript

Jev exposes three primitives — `Choice`, `Score`, `Noul` — and all three return
**probability distributions over options defined in advance**. None returns text.

For *"search global warming"*:

- *Which action is this?* — `Choice` over eight verbs. Jev is excellent at this.
- *What is the query string?* — the literal `"global warming"`. Jev **cannot** return
  this, at any prompt, ever.

So `slots.py` extracts literal spans by rule, and Jev judges what the utterance means.
Jev is never asked a question it cannot answer with a probability.

### The five decisions

All five ride in a **single request per utterance**, evaluated in parallel.

| Question | Primitive | Returns |
| --- | --- | --- |
| `command` | `Choice` over 8 verbs | verb + full distribution + confidence |
| `addressed_to_computer` | `Noul` | probability 0–1 |
| `continues_context` | `Noul` | probability 0–1 |
| `target_is_site` | `Noul` | probability 0–1 |
| `ambiguity` | `Score` over a 5-level rubric | weighted position + confidence |

### Why the policy layer is separate

Jev returns judgements, not actions. `policy.py` turns them into actions under explicit
rules:

- Not addressed to the computer (< `0.60`) → ignored. This is what stops it acting on
  speech aimed at a person; measured at **0.09** for conversational speech.
- Command confidence < `0.50` → ignored; between `0.50` and `0.80` → confirm.
- **Ambiguity > `1.0` → confirm**, even at high command confidence. See below.
- A command missing its target is rescued by screen context only when
  `continues_context` ≥ `0.50`; otherwise it asks.
- A Jev error never results in an action.

#### The ambiguity gate is the one that matters

`Choice` confidence saturates. Among eight verbs, a misheard phrase still has a
*nearest* verb, so live Jev scores the mis-hearing `"close time"` as `close_tab` at
**0.98** — correct behaviour for a `Choice`, useless as a measure of whether the
utterance was understood.

The `ambiguity` Score is what carries that signal. Measured against live Jev:

| Utterance | `command_confidence` | `ambiguity` | Decision |
| --- | --- | --- | --- |
| `"close tab"` | 1.00 | 0.36 | act |
| `"close time"` (misheard) | 0.98 | 1.55 | **confirm** |
| `"purge everything"` | 0.96 | 2.35 | **confirm** |
| `"yeah I'll call you back later"` | 0.61 | 3.88 | **ignored** (addressed 0.09) |

## Setup

### 1. Install

```bash
cd audio-computer-use
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### 2. TypeSafe API key

```bash
cp .env.example .env
# edit .env and set TYPESAFE_API_KEY
```

### 3. Microphone permission

Voice mode needs microphone access for the terminal you run it in. macOS prompts on
first use; if you miss it, grant it under **System Settings → Privacy & Security →
Microphone**.

Chrome control uses AppleScript and needs no Accessibility grant.

## Usage

Type commands instead of speaking them — the whole pipeline except audio:

```bash
.venv/bin/listen --dry-run --text "open chrome" "search global warming"
```

`--dry-run` prints the AppleScript instead of running it. Drop it to act for real:

```bash
.venv/bin/listen --text "search global warming"
```

Voice:

```bash
.venv/bin/listen
```

Then say *"computer, open chrome"*. Options:

```bash
.venv/bin/listen --wake-word jarvis
.venv/bin/listen --model jev-latest
```

## The eight commands

`open_app`, `search`, `goto_site`, `new_tab`, `close_tab`, `switch_tab`, `back`,
`scroll` — all Chrome, all AppleScript-native.

## Tuning

Start in `acu/intent/questions.py` — the verb criteria and the ambiguity rubric are
plain text, and rewording a criterion is the highest-leverage change you can make.
Thresholds live as named constants at the top of `acu/policy.py`.

If a command is refused, read the `ambiguity` row before touching the questions. A high
ambiguity with a confident verb means the phrase was genuinely unclear — usually a
mis-hearing, not a misfire.

`AMBIGUITY_CEILING` is the constant to move first: lower it to ask more often, raise it
to act more readily.

## Cost

Jev bills on input tokens only, at $0.042 per million. A command costs about
**0.004¢** — roughly 25,000 commands per dollar.

## Limits of v1

- **Chrome only.** No other applications, no arbitrary UI clicking.
- **Confidence tiers are risk-blind.** `open` and `close_tab` sit behind the same
  thresholds; no verb is protected by consequence. `RISK_TIERS` in `policy.py` is the
  seam where that would go.
- **Wake word required.** Always-on listening is a configuration change away — the
  `addressed_to_computer` question already exists — but is not enabled.
- **Prompts are printed, not spoken.** Confirmation is answered by voice, but the
  question appears in the terminal.
- **One command per utterance.** *"Open Chrome and search X"* is not handled.

## Tests

```bash
.venv/bin/pytest
```

61 tests, no network and no microphone: the Jev client is faked, the actuator is built
but not run, and the transcription test synthesizes its own audio with `say`.
