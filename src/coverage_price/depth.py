"""How deep the screener's defender sits at the moment of a ball screen.

A label-free description of the coverage: positive depth means the defender is
between the screener and the hoop (dropping); zero or negative means level with or
above the screen (showing).
"""

import numpy as np
import pandas as pd

from coverage_price.constants import HOOP_XY, MAX_PRED_ERROR_FT

DEPTH_COLUMNS = ["action_id", "depth_ft"]
SKIP_REASONS = ("null_location", "player_not_tracked", "ineligible")


def x_sign(tracked_x: float, event_x: float) -> int:
    """+1 if tracking x already matches the normalised event frame, -1 if it is mirrored.

    Event locations always put the offensive hoop on the negative-x side; tracking is
    camera-oriented, so x is mirrored whenever the offence attacks the other hoop.
    Tracking y is the event y negated, which does not affect depth: the hoop is at y = 0.
    """
    return 1 if tracked_x * event_x >= 0 else -1


def screener_defender_depth(
    picks: pd.DataFrame,
    frames: pd.DataFrame,
    max_pred_error: float = MAX_PRED_ERROR_FT,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Depth in feet for each pick, plus counts of picks skipped and why.

    `picks` needs action_id, frame, second_id, second_def_id, loc_x, loc_y.
    Depth is the defender's offset from the screener along the screener-to-hoop line.
    """
    skipped = dict.fromkeys(SKIP_REASONS, 0)
    position = {
        (int(r.frame), int(r.player_id)): (r.x, r.y, r.pred_error)
        for r in frames.itertuples(index=False)
    }
    hoop, rows = np.asarray(HOOP_XY), []
    for pick in picks.itertuples(index=False):
        if pd.isna(pick.loc_x) or pd.isna(pick.loc_y):
            skipped["null_location"] += 1
            continue
        ids = (pick.second_id, pick.second_def_id)
        found = [None if pd.isna(i) else position.get((int(pick.frame), int(i))) for i in ids]
        if any(p is None for p in found):
            skipped["player_not_tracked"] += 1
            continue
        screener, defender = found
        if screener[2] > max_pred_error or defender[2] > max_pred_error:
            skipped["ineligible"] += 1
            continue
        # A pick's `location` is the screener's position, so the screener fixes the side.
        flip = np.array([x_sign(screener[0], pick.loc_x), 1.0])
        screener_xy, defender_xy = flip * np.asarray(screener[:2]), flip * np.asarray(defender[:2])
        to_hoop = hoop - screener_xy
        unit = to_hoop / np.linalg.norm(to_hoop)
        rows.append((pick.action_id, float((defender_xy - screener_xy) @ unit)))
    return pd.DataFrame(rows, columns=DEPTH_COLUMNS), skipped
