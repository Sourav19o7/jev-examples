# Generic App Control — Design

Extend voice control from Chrome alone to every application that exposes its user
interface, by naming on-screen controls out loud: *"computer, click source control."*

Builds on `2026-09-24-audio-computer-use-design.md`, which this document assumes. The
listening pipeline, wake gate, question set, and confidence tiers are unchanged. What
changes is the actuator and one new question.

## What is actually possible

Measured on the target machine rather than assumed. Each app's frontmost window was
walked through the Accessibility API and its labelled, actionable controls counted.

| App | Backend | Labelled controls | Verdict |
| --- | --- | --- | --- |
| VS Code | Accessibility | 175 | drivable |
| Android Studio | Accessibility | 105 | drivable |
| Claude | Accessibility | 78 | drivable |
| WhatsApp | Accessibility | 28 | drivable |
| Fellow | Accessibility | 21 | drivable |
| Chrome | AppleScript + Accessibility | 20 | drivable |
| Spotify | **AppleScript** | 1 | drivable — its scripting dictionary covers playback |
| Slack | — | 1 | **opaque** |
| Notion | — | 1 | **opaque** |
| Warp, Finder | — | ≤1 | **opaque** |

Three findings shape the design.

**Two backends are needed, not one.** Spotify is opaque to the Accessibility API and
fully controllable through AppleScript; VS Code is the reverse. Neither alone covers
the machine.

**Accessibility trees populate lazily.** Claude and Fellow reported one control each
until they were focused, then 78 and 21. The element probe must therefore run at
command time against the frontmost app — never cached at startup.

**Walking is fast enough.** VS Code's 1,188-node window surveyed in 0.08s; the slowest
app measured 0.55s. Both fit inside the voice loop, whose transcription step alone
costs 0.09s.

**Slack and Notion cannot be driven semantically.** This is a property of applications
that do not opt into accessibility, not a limitation of this approach: no automation
tool on macOS can see inside them. They receive safe universal keystrokes and nothing
more. This limit is permanent and is stated plainly in the README rather than worked
around.

## Decisions taken

### 1. Semantic control, not coordinate synthesis

Elements are located in the Accessibility tree and pressed through `AXPress`.

*Rejected:* synthesising keystrokes and clicks at screen coordinates. That works
everywhere, including Slack, because it bypasses accessibility entirely — and that is
exactly the problem. It cannot know what it is clicking, so a misheard command does not
fail, it presses something arbitrary. Semantic control fails cleanly: an unknown
element is simply not found.

*Consequence accepted:* opaque applications get a small set of safe universal
keystrokes and are otherwise unreachable.

### 2. Generic control, not per-app vocabularies

One verb, `click_element`, that names whatever control is on screen. No per-application
verb sets.

*Rejected:* per-app vocabularies (*"next track"* for Spotify, *"commit"* for VS Code).
More natural to speak, but each application needs its own maintained verb list, and
newly installed applications work only after someone adds them.

*Consequence:* the system works on any application that exposes its tree, including
ones installed later, with no curation.

### 3. Destructive labels always confirm

A control whose label matches a destructive pattern asks before it is pressed,
whatever the confidence.

This reverses, for element presses only, the risk-blind tiering of the parent design.
That decision was made when the vocabulary was eight read-mostly browser verbs, and its
stated justification was that the v1 vocabulary "is read-mostly, which bounds the
exposure." Generic element pressing removes that bound: *Send*, *Delete*, *Publish* and
*Merge* are all simply buttons.

The guard is deliberately narrow — a label pattern, not a full risk-tier system — and
uses the `RISK_TIERS` seam the parent design left in place.

## Architecture

The pipeline is unchanged through the wake gate. Two stages are added: a live element
probe before Jev, and a backend router after policy.

```text
… wake gate ──> probe frontmost app ──> slots ──> JEV ──> policy ──> router
                (AX tree, live)                  (judge)  (decide)   ├─ sdef
                       │                                             ├─ AX press
                  candidates ───────────────────┘                    └─ keystroke
```

| Layer | Module | Responsibility |
| --- | --- | --- |
| Probe | `acu/ax/tree.py` | Walk the frontmost window; return labelled elements |
| Shortlist | `acu/ax/shortlist.py` | Rank and cap candidates against the utterance |
| Press | `acu/ax/press.py` | `AXPress` a chosen element; the only new mutation point |
| Keystrokes | `acu/actuator/keystroke.py` | The safe universal set for opaque apps |
| Route | `acu/actuator/router.py` | Choose the backend: sdef → Accessibility → keystroke |

`acu/actuator/chrome.py` is unchanged and becomes one scripting-dictionary backend
rather than the only actuator.

