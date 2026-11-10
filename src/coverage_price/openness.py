"""Openness: distance from each offensive player to the nearest defender."""

import numpy as np
import pandas as pd

from coverage_price.constants import MAX_PRED_ERROR_FT, MIN_PLAYERS_PER_SIDE

OPENNESS_COLUMNS = ["frame", "player_id", "dist_ft", "defender_id", "eligible"]


def openness(
    frames: pd.DataFrame,
    sides: pd.DataFrame,
    max_pred_error: float = MAX_PRED_ERROR_FT,
) -> pd.DataFrame:
    """One row per offensive player per frame listed in `sides`.

    `sides` names the offensive and defensive team for each frame. A row is eligible
    when the offensive player and the nearest defender both have `pred_error` at or
    below the gate and the frame has a full five tracked on each side. Ineligible
    rows keep their measured distance so callers can count them; they must not be
    averaged.
    """
    sides = sides.drop_duplicates("frame")
    tagged = frames.merge(sides, on="frame", how="inner")
    off = tagged[tagged.team_id == tagged.off_team_id]
    dfn = tagged[tagged.team_id == tagged.def_team_id]
    if off.empty or dfn.empty:
        return pd.DataFrame(columns=OPENNESS_COLUMNS)
    pairs = off[["frame", "player_id", "x", "y", "pred_error"]].merge(
        dfn[["frame", "player_id", "x", "y", "pred_error"]], on="frame", suffixes=("", "_def")
    )
    pairs["dist_ft"] = np.hypot(pairs.x - pairs.x_def, pairs.y - pairs.y_def)
    nearest = pairs.loc[pairs.groupby(["frame", "player_id"]).dist_ft.idxmin()]
    full = (
        (off.groupby("frame").size() >= MIN_PLAYERS_PER_SIDE)
        & (dfn.groupby("frame").size() >= MIN_PLAYERS_PER_SIDE)
    ).rename("full")
    nearest = nearest.join(full, on="frame")
    nearest["eligible"] = (
        nearest.full.fillna(False).astype(bool)
        & (nearest.pred_error <= max_pred_error)
        & (nearest.pred_error_def <= max_pred_error)
    )
    out = nearest.rename(columns={"player_id_def": "defender_id"})[OPENNESS_COLUMNS]
    return out.sort_values(["frame", "player_id"]).reset_index(drop=True)
