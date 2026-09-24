import pytest
from acu.actuator.chrome import build
from acu.intent.slots import Slots


def test_search_builds_an_encoded_google_url():
    script = build("search", Slots(query="global warming"))
    assert "google.com/search?q=global+warming" in script


def test_search_query_with_quotes_is_escaped():
    script = build("search", Slots(query='say "hi"'))
    assert '\\"' not in script.split("google.com")[0]
    assert "%22hi%22" in script


def test_bare_site_gets_a_scheme():
    assert "https://github.com" in build("goto_site", Slots(site="github"))


def test_site_with_scheme_is_left_alone():
    assert "https://github.com" in build("goto_site", Slots(site="https://github.com"))


def test_targetless_verbs_build():
    for verb in ("new_tab", "close_tab", "back", "scroll"):
        assert build(verb, Slots()).strip()


def test_unknown_verb_is_rejected():
    with pytest.raises(ValueError):
        build("teleport", Slots())
