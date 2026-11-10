"""Run the study on games, build the result tables, and draw the two figures."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from coverage_price.actions import collect_actions, control_moments  # noqa: E402
from coverage_price.constants import BASELINE_OFFSET, FPS, MAX_PRED_ERROR_FT  # noqa: E402
from coverage_price.depth import screener_defender_depth  # noqa: E402
from coverage_price.eventstudy import (  # noqa: E402
    PERMUTATION_MIN_N,
    frames_needed,
    gap_between,
    permutation_p,
    sides_for,
    space_created,
    summarise,
)
from coverage_price.loader import load_events, load_game, read_frames  # noqa: E402
from coverage_price.openness import openness  # noqa: E402

ROLE_NAMES = {
    "main": "Ball handler",
    "second": "Screener",
    "other_max": "Most open teammate",
    "team_mean": "Team average",
}
HEADLINE_OFFSETS = (25, 50)  # +1.0 s and +2.0 s
SENSITIVITY_OFFSETS = (25, 40, 50)
SENSITIVITY_BASELINES = (-10, -15, -25)
SENSITIVITY_GATES = (2.0, 3.0, 5.0)
CONTRASTS = (  # (label column, a, b, roles)
    ("second_cov", "show", "drop", ("second", "other_max", "team_mean", "main")),
    ("main_cov", "under", "over", ("main",)),
)
DEPTH_BINS = (-np.inf, 0.0, 3.0, 6.0, np.inf)
DEPTH_BIN_LABELS = ("above screen (<0 ft)", "0-3 ft", "3-6 ft", "deep (>6 ft)")
GAP_COLUMNS = ["gap_ft", "lo", "hi", "games_same_sign", "n_games", "n_a", "n_b"]


def load_inputs(game_dir: Path, aliases: dict[int, int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Actions (with control moments) and the tracking frames their windows need.

    The widest sensitivity baseline is included so every setting reuses one read.
    """
    game = load_game(game_dir)
    events = load_events(game_dir, aliases)
    actions = collect_actions(events, game.game_id)
    controls = control_moments(events, actions, game.game_id)
    actions = pd.concat(
        [a for a in (actions, controls) if not a.empty] or [actions], ignore_index=True
    )
    frames = read_frames(game_dir, game, frames_needed(actions), aliases)
    return actions, frames


def study(
    actions: pd.DataFrame,
    frames: pd.DataFrame,
    max_pred_error: float = MAX_PRED_ERROR_FT,
    baseline: int = BASELINE_OFFSET,
) -> pd.DataFrame:
    """Space created for one game's actions under one eligibility gate and baseline."""
    open_long = openness(frames, sides_for(actions), max_pred_error)
    return space_created(actions, open_long, baseline=baseline)


