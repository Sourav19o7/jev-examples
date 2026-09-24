"""The only module that mutates the browser."""

import urllib.parse

from acu.actuator.applescript import escape, run
from acu.intent.slots import Slots

# v1 drives Chrome only, and open_app interpolates transcribed speech, so the
# set of launchable applications is closed rather than whatever was heard.
LAUNCHABLE = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "the browser": "Google Chrome",
    "browser": "Google Chrome",
}

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
    unknown = {"frontmost_app": "unknown", "chrome_running": False,
               "active_tab_title": "", "tab_count": 0}
    try:
        parts = run(_CONTEXT_SCRIPT).strip().split("\t")
    except (RuntimeError, OSError):
        return unknown
    if len(parts) < 4:
        return unknown
    try:
        count = int(parts[-1] or 0)
    except ValueError:
        count = 0
    return {
        "frontmost_app": parts[0],
        "chrome_running": parts[1] == "true",
        # A page title may itself contain a tab, so rebuild the middle.
        "active_tab_title": "\t".join(parts[2:-1]),
        "tab_count": count,
    }


def _url_for(slots: Slots) -> str:
    if not (slots.site or slots.query):
        raise ValueError("no target to open")
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
        spoken = (slots.app or "chrome").strip().lower()
        if spoken not in LAUNCHABLE:
            raise ValueError(f"only Chrome can be launched, not {slots.app!r}")
        return f'tell application "{LAUNCHABLE[spoken]}" to activate'
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
        index = slots.ordinal
        if index is None or index == 0 or index < -1:
            raise ValueError(f"no such tab: {slots.ordinal}")
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
