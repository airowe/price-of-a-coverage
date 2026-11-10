"""Event study: how openness changes around each action."""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from coverage_price.constants import BASELINE_OFFSET, MIN_PLAYERS_PER_SIDE, OFFSETS

SPACE_COLUMNS = [
    "action_id", "game_id", "kind", "main_cov", "second_cov",
    "role", "offset", "baseline_ft", "delta_ft",
]  # fmt: skip
_META = ["action_id", "game_id", "kind", "main_cov", "second_cov"]


def _grid(actions: pd.DataFrame, offsets: Sequence[int]) -> pd.DataFrame:
    grid = actions.merge(pd.DataFrame({"offset": list(offsets)}), how="cross")
    grid["abs_frame"] = grid.frame + grid.offset
    return grid


def frames_needed(actions: pd.DataFrame, offsets: Sequence[int] = OFFSETS) -> set[int]:
    """Every tracking frame the event study will sample for these actions."""
    return set(_grid(actions, offsets).abs_frame.astype(int))


def sides_for(actions: pd.DataFrame, offsets: Sequence[int] = OFFSETS) -> pd.DataFrame:
    """Offensive and defensive team for each sampled frame, as `openness` expects."""
    grid = _grid(actions, offsets)
    sides = grid[["abs_frame", "off_team_id", "def_team_id"]].rename(columns={"abs_frame": "frame"})
    return sides.drop_duplicates("frame").reset_index(drop=True)


def space_created(
    actions: pd.DataFrame,
    open_long: pd.DataFrame,
    offsets: Sequence[int] = OFFSETS,
    baseline: int = BASELINE_OFFSET,
) -> pd.DataFrame:
    """Change in openness from the baseline offset, per action, role and offset.

    Roles: `main` and `second` are the action's named players; `other_max` is the
    most open of the remaining offensive players; `team_mean` is the average of all
    five. A row exists only when every measurement behind it is eligible at both the
    baseline and the offset, and the offset falls within the action's chance. Actions
    from one game only: frame numbers repeat across
    games.
    """
    if actions.empty or open_long.empty:
        return pd.DataFrame(columns=SPACE_COLUMNS)
    grid = _grid(actions[[*_META, "frame", "main_id", "second_id", "end_frame"]], offsets)
    # A window that runs past the end of the chance would measure the next possession.
    grid = grid[grid.end_frame.isna() | (grid.abs_frame <= grid.end_frame)]
    seen = grid.merge(open_long.rename(columns={"frame": "abs_frame"}), on="abs_frame", how="inner")
    seen["is_main"] = seen.player_id == seen.main_id
    seen["is_second"] = seen.player_id == seen.second_id
    key = ["action_id", "offset"]

    def named(mask: pd.Series, role: str) -> pd.DataFrame:
        rows = seen[mask & seen.eligible]
        return rows[key].assign(value=rows.dist_ft.to_numpy(), role=role)

    def pooled(rows: pd.DataFrame, how: str, role: str, min_players: int) -> pd.DataFrame:
        grouped = rows.groupby(key)
        stats = grouped.agg(value=("dist_ft", how), ok=("eligible", "all"), n=("dist_ft", "size"))
        stats = stats[stats.ok & (stats.n >= min_players)]
        return stats.reset_index()[[*key, "value"]].assign(role=role)

    values = pd.concat(
        [
            named(seen.is_main, "main"),
            named(seen.is_second, "second"),
            pooled(seen[~seen.is_main & ~seen.is_second], "max", "other_max", 1),
            pooled(seen, "mean", "team_mean", MIN_PLAYERS_PER_SIDE),
        ],
        ignore_index=True,
    )
    base = values[values.offset == baseline][["action_id", "role", "value"]]
    base = base.rename(columns={"value": "baseline_ft"})
    out = values.merge(base, on=["action_id", "role"], how="inner")
    out["delta_ft"] = out.value - out.baseline_ft
    out = out.merge(actions[_META], on="action_id", how="left")
    return out[SPACE_COLUMNS].sort_values(["action_id", "role", "offset"]).reset_index(drop=True)


# ---- summaries ---------------------------------------------------------------------------
# Each function below expects `space` already filtered to one kind, role and offset.


