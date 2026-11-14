from pathlib import Path

import pandas as pd
import pytest

from coverage_price.freezes import (
    CLOSE_MARGIN,
    LATE_PERIOD,
    MIN_RULE_SET,
    game_freezes,
    gaps,
    menus_for,
    summarise_menus,
    worked_moment,
)
from coverage_price.menu import MENU_COLUMNS, League

REAL_DATA = Path(__file__).parents[1] / "data" / "opendata-basketball"
GAME_ID = 999


def _pick(pick_id, chance, period=1, handler=1, screener=2):
    return {"id": pick_id, "gameId": GAME_ID, "chanceId": chance, "period": period,
            "ballhandlerId": handler, "screenerId": screener}  # fmt: skip


def _chance(chance_id, off=(1, 2, 3, 4, 5), home=0, away=0):
    return {"id": chance_id, "offPlayerIds": list(off), "homeStartScore": home,
            "awayStartScore": away}  # fmt: skip


def _menu_row(action_id, game_id, price, lo, hi, used, best):
    return {"action_id": action_id, "game_id": game_id, "handler_id": 1, "screener_id": 2,
            "price": price, "lo": lo, "hi": hi, "used": used, "below_volume": False,
            "best": best, "too_close_to_best": False}  # fmt: skip


def _menus(*rows):
    menus = pd.DataFrame(rows)
    for _, menu in menus.groupby("action_id"):
        top = menu[menu.best].iloc[0]
        close = (menu.lo <= top.hi) & (top.lo <= menu.hi)
        menus.loc[menu.index, "too_close_to_best"] = close
    return menus


def test_freeze_reads_five_period_and_margin_from_the_chance():
    events = {
        "picks": pd.DataFrame([_pick("p1", "c1", period=4)]),
        "chances": pd.DataFrame([_chance("c1", home=70, away=66)]),
    }
    row = game_freezes(events).iloc[0]
    assert (row.action_id, row.game_id, row.period, row.margin) == ("p1", GAME_ID, 4, 4)
    assert (row.handler_id, row.screener_id, row.on_floor) == (1, 2, (1, 2, 3, 4, 5))


def test_pick_without_a_chance_is_dropped():
    events = {
        "picks": pd.DataFrame([_pick("p1", "c1"), _pick("p2", "missing")]),
        "chances": pd.DataFrame([_chance("c1")]),
    }
    assert game_freezes(events).action_id.tolist() == ["p1"]


def test_menus_for_tags_each_menu_with_its_action():
    events = {
        "picks": pd.DataFrame([_pick("p1", "c1"), _pick("p2", "c1", handler=3, screener=4)]),
        "chances": pd.DataFrame([_chance("c1")]),
    }
    league = League(0.7, 0.25, 1.0, 0.8, 0.07, 2.1)
    menus = menus_for(game_freezes(events), pd.DataFrame(), league)
    assert set(menus.columns) >= {*MENU_COLUMNS, "action_id", "game_id"}
    assert menus.groupby("action_id").used.sum().to_dict() == {"p1": 1, "p2": 1}


def test_summary_counts_left_out_and_share_too_close():
    menus = _menus(
        _menu_row("alone", 1, 1.0, 0.9, 1.1, used=True, best=True),
        _menu_row("tie", 1, 1.0, 0.9, 1.1, used=True, best=True),
        _menu_row("tie", 1, 0.95, 0.85, 1.05, used=False, best=False),
        _menu_row("worse", 2, 1.5, 1.4, 1.6, used=False, best=True),
        _menu_row("worse", 2, 0.5, 0.4, 0.6, used=True, best=False),
    )
    summary = summarise_menus(menus, n_boot=50)
    assert (summary["picks_with_menu"], summary["left_out"]) == (2, 1)
    assert summary["share_too_close"] == pytest.approx(0.5)
    assert summary["mean_gap"] == pytest.approx((0.0 + 1.0) / 2)
    assert summary["gap_lo"] <= summary["mean_gap"] <= summary["gap_hi"]
    assert summary["n_games"] == 2


def test_gap_is_best_minus_used():
    menus = _menus(
        _menu_row("a", 1, 1.5, 1.4, 1.6, used=False, best=True),
        _menu_row("a", 1, 1.2, 1.1, 1.3, used=True, best=False),
    )
    row = gaps(menus).iloc[0]
    assert row.gap == pytest.approx(0.3)
    assert not row.used_too_close


def _rule_inputs(periods, gap_values, ids=None, margin=CLOSE_MARGIN):
    ids = ids or [f"a{i}" for i in range(len(periods))]
    gap_table = pd.DataFrame(
        {"action_id": ids, "game_id": 1, "gap": gap_values, "used_too_close": False}
    )
    freezes = pd.DataFrame({"action_id": ids, "period": periods, "margin": margin})
    return gap_table, freezes


@pytest.mark.parametrize(
    "periods, expected_rule",
    [
        ([LATE_PERIOD] * MIN_RULE_SET, "fourth quarter, within 6"),
        ([LATE_PERIOD] * 2 + [3] * 3, "second half, within 6"),
        ([1] * MIN_RULE_SET, "whole game, within 6"),
    ],
)
def test_worked_moment_falls_back(periods, expected_rule):
    _, rule = worked_moment(*_rule_inputs(periods, [0.1] * len(periods)))
    assert rule == expected_rule


def test_worked_moment_ignores_wide_margins():
    gap_table, freezes = _rule_inputs([LATE_PERIOD] * 6, [0.0, 0.1, 0.2, 0.3, 0.4, 9.0])
    freezes.loc[5, "margin"] = CLOSE_MARGIN + 1
    action_id, _ = worked_moment(gap_table, freezes)
    assert action_id == "a2"


def test_worked_moment_takes_the_median_gap():
    action_id, _ = worked_moment(*_rule_inputs([LATE_PERIOD] * 5, [0.4, 0.0, 0.2, 0.1, 0.3]))
    assert action_id == "a2"


def test_even_set_takes_the_lower_middle_by_gap_then_id():
    ids = ["p", "q", "b", "a", "r", "s"]
    gap_table, freezes = _rule_inputs([LATE_PERIOD] * 6, [0.0, 0.1, 0.2, 0.2, 0.3, 0.4], ids)
    assert worked_moment(gap_table, freezes)[0] == "a"


@pytest.mark.skipif(not REAL_DATA.exists(), reason="open data not downloaded")
def test_real_game_menus_are_well_formed():
    from coverage_price.cli import PICKS_AGGREGATE
    from coverage_price.loader import list_games, load_aliases, load_events
    from coverage_price.menu import league_rates, player_rates

    aliases = load_aliases(REAL_DATA)
    agg = pd.read_csv(REAL_DATA / PICKS_AGGREGATE)
    freezes = game_freezes(load_events(list_games(REAL_DATA)[0], aliases))
    assert len(freezes) > 0
    assert freezes.on_floor.map(len).eq(5).all()
    menus = menus_for(freezes, player_rates(agg, aliases), league_rates(agg))
    assert menus.groupby("action_id").used.sum().eq(1).all()
    assert menus.price.between(0, 3).all()
