import math

import pandas as pd
import pytest

from coverage_price.menu import (
    MENU_COLUMNS,
    MIN_ROLE_PICKS,
    PRIOR_PICKS,
    Z95,
    League,
    build_menu,
    difference_sd,
    league_rates,
    pair_price,
    player_rates,
    role_rate,
    too_close,
)

COUNTS = ("total_picks", "points", "score_2pt", "score_3pt", "assist_2pt", "assist_3pt")


def _agg_row(player_id, team_name="A", **counts):
    """A pick-aggregate row with every count at zero unless given, e.g. handler_points=8."""
    row = {"player_id": player_id, "team_name": team_name, "handler_assist_to_screener": 0}
    for role in ("handler", "screener"):
        for count in COUNTS:
            row[f"{role}_{count}"] = 0
    row.update(counts)
    return row


def _table(*rows):
    return pd.DataFrame(rows)


def test_pair_price_subtracts_the_overlap_once():
    assert pair_price(0.80, 0.30, 0.10, 2.25) == pytest.approx(0.80 + 0.30 - 0.10 * 2.25)


def test_league_points_per_screener_basket_uses_the_two_three_mix():
    table = _table(
        _agg_row(1, screener_score_2pt=3, screener_score_3pt=1, screener_total_picks=10,
                 screener_points=9)
    )  # fmt: skip
    assert league_rates(table).points_per_screener_basket == pytest.approx((2 * 3 + 3 * 1) / 4)


def test_league_sd_matches_the_outcome_mix():
    # 10 picks: two 2-point scores and one 3-point assist -> mean 0.7, E[X^2] = (2*4 + 9) / 10
    table = _table(
        _agg_row(1, handler_total_picks=10, handler_points=7, handler_score_2pt=2,
                 handler_assist_3pt=1)
    )  # fmt: skip
    assert league_rates(table).handler_sd == pytest.approx(math.sqrt(1.7 - 0.7**2))


def test_player_with_no_picks_in_a_role_prices_at_league():
    table = _table(
        _agg_row(1, handler_total_picks=100, handler_points=80),
        _agg_row(2, screener_total_picks=40, screener_points=20),
    )
    rates = player_rates(table, aliases={}, prior_picks=10)
    assert rates.loc[2, "handler_rate"] == pytest.approx(league_rates(table).handler_rate)
    assert rates.loc[2, "handler_picks"] == 0


def test_player_with_many_picks_prices_near_his_own_rate():
    table = _table(
        _agg_row(1, handler_total_picks=10_000, handler_points=12_000),
        _agg_row(2, handler_total_picks=100, handler_points=70),
    )
    rates = player_rates(table, aliases={})
    assert rates.loc[1, "handler_rate"] == pytest.approx(1.2, abs=0.01)


def test_missing_player_gets_league_rate_and_no_picks():
    table = _table(_agg_row(1, screener_total_picks=40, screener_points=20, screener_score_2pt=10))
    league = league_rates(table)
    rates = player_rates(table, aliases={})
    rate, sd, picks = role_rate(rates, league, 999, "screener")
    assert rate == pytest.approx(league.screener_rate)
    assert sd == pytest.approx(league.screener_sd / math.sqrt(PRIOR_PICKS))
    assert picks == 0


def test_traded_and_aliased_rows_are_counted_once():
    table = _table(
        _agg_row(7, "A", handler_total_picks=20),
        _agg_row(7, "B", handler_total_picks=15),
        _agg_row(7, "total", handler_total_picks=35),
        _agg_row(70, "A", handler_total_picks=5),
    )
    rates = player_rates(table, aliases={70: 7})
    assert rates.loc[7, "handler_picks"] == 40
    assert 70 not in rates.index


def test_shrunk_rate_weights_own_picks_against_the_prior():
    table = _table(
        _agg_row(1, handler_total_picks=30, handler_points=30),
        _agg_row(2, handler_total_picks=70, handler_points=40),
    )
    league = league_rates(table)
    rates = player_rates(table, aliases={}, prior_picks=20)
    expected = (30 + 20 * league.handler_rate) / (30 + 20)
    assert rates.loc[1, "handler_rate"] == pytest.approx(expected)
    assert rates.loc[1, "handler_sd"] == pytest.approx(league.handler_sd / math.sqrt(30 + 20))


LEAGUE = League(
    handler_rate=0.7, screener_rate=0.25, handler_sd=1.0, screener_sd=0.8,
    assist_to_screener_rate=0.07, points_per_screener_basket=2.1,
)  # fmt: skip
ENOUGH, TOO_FEW = MIN_ROLE_PICKS, MIN_ROLE_PICKS - 1


