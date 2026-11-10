import pandas as pd
import pytest

from conftest import (
    AWAY,
    AWAY_IDS,
    DEFAULT_AWAY_XY,
    DEFAULT_HOME_XY,
    HOME,
    live_frame,
    sides_table,
    to_table,
)
from coverage_price.constants import MAX_PRED_ERROR_FT
from coverage_price.openness import OPENNESS_COLUMNS, openness

FRAME = 100
SHOOTER, NEAREST_DEFENDER = 1, 11
DEFENDER_GAP_FT = 4.0
SHOOTER_XY = DEFAULT_HOME_XY[0]
# Defender 11 stands DEFENDER_GAP_FT from the shooter; the other four stay 20 ft or more away.
NEAR_AWAY_XY = ((SHOOTER_XY[0] + DEFENDER_GAP_FT, SHOOTER_XY[1]), *DEFAULT_AWAY_XY[1:])
JUST_OVER_GATE = MAX_PRED_ERROR_FT + 0.1


def _shooter_row(frames, **kwargs):
    out = openness(to_table(frames), sides_table([f["frameIdx"] for f in frames]), **kwargs)
    return out[out.player_id == SHOOTER].iloc[0]


def test_distance_is_to_the_nearest_defender():
    row = _shooter_row([live_frame(FRAME, away_xy=NEAR_AWAY_XY)])
    assert row.dist_ft == pytest.approx(DEFENDER_GAP_FT)
    assert row.defender_id == NEAREST_DEFENDER
    assert row.eligible


def test_one_row_per_offensive_player_per_frame():
    out = openness(
        to_table([live_frame(FRAME), live_frame(FRAME + 1)]), sides_table([FRAME, FRAME + 1])
    )
    assert len(out) == 10
    assert list(out.columns) == OPENNESS_COLUMNS
    assert set(out.off_team_id) == {HOME}
    assert not set(out.player_id) & set(AWAY_IDS)


def test_high_pred_error_on_offensive_player_is_ineligible():
    row = _shooter_row(
        [live_frame(FRAME, away_xy=NEAR_AWAY_XY, pred_error={SHOOTER: JUST_OVER_GATE})]
    )
    assert not row.eligible
    assert row.dist_ft == pytest.approx(DEFENDER_GAP_FT)


def test_high_pred_error_on_nearest_defender_is_ineligible():
    frame = live_frame(FRAME, away_xy=NEAR_AWAY_XY, pred_error={NEAREST_DEFENDER: JUST_OVER_GATE})
    assert not _shooter_row([frame]).eligible


def test_high_pred_error_on_a_far_defender_does_not_matter():
    far_defender = 15
    frame = live_frame(FRAME, away_xy=NEAR_AWAY_XY, pred_error={far_defender: JUST_OVER_GATE})
    assert _shooter_row([frame]).eligible


def test_threshold_is_inclusive():
    frame = live_frame(FRAME, away_xy=NEAR_AWAY_XY, pred_error={SHOOTER: MAX_PRED_ERROR_FT})
    assert _shooter_row([frame]).eligible


def test_gate_is_a_parameter():
    frame = live_frame(FRAME, away_xy=NEAR_AWAY_XY, pred_error={SHOOTER: JUST_OVER_GATE})
    assert _shooter_row([frame], max_pred_error=JUST_OVER_GATE).eligible


def test_fewer_than_five_a_side_makes_every_row_ineligible():
    frame = live_frame(FRAME, away_xy=NEAR_AWAY_XY[:4])
    out = openness(to_table([frame]), sides_table([FRAME]))
    assert len(out) == 5 and not out.eligible.any()


def test_frame_missing_from_sides_is_dropped():
    out = openness(to_table([live_frame(FRAME), live_frame(FRAME + 1)]), sides_table([FRAME]))
    assert set(out.frame) == {FRAME}


def test_offence_and_defence_follow_the_sides_table():
    out = openness(
        to_table([live_frame(FRAME)]), sides_table([FRAME], off_team=AWAY, def_team=HOME)
    )
    assert set(out.player_id) == set(AWAY_IDS)


def test_short_handed_offence_makes_every_row_ineligible():
    from conftest import DEFAULT_HOME_XY as HOME_XY

    out = openness(to_table([live_frame(FRAME, home_xy=HOME_XY[:4])]), sides_table([FRAME]))
    assert len(out) == 4 and not out.eligible.any()


def test_a_duplicated_player_row_does_not_count_as_a_fifth_player():
    table = to_table([live_frame(FRAME, home_xy=DEFAULT_HOME_XY[:4])])
    duplicate = table[table.player_id == SHOOTER]
    out = openness(pd.concat([table, duplicate], ignore_index=True), sides_table([FRAME]))
    assert len(out) == 4 and not out.eligible.any()


def test_both_teams_can_be_on_offence_in_the_same_frame():
    both = pd.concat([sides_table([FRAME]), sides_table([FRAME], off_team=AWAY, def_team=HOME)])
    out = openness(to_table([live_frame(FRAME)]), both)
    assert len(out) == 10 and set(out.off_team_id) == {HOME, AWAY}
