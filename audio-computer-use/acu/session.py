"""Entry point. Code owns the control flow; Jev only judges."""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from acu.actuator import chrome
from acu.intent.classify import judge
from acu.intent.slots import extract
from acu.listener.wake import WAKE_WORD
from acu.policy import Decision, decide
from acu.report import console, render_decision


async def handle(
    command: str, recent: list[str], screen: dict, dry_run: bool
) -> Decision:
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
