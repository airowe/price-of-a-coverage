"""Freeze each pick at its decision, build its menu, and summarise the menus.

A freeze holds the five offensive players SkillCorner lists for the pick's chance, the
pair actually used, the period and the score margin at the chance's start.
"""

import numpy as np
import pandas as pd

from coverage_price.eventstudy import _game_draws
from coverage_price.menu import League, build_menu

FREEZE_COLUMNS = [
    "action_id", "game_id", "period", "margin", "handler_id", "screener_id", "on_floor",
]  # fmt: skip
LATE_PERIOD = 4
CLOSE_MARGIN = 6
MIN_RULE_SET = 5
RULES = (
    ("fourth quarter, within 6", lambda period: period == LATE_PERIOD),
    ("second half, within 6", lambda period: period >= 3),
    ("whole game, within 6", lambda period: period >= 1),
)


def game_freezes(events: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per pick whose chance is known."""
    picks, chances = events.get("picks"), events.get("chances")
    if picks is None or picks.empty or chances is None or chances.empty:
        return pd.DataFrame(columns=FREEZE_COLUMNS)
    by_id = chances.set_index("id")
    known = picks[picks.chanceId.isin(by_id.index)]
    chance = by_id.loc[known.chanceId]
    return pd.DataFrame({
        "action_id": known["id"].to_numpy(),
        "game_id": known["gameId"].astype(int).to_numpy(),
        "period": known["period"].astype(int).to_numpy(),
        "margin": (chance.homeStartScore - chance.awayStartScore).abs().astype(int).to_numpy(),
        "handler_id": known["ballhandlerId"].astype(int).to_numpy(),
        "screener_id": known["screenerId"].astype(int).to_numpy(),
        "on_floor": [tuple(int(p) for p in ids) for ids in chance.offPlayerIds],
    })[FREEZE_COLUMNS]  # fmt: skip


def menus_for(freezes: pd.DataFrame, rates: pd.DataFrame, league: League) -> pd.DataFrame:
    """Every freeze's menu, tagged with its action and game."""
    parts = [
        build_menu(f.on_floor, (f.handler_id, f.screener_id), rates, league).assign(
            action_id=f.action_id, game_id=f.game_id
        )
        for f in freezes.itertuples(index=False)
    ]
    return pd.concat(parts, ignore_index=True)


def gaps(menus: pd.DataFrame) -> pd.DataFrame:
    """Best price minus the used pair's price, for actions with any pair beside the used one."""
    rows = []
    for action_id, menu in menus.groupby("action_id", sort=False):
        if len(menu) < 2:
            continue
        used = menu[menu.used].iloc[0]
        rows.append((action_id, used.game_id, menu.price.max() - used.price,
                     bool(used.too_close_to_best)))  # fmt: skip
    return pd.DataFrame(rows, columns=["action_id", "game_id", "gap", "used_too_close"])


def summarise_menus(menus: pd.DataFrame, n_boot: int, seed: int = 0) -> dict:
    """Share of picks too close to call with the best pair, and the mean gap with a
    95% range from resampling whole games."""
    table = gaps(menus)
    per_game = table.groupby("game_id").gap.agg(["sum", "size"])
    draws = _game_draws(per_game.index.to_numpy(), n_boot, np.random.default_rng(seed))
    means = per_game["sum"].to_numpy()[draws].sum(1) / per_game["size"].to_numpy()[draws].sum(1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {
        "picks_with_menu": len(table),
        "left_out": int(menus.action_id.nunique() - len(table)),
        "share_too_close": float(table.used_too_close.mean()),
        "mean_gap": float(table.gap.mean()),
        "gap_lo": float(lo),
        "gap_hi": float(hi),
        "n_games": len(per_game),
    }


def worked_moment(gap_table: pd.DataFrame, freezes: pd.DataFrame) -> tuple[str, str]:
    """The median-gap pick (lower middle, ties by id) in the narrowest rule with enough picks."""
    close = gap_table.merge(freezes[["action_id", "period", "margin"]], on="action_id")
    close = close[close.margin <= CLOSE_MARGIN]
    for name, in_window in RULES:
        chosen = close[close.period.map(in_window)]
        if len(chosen) >= MIN_RULE_SET or name == RULES[-1][0]:
            break
    if chosen.empty:
        raise ValueError("no close-game pick has a menu")
    ordered = chosen.sort_values(["gap", "action_id"]).reset_index(drop=True)
    return str(ordered.action_id[(len(ordered) - 1) // 2]), name
