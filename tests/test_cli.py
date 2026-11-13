import json

import pandas as pd
import pytest

from conftest import AWAY, GAME, HOME, HOME_IDS, live_frame, write_game
from coverage_price import cli
from coverage_price.constants import OFFSETS
from coverage_price.pricing import HANDLER_COVERAGES, SCREENER_COVERAGES

PICK_FRAME = 1000
PICK_ID, DRIVE_ID = "pick-1", "drive-1"


def _game(tmp_path):
    pick = {
        "id": PICK_ID, "gameId": GAME, "frame": PICK_FRAME, "chanceId": "chance-1",
        "period": 4, "ballhandlerId": 1, "screenerId": 2, "ballhandlerDefId": 11,
        "screenerDefId": 12, "offTeamId": HOME, "defTeamId": AWAY, "bhrDefType": "over",
        "scrDefType": "soft", "location": [-30.0, -20.0],
    }  # fmt: skip
    drive = {"id": DRIVE_ID, "gameId": GAME, "startFrame": PICK_FRAME + 5, "chanceId": "chance-1",
             "ballhandlerId": 1, "offTeamId": HOME, "defTeamId": AWAY}  # fmt: skip
    chance = {
        "id": "chance-1", "startFrame": PICK_FRAME - 10, "endFrame": PICK_FRAME + 80,
        "offTeamId": HOME, "defTeamId": AWAY, "offPlayerIds": list(HOME_IDS),
        "homeStartScore": 60, "awayStartScore": 58,
    }  # fmt: skip
    frames = [live_frame(PICK_FRAME + o) for o in OFFSETS]
    write_game(
        tmp_path, GAME, events={"picks": [pick], "drives": [drive], "chances": [chance]},
        frames=frames,
    )  # fmt: skip
    agg = {"player_id": list(HOME_IDS), "team_name": ["A"] * 5, "handler_assist_to_screener": 5}
    for role, covs in (("handler", HANDLER_COVERAGES), ("screener", SCREENER_COVERAGES)):
        for cov in covs:
            for metric in ("picks", "points", "score", "assist", "turnover"):
                agg[f"{role}_{metric}_vs_{cov}"] = 10
        agg |= {f"{role}_total_picks": 100, f"{role}_points": 70, f"{role}_score_2pt": 20,
                f"{role}_score_3pt": 5, f"{role}_assist_2pt": 5, f"{role}_assist_3pt": 0}  # fmt: skip
    folder = tmp_path / "data" / "aggregates"
    folder.mkdir()
    pd.DataFrame(agg).to_csv(folder / "acb_picksaggregates_20252026.csv", index=False)
    return tmp_path


@pytest.mark.parametrize("action_id", ["no-such-id", DRIVE_ID])
def test_menu_rejects_unknown_and_non_pick_ids(tmp_path, capsys, action_id):
    root = _game(tmp_path)
    assert cli.main(["menu", "--data-dir", str(root), action_id]) == 2
    assert action_id in capsys.readouterr().err


def test_menu_fails_clearly_without_data(tmp_path, capsys):
    assert cli.main(["menu", "--data-dir", str(tmp_path / "nope"), PICK_ID]) == 2
    assert "download_data.sh" in capsys.readouterr().err


def test_menu_prints_every_pair_and_marks_the_used_one(tmp_path, capsys):
    root = _game(tmp_path)
    assert cli.main(["menu", "--data-dir", str(root), PICK_ID]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if " + " in line]
    assert len(lines) == 5 * 4
    used = [line for line in lines if "used" in line]
    assert len(used) == 1 and used[0].startswith("P 1 + P 2")


def test_reproduce_adds_the_other_calls_summary(tmp_path):
    root, out = _game(tmp_path), tmp_path / "results"
    assert cli.main(["reproduce", "--data-dir", str(root), "--out", str(out), "--quick"]) == 0
    other = json.loads((out / "summary.json").read_text())["other_calls"]
    assert other["picks_with_menu"] == 1 and other["left_out"] == 0
    assert other["worked_moment"] == PICK_ID
    assert other["worked_rule"] == "whole game, within 6"
    assert (other["prior_picks"], other["min_role_picks"]) == (50, 30)
    menus = pd.read_csv(out / "menus.csv")
    assert menus.used.sum() == 1
