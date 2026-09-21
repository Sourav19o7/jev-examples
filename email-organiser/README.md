# Email Organiser

Organises a Gmail inbox using [TypeSafe Jev](https://docs.typesafe.ai), a System One
model that returns typed, calibrated decisions instead of text.

## Architecture

The shape follows TypeSafe's core guidance: **code owns control flow, Jev only judges.**

```
Gmail API ──> state builder ──> JEV ──> policy ──> Gmail labels
 (fetch)      (structured      (judge)  (decide)    (act)
              text state)
```

| Layer | Module | Responsibility |
| --- | --- | --- |
| Fetch | `organiser/gmail/messages.py` | Pull messages, decode MIME, strip quoted replies |
| State | `organiser/jev/state.py` | Build the named-field state object Jev reads |
| Questions | `organiser/jev/questions.py` | The four typed questions — the only place decisions are defined |
| Judge | `organiser/jev/classify.py` | One request per email, four questions evaluated in parallel |
| Policy | `organiser/policy.py` | Deterministic composition + confidence gating |
| Act | `organiser/gmail/labels.py` | The only module that mutates the mailbox |

### The four decisions

All four ride in a **single request per email**. Jev evaluates independent questions in
parallel, which the docs measure at ~12x cheaper and ~10x faster than separate calls.

| Question | Primitive | Returns |
| --- | --- | --- |
| `category` | `Choice` over 9 categories | label + full probability distribution + confidence |
| `urgency` | `Score` over a 5-level rubric | probability-weighted position + confidence |
| `needs_reply` | `Noul` | probability 0–1 |
| `bulk_archivable` | `Noul` | probability 0–1 |

### Why the policy layer is separate

Jev returns judgements, not actions. `policy.py` turns them into actions under explicit
rules, gated by risk — archiving hides mail, so it demands more evidence than labelling:

- Category confidence < `0.60` → held for review, nothing applied.
- Archive requires bulk ≥ `0.85` **and** category confidence ≥ `0.85` **and** not
  awaiting a reply **and** not urgent.
- `personal`, `work`, `security`, `transactional` are **never** archived, whatever the
  model says. A wrong archive there costs you something real.

Jev's documented weak spots (dates, counting, prompt injection from hostile message
bodies) are deliberately kept out of its remit — no question asks it to compare dates or
do arithmetic.

## Setup

### 1. Install

```bash
cd email-organiser
python3 -m venv .venv
.venv/bin/pip install -e .
```

### 2. TypeSafe API key

Create a key at [console.typesafe.ai](https://console.typesafe.ai), then:

```bash
cp .env.example .env
# edit .env and set TYPESAFE_API_KEY
```

### 3. Gmail OAuth credentials

1. Open [Google Cloud Console](https://console.cloud.google.com/) → new (or existing) project.
2. **APIs & Services → Library →** enable **Gmail API**.
3. **OAuth consent screen →** External, add your own address as a test user.
4. **Credentials → Create credentials → OAuth client ID → Desktop app.**
5. Download the JSON and save it as:

```bash
mkdir -p ~/.email-organiser
mv ~/Downloads/client_secret_*.json ~/.email-organiser/credentials.json
```

The first run opens a browser to authorise. The token is cached at
`~/.email-organiser/token.json` (chmod 600) and refreshed automatically.

The app requests `gmail.modify`: it can label and archive, but **cannot delete
permanently** — there is no scope here that can destroy mail.

## Usage

Dry run — prints the table, touches nothing:

```bash
.venv/bin/organise
```

Apply to Gmail:

```bash
.venv/bin/organise --apply
```

Options:

```bash
.venv/bin/organise --query "in:inbox newer_than:2d" --limit 50
.venv/bin/organise --concurrency 12     # parallel Jev requests
.venv/bin/organise --model jev-latest
```

Labels are created on demand under a `Jev/` parent: `Jev/work`, `Jev/newsletter`,
`Jev/needs-reply`, `Jev/urgent`, and so on. To undo an experiment, delete the `Jev`
label tree in Gmail settings; archived mail is still in **All Mail**.

## Tuning

Start in `organiser/jev/questions.py` — the categories and the urgency rubric are plain
text, and rewording a level is the highest-leverage change you can make. Thresholds live
as named constants at the top of `organiser/policy.py`.

If results look wrong, read the `Conf` column before touching the questions: a spread
distribution usually means the category boundary is genuinely ambiguous, not that the
model misfired.

## Cost

Jev is billed on input tokens only, at $0.042 per million. Scanning a few hundred emails
costs a fraction of a cent.
