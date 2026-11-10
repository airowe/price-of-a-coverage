"""Unify SkillCorner's action event families into one table, and sample control moments."""

import bisect

import numpy as np
import pandas as pd

from coverage_price.constants import COVERAGE_NAMES

ACTION_COLUMNS = [
    "action_id", "kind", "game_id", "frame", "main_id", "second_id", "second_def_id",
    "off_team_id", "def_team_id", "main_cov", "second_cov", "chance_id", "end_frame",
    "direct", "loc_x", "loc_y",
]  # fmt: skip

# family -> (kind, frame, main player, second player, second player's defender,
#            main coverage, second coverage)
FAMILIES = {
    "picks": ("pick", "frame", "ballhandlerId", "screenerId", "screenerDefId",
              "bhrDefType", "scrDefType"),
    "handoffs": ("handoff", "frame", "receiverId", "setterId", "setterDefId",
                 "receiverDefType", "setterDefType"),
    "off_ball_screens": ("off_ball_screen", "frame", "cutterId", "screenerId", "screenerDefId",
                         "cutterDefType", "screenerDefType"),
    "drives": ("drive", "startFrame", "ballhandlerId", None, None, None, None),
    "isolations": ("isolation", "startFrame", "ballhandlerId", None, None, None, None),
    "posts": ("post", "startFrame", "ballhandlerId", None, None, None, None),
}  # fmt: skip
CONTROL_LEAD_FRAMES = 50  # keep control moments this far after the ball crosses half court
CONTROL_TAIL_FRAMES = 100  # and this far before the chance ends, so the window stays in play


def _column(table: pd.DataFrame, name: str | None) -> pd.Series:
    if name is None or name not in table.columns:
        return pd.Series(np.nan, index=table.index, dtype="float64")
    return table[name]


def _coverage(table: pd.DataFrame, name: str | None) -> pd.Series:
    labels = _column(table, name).astype("object")
    labels = labels.where(labels.notna(), "none").astype(str)
    return labels.replace(COVERAGE_NAMES)


def _location(table: pd.DataFrame, axis: int) -> pd.Series:
    def pick(value):
        return float(value[axis]) if isinstance(value, list | tuple) and len(value) == 2 else np.nan

    return _column(table, "location").map(pick).astype("float64")


def collect_actions(events: dict[str, pd.DataFrame], game_id: int) -> pd.DataFrame:
    """One row per pick, handoff, off-ball screen, drive, isolation and post.

    `direct` is SkillCorner's flag for an action that led straight to a shot, assist or
    foul; the season aggregates count only those. `end_frame` is the last frame of the action's chance (null if unknown): after it the
    possession is over and "offence" no longer means anything.
    """
    chances = events.get("chances")
    chance_end = (
        {}
        if chances is None or chances.empty
        else dict(zip(chances["id"], chances["endFrame"], strict=True))
    )
    parts = []
    for family, (kind, frame, main, second, second_def, main_cov, second_cov) in FAMILIES.items():
        table = events.get(family)
        if table is None or table.empty:
            continue
        table = table[table[frame].notna()]
        parts.append(
            pd.DataFrame({
                "action_id": table["id"],
                "kind": kind,
                "game_id": game_id,
                "frame": table[frame].astype(int),
                "main_id": _column(table, main),
                "second_id": _column(table, second),
                "second_def_id": _column(table, second_def),
                "off_team_id": table["offTeamId"],
                "def_team_id": table["defTeamId"],
                "main_cov": _coverage(table, main_cov),
                "second_cov": _coverage(table, second_cov),
                "chance_id": _column(table, "chanceId"),
                "end_frame": _column(table, "chanceId").map(chance_end).astype("float64"),
                "direct": _column(table, "direct").fillna(0).astype(bool),
                "loc_x": _location(table, 0),
                "loc_y": _location(table, 1),
            })
        )  # fmt: skip
    if not parts:
        return pd.DataFrame(columns=ACTION_COLUMNS)
    return pd.concat(parts, ignore_index=True)[ACTION_COLUMNS]


def control_moments(
    events: dict[str, pd.DataFrame],
    actions: pd.DataFrame,
    game_id: int,
    seed: int = 0,
    clear_frames: int = 75,
) -> pd.DataFrame:
    """At most one no-action moment per chance, as rows shaped like actions.

    A frame is drawn inside the chance's half-court play and kept only if no action
    lies within `clear_frames` of it. These are the placebo for the event study.
    """
    chances = events.get("chances")
    if chances is None or chances.empty:
        return pd.DataFrame(columns=ACTION_COLUMNS)
    rng = np.random.default_rng(seed)
    busy = sorted(actions.frame.tolist())
    rows = []
    for chance in chances.itertuples(index=False):
        front = getattr(chance, "frontcourtFrame", None)
        start = chance.startFrame if front is None or pd.isna(front) else front
        low, high = int(start) + CONTROL_LEAD_FRAMES, int(chance.endFrame) - CONTROL_TAIL_FRAMES
        if high <= low:
            continue
        frame = int(rng.integers(low, high + 1))
        nearest = bisect.bisect_left(busy, frame - clear_frames)
        if nearest < len(busy) and busy[nearest] <= frame + clear_frames:
            continue
        rows.append({
            "action_id": f"control-{chance.id}", "kind": "control", "game_id": game_id,
            "frame": frame, "main_id": np.nan, "second_id": np.nan, "second_def_id": np.nan,
            "off_team_id": chance.offTeamId, "def_team_id": chance.defTeamId,
            "main_cov": "none", "second_cov": "none", "chance_id": chance.id,
            "end_frame": float(chance.endFrame), "direct": False, "loc_x": np.nan, "loc_y": np.nan,
        })  # fmt: skip
    return pd.DataFrame(rows, columns=ACTION_COLUMNS)