def run_game(
    game_dir: Path,
    aliases: dict[int, int],
    max_pred_error: float = MAX_PRED_ERROR_FT,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Space-created table, pick depth table and counts for one game."""
    actions, frames = load_inputs(game_dir, aliases)
    space = study(actions, frames, max_pred_error)
    depth, skipped = screener_defender_depth(
        actions[actions.kind == "pick"], frames, max_pred_error
    )
    counts = {"actions": actions.kind.value_counts().to_dict(), "depth_skipped": skipped}
    return space, depth, counts


def _gap(space: pd.DataFrame, label_col: str, a: str, b: str, n_boot: int) -> dict:
    present = set(space[label_col]) if not space.empty else set()
    if a not in present or b not in present:
        return dict.fromkeys(GAP_COLUMNS, np.nan)
    return gap_between(space, label_col, a, b, n_boot=n_boot)


def _cell(space: pd.DataFrame, kind: str, role: str, offset: int) -> pd.DataFrame:
    return space[(space.kind == kind) & (space.role == role) & (space.offset == offset)]


def sensitivity_table(
    spaces: dict[tuple[float, int], pd.DataFrame], n_boot: int = 2000
) -> pd.DataFrame:
    """Show-minus-drop gap in team-average openness under each gate, baseline and horizon."""
    rows = []
    for (gate, baseline), space in spaces.items():
        for offset in SENSITIVITY_OFFSETS:
            gap = _gap(
                _cell(space, "pick", "team_mean", offset), "second_cov", "show", "drop", n_boot
            )
            rows.append(
                {"max_pred_error": gate, "baseline_offset": baseline, "offset": offset, **gap}
            )
    return pd.DataFrame(rows)


def _curves(space: pd.DataFrame, n_boot: int) -> pd.DataFrame:
    parts = []
    for kind, of_kind in space.groupby("kind"):
        everything = summarise(of_kind, ["role", "offset"], n_boot=n_boot)
        parts.append(everything.assign(kind=kind, cov_role="all", coverage="all"))
        for cov_role in ("main_cov", "second_cov"):
            if set(of_kind[cov_role]) == {"none"}:
                continue
            by_cov = summarise(of_kind, [cov_role, "role", "offset"], n_boot=n_boot)
            by_cov = by_cov.rename(columns={cov_role: "coverage"})
            parts.append(by_cov.assign(kind=kind, cov_role=cov_role))
    curves = pd.concat(parts, ignore_index=True)
    curves["seconds"] = curves.offset / FPS
    lead = ["kind", "cov_role", "coverage", "role", "offset", "seconds"]
    return curves[[*lead, *[c for c in curves.columns if c not in lead]]]


def _pick_coverage(space: pd.DataFrame, n_boot: int, n_perm: int) -> pd.DataFrame:
    parts = []
    for cov_role in ("main_cov", "second_cov"):
        for role in ROLE_NAMES:
            for offset in HEADLINE_OFFSETS:
                cell = _cell(space, "pick", role, offset)
                if cell.empty:
                    continue
                table = summarise(cell, [cov_role], n_boot=n_boot).rename(
                    columns={cov_role: "coverage"}
                )
                # One test across every coverage with enough picks; not a pairwise p-value.
                p = permutation_p(cell, cov_role, n_perm=n_perm)
                table["omnibus_p"] = np.where(table.n >= PERMUTATION_MIN_N, p, np.nan)
                parts.append(table.assign(cov_role=cov_role, role=role, offset=offset))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _gaps(space: pd.DataFrame, n_boot: int) -> pd.DataFrame:
    rows = []
    for label_col, a, b, roles in CONTRASTS:
        for role in roles:
            for offset in HEADLINE_OFFSETS:
                gap = _gap(_cell(space, "pick", role, offset), label_col, a, b, n_boot)
                rows.append({"contrast": f"{a} - {b}", "role": role, "offset": offset, **gap})
    return pd.DataFrame(rows)


def _depth_tables(space: pd.DataFrame, depth: pd.DataFrame, n_boot: int):
    picks = space[space.kind == "pick"]
    labels = picks.drop_duplicates("action_id")[["action_id", "second_cov"]].merge(
        depth, on="action_id"
    )
    by_label = (
        labels.groupby("second_cov")
        .depth_ft.agg(
            n="size",
            mean_depth_ft="mean",
            median_depth_ft="median",
            share_below_screen=lambda d: float((d > 0).mean()),
        )
        .reset_index()
    )
    binned = depth.assign(
        depth_bin=pd.cut(depth.depth_ft, DEPTH_BINS, labels=list(DEPTH_BIN_LABELS), right=False)
    )
    at_one_second = picks[picks.offset == HEADLINE_OFFSETS[0]].merge(binned, on="action_id")
    parts = [
        summarise(of_role, ["depth_bin"], n_boot=n_boot).assign(role=role)
        for role, of_role in at_one_second.groupby("role")
    ]
    dose = (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame(columns=["role", "depth_bin"])
    )
    if not dose.empty:
        dose["depth_bin"] = pd.Categorical(
            dose.depth_bin, categories=list(DEPTH_BIN_LABELS), ordered=True
        )
        dose = dose.sort_values(["role", "depth_bin"]).reset_index(drop=True)
        dose["depth_bin"] = dose.depth_bin.astype(str)
        dose = dose[["role", *[c for c in dose.columns if c != "role"]]]
    return by_label, dose


def build_tables(
    space: pd.DataFrame,
    depth: pd.DataFrame,
    prices: pd.DataFrame,
    sensitivity: pd.DataFrame,
    n_boot: int = 2000,
    n_perm: int = 5000,
) -> dict[str, pd.DataFrame]:
    """Every table the write-up quotes, keyed by name."""
    controls = space[(space.kind == "control") & space.offset.isin(SENSITIVITY_OFFSETS)]
    depth_by_label, dose = _depth_tables(space, depth, n_boot)
    return {
        "curves": _curves(space, n_boot),
        "pick_coverage": _pick_coverage(space, n_boot, n_perm),
        # The season aggregates count direct picks only, so the priced comparison does too.
        "pick_coverage_direct": _pick_coverage(space[space.direct.astype(bool)], n_boot, n_perm),
        "gaps": _gaps(space, n_boot),
        "controls": summarise(controls, ["role", "offset"], n_boot=n_boot),
        "depth_by_label": depth_by_label,
        "depth_dose_response": dose,
        "prices": prices,
        "sensitivity": sensitivity,
    }


# ---- figures -------------------------------------------------------------------------------

_COVERAGE_STYLE = {"show": "#c2410c", "drop": "#1d4ed8", "switch": "#4b5563"}
_FIGURE_ROLES = ("second", "other_max", "team_mean")


def figure_curves(tables: dict[str, pd.DataFrame], path: Path) -> None:
    """Space created after a ball screen, by how the screener's defender played it."""
    curves = tables["curves"]
    picks = curves[(curves.kind == "pick") & (curves.cov_role == "second_cov")]
    fig, axes = plt.subplots(1, len(_FIGURE_ROLES), figsize=(12, 4), sharey=True)
    for ax, role in zip(axes, _FIGURE_ROLES, strict=True):
        for coverage, colour in _COVERAGE_STYLE.items():
            line = picks[(picks.role == role) & (picks.coverage == coverage)].sort_values("seconds")
            if line.empty:
                continue
            n = int(line.n.max())
            ax.plot(
                line.seconds, line.mean_delta_ft, color=colour, lw=2, label=f"{coverage} (n={n})"
            )
            if line.lo.notna().any():
                ax.fill_between(line.seconds, line.lo, line.hi, color=colour, alpha=0.15, lw=0)
        ax.axhline(0, color="black", lw=0.6)
        ax.axvline(0, color="black", lw=0.6, ls=":")
        ax.set_title(ROLE_NAMES[role])
        ax.set_xlabel("Seconds from the screen")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Change in nearest-defender distance (ft)")
    axes[0].legend(frameon=False, title="Screener's defender")
    fig.suptitle("Space created by a ball screen, by coverage")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def priced_points(
    tables: dict[str, pd.DataFrame], price_role: str, role: str, cov_role: str
) -> pd.DataFrame:
    """Coverages with both a tracked space-created range and a season price.

    The tracked side uses direct picks only, the same population the season file prices.

    Coverages too thin for a range in the tracked games (blitz, ice) are left out:
    a point from a handful of picks would set the axis and say nothing.
    """
    coverage = tables["pick_coverage_direct"]
    if coverage.empty:
        return pd.DataFrame(columns=["coverage", "mean_delta_ft", "lo", "hi", "points_per_pick"])
    space = coverage[
        (coverage.cov_role == cov_role)
        & (coverage.role == role)
        & (coverage.offset == HEADLINE_OFFSETS[0])
        & coverage.lo.notna()
    ]
    prices = tables["prices"]
    both = space.merge(prices[prices.role == price_role], on="coverage")
    return both[both.points_per_pick.notna()].sort_values("mean_delta_ft").reset_index(drop=True)


def figure_space_vs_points(tables: dict[str, pd.DataFrame], path: Path) -> None:
    """Space each coverage gives a role (10 tracked games) against season points per pick."""
    panels = (("screener", "second", "second_cov"), ("handler", "main", "main_cov"))
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5))
    for ax, (price_role, role, cov_role) in zip(axes, panels, strict=True):
        points = priced_points(tables, price_role, role, cov_role)
        for i, row in enumerate(points.itertuples(index=False)):
            ax.plot([row.lo, row.hi], [row.points_per_pick] * 2, color="#1d4ed8", lw=1)
            ax.scatter(row.mean_delta_ft, row.points_per_pick, s=70, color="#1d4ed8", zorder=3)
            ax.annotate(
                f"{row.coverage} ({int(row.picks):,} picks)",
                (row.mean_delta_ft, row.points_per_pick),
                textcoords="offset points",
                xytext=(0, 10 if i % 2 == 0 else -16),
                ha="center",
            )
        ax.margins(x=0.25, y=0.35)
        defender = "screener's" if role == "second" else "handler's"
        ax.set_title(f"{ROLE_NAMES[role]}, by how the {defender} defender played it", fontsize=11)
        ax.set_xlabel(
            f"Space created for the {ROLE_NAMES[role].lower()} at +1 s (ft)\n10 tracked games, picks ending directly in a shot, assist or foul"
        )
        ax.set_ylabel(f"Points per pick, {price_role}, full season")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Space created in the tracked games against season scoring, by coverage")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
