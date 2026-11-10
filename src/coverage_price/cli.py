"""Command line: `coverage-price reproduce` rebuilds every table and figure."""

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

from coverage_price import report
from coverage_price.constants import BASELINE_OFFSET, MAX_PRED_ERROR_FT
from coverage_price.depth import SKIP_REASONS, screener_defender_depth
from coverage_price.loader import DataNotDownloadedError, list_games, load_aliases
from coverage_price.pricing import price_by_coverage

PICKS_AGGREGATE = Path("data") / "aggregates" / "acb_picksaggregates_20252026.csv"
QUICK = {"n_boot": 100, "n_perm": 100}
FULL = {"n_boot": 2000, "n_perm": 5000}


def _sensitivity_rows(space: pd.DataFrame) -> pd.DataFrame:
    keep = (
        (space.kind == "pick")
        & (space.role == "team_mean")
        & space.offset.isin(report.SENSITIVITY_OFFSETS)
    )
    return space[keep]


def reproduce(data_dir: Path, out: Path, max_pred_error: float, quick: bool) -> int:
    matches = data_dir / "data" / "matches"
    if not matches.is_dir():
        print(f"No data at {matches}. Run: bash scripts/download_data.sh", file=sys.stderr)
        return 2
    started, effort = time.monotonic(), QUICK if quick else FULL
    aliases = load_aliases(data_dir)
    settings = [(max_pred_error, BASELINE_OFFSET)]
    if not quick:
        settings += [(g, BASELINE_OFFSET) for g in report.SENSITIVITY_GATES if g != max_pred_error]
        settings += [
            (max_pred_error, b) for b in report.SENSITIVITY_BASELINES if b != BASELINE_OFFSET
        ]
    spaces, depths, by_setting = [], [], {s: [] for s in settings}
    action_counts: dict[str, int] = {}
    depth_skipped = dict.fromkeys(SKIP_REASONS, 0)
    games = list_games(data_dir)
    try:
        for game_dir in games:
            actions, frames = report.load_inputs(game_dir, aliases)
            for gate, baseline in settings:
                space = report.study(actions, frames, gate, baseline)
                by_setting[(gate, baseline)].append(_sensitivity_rows(space))
                if (gate, baseline) == settings[0]:
                    spaces.append(space)
            depth, skipped = screener_defender_depth(
                actions[actions.kind == "pick"], frames, max_pred_error
            )
            depths.append(depth)
            for kind, n in actions.kind.value_counts().items():
                action_counts[kind] = action_counts.get(kind, 0) + int(n)
            for reason, n in skipped.items():
                depth_skipped[reason] += n
            print(
                f"  {game_dir.name}: {len(actions)} actions, {frames.frame.nunique()} frames",
                flush=True,
            )
    except DataNotDownloadedError as error:
        print(str(error), file=sys.stderr)
        return 2
    space, depth = pd.concat(spaces, ignore_index=True), pd.concat(depths, ignore_index=True)
    sensitivity = report.sensitivity_table(
        {s: pd.concat(parts, ignore_index=True) for s, parts in by_setting.items()},
        n_boot=effort["n_boot"],
    )
    prices = price_by_coverage(pd.read_csv(data_dir / PICKS_AGGREGATE))
    tables = report.build_tables(space, depth, prices, sensitivity, **effort)

    (out / "tables").mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(out / "tables" / f"{name}.csv", index=False, float_format="%.4f")
    report.figure_curves(tables, out / "fig1_curves.png")
    report.figure_space_vs_points(tables, out / "fig2_space_vs_points.png")
    picks = space[(space.kind == "pick") & (space.offset == report.HEADLINE_OFFSETS[0])]
    n_picks = action_counts.get("pick", 0)
    summary = {
        "games": len(games),
        "actions": action_counts,
        "max_pred_error_ft": max_pred_error,
        "baseline_offset_frames": BASELINE_OFFSET,
        "pick_share_eligible_at_plus_1s": {
            role: round(picks[picks.role == role].action_id.nunique() / n_picks, 4)
            if n_picks
            else None
            for role in report.ROLE_NAMES
        },
        "depth_measured": len(depth),
        "depth_skipped": depth_skipped,
        "resamples": effort,
        "seconds": round(time.monotonic() - started, 1),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Wrote {len(tables)} tables, 2 figures and summary.json to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coverage-price", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("reproduce", help="rebuild all tables and figures")
    run.add_argument("--data-dir", type=Path, default=Path("data/opendata-basketball"))
    run.add_argument("--out", type=Path, default=Path("results"))
    run.add_argument("--max-pred-error", type=float, default=MAX_PRED_ERROR_FT)
    run.add_argument(
        "--quick", action="store_true", help="few resamples, no sensitivity grid (smoke test)"
    )
    args = parser.parse_args(argv)
    return reproduce(args.data_dir, args.out, args.max_pred_error, args.quick)


if __name__ == "__main__":
    sys.exit(main())
