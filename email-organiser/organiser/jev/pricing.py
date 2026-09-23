"""Jev bills on input tokens only; output tokens are free."""

USD_PER_MILLION_INPUT_TOKENS = 0.042


def cost_usd(input_tokens: int) -> float:
    return input_tokens / 1_000_000 * USD_PER_MILLION_INPUT_TOKENS


def format_usd(amount: float) -> str:
    """Sub-cent runs are the norm here, so don't round them away to $0.00."""
    if amount == 0:
        return "$0"
    if amount < 0.01:
        return f"{amount * 100:.3f}¢"
    return f"${amount:.4f}"
