import numpy as np
import pandas as pd
import pytest

from conftest import (
    AWAY,
    DEFAULT_AWAY_XY,
    DEFAULT_HOME_XY,
    GAME,
    HOME,
    live_frame,
    to_table,
)
from coverage_price.actions import ACTION_COLUMNS
from coverage_price.constants import BASELINE_OFFSET, MAX_PRED_ERROR_FT, OFFSETS
from coverage_price.eventstudy import SPACE_COLUMNS as SPACE_COLUMNS_EXPECTED
from coverage_price.eventstudy import frames_needed, sides_for, space_created
from coverage_price.openness import openness

ACTION_FRAME = 1000
MAIN, SECOND, MAIN_DEFENDER = 1, 2, 11
START_GAP_FT, END_GAP_FT = 4.0, 9.0
AFTER = 25
MAIN_XY = DEFAULT_HOME_XY[0]
ROLES = {"main", "second", "other_max", "team_mean"}
# With default positions every offensive player's nearest defender is 20 ft away.
DEFAULT_GAP_FT = 20.0
TOO_NOISY = MAX_PRED_ERROR_FT + 1.0


def _action(**overrides):
    row = {
        "action_id": "pick-1", "kind": "pick", "game_id": GAME, "frame": ACTION_FRAME,
        "main_id": MAIN, "second_id": SECOND, "second_def_id": 12,
        "off_team_id": HOME, "def_team_id": AWAY, "main_cov": "over", "second_cov": "show",
        "chance_id": "chance-1", "end_frame": np.nan, "direct": True,
        "loc_x": np.nan, "loc_y": np.nan,
    }  # fmt: skip
    return pd.DataFrame([{**row, **overrides}], columns=ACTION_COLUMNS)


def _away_with_main_gap(gap_ft):
    return ((MAIN_XY[0] + gap_ft, MAIN_XY[1]), *DEFAULT_AWAY_XY[1:])


def _run(actions, frame_for_offset):
    frames = [frame_for_offset(o) for o in OFFSETS]
    frames = [f for f in frames if f is not None]
    return space_created(actions, openness(to_table(frames), sides_for(actions)))


def _defender_leaves(offset):
    gap = START_GAP_FT if offset <= 0 else END_GAP_FT
    return live_frame(ACTION_FRAME + offset, away_xy=_away_with_main_gap(gap))


def _static(offset):
    return live_frame(ACTION_FRAME + offset)


def test_frames_needed_and_sides_cover_every_offset():
    actions = _action()
    expected = {ACTION_FRAME + o for o in OFFSETS}
    assert frames_needed(actions) == expected
    sides = sides_for(actions)
    assert set(sides.frame) == expected
    assert set(sides.off_team_id) == {HOME} and set(sides.def_team_id) == {AWAY}


def test_defender_leaving_gives_positive_space_created():
    out = _run(_action(), _defender_leaves)
    row = out[(out.role == "main") & (out.offset == AFTER)].iloc[0]
    assert row.baseline_ft == pytest.approx(START_GAP_FT)
    assert row.delta_ft == pytest.approx(END_GAP_FT - START_GAP_FT)
    assert (row.kind, row.main_cov, row.second_cov, row.game_id) == ("pick", "over", "show", GAME)


def test_static_players_give_zero_for_every_role_and_offset():
    out = _run(_action(), _static)
    assert set(out.role) == ROLES
    assert len(out) == len(ROLES) * len(OFFSETS)
    assert out.delta_ft.abs().max() == pytest.approx(0.0)
    assert out.baseline_ft.unique() == pytest.approx([DEFAULT_GAP_FT])


def test_main_player_missing_at_baseline_drops_main_role_only():
    def frame(offset):
        if offset != BASELINE_OFFSET:
            return _static(offset)
        return live_frame(ACTION_FRAME + offset, pred_error={MAIN: TOO_NOISY})

    out = _run(_action(), frame)
    assert "main" not in set(out.role)
    assert "second" in set(out.role)
    # team_mean needs every player eligible at the baseline, so it drops too.
    assert "team_mean" not in set(out.role)


def test_ineligible_offset_is_missing_not_zero():
    def frame(offset):
        if offset != AFTER:
            return _static(offset)
        return live_frame(ACTION_FRAME + offset, pred_error={MAIN: TOO_NOISY})

    out = _run(_action(), frame)
    main = out[out.role == "main"]
    assert AFTER not in set(main.offset)
    assert len(main) == len(OFFSETS) - 1


