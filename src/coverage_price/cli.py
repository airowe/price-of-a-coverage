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
from coverage_price.freezes import game_freezes, gaps, menus_for, summarise_menus, worked_moment
from coverage_price.loader import (
    DataNotDownloadedError,
    list_games,
    load_aliases,
    load_events,
    load_game,
)
from coverage_price.menu import (
    MIN_ROLE_PICKS,
    PRIOR_PICKS,
    build_menu,
    league_rates,
    player_rates,
)
from coverage_price.pricing import price_by_coverage
from coverage_price.replay import court_frames, render, typical_pick

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


def _other_calls(data_dir: Path, aliases: dict[int, int], freezes: pd.DataFrame, n_boot: int):
    """Menus for the gate-eligible picks, their summary, and the worked moment."""
    if freezes.empty:
        return None, None
    agg = pd.read_csv(data_dir / PICKS_AGGREGATE)
    menus = menus_for(freezes, player_rates(agg, aliases), league_rates(agg))
    gap_table = gaps(menus)
    if gap_table.empty:
        return menus, None
    moment, rule = worked_moment(gap_table, freezes)
    summary = summarise_menus(menus, n_boot=n_boot)
    return menus, {
        **summary, "worked_moment": moment, "worked_rule": rule,
        "prior_picks": PRIOR_PICKS, "min_role_picks": MIN_ROLE_PICKS,
    }  # fmt: skip


def reproduce(data_dir: Path, out: Path, max_pred_error: float, quick: bool) -> int:
    matches = data_dir / "data" / "matches"
    if not matches.is_dir():
        print(f"No data at {matches}. Run: bash scripts/download_data.sh", file=sys.stderr)
        return 2
    games = list_games(data_dir)
    if not games:
        print(f"No games in {matches}. Run: bash scripts/download_data.sh", file=sys.stderr)
        return 2
    started, effort = time.monotonic(), QUICK if quick else FULL
    aliases = load_aliases(data_dir)
    settings = [(max_pred_error, BASELINE_OFFSET)]
    if not quick:
        settings += [(g, BASELINE_OFFSET) for g in report.SENSITIVITY_GATES if g != max_pred_error]
        settings += [
            (max_pred_error, b) for b in report.SENSITIVITY_BASELINES if b != BASELINE_OFFSET
        ]
    spaces, depths, by_setting, freezes = [], [], {s: [] for s in settings}, []
    action_counts: dict[str, int] = {}
    depth_skipped = dict.fromkeys(SKIP_REASONS, 0)
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
            eligible = spaces[-1]
            eligible = eligible[
                (eligible.kind == "pick") & (eligible.offset == 0) & (eligible.role == "team_mean")
            ]
            game_picks = game_freezes(load_events(game_dir, aliases))
            freezes.append(game_picks[game_picks.action_id.isin(eligible.action_id)])
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
    }
    menus, other_calls = _other_calls(
        data_dir, aliases, pd.concat(freezes, ignore_index=True), effort["n_boot"]
    )
    if menus is not None:
        menus.to_csv(out / "menus.csv", index=False, float_format="%.4f")
    summary["other_calls"] = other_calls
    summary["seconds"] = round(time.monotonic() - started, 1)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Wrote {len(tables)} tables, 2 figures and summary.json to {out}")
    return 0


def replay(data_dir: Path, out: Path, action_id: str | None, coverage: str) -> int:
    """Write a clip of one pick: a named action, or a typical one for a coverage."""
    matches = data_dir / "data" / "matches"
    if not matches.is_dir() or not list_games(data_dir):
        print(f"No games in {matches}. Run: bash scripts/download_data.sh", file=sys.stderr)
        return 2
    aliases, games = load_aliases(data_dir), list_games(data_dir)
    title = f"Ball screen {action_id}"
    if action_id is None:
        space = pd.concat([report.run_game(g, aliases)[0] for g in games], ignore_index=True)
        action_id = typical_pick(space, coverage)
        title = f"A typical ball screen against a {coverage}"
    for game_dir in games:
        try:
            frames = court_frames(game_dir, aliases, action_id)
        except KeyError:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        render(frames, out, title=title)
        print(f"Wrote {out} ({action_id})")
        return 0
    print(f"No action {action_id} in {matches}", file=sys.stderr)
    return 2


def _find_pick(games: list[Path], aliases: dict[int, int], action_id: str):
    """(game folder, freeze row) for a pick id, or (None, reason) when it is not a pick."""
    for game_dir in games:
        events = load_events(game_dir, aliases)
        picks = game_freezes(events)
        found = picks[picks.action_id == action_id]
        if not found.empty:
            return game_dir, found.iloc[0]
        for family, table in events.items():
            if "id" in table.columns and (table["id"] == action_id).any():
                return None, f"{action_id} is a {family} event, not a pick"
    return None, f"No pick {action_id} in {games[0].parent}"


def menu(data_dir: Path, action_id: str) -> int:
    """Print the priced handler–screener menu for one pick."""
    matches = data_dir / "data" / "matches"
    if not matches.is_dir() or not list_games(data_dir):
        print(f"No games in {matches}. Run: bash scripts/download_data.sh", file=sys.stderr)
        return 2
    aliases = load_aliases(data_dir)
    game_dir, freeze = _find_pick(list_games(data_dir), aliases, action_id)
    if game_dir is None:
        print(freeze, file=sys.stderr)
        return 2
    agg = pd.read_csv(data_dir / PICKS_AGGREGATE)
    table = build_menu(
        freeze.on_floor,
        (freeze.handler_id, freeze.screener_id),
        player_rates(agg, aliases),
        league_rates(agg),
    )
    names = load_game(game_dir).players.set_index("player_id").name.to_dict()
    print(f"{action_id}: period {freeze.period}, margin {freeze.margin}")
    print("Points per direct pick, 95% interval")
    for row in table.itertuples(index=False):
        marks = [
            label
            for label, on in (
                ("used", row.used), ("best", row.best),
                ("too close", row.too_close_to_best and not row.best),
                (f"below {MIN_ROLE_PICKS}", row.below_volume),
            )
            if on
        ]  # fmt: skip
        pair = f"{names.get(row.handler_id, row.handler_id)} + {names.get(row.screener_id, row.screener_id)}"
        print(f"{pair:<40} {row.price:.3f} [{row.lo:.3f}, {row.hi:.3f}]  {', '.join(marks)}")
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
    clip = commands.add_parser("replay", help="draw one pick as moving dots (GIF or MP4)")
    clip.add_argument("--data-dir", type=Path, default=Path("data/opendata-basketball"))
    clip.add_argument("--out", type=Path, default=Path("results/replay.gif"))
    clip.add_argument("--action-id", help="a pick id from the event data; default: a typical pick")
    clip.add_argument("--coverage", default="show", help="coverage to pick a typical example of")
    card = commands.add_parser("menu", help="price every handler–screener pair at one pick")
    card.add_argument("action_id", help="a pick id from the event data")
    card.add_argument("--data-dir", type=Path, default=Path("data/opendata-basketball"))
    args = parser.parse_args(argv)
    if args.command == "menu":
        return menu(args.data_dir, args.action_id)
    if args.command == "replay":
        return replay(args.data_dir, args.out, args.action_id, args.coverage)
    return reproduce(args.data_dir, args.out, args.max_pred_error, args.quick)


if __name__ == "__main__":
    sys.exit(main())
