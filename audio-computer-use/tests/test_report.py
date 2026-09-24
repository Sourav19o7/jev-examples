from acu.report import cost_usd, format_usd


def test_sub_cent_runs_are_not_rounded_away():
    assert format_usd(cost_usd(1000)) != "$0.00"


def test_zero_is_plain():
    assert format_usd(0) == "$0"


def test_cost_tracks_the_published_rate():
    assert cost_usd(1_000_000) == 0.042
