from acu.listener.wake import strip_wake_word


def test_plain_prefix():
    assert strip_wake_word("computer search global warming") == "search global warming"


def test_transcriber_casing_and_comma():
    assert strip_wake_word("Computer, Open Chrome.") == "Open Chrome"


def test_trailing_period_only():
    assert strip_wake_word("computer close tab.") == "close tab"


def test_missing_wake_word_is_rejected():
    assert strip_wake_word("search global warming") is None


def test_wake_word_mid_sentence_is_rejected():
    assert strip_wake_word("ask the computer to search") is None


def test_wake_word_alone_is_rejected():
    assert strip_wake_word("Computer.") is None


def test_embedded_in_longer_word_is_rejected():
    assert strip_wake_word("computerised records") is None
