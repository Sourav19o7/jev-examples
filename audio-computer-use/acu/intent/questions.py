"""The question set. This is the only place decisions are defined."""

from typesafe_sdk import Choice, Noul, Score

VERBS = {
    "open_app": "Launch or focus an application, such as Chrome itself.",
    "search": "Search the web for a phrase the speaker supplied.",
    "goto_site": "Navigate to a named website or URL.",
    "new_tab": "Open a new, empty browser tab.",
    "close_tab": "Close the tab that is currently active.",
    "switch_tab": "Move to a different already-open tab.",
    "back": "Return to the previous page in history.",
    "scroll": "Scroll the current page up or down.",
}

AMBIGUITY_LEVELS = [
    "Unmistakable. The words name one action and one target plainly.",
    "Clear. A competent listener would agree on the action without hesitating.",
    "Mostly clear, but the phrasing or a mis-heard word leaves some doubt.",
    "Genuinely ambiguous. Two different actions fit the words equally well.",
    "Unintelligible as a command. The words do not form a browser instruction.",
]


def build_questions() -> dict:
    """One request, five independent judgements, evaluated in parallel."""
    return {
        "command": Choice(
            instructions=(
                "Which browser action is the speaker asking for? Judge by what they "
                "want to happen, not by the exact words they used."
            ),
            criteria=VERBS,
        ),
        "addressed_to_computer": Noul(
            instructions=(
                "Is the speaker instructing this computer, rather than talking to "
                "another person within earshot?"
            ),
            criteria={
                "true": "An instruction directed at a machine, phrased as a command.",
                "false": "Conversation, thinking aloud, or speech aimed at another person.",
            },
        ),
        "continues_context": Noul(
            instructions=(
                "Does this command depend on what is already on screen to make sense?"
            ),
            criteria={
                "true": "It omits its target and only resolves against the focused app or tab.",
                "false": "It names its own target and stands alone.",
            },
        ),
        "target_is_site": Noul(
            instructions=(
                "Is the target a specific website to visit, rather than a phrase to "
                "search for?"
            ),
            criteria={
                "true": "A domain, a URL, or a well-known site the speaker wants to open.",
                "false": "A topic, question, or phrase the speaker wants results about.",
            },
        ),
        "ambiguity": Score(
            instructions=(
                "How clear is this as a browser command? Judge how confidently a "
                "listener could carry it out without asking."
            ),
            criteria=AMBIGUITY_LEVELS,
        ),
    }
