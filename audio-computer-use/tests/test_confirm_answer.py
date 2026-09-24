from acu.listener.loop import is_affirmative


def test_plain_yes():
    assert is_affirmative("yes")


def test_transcriber_casing_and_punctuation():
    assert is_affirmative("Yes.")


def test_no_is_not_affirmative():
    assert not is_affirmative("no")


def test_unrelated_speech_is_not_affirmative():
    assert not is_affirmative("what time is it")


def test_empty_answer_is_not_affirmative():
    assert not is_affirmative("")
