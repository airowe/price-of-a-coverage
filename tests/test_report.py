import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import AWAY, GAME, HOME, live_frame, write_game
from coverage_price import cli, report
from coverage_price.constants import OFFSETS
from coverage_price.eventstudy import SPACE_COLUMNS
from coverage_price.pricing import PRICE_COLUMNS

PICK_FRAME = 1000
REAL_DATA = Path(__file__).parents[1] / "data" / "opendata-basketball"
REAL_GAME = 114243
TABLE_KEYS = {
    "curves", "pick_coverage", "gaps", "controls", "depth_by_label",
    "depth_dose_response", "prices", "sensitivity",
}  # fmt: skip


def _synthetic_game(tmp_path):
    pick = {
        "id": "pick-1", "frame": PICK_FRAME, "chanceId": "chance-1", "ballhandlerId": 1,
        "screenerId": 2, "ballhandlerDefId": 11, "screenerDefId": 12, "offTeamId": HOME,
        "defTeamId": AWAY, "bhrDefType": "over", "scrDefType": "soft", "location": [-30.0, -20.0],
    }  # fmt: skip
    frames = [live_frame(PICK_FRAME + o) for o in OFFSETS]
    return write_game(tmp_path, GAME, events={"picks": [pick]}, frames=frames)


def _space(n_games=4, per_cell=40, seed=0):
    """Synthetic pick results: `show` creates 1 ft more than `drop` for every role."""
    rng = np.random.default_rng(seed)
    rows = []
    for game in range(n_games):
        for cov, shift in (("show", 1.0), ("drop", 0.0)):
            for i in range(per_cell):
                for role in ("main", "second", "other_max", "team_mean"):
                    for offset in OFFSETS:
                        rows.append((
                            f"pick-{game}-{cov}-{i}", game, "pick", "over", cov, role, offset,
                            6.0, rng.normal(shift, 1.0),
                        ))  # fmt: skip
        for i in range(10):
            for role in ("other_max", "team_mean"):
                for offset in OFFSETS:
                    rows.append((
                        f"control-{game}-{i}", game, "control", "none", "none", role, offset,
                        6.0, rng.normal(0.0, 1.0),
                    ))  # fmt: skip
    return pd.DataFrame(rows, columns=SPACE_COLUMNS)


def _depth(space):
    picks = space[space.kind == "pick"].drop_duplicates("action_id")
    depth = np.where(picks.second_cov == "drop", 5.0, -1.0)
    return pd.DataFrame({"action_id": picks.action_id.to_numpy(), "depth_ft": depth})


def _prices():
    rows = [("screener", "show", 100, 0.3, 0.1, 0.04, 0.02), ("screener", "drop", 100, 0.2, 0.08, 0.02, 0.01),
            ("handler", "over", 100, 0.7, 0.15, 0.15, 0.1), ("handler", "under", 100, 0.77, 0.17, 0.14, 0.09)]  # fmt: skip
    return pd.DataFrame(rows, columns=PRICE_COLUMNS)


def _tables():
    space = _space()
    sensitivity = report.sensitivity_table({(3.0, -15): space}, n_boot=200)
    return report.build_tables(space, _depth(space), _prices(), sensitivity, n_boot=200, n_perm=200)


def test_run_game_on_a_synthetic_game_returns_expected_shapes(tmp_path):
    space, depth, counts = report.run_game(_synthetic_game(tmp_path), aliases={})
    assert list(space.columns) == SPACE_COLUMNS
    assert set(space.kind) == {"pick"} and set(space.second_cov) == {"drop"}
    assert space.delta_ft.abs().max() == pytest.approx(0.0)
    assert list(depth.columns) == ["action_id", "depth_ft"] and len(depth) == 1
    assert counts["actions"] == {"pick": 1}


def test_build_tables_has_every_documented_key():
    tables = _tables()
    assert set(tables) == TABLE_KEYS
    assert all(isinstance(t, pd.DataFrame) and not t.empty for t in tables.values())


def test_gaps_table_recovers_the_planted_show_minus_drop_gap():
    gaps = _tables()["gaps"]
    row = gaps[(gaps.contrast == "show - drop") & (gaps.role == "team_mean") & (gaps.offset == 25)]
    assert row.gap_ft.iloc[0] == pytest.approx(1.0, abs=0.3)
    assert row.games_same_sign.iloc[0] == row.n_games.iloc[0] == 4


def test_depth_by_label_puts_drop_deeper_than_show():
    by_label = _tables()["depth_by_label"].set_index("second_cov")
    assert by_label.loc["drop", "median_depth_ft"] > by_label.loc["show", "median_depth_ft"]


