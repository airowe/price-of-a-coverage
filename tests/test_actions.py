import pandas as pd

from conftest import AWAY, GAME, HOME
from coverage_price.actions import ACTION_COLUMNS, collect_actions, control_moments

PICK_FRAME = 1000
HANDLER, SCREENER, SCREENER_DEFENDER = 1, 2, 12
PICK = {
    "id": "pick-1", "frame": PICK_FRAME, "chanceId": "chance-1",
    "ballhandlerId": HANDLER, "screenerId": SCREENER,
    "ballhandlerDefId": 11, "screenerDefId": SCREENER_DEFENDER,
    "offTeamId": HOME, "defTeamId": AWAY, "bhrDefType": "over", "scrDefType": "show",
    "location": [-12.0, 3.0],
}  # fmt: skip
CHANCE = {
    "id": "chance-1", "startFrame": 0, "frontcourtFrame": 100, "endFrame": 2000,
    "offTeamId": HOME, "defTeamId": AWAY,
}  # fmt: skip


def _events(**families):
    return {name: pd.DataFrame(records) for name, records in families.items()}


def test_pick_maps_to_unified_columns():
    out = collect_actions(_events(picks=[PICK]), GAME)
    row = out.iloc[0]
    assert list(out.columns) == ACTION_COLUMNS
    assert (row.kind, row.frame, row.main_id, row.second_id) == (
        "pick",
        PICK_FRAME,
        HANDLER,
        SCREENER,
    )
    assert (row.main_cov, row.second_cov, row.second_def_id) == ("over", "show", SCREENER_DEFENDER)
    assert (row.off_team_id, row.def_team_id, row.game_id) == (HOME, AWAY, GAME)
    assert (row.loc_x, row.loc_y, row.chance_id) == (-12.0, 3.0, "chance-1")


def test_soft_is_renamed_drop():
    out = collect_actions(_events(picks=[{**PICK, "scrDefType": "soft"}]), GAME)
    assert out.second_cov.iloc[0] == "drop"


def test_null_coverage_reads_none():
    out = collect_actions(_events(picks=[{**PICK, "bhrDefType": None}]), GAME)
    assert out.main_cov.iloc[0] == "none"


def test_null_location_gives_null_loc_and_keeps_the_row():
    out = collect_actions(_events(picks=[{**PICK, "location": None}]), GAME)
    assert len(out) == 1 and pd.isna(out.loc_x.iloc[0]) and pd.isna(out.loc_y.iloc[0])


def test_drive_uses_start_frame_and_has_no_second_player_or_coverage():
    drive_start = 500
    drive = {
        "id": "drive-1", "startFrame": drive_start, "endFrame": 540, "chanceId": "chance-1",
        "ballhandlerId": HANDLER, "offTeamId": HOME, "defTeamId": AWAY, "location": [-5.0, 9.0],
    }  # fmt: skip
    row = collect_actions(_events(drives=[drive]), GAME).iloc[0]
    assert (row.kind, row.frame, row.main_id) == ("drive", drive_start, HANDLER)
    assert pd.isna(row.second_id) and row.main_cov == "none" and row.second_cov == "none"


def test_missing_and_empty_families_are_skipped():
    out = collect_actions(_events(picks=[PICK], posts=[]), GAME)
    assert list(out.kind) == ["pick"]


def test_action_without_a_frame_is_dropped():
    out = collect_actions(_events(picks=[PICK, {**PICK, "id": "pick-2", "frame": None}]), GAME)
    assert list(out.action_id) == ["pick-1"]


def test_control_moment_lies_inside_the_chance_and_clear_of_actions():
    events = _events(chances=[CHANCE])
    no_actions = collect_actions(events, GAME)
    out = control_moments(events, no_actions, GAME, seed=0)
    assert list(out.columns) == ACTION_COLUMNS
    row = out.iloc[0]
    assert row.kind == "control" and pd.isna(row.main_id) and row.main_cov == "none"
    assert CHANCE["frontcourtFrame"] + 50 <= row.frame <= CHANCE["endFrame"] - 100
    assert (row.off_team_id, row.def_team_id) == (HOME, AWAY)


def test_control_moment_is_rejected_near_an_action():
    events = _events(picks=[PICK], chances=[CHANCE])
    whole_chance = CHANCE["endFrame"]
    out = control_moments(events, collect_actions(events, GAME), GAME, clear_frames=whole_chance)
    assert out.empty and list(out.columns) == ACTION_COLUMNS


def test_chance_too_short_for_a_window_gives_no_control_moment():
    short = {**CHANCE, "frontcourtFrame": 100, "endFrame": 200}
    events = _events(chances=[short])
    assert control_moments(events, collect_actions(events, GAME), GAME).empty


def test_control_moments_are_reproducible_for_a_seed():
    chances = [{**CHANCE, "id": f"chance-{i}"} for i in range(20)]
    events = _events(chances=chances)
    empty = collect_actions(events, GAME)
    first = control_moments(events, empty, GAME, seed=7)
    assert first.frame.tolist() == control_moments(events, empty, GAME, seed=7).frame.tolist()
    assert first.frame.tolist() != control_moments(events, empty, GAME, seed=8).frame.tolist()


def test_action_carries_the_end_frame_of_its_chance():
    out = collect_actions(_events(picks=[PICK], chances=[CHANCE]), GAME)
    assert out.end_frame.iloc[0] == CHANCE["endFrame"]


def test_end_frame_is_null_when_the_chance_is_unknown():
    out = collect_actions(_events(picks=[PICK]), GAME)
    assert pd.isna(out.end_frame.iloc[0])


def test_control_moment_carries_its_chance_end_frame():
    events = _events(chances=[CHANCE])
    out = control_moments(events, collect_actions(events, GAME), GAME)
    assert out.end_frame.iloc[0] == CHANCE["endFrame"]


def test_pick_carries_its_direct_flag():
    out = collect_actions(
        _events(picks=[{**PICK, "direct": True}, {**PICK, "id": "pick-2", "direct": False}]), GAME
    )
    assert out.direct.tolist() == [True, False]


def test_direct_is_false_when_the_source_has_no_flag():
    assert collect_actions(_events(picks=[PICK]), GAME).direct.tolist() == [False]
