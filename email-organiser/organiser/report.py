"""Render plans for a human before anything is applied."""

from rich.console import Console
from rich.table import Table

from organiser.gmail.messages import sender_name
from organiser.policy import Plan

console = Console()


def _truncate(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def render(plans: list[Plan], apply_mode: bool) -> None:
    table = Table(
        title="Proposed organisation" if not apply_mode else "Applied",
        show_lines=False,
        header_style="bold",
    )
    table.add_column("From", style="cyan", max_width=22)
    table.add_column("Subject", max_width=42)
    table.add_column("Category")
    table.add_column("Conf", justify="right")
    table.add_column("Urg", justify="right")
    table.add_column("Reply", justify="right")
    table.add_column("Act", justify="right")
    table.add_column("Action", style="magenta")

    for plan in sorted(plans, key=lambda p: p.judgement.urgency, reverse=True):
        j = plan.judgement

        if plan.needs_review:
            action = "[yellow]review[/yellow]"
        elif plan.archive:
            action = "label + archive"
        elif plan.add_labels:
            action = "label"
        else:
            action = "[dim]leave[/dim]"

        labels = ", ".join(n.split("/")[-1] for n in plan.add_labels)
        table.add_row(
            _truncate(sender_name(j.email), 22),
            _truncate(j.email.subject, 42),
            j.category if not j.error else "[red]error[/red]",
            f"{j.category_confidence:.2f}",
            f"{j.urgency:.1f}",
            f"{j.needs_reply:.2f}",
            f"{j.owner_must_act:.2f}",
            f"{action} {labels}".strip(),
        )

    console.print(table)

    review = [p for p in plans if p.needs_review]
    if review:
        console.print("\n[yellow]Held for review[/yellow]")
        for plan in review:
            console.print(
                f"  • {_truncate(plan.subject, 60)} — {'; '.join(plan.review_reasons)}"
            )


def summarise(plans: list[Plan], apply_mode: bool) -> None:
    total = len(plans)
    review = sum(1 for p in plans if p.needs_review)
    archive = sum(1 for p in plans if p.archive)
    labelled = sum(1 for p in plans if p.add_labels and not p.needs_review)

    verb = "Applied" if apply_mode else "Would apply"
    console.print(
        f"\n[bold]{total}[/bold] scanned · {verb} labels to [bold]{labelled}[/bold] "
        f"· archive [bold]{archive}[/bold] · [yellow]{review}[/yellow] held for review"
    )
    if not apply_mode:
        console.print("[dim]Dry run. Re-run with --apply to write to Gmail.[/dim]")