def _game_draws(games: np.ndarray, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Indices of games drawn with replacement, shape (n_boot, n_games)."""
    return rng.integers(0, len(games), size=(n_boot, len(games)))


def summarise(
    space: pd.DataFrame,
    by: list[str],
    n_boot: int = 2000,
    seed: int = 0,
    min_n_for_range: int = 30,
) -> pd.DataFrame:
    """Mean space created per group, with a 95% range from resampling whole games.

    Actions within a possession are not independent, so games are the resampling
    unit. Groups with fewer than `min_n_for_range` actions, or seen in a single game,
    keep their count and mean but get an empty range rather than a misleading one.
    """
    columns = [*by, "n", "n_games", "mean_delta_ft", "lo", "hi", "mean_baseline_ft"]
    if space.empty:
        return pd.DataFrame(columns=columns)
    rng = np.random.default_rng(seed)
    games = np.sort(space.game_id.unique())
    draws = _game_draws(games, n_boot, rng)
    rows = []
    for group_key, group in space.groupby(by, sort=True):
        per_game = (
            group.groupby("game_id").delta_ft.agg(["sum", "size"]).reindex(games, fill_value=0)
        )
        n, n_games = int(per_game["size"].sum()), int((per_game["size"] > 0).sum())
        lo = hi = np.nan
        if n >= min_n_for_range and n_games >= 2:
            sums, sizes = per_game["sum"].to_numpy()[draws], per_game["size"].to_numpy()[draws]
            totals = sizes.sum(axis=1)
            means = sums.sum(axis=1)[totals > 0] / totals[totals > 0]
            lo, hi = np.percentile(means, [2.5, 97.5])
        key = group_key if isinstance(group_key, tuple) else (group_key,)
        rows.append((*key, n, n_games, group.delta_ft.mean(), lo, hi, group.baseline_ft.mean()))
    return pd.DataFrame(rows, columns=columns)


def gap_between(
    space: pd.DataFrame,
    label_col: str,
    a: str,
    b: str,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, float]:
    """Mean of label `a` minus mean of label `b`, its game-resampled range, and how
    many of the games containing both labels show the same sign as the overall gap."""
    rng = np.random.default_rng(seed)
    both = space[space[label_col].isin([a, b])]
    games = np.sort(both.game_id.unique())
    stats = both.groupby(["game_id", label_col]).delta_ft.agg(["sum", "size"]).unstack(label_col)
    stats = stats.reindex(games).fillna(0.0)
    sum_a, n_a = stats[("sum", a)].to_numpy(), stats[("size", a)].to_numpy()
    sum_b, n_b = stats[("sum", b)].to_numpy(), stats[("size", b)].to_numpy()
    gap = sum_a.sum() / n_a.sum() - sum_b.sum() / n_b.sum()
    draws = _game_draws(games, n_boot, rng)
    with np.errstate(invalid="ignore", divide="ignore"):
        boot = sum_a[draws].sum(1) / n_a[draws].sum(1) - sum_b[draws].sum(1) / n_b[draws].sum(1)
        present = (n_a > 0) & (n_b > 0)
        per_game = sum_a[present] / n_a[present] - sum_b[present] / n_b[present]
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    return {
        "gap_ft": float(gap),
        "lo": float(lo),
        "hi": float(hi),
        "games_same_sign": int((np.sign(per_game) == np.sign(gap)).sum()),
        "n_games": int(present.sum()),
        "n_a": int(n_a.sum()),
        "n_b": int(n_b.sum()),
    }


def permutation_p(
    space: pd.DataFrame,
    label_col: str,
    n_perm: int = 5000,
    seed: int = 0,
    min_n: int = 40,
) -> float:
    """P-value for "the labels' mean space created differ", shuffling labels within game.

    The statistic is the between-label sum of squares. Labels with fewer than `min_n`
    actions are left out; with fewer than two labels remaining the result is NaN.
    """
    counts = space[label_col].value_counts()
    kept = space[space[label_col].isin(counts[counts >= min_n].index)]
    if kept[label_col].nunique() < 2:
        return float("nan")
    rng = np.random.default_rng(seed)
    y = kept.delta_ft.to_numpy()
    codes, _ = pd.factorize(kept[label_col])
    n_labels = codes.max() + 1
    game_rows = [
        np.flatnonzero(g)
        for g in (kept.game_id.to_numpy()[None, :] == kept.game_id.unique()[:, None])
    ]

    def between(labels: np.ndarray) -> float:
        sums = np.bincount(labels, weights=y, minlength=n_labels)
        sizes = np.bincount(labels, minlength=n_labels)
        return float((sums**2 / sizes).sum())

    observed, exceed = between(codes), 0
    for _ in range(n_perm):
        shuffled = codes.copy()
        for rows in game_rows:
            shuffled[rows] = rng.permutation(codes[rows])
        exceed += between(shuffled) >= observed - 1e-12
    return (exceed + 1) / (n_perm + 1)
