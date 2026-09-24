import pytest

from acu.actuator.applescript import escape, run


def test_plain_text_is_unchanged():
    assert escape("global warming") == "global warming"


def test_quote_is_escaped():
    assert escape('say "hi"') == 'say \\"hi\\"'


def test_backslash_is_escaped_before_quotes():
    assert escape(r"a\b") == r"a\\b"


def test_quote_cannot_escape_the_literal():
    hostile = 'x" & (do shell script "echo PWNED") & "y'
    assert run(f'return "{escape(hostile)}"').strip() == hostile


def test_timeout_becomes_a_runtime_error(monkeypatch):
    import subprocess
    from acu.actuator import applescript

    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="osascript", timeout=10)

    monkeypatch.setattr(subprocess, "run", _timeout)
    with pytest.raises(RuntimeError):
        applescript.run('return "x"')