`tree.py` is read-only and runs before Jev, exactly as `chrome.read_context()` does
today. It produces candidates; Jev chooses among them; `press.py` alone acts.

## How Jev chooses an element

Jev cannot return text, so it cannot name a button. The shortlist is built by code and
becomes the `Choice` criteria, generated fresh for each utterance:

```python
Choice(
    instructions="Which on-screen control is the speaker asking for?",
    criteria={
        "el_7":  "button: Source Control",
        "el_31": "button: Run and Debug",
        "el_44": "checkbox: Toggle Panel",
        "none":  "No control on screen matches what was said.",
    },
)
```

Three properties make this sound:

**Jev can only choose what exists.** The criteria come from the live tree, so no
invented element is representable.

**`none` is always present.** A `Choice` with no escape is forced to pick, and — as the
parent design measured with `"close time"` scoring `close_tab` at 0.98 — it will pick
confidently. `none` is what lets Jev decline, and it is the element-level analogue of
the ambiguity gate.

**The shortlist is capped at 25.** VS Code exposes 175 controls; sending them all would
spread the distribution and pad the state with irrelevant bulk, which the parent design
already identifies as an accuracy risk. Candidates are pre-ranked by token overlap with
the utterance and truncated.

### The question set

`click_element` joins the existing eight verbs in the `command` Choice. One new question
rides in the same request:

| Question | Primitive | Asks |
| --- | --- | --- |
| `element` | `Choice` over the live shortlist plus `none` | Which on-screen control was meant? |

It is included only when the probe returned candidates. The existing five questions are
unchanged, so `addressed_to_computer` and `ambiguity` gate element presses exactly as
they gate browser verbs.

## Policy

Existing thresholds are unchanged. Two additions:

```python
ELEMENT_FLOOR = 0.70      # below this, or on "none", ask rather than press
DESTRUCTIVE = (
    "delete", "remove", "send", "publish", "merge",
    "discard", "trash", "quit", "close without saving",
)
```

For a `click_element` decision:

1. The probe found no candidates → `confirm`, reporting that nothing was readable.
2. `element` resolves to `none`, or below `ELEMENT_FLOOR` → `confirm`.
3. The chosen element's label matches `DESTRUCTIVE` → `confirm`, always, whatever the
   confidence.
4. Otherwise the existing tiers apply unchanged.

Matching is on the element's label, case-insensitively, on word boundaries — so
*"Send"* and *"Send message"* match, while *"Sender"* does not.

## Backend routing

`router.py` resolves a decision to exactly one backend, in order:

1. **Scripting dictionary**, when the frontmost app has one and the verb maps to it.
   Chrome and Spotify take this path; it is the most reliable and needs no tree walk.
2. **Accessibility press**, when the probe found the element.
3. **Safe keystroke**, when the app is opaque and the utterance maps to the universal
   set.

The safe keystroke set is deliberately small and non-destructive: save (`⌘S`), close
window (`⌘W`), escape, and the arrow keys. Notably it excludes `⌘Q`, `⌘Delete` and any
text entry — an opaque app is one whose state cannot be inspected, so it is the worst
place to act blind.

When no backend applies, the decision reports that the application cannot be driven.
This is a normal outcome, not an error.

## Failure modes

| Stage | Failure | Behaviour |
| --- | --- | --- |
| Probe | App opaque, no candidates | `confirm`, reporting nothing readable |
| Probe | Walk exceeds its budget | Truncate; judge on what was found |
| Jev | Chooses `none` | `confirm`; never press a guessed element |
| Press | Element vanished between probe and press | Report; do not retry or re-probe |
| Press | `AXPress` unavailable on the element | Report the available actions |
| Router | No backend applies | Report that the app cannot be driven |

Re-probing after a failed press is explicitly rejected: the tree has changed, so the
element that would be found second is not the one the user chose.

## Testing

The parent design's rule holds — the pipeline stays testable without a microphone, a
browser, or a focused application:

- `shortlist.py`, the `DESTRUCTIVE` matcher, and routing are pure functions over
  fabricated element lists.
- `tree.py` is tested against a recorded tree fixture captured from a real application,
  so no live app is required.
- `press.py` is exercised with a fake element object; a real `AXPress` is never
  performed in a test.
- The `--text` mode gains `--elements` to inject a fabricated candidate list, so element
  selection is exercisable end to end without any application in focus.

## Out of scope

- Typing arbitrary text into arbitrary fields. Reading a field's label is safe;
  entering text is a larger surface and a separate decision.
- Coordinate or keystroke synthesis beyond the safe universal set (see decision 1).
- Per-application vocabularies (see decision 2).
- Window and space management.
- Making opaque applications drivable. Not achievable by any means available here.