def _rates(*players):
    """(player_id, handler_rate, handler_picks, screener_rate, screener_picks)."""
    rows = [
        {"player_id": pid, "handler_picks": hp, "handler_rate": hr, "handler_sd": 0.01,
         "assist_to_screener_rate": 0.0, "screener_picks": sp, "screener_rate": sr,
         "screener_sd": 0.01}
        for pid, hr, hp, sr, sp in players
    ]  # fmt: skip
    return pd.DataFrame(rows).set_index("player_id")


FIVE = _rates(
    (1, 0.9, 200, 0.2, ENOUGH),
    (2, 0.8, 150, 0.3, ENOUGH),
    (3, 0.7, ENOUGH, 0.1, TOO_FEW),
    (4, 0.6, TOO_FEW, 0.4, 100),
    (5, 0.5, 3, 0.5, 300),
)


SD = 0.1


@pytest.mark.parametrize(
    "gap, expected",
    [(Z95 * SD, True), (-Z95 * SD, True), (0.0, True), (Z95 * SD + 1e-9, False)],
)
def test_too_close_when_the_gap_is_inside_the_difference_interval(gap, expected):
    assert too_close(gap, SD) is expected


def test_a_term_both_pairs_share_cancels_from_the_difference():
    best = {(1, "handler"): 0.3, (2, "screener"): 0.4}
    rival = {(1, "handler"): 0.3, (3, "screener"): 0.5}
    assert difference_sd(best, rival) == pytest.approx(math.hypot(0.4, 0.5))


def test_the_same_player_in_another_role_does_not_cancel():
    best = {(1, "handler"): 0.3, (2, "screener"): 0.4}
    rival = {(2, "handler"): 0.6, (1, "screener"): 0.2}
    assert difference_sd(best, rival) == pytest.approx(math.sqrt(0.3**2 + 0.4**2 + 0.6**2 + 0.2**2))


def test_a_shared_handlers_uncertainty_does_not_hide_a_gap_between_screeners():
    rates = _rates((1, 0.9, 200, 0.1, 200), (2, 0.1, 200, 0.5, 200), (3, 0.1, 200, 0.3, 200))
    rates.loc[1, "handler_sd"] = 1.0
    menu = build_menu([1, 2, 3], (1, 3), rates, LEAGUE).set_index(["handler_id", "screener_id"])
    assert menu.loc[(1, 2), "best"]
    assert not menu.loc[(1, 3), "too_close_to_best"]  # differs only in the screener
    assert menu.loc[(3, 2), "too_close_to_best"]  # differs in the uncertain handler


def test_menu_offers_only_players_with_enough_picks_in_the_role():
    menu = build_menu([1, 2, 3, 4, 5], (1, 2), FIVE, LEAGUE)
    assert list(menu.columns) == MENU_COLUMNS
    assert set(menu.handler_id) == {1, 2, 3}
    assert set(menu.screener_id) == {1, 2, 4, 5}
    assert len(menu) == 3 * 4 - 2  # minus the two self-pairs


def test_menu_never_pairs_a_player_with_himself():
    menu = build_menu([1, 2, 3, 4, 5], (1, 2), FIVE, LEAGUE)
    assert not (menu.handler_id == menu.screener_id).any()


def test_low_volume_used_pair_is_priced_and_marked():
    menu = build_menu([1, 2, 3, 4, 5], (5, 1), FIVE, LEAGUE)
    assert (menu.handler_id == 5).sum() == 1
    used = menu[menu.used].iloc[0]
    assert (used.handler_id, used.screener_id, bool(used.below_volume)) == (5, 1, True)
    assert used.price == pytest.approx(0.5 + 0.2)


def test_used_pair_off_the_listed_five_is_still_on_the_menu():
    menu = build_menu([1, 2, 3, 4, 6], (5, 1), FIVE, LEAGUE)
    assert menu.used.sum() == 1
    assert menu[menu.used].iloc[0].handler_id == 5


def test_price_interval_combines_both_players_sd():
    menu = build_menu([1, 2], (1, 2), FIVE, LEAGUE).set_index(["handler_id", "screener_id"])
    row = menu.loc[(1, 2)]
    half = Z95 * math.sqrt(0.01**2 + 0.01**2)
    assert (row.lo, row.hi) == (pytest.approx(row.price - half), pytest.approx(row.price + half))


def test_best_is_the_highest_price_and_close_rivals_are_flagged():
    rates = _rates((1, 0.9, 200, 0.3, 200), (2, 0.9, 200, 0.29, 200), (3, 0.2, 200, 0.1, 200))
    menu = build_menu([1, 2, 3], (3, 1), rates, LEAGUE)
    best = menu[menu.best]
    assert len(best) == 1
    assert (best.iloc[0].handler_id, best.iloc[0].screener_id) == (2, 1)  # 0.9 + 0.3
    assert menu.price.is_monotonic_decreasing
    close = menu[menu.too_close_to_best]
    assert set(zip(close.handler_id, close.screener_id, strict=True)) == {(1, 2), (2, 1)}
