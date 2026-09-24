from acu.intent.slots import extract


def test_search_query():
    assert extract("search global warming").query == "global warming"


def test_search_for_query():
    assert extract("search for global warming").query == "global warming"


def test_open_app():
    assert extract("open chrome").app == "chrome"


def test_goto_site():
    assert extract("go to github.com").site == "github.com"


def test_bare_site_name():
    assert extract("go to github").site == "github"


def test_switch_tab_ordinal_digit():
    assert extract("switch to tab 3").ordinal == 3


def test_switch_tab_ordinal_word():
    assert extract("switch to the second tab").ordinal == 2


def test_verbless_command_has_no_slots():
    slots = extract("back")
    assert slots.query is None and slots.app is None and slots.site is None


def test_unknown_verb_is_not_an_error():
    slots = extract("close time")
    assert slots.query is None


def test_empty_string_is_safe():
    assert extract("").query is None
