import numpy as np
import pandas as pd
import pytest
from PIL import Image

from conftest import AWAY, DEFAULT_AWAY_XY, DEFAULT_HOME_XY, GAME, HOME, live_frame, write_game
from coverage_price import cli
from coverage_price.constants import FPS
from coverage_price.loader import load_game, read_ball
from coverage_price.replay import (
    HALF_WIDTH,
    LINK_COLUMNS,
    RENDER_PIXELS,
    REPLAY_COLUMNS,
    REPLAY_OFFSETS,
    canvas,
    court_frames,
    nearest_defender_links,
    render,
    typical_pick,
)

PICK_FRAME = 1000
HANDLER, SCREENER, SCREENER_DEFENDER = 1, 2, 12
SCREENER_EVENT_XY = (-20.0, 4.0)
WINDOW = (-5, 0, 5)


def _game(tmp_path, x_flip):
    """A pick whose event-frame screener position is SCREENER_EVENT_XY. Tracking stores
    y negated, and x negated too when x_flip is -1, as SkillCorner's files do."""
    home_event = (DEFAULT_HOME_XY[0], SCREENER_EVENT_XY, *DEFAULT_HOME_XY[2:])
    to_tracking = lambda pts: tuple((x_flip * x, -y) for x, y in pts)  # noqa: E731
    frames = [
        live_frame(
            PICK_FRAME + o, home_xy=to_tracking(home_event), away_xy=to_tracking(DEFAULT_AWAY_XY)
        )
        for o in WINDOW
    ]
    pick = {
        "id": "pick-1", "frame": PICK_FRAME, "chanceId": "c1", "ballhandlerId": HANDLER,
        "screenerId": SCREENER, "screenerDefId": SCREENER_DEFENDER, "offTeamId": HOME,
        "defTeamId": AWAY, "bhrDefType": "over", "scrDefType": "show",
        "location": list(SCREENER_EVENT_XY),
    }  # fmt: skip
    return write_game(tmp_path, GAME, events={"picks": [pick]}, frames=frames)


def test_read_ball_returns_one_row_per_live_frame(tmp_path):
    game_dir = write_game(tmp_path, GAME, events={}, frames=[live_frame(7)])
    ball = read_ball(game_dir, {7, 8})
    assert list(ball.columns) == ["frame", "x", "y", "z"]
    assert ball.to_dict("records") == [{"frame": 7, "x": 0.0, "y": 0.0, "z": 5.0}]


@pytest.mark.parametrize("x_flip", [1, -1])
def test_court_frames_are_in_the_event_frame_whichever_hoop_is_attacked(tmp_path, x_flip):
    out = court_frames(_game(tmp_path, x_flip), {}, "pick-1", offsets=WINDOW)
    assert list(out.columns) == REPLAY_COLUMNS
    screener = out[(out.role == "screener") & (out.offset == 0)].iloc[0]
    assert (screener.x, screener.y) == pytest.approx(SCREENER_EVENT_XY)
    assert set(out.offset) == set(WINDOW)


def test_court_frames_label_every_role(tmp_path):
    out = court_frames(_game(tmp_path, 1), {}, "pick-1", offsets=(0,))
    roles = out.set_index("player_id").role.to_dict()
    assert roles[HANDLER] == "handler" and roles[SCREENER] == "screener"
    assert roles[SCREENER_DEFENDER] == "screener_defender"
    assert roles[3] == "offence" and roles[13] == "defence" and roles[-1] == "ball"


def test_court_frames_rejects_an_unknown_action(tmp_path):
    with pytest.raises(KeyError, match="pick-404"):
        court_frames(_game(tmp_path, 1), {}, "pick-404")


def test_typical_pick_is_the_one_nearest_the_coverage_median():
    deltas = {"a": 0.1, "b": 1.0, "c": 5.0, "d": -3.0, "e": 1.1}
    rows = [
        {"action_id": k, "kind": "pick", "second_cov": "show", "role": "team_mean", "offset": 25,
         "delta_ft": v, "game_id": 1}
        for k, v in deltas.items()
    ]  # fmt: skip
    other = {**rows[0], "action_id": "z", "second_cov": "drop", "delta_ft": 1.0}
    assert typical_pick(pd.DataFrame([*rows, other]), "show") == "b"


def test_render_writes_an_animation(tmp_path):
    frames = court_frames(_game(tmp_path, 1), {}, "pick-1", offsets=WINDOW)
    path = tmp_path / "clip.gif"
    render(frames, path, title="Show")
    assert path.stat().st_size > 1000


def test_replay_command_writes_a_clip_for_a_named_action(tmp_path):
    game_dir = _game(tmp_path, 1)
    assert load_game(game_dir).game_id == GAME
    out = tmp_path / "clip.gif"
    code = cli.main(
        ["replay", "--data-dir", str(tmp_path), "--action-id", "pick-1", "--out", str(out)]
    )
    assert code == 0 and out.stat().st_size > 1000
    assert np.isfinite(out.stat().st_size)


def test_replay_uses_every_tracking_frame_from_one_second_before_to_three_after():
    assert REPLAY_OFFSETS == tuple(range(-FPS, 3 * FPS + 1))


def _positions(rows):
    return pd.DataFrame(rows, columns=["player_id", "role", "x", "y"]).assign(offset=0)


def test_links_join_each_attacker_to_the_closest_defender():
    near, far = (-10.0, 3.0), (-30.0, -20.0)
    now = _positions([
        (HANDLER, "handler", -10.0, 0.0),
        (SCREENER, "screener", -30.0, -16.0),
        (3, "offence", -10.0, 7.0),
        (SCREENER_DEFENDER, "screener_defender", *near),
        (13, "defence", *far),
    ])  # fmt: skip
    links = nearest_defender_links(now).set_index("player_id")
    assert list(links.reset_index().columns) == LINK_COLUMNS
    assert (links.loc[HANDLER, "defender_x"], links.loc[HANDLER, "defender_y"]) == near
    assert links.loc[HANDLER, "feet"] == pytest.approx(3.0)
    assert (links.loc[SCREENER, "defender_x"], links.loc[SCREENER, "defender_y"]) == far
    assert links.loc[SCREENER, "feet"] == pytest.approx(4.0)
    assert links.loc[3, "feet"] == pytest.approx(4.0)


def test_links_leave_out_the_ball_and_the_defenders():
    now = _positions([
        (HANDLER, "handler", 0.0, 0.0),
        (13, "defence", 1.0, 0.0),
        (-1, "ball", 0.0, 0.5),
    ])  # fmt: skip
    assert list(nearest_defender_links(now).player_id) == [HANDLER]


def test_links_are_empty_when_no_defender_is_tracked():
    now = _positions([(HANDLER, "handler", 0.0, 0.0)])
    links = nearest_defender_links(now)
    assert links.empty and list(links.columns) == LINK_COLUMNS


def test_clock_sits_above_the_court_not_over_it():
    fig, ax, clock = canvas("A typical ball screen against a show")
    clock.set_text("-1.0 s from the screen")
    fig.canvas.draw()
    court_top = ax.transData.transform((0.0, HALF_WIDTH))[1]
    assert clock.get_window_extent().y0 > court_top


def test_render_is_a_full_hd_square(tmp_path):
    frames = court_frames(_game(tmp_path, 1), {}, "pick-1", offsets=WINDOW)
    path = tmp_path / "clip.gif"
    render(frames, path, title="Show")
    with Image.open(path) as clip:
        assert clip.size == (RENDER_PIXELS, RENDER_PIXELS)
