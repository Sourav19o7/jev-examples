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
