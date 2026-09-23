"""Local review UI. Serves proposals; applies only what the browser ticked."""

import argparse
import asyncio
import os
import threading
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from organiser.gmail import labels as labels_module
from organiser.gmail.auth import get_owner_address, get_service
from organiser.gmail.messages import fetch, sender_name
from organiser.jev.classify import judge_all
from organiser.jev.pricing import USD_PER_MILLION_INPUT_TOKENS, cost_usd
from organiser.policy import Plan, plan_all

DEFAULT_QUERY = "in:inbox is:unread newer_than:7d"
TEMPLATE = Path(__file__).parent / "templates" / "index.html"

app = FastAPI(title="Jev Email Organiser")

# Apply must act on the judgements the user actually saw, so scans are cached
# here by message id rather than re-judged on submit.
_scanned: dict[str, Plan] = {}
_lock = threading.Lock()


class ApplyRequest(BaseModel):
    label_ids: list[str] = []
    archive_ids: list[str] = []


def _serialise(plan: Plan) -> dict:
    j = plan.judgement
    return {
        "id": j.email.id,
        "sender": sender_name(j.email),
        "subject": j.email.subject,
        "category": j.category,
        "confidence": round(j.category_confidence, 2),
        "urgency": round(j.urgency, 1),
        "needs_reply": round(j.needs_reply, 2),
        "owner_must_act": round(j.owner_must_act, 2),
        "labels": [name.split("/")[-1] for name in plan.add_labels],
        "archive": plan.archive,
        "needs_review": plan.needs_review,
        "review_reasons": plan.review_reasons,
        "input_tokens": j.input_tokens,
        "error": j.error,
        "category_probabilities": {
            k: round(v, 4)
            for k, v in sorted(
                j.category_probabilities.items(), key=lambda kv: -kv[1]
            )
        },
        "urgency_confidence": round(j.urgency_confidence, 2),
        "urgency_legend": {str(k): v for k, v in (j.urgency_legend or {}).items()},
        "urgency_probabilities": {
            str(k): round(v, 4) for k, v in (j.urgency_probabilities or {}).items()
        },
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(TEMPLATE)


@app.get("/api/scan")
def scan(limit: int = 25, query: str = DEFAULT_QUERY) -> dict:
    try:
        service = get_service()
        owner = get_owner_address(service)
        emails = fetch(service, query, limit)
        if not emails:
            return {"owner": owner, "rows": [], "error": None}

        judgements = asyncio.run(judge_all(emails, owner, "jev-latest", 8))
        plans = plan_all(judgements)
    except Exception as exc:
        return {"rows": [], "error": f"{type(exc).__name__}: {exc}"}

    with _lock:
        _scanned.clear()
        _scanned.update({p.judgement.email.id: p for p in plans})

    tokens = sum(p.judgement.input_tokens for p in plans)
    failed = sum(1 for p in plans if p.judgement.error)
    return {
        "owner": owner,
        "rows": [_serialise(p) for p in plans],
        "usage": {
            "input_tokens": tokens,
            "cost_usd": cost_usd(tokens),
            "rate_per_mtok": USD_PER_MILLION_INPUT_TOKENS,
            "emails": len(plans),
            "failed": failed,
        },
        "error": None,
    }


@app.post("/api/apply")
def apply(request: ApplyRequest) -> dict:
    with _lock:
        known = dict(_scanned)

    chosen = set(request.label_ids) | set(request.archive_ids)
    if not chosen:
        return {"labelled": 0, "archived": 0, "error": "Nothing selected."}

    # Ids the browser sends must come from the last scan; anything else is stale.
    unknown = chosen - known.keys()
    if unknown:
        return {
            "labelled": 0,
            "archived": 0,
            "error": "Selection is out of date. Re-scan and try again.",
        }

    plans = [known[i] for i in chosen]
    try:
        service = get_service()
        labelled, archived = labels_module.apply(
            service, plans, only=chosen, archive_only=set(request.archive_ids)
        )
    except Exception as exc:
        return {"labelled": 0, "archived": 0, "error": f"{type(exc).__name__}: {exc}"}

    return {"labelled": labelled, "archived": archived, "error": None}


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="organise-ui")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)

    if not os.environ.get("TYPESAFE_API_KEY"):
        print("TYPESAFE_API_KEY is not set. Add it to .env")
        return 1

    import uvicorn

    url = f"http://127.0.0.1:{args.port}"
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    print(f"Review UI on {url}  (ctrl-c to stop)")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
