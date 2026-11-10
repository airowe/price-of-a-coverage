import numpy as np
import pandas as pd
import pytest

from conftest import DEFAULT_AWAY_XY, DEFAULT_HOME_XY, live_frame, to_table
from coverage_price.constants import MAX_PRED_ERROR_FT
from coverage_price.depth import screener_defender_depth, x_sign

FRAME = 1000
HANDLER, SCREENER, SCREENER_DEFENDER = 1, 2, 12
DROP_FT = 6.0
HANDLER_XY = (-15.0, 0.0)
SCREENER_XY = (-20.0, 0.0)  # on the hoop's centre line, so "toward the hoop" is -x


def _picks(loc=SCREENER_XY, screener_def=SCREENER_DEFENDER):
    return pd.DataFrame([{
        "action_id": "pick-1", "frame": FRAME, "main_id": HANDLER, "second_id": SCREENER,
        "second_def_id": screener_def, "loc_x": loc[0], "loc_y": loc[1],
    }])  # fmt: skip


def _frames(defender_xy, x_flip=1, pred_error=1.0, handler_xy=HANDLER_XY):
    """Tracking for a pick described in the event frame. As in SkillCorner's data,
    tracking y is the event y negated; x is negated too when `x_flip` is -1."""
    home = (handler_xy, SCREENER_XY, *DEFAULT_HOME_XY[2:])
    away = (DEFAULT_AWAY_XY[0], defender_xy, *DEFAULT_AWAY_XY[2:])
    home = tuple((x_flip * x, -y) for x, y in home)
    away = tuple((x_flip * x, -y) for x, y in away)
    return to_table([live_frame(FRAME, home_xy=home, away_xy=away, pred_error=pred_error)])


def test_x_sign_is_plus_when_tracking_and_event_agree_on_the_side_of_the_court():
    assert x_sign(tracked_x=-20.0, event_x=-20.3) == 1


def test_x_sign_is_minus_when_tracking_is_on_the_other_side():
    assert x_sign(tracked_x=20.0, event_x=-20.3) == -1


def test_defender_between_screener_and_hoop_has_positive_depth():
    table, skipped = screener_defender_depth(_picks(), _frames((SCREENER_XY[0] - DROP_FT, 0.0)))
    assert list(table.columns) == ["action_id", "depth_ft"]
    assert table.depth_ft.iloc[0] == pytest.approx(DROP_FT)
    assert sum(skipped.values()) == 0


@pytest.mark.parametrize("x_flip", [1, -1])
def test_depth_is_the_same_whichever_hoop_the_offence_attacks(x_flip):
    table, _ = screener_defender_depth(
        _picks(), _frames((SCREENER_XY[0] - DROP_FT, 0.0), x_flip=x_flip)
    )
    assert table.depth_ft.iloc[0] == pytest.approx(DROP_FT)


@pytest.mark.parametrize("x_flip", [1, -1])
def test_handler_far_out_on_the_wing_does_not_flip_the_orientation(x_flip):
    # Regression: orientation used to be matched on the ball handler with a point
    # reflection, which chose the wrong side when the handler's |y| exceeded |x|.
    wing_handler = (-3.0, 22.0)
    frames = _frames((SCREENER_XY[0] - DROP_FT, 0.0), x_flip=x_flip, handler_xy=wing_handler)
    table, _ = screener_defender_depth(_picks(), frames)
    assert table.depth_ft.iloc[0] == pytest.approx(DROP_FT)


def test_defender_above_the_screen_has_negative_depth():
    step_out_ft = 3.0
    table, _ = screener_defender_depth(_picks(), _frames((SCREENER_XY[0] + step_out_ft, 0.0)))
    assert table.depth_ft.iloc[0] == pytest.approx(-step_out_ft)


def test_sideways_offset_does_not_count_as_depth():
    table, _ = screener_defender_depth(_picks(), _frames((SCREENER_XY[0], 5.0)))
    assert table.depth_ft.iloc[0] == pytest.approx(0.0)


def test_null_location_is_skipped_and_counted():
    table, skipped = screener_defender_depth(
        _picks(loc=(np.nan, np.nan)), _frames((SCREENER_XY[0] - DROP_FT, 0.0))
    )
    assert table.empty and skipped["null_location"] == 1


def test_untracked_or_unknown_defender_is_skipped_and_counted():
    frames = _frames((SCREENER_XY[0] - DROP_FT, 0.0))
    absent_player = 99
    table, skipped = screener_defender_depth(_picks(screener_def=absent_player), frames)
    assert table.empty and skipped["player_not_tracked"] == 1
    table, skipped = screener_defender_depth(_picks(screener_def=np.nan), frames)
    assert table.empty and skipped["player_not_tracked"] == 1


def test_noisy_tracking_is_skipped_and_counted():
    frames = _frames(
        (SCREENER_XY[0] - DROP_FT, 0.0), pred_error={SCREENER_DEFENDER: MAX_PRED_ERROR_FT + 1}
    )
    table, skipped = screener_defender_depth(_picks(), frames)
    assert table.empty and skipped["ineligible"] == 1