def test_dead_frame_inside_the_window_removes_that_offset_for_every_role():
    out = _run(_action(), lambda o: None if o == AFTER else _static(o))
    assert AFTER not in set(out.offset)
    assert set(out.role) == ROLES


def test_second_role_absent_when_action_has_no_second_player():
    out = _run(_action(kind="drive", second_id=np.nan), _static)
    assert set(out.role) == ROLES - {"second"}


def test_other_max_excludes_main_and_second():
    # The defenders of the main and second players both move away; the other three
    # offensive players stay at DEFAULT_GAP_FT.
    def frame(offset):
        extra = 0.0 if offset <= 0 else 15.0
        away = (
            (DEFAULT_AWAY_XY[0][0] + extra, DEFAULT_AWAY_XY[0][1]),
            (DEFAULT_AWAY_XY[1][0] + extra, DEFAULT_AWAY_XY[1][1]),
            *DEFAULT_AWAY_XY[2:],
        )
        return live_frame(ACTION_FRAME + offset, away_xy=away)

    out = _run(_action(), frame)
    other = out[(out.role == "other_max") & (out.offset == AFTER)].iloc[0]
    main = out[(out.role == "main") & (out.offset == AFTER)].iloc[0]
    second = out[(out.role == "second") & (out.offset == AFTER)].iloc[0]
    assert other.delta_ft == pytest.approx(0.0)
    assert main.delta_ft > 0 and second.delta_ft > 0


def test_control_moment_has_team_roles_only():
    out = _run(_action(kind="control", main_id=np.nan, second_id=np.nan), _static)
    assert set(out.role) == {"other_max", "team_mean"}


# ---- summaries -------------------------------------------------------------------------

from coverage_price.eventstudy import gap_between, permutation_p, summarise  # noqa: E402

N_GAMES, PER_LABEL_PER_GAME = 4, 50
PLANTED_GAP_FT = 2.0
NOISE_SD_FT = 1.5
THIN_LABEL, THIN_COUNT = "blitz", 3


def _space(gap_ft, seed=0, thin=False):
    """One role, one offset: `show` and `drop` actions in N_GAMES games, `show` higher by gap_ft."""
    rng = np.random.default_rng(seed)
    rows = []
    for game in range(N_GAMES):
        for label, shift in (("show", gap_ft), ("drop", 0.0)):
            for delta in rng.normal(shift, NOISE_SD_FT, PER_LABEL_PER_GAME):
                rows.append(
                    {"game_id": game, "second_cov": label, "delta_ft": delta, "baseline_ft": 6.0}
                )
    if thin:
        rows += [
            {"game_id": 0, "second_cov": THIN_LABEL, "delta_ft": 1.0, "baseline_ft": 6.0}
        ] * THIN_COUNT
    return pd.DataFrame(rows)


def test_summarise_reports_thin_groups_with_count_and_empty_range():
    row = (
        summarise(_space(PLANTED_GAP_FT, thin=True), by=["second_cov"])
        .set_index("second_cov")
        .loc[THIN_LABEL]
    )
    assert row.n == THIN_COUNT and row.n_games == 1
    assert row.mean_delta_ft == pytest.approx(1.0)
    assert np.isnan(row.lo) and np.isnan(row.hi)


def test_summarise_range_contains_mean_for_a_well_populated_group():
    table = summarise(_space(PLANTED_GAP_FT), by=["second_cov"]).set_index("second_cov")
    show = table.loc["show"]
    assert show.n == N_GAMES * PER_LABEL_PER_GAME and show.n_games == N_GAMES
    assert show.lo < show.mean_delta_ft < show.hi
    assert show.mean_delta_ft == pytest.approx(PLANTED_GAP_FT, abs=0.4)
    assert show.mean_baseline_ft == pytest.approx(6.0)


def test_gap_between_recovers_planted_gap_and_counts_games_with_the_same_sign():
    out = gap_between(_space(PLANTED_GAP_FT), "second_cov", "show", "drop")
    assert out["gap_ft"] == pytest.approx(PLANTED_GAP_FT, abs=0.4)
    assert out["lo"] < out["gap_ft"] < out["hi"] and out["lo"] > 0
    assert out["games_same_sign"] == N_GAMES and out["n_games"] == N_GAMES


def test_gap_between_ignores_games_missing_one_label_when_counting_signs():
    space = _space(PLANTED_GAP_FT)
    space = space[~((space.game_id == 0) & (space.second_cov == "drop"))]
    out = gap_between(space, "second_cov", "show", "drop")
    assert out["n_games"] == N_GAMES - 1 and out["games_same_sign"] == N_GAMES - 1


