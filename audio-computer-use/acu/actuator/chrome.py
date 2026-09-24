"""The only module that mutates the browser."""

import urllib.parse

from acu.actuator.applescript import escape, run
from acu.intent.slots import Slots

_CONTEXT_SCRIPT = """
set appName to ""
tell application "System Events"
  set appName to name of first process whose frontmost is true
  set chromeRunning to (exists process "Google Chrome")
end tell
if chromeRunning then
  tell application "Google Chrome"
    if (count of windows) = 0 then
      return appName & "\t" & "true" & "\t" & "" & "\t" & "0"
    end if
    return appName & "\t" & "true" & "\t" & (title of active tab of front window) ¬
      & "\t" & (count of tabs of front window)
  end tell
else
  return appName & "\t" & "false" & "\t" & "" & "\t" & "0"
end if
"""


def read_context() -> dict:
    """Read-only. Runs before Jev so the screen becomes evidence."""
    try:
        parts = run(_CONTEXT_SCRIPT).strip().split("\t")
    except (RuntimeError, OSError):
        return {"frontmost_app": "unknown", "chrome_running": False,
                "active_tab_title": "", "tab_count": 0}
    app, running, title, count = (parts + ["", "", "", "0"])[:4]
    return {
        "frontmost_app": app,
        "chrome_running": running == "true",
        "active_tab_title": title,
        "tab_count": int(count or 0),
    }


def _url_for(slots: Slots) -> str:
    if slots.site:
        site = slots.site.strip()
        if "://" in site:
            return site
        # A spoken site name rarely carries its TLD, and "https://github" is not
        # a resolvable host.
        if "." not in site:
            site = f"{site}.com"
        return f"https://{site}"
    query = urllib.parse.quote_plus(slots.query or "")
    return f"https://www.google.com/search?q={query}"


def build(verb: str, slots: Slots) -> str:
    if verb in ("search", "goto_site"):
        url = escape(_url_for(slots))
        return (
            'tell application "Google Chrome"\n'
            " activate\n"
            " if (count of windows) = 0 then make new window\n"
            f' set URL of active tab of front window to "{url}"\n'
            "end tell"
        )
    if verb == "open_app":
        app = escape((slots.app or "Google Chrome").strip())
        return f'tell application "{app}" to activate'
    if verb == "new_tab":
        return (
            'tell application "Google Chrome"\n'
            " activate\n"
            " if (count of windows) = 0 then\n"
            "  make new window\n"
            " else\n"
            "  tell front window to make new tab\n"
            " end if\n"
            "end tell"
        )
    if verb == "close_tab":
        return 'tell application "Google Chrome" to close active tab of front window'
    if verb == "switch_tab":
        index = slots.ordinal or 1
        if index == -1:
            return (
                'tell application "Google Chrome" to tell front window to '
                "set active tab index to (count of tabs)"
            )
        return (
            'tell application "Google Chrome" to tell front window to '
            f"set active tab index to {int(index)}"
        )
    if verb == "back":
        return (
            'tell application "Google Chrome" to tell active tab of front window to '
            "go back"
        )
    if verb == "scroll":
        return (
            'tell application "Google Chrome" to tell active tab of front window to '
            'execute javascript "window.scrollBy(0, window.innerHeight * 0.8)"'
        )
    raise ValueError(f"unknown verb: {verb}")


def perform(verb: str, slots: Slots, dry_run: bool = False) -> str:
    script = build(verb, slots)
    if dry_run:
        return script
    run(script)
    return script
