import numpy as np
import pandas as pd
import pytest

from coverage_price.pricing import HANDLER_COVERAGES, SCREENER_COVERAGES, price_by_coverage

METRICS = ("picks", "points", "score", "assist", "turnover")


def _row(team_name="Team A", **cells):
    """A player row with every per-coverage count at zero unless given, e.g.
    screener_show=dict(picks=10, points=8)."""
    row = {"player_id": 1, "team_name": team_name}
    for role, sources in (("handler", HANDLER_COVERAGES), ("screener", SCREENER_COVERAGES)):
        for source in sources:
            given = cells.get(f"{role}_{source}", {})
            for metric in METRICS:
                row[f"{role}_{metric}_vs_{source}"] = given.get(metric, 0)
    return row


def _priced(*rows):
    return price_by_coverage(pd.DataFrame(rows)).set_index(["role", "coverage"])


def test_rates_are_summed_counts_over_summed_picks():
    out = _priced(
        _row(screener_show=dict(picks=10, points=8, score=3, assist=1, turnover=2)),
        _row(screener_show=dict(picks=30, points=12, score=5, assist=3, turnover=2)),
    )
    show = out.loc[("screener", "show")]
    assert show.picks == 40
    assert show.points_per_pick == pytest.approx(20 / 40)
    assert show.score_rate == pytest.approx(8 / 40)
    assert show.assist_rate == pytest.approx(4 / 40)
    assert show.turnover_rate == pytest.approx(4 / 40)


def test_season_total_rows_are_not_double_counted():
    out = _priced(
        _row(team_name="Team A", handler_over=dict(picks=10, points=7)),
        _row(team_name="Team B", handler_over=dict(picks=10, points=7)),
        _row(team_name="total", handler_over=dict(picks=20, points=14)),
    )
    assert out.loc[("handler", "over"), "picks"] == 20


def test_soft_is_reported_as_drop():
    out = _priced(_row(screener_soft=dict(picks=5, points=1)))
    assert ("screener", "drop") in out.index and ("screener", "soft") not in out.index
    assert out.loc[("screener", "drop"), "picks"] == 5


def test_every_documented_coverage_appears_for_each_role():
    out = _priced(_row())
    assert set(out.loc["handler"].index) == {"over", "under", "switch", "ice", "blitz"}
    assert set(out.loc["screener"].index) == {"drop", "show", "switch", "ice", "blitz"}


def test_coverage_with_zero_picks_has_nan_rates_not_an_error():
    out = _priced(_row())
    blitz = out.loc[("handler", "blitz")]
    assert blitz.picks == 0 and np.isnan(blitz.points_per_pick)