def test_depth_dose_response_bins_are_ordered_and_counted():
    dose = _tables()["depth_dose_response"]
    team = dose[dose.role == "team_mean"]
    assert list(team.depth_bin) == [b for b in report.DEPTH_BIN_LABELS if b in set(team.depth_bin)]
    assert team.n.sum() == 4 * 2 * 40


def test_sensitivity_has_one_row_per_setting_and_offset():
    table = report.sensitivity_table({(3.0, -15): _space(), (5.0, -15): _space(seed=1)}, n_boot=100)
    assert len(table) == 2 * len(report.SENSITIVITY_OFFSETS)
    assert set(table.max_pred_error) == {3.0, 5.0}
    assert (table.gap_ft > 0).all()


def test_figures_are_written(tmp_path):
    tables = _tables()
    one, two = tmp_path / "fig1.png", tmp_path / "fig2.png"
    report.figure_curves(tables, one)
    report.figure_space_vs_points(tables, two)
    assert one.stat().st_size > 1000 and two.stat().st_size > 1000


def test_reproduce_fails_clearly_when_data_dir_is_missing(tmp_path, capsys):
    code = cli.main(
        ["reproduce", "--data-dir", str(tmp_path / "nope"), "--out", str(tmp_path / "out")]
    )
    assert code == 2
    assert "download_data.sh" in capsys.readouterr().err


def test_reproduce_writes_tables_figures_and_summary(tmp_path):
    _synthetic_game(tmp_path)
    (tmp_path / "data" / "aggregates").mkdir()
    agg = {"player_id": [1], "team_name": ["A"]}
    for role, covs in (("handler", ("over", "under", "switch", "ice", "blitz")),
                       ("screener", ("soft", "show", "switch", "ice", "blitz"))):  # fmt: skip
        for cov in covs:
            for metric in ("picks", "points", "score", "assist", "turnover"):
                agg[f"{role}_{metric}_vs_{cov}"] = [10]
    pd.DataFrame(agg).to_csv(
        tmp_path / "data" / "aggregates" / "acb_picksaggregates_20252026.csv", index=False
    )
    out = tmp_path / "results"
    assert cli.main(["reproduce", "--data-dir", str(tmp_path), "--out", str(out), "--quick"]) == 0
    assert {p.stem for p in (out / "tables").glob("*.csv")} == TABLE_KEYS
    assert (out / "fig1_curves.png").exists() and (out / "fig2_space_vs_points.png").exists()
    summary = json.loads((out / "summary.json").read_text())
    assert summary["games"] == 1 and summary["actions"] == {"pick": 1}


@pytest.mark.skipif(not REAL_DATA.exists(), reason="open data not downloaded")
def test_real_game_openness_matches_supplied_shot_distance():
    from coverage_price.loader import load_aliases, load_events, load_game, read_frames
    from coverage_price.openness import openness

    game_dir = REAL_DATA / "data" / "matches" / str(REAL_GAME)
    aliases = load_aliases(REAL_DATA)
    game, shots = load_game(game_dir), load_events(game_dir, aliases)["shots"]
    shots = shots.dropna(subset=["closestDefDist"])
    frames = read_frames(game_dir, game, set(shots.startFrame), aliases)
    sides = shots.rename(
        columns={"startFrame": "frame", "offTeamId": "off_team_id", "defTeamId": "def_team_id"}
    )[["frame", "off_team_id", "def_team_id"]]
    ours = openness(frames, sides).rename(columns={"frame": "startFrame", "player_id": "shooterId"})
    both = shots.merge(ours, on=["startFrame", "shooterId"])
    assert len(both) > 100
    assert (both.dist_ft - both.closestDefDist).abs().median() < 0.1


def test_priced_points_leave_out_coverages_too_thin_for_a_range():
    tables = _tables()
    thin = tables["pick_coverage"].iloc[[0]].assign(coverage="blitz", n=4, lo=np.nan, hi=np.nan)
    thin = thin.assign(cov_role="second_cov", role="second", offset=report.HEADLINE_OFFSETS[0])
    tables["pick_coverage"] = pd.concat([tables["pick_coverage"], thin], ignore_index=True)
    blitz_price = pd.DataFrame(
        [("screener", "blitz", 67, 0.43, 0.09, 0.09, 0.0)], columns=PRICE_COLUMNS
    )
    tables["prices"] = pd.concat([tables["prices"], blitz_price], ignore_index=True)
    points = report.priced_points(
        tables, price_role="screener", role="second", cov_role="second_cov"
    )
    assert set(points.coverage) == {"show", "drop"}
    assert {"mean_delta_ft", "lo", "hi", "points_per_pick"} <= set(points.columns)