def test_permutation_p_is_small_for_a_planted_difference():
    assert permutation_p(_space(PLANTED_GAP_FT), "second_cov", n_perm=500) < 0.01


def test_permutation_p_is_not_small_for_identical_groups():
    assert permutation_p(_space(0.0), "second_cov", n_perm=500) > 0.05


def test_permutation_p_drops_thin_labels_and_is_nan_with_one_label_left():
    one_label = _space(PLANTED_GAP_FT, thin=True)
    one_label = one_label[one_label.second_cov != "drop"]
    assert np.isnan(permutation_p(one_label, "second_cov", n_perm=100))


def test_summaries_are_reproducible_for_a_seed():
    space = _space(PLANTED_GAP_FT)
    assert summarise(space, ["second_cov"], seed=3).equals(summarise(space, ["second_cov"], seed=3))
    assert permutation_p(space, "second_cov", n_perm=200, seed=3) == permutation_p(
        space, "second_cov", n_perm=200, seed=3
    )


GAME_EFFECT_SD_FT, TINY_NOISE_FT = 2.0, 0.01


def _space_with_game_effects(confound_label_with_game=False, seed=0):
    """Games differ a lot from each other; actions within a game barely differ."""
    rng = np.random.default_rng(seed)
    rows = []
    for game, effect in enumerate(rng.normal(0.0, GAME_EFFECT_SD_FT, 8)):
        labels = ("show",) if game % 2 else ("drop",)
        labels = labels if confound_label_with_game else ("show", "drop")
        for label in labels:
            for delta in rng.normal(effect, TINY_NOISE_FT, PER_LABEL_PER_GAME):
                rows.append(
                    {"game_id": game, "second_cov": label, "delta_ft": delta, "baseline_ft": 6.0}
                )
    return pd.DataFrame(rows)


def test_summarise_range_reflects_differences_between_games_not_action_count():
    space = _space_with_game_effects().assign(everything="all")
    row = summarise(space, by=["everything"]).iloc[0]
    action_level_se = space.delta_ft.std() / np.sqrt(len(space))
    assert (row.hi - row.lo) > 5 * (2 * 1.96 * action_level_se)


def test_permutation_p_ignores_label_differences_that_are_really_game_differences():
    # Each game has one label only, so within-game shuffling can never reproduce a gap.
    space = _space_with_game_effects(confound_label_with_game=True)
    assert permutation_p(space, "second_cov", n_perm=300) > 0.5


# ---- windows stop at the end of the chance ---------------------------------------------

CHANCE_ENDS_AFTER = 30  # frames after the action


def test_offsets_after_the_chance_ends_are_dropped():
    out = _run(_action(end_frame=ACTION_FRAME + CHANCE_ENDS_AFTER), _static)
    assert out.offset.max() == CHANCE_ENDS_AFTER
    assert set(out.role) == ROLES


def test_unknown_chance_end_keeps_the_full_window():
    out = _run(_action(end_frame=np.nan), _static)
    assert out.offset.max() == max(OFFSETS)


def test_main_player_absent_from_tracking_gives_no_rows_and_no_error():
    from conftest import DEFAULT_HOME_XY as HOME_XY

    # The main player (id 1) is not tracked at all, so every frame is short-handed.
    out = _run(
        _action(),
        lambda o: live_frame(ACTION_FRAME + o, home_xy=((999.0, 999.0), *HOME_XY[1:])[1:]),
    )
    assert out.empty and list(out.columns) == list(SPACE_COLUMNS_EXPECTED)


def test_two_teams_acting_in_the_same_frame_each_get_their_own_openness():
    ours = _action()
    theirs = _action(
        action_id="pick-2", main_id=11, second_id=12, off_team_id=AWAY, def_team_id=HOME
    )
    actions = pd.concat([ours, theirs], ignore_index=True)
    # Home's defenders are 20 ft away; shift one away player so away's team mean differs.
    away_xy = ((DEFAULT_AWAY_XY[0][0] + 10.0, DEFAULT_AWAY_XY[0][1]), *DEFAULT_AWAY_XY[1:])
    frames = [live_frame(ACTION_FRAME + o, away_xy=away_xy) for o in OFFSETS]
    out = space_created(actions, openness(to_table(frames), sides_for(actions)))
    base = out[out.role == "team_mean"].groupby("action_id").baseline_ft.first()
    assert base["pick-1"] != pytest.approx(base["pick-2"])
    assert set(out.action_id) == {"pick-1", "pick-2"}
