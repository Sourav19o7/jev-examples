"""Entry point. Code owns the control flow; Jev only judges."""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from organiser.gmail import labels as labels_module
from organiser.gmail.auth import get_owner_address, get_service
from organiser.gmail.messages import fetch
from organiser.jev.classify import judge_all
from organiser.policy import plan_all
from organiser.report import console, render, summarise

DEFAULT_QUERY = "in:inbox is:unread newer_than:7d"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="organise",
        description="Organise Gmail with TypeSafe Jev typed decisions.",
    )
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Gmail search query")
    parser.add_argument("--limit", type=int, default=25, help="max messages to scan")
    parser.add_argument(
        "--apply", action="store_true", help="write labels to Gmail (default: dry run)"
    )
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument(
        "--concurrency", type=int, default=8, help="parallel Jev requests"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if not os.environ.get("TYPESAFE_API_KEY"):
        console.print("[red]TYPESAFE_API_KEY is not set.[/red] Add it to .env")
        return 1

    service = get_service()
    owner = get_owner_address(service)

    with console.status(f"Fetching from {owner}…"):
        emails = fetch(service, args.query, args.limit)

    if not emails:
        console.print(f"No messages matched [cyan]{args.query}[/cyan]")
        return 0

    with console.status(f"Asking Jev about {len(emails)} emails…"):
        judgements = asyncio.run(
            judge_all(emails, owner, args.model, args.concurrency)
        )

    plans = plan_all(judgements)
    render(plans, args.apply)

    if args.apply:
        labelled, archived = labels_module.apply(service, plans)
        console.print(f"\n[green]Wrote {labelled} labelled, {archived} archived.[/green]")

    summarise(plans, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
