"""Every value crossing into a script is transcribed speech, so escape it."""

import subprocess


def escape(value: str) -> str:
    # Backslash first: escaping quotes first would double-escape its output.
    return value.replace("\\", "\\\\").replace('"', '\\"')


def run(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "osascript failed")
    return result.stdout
