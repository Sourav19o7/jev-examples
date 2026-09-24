from acu.actuator import chrome


def _fake_run(out: str):
    return lambda script: out


def test_tab_inside_a_page_title_does_not_break_parsing(monkeypatch):
    monkeypatch.setattr(chrome, "run", _fake_run("Code\ttrue\tMy\tPage Title\t3\n"))
    ctx = chrome.read_context()
    assert ctx["tab_count"] == 3
    assert ctx["active_tab_title"] == "My\tPage Title"


def test_plain_title_parses(monkeypatch):
    monkeypatch.setattr(chrome, "run", _fake_run("Google Chrome\ttrue\tNew Tab\t7\n"))
    ctx = chrome.read_context()
    assert ctx == {"frontmost_app": "Google Chrome", "chrome_running": True,
                   "active_tab_title": "New Tab", "tab_count": 7}


def test_non_numeric_count_degrades(monkeypatch):
    monkeypatch.setattr(chrome, "run", _fake_run("Code\ttrue\tTitle\tnope\n"))
    assert chrome.read_context()["tab_count"] == 0


def test_osascript_failure_degrades(monkeypatch):
    def _boom(script):
        raise RuntimeError("osascript failed")
    monkeypatch.setattr(chrome, "run", _boom)
    assert chrome.read_context()["chrome_running"] is False
