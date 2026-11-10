import pytest

from conftest import AWAY, GAME, HOME, dead_frame, live_frame, write_game
from coverage_price.loader import (
    DataNotDownloadedError,
    list_games,
    load_aliases,
    load_events,
    load_game,
    read_frames,
)

PLAYERS_PER_FRAME = 10


def test_load_game_reads_team_ids_and_players(tmp_path):
    game_dir = write_game(tmp_path, GAME, events={}, frames=[])
    game = load_game(game_dir)
    assert (game.game_id, game.home_team_id, game.away_team_id) == (GAME, HOME, AWAY)
    assert set(game.players.columns) == {"player_id", "team_id", "name", "jersey"}
    assert len(game.players) == PLAYERS_PER_FRAME


def test_load_events_returns_one_table_per_family_and_applies_aliases(tmp_path):
    duplicate, canonical = 501, 500
    events = {
        "picks": [{"id": "pick-1", "frame": 100, "ballhandlerId": duplicate, "screenerId": 7}],
        "shots": [],
    }
    game_dir = write_game(tmp_path, GAME, events=events, frames=[])
    tables = load_events(game_dir, aliases={duplicate: canonical})
    assert tables["picks"].loc[0, "ballhandlerId"] == canonical
    assert tables["picks"].loc[0, "screenerId"] == 7
    assert tables["shots"].empty


def test_load_events_keeps_null_player_ids_null(tmp_path):
    events = {"shots": [{"id": "s1", "shooterId": 1, "blockerId": None}]}
    game_dir = write_game(tmp_path, GAME, events=events, frames=[])
    tables = load_events(game_dir, aliases={1: 2})
    assert tables["shots"].loc[0, "shooterId"] == 2
    assert tables["shots"]["blockerId"].isna().all()


def test_list_games_is_sorted(tmp_path):
    later, earlier = 200, 100
    write_game(tmp_path, later, events={}, frames=[])
    write_game(tmp_path, earlier, events={}, frames=[])
    assert [p.name for p in list_games(tmp_path)] == [str(earlier), str(later)]


def test_load_aliases_maps_duplicate_to_canonical(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "player_id_aliases.csv").write_text(
        "player_id,player_name,canonical_player_id,canonical_player_name,acb_player_id\n"
        "59237,Nihad Dedovic,59129,Nihad Djedovic,1\n"
        "59129,Nihad Djedovic,59129,Nihad Djedovic,1\n"
    )
    assert load_aliases(tmp_path) == {59237: 59129}


def test_load_aliases_is_empty_when_file_is_absent(tmp_path):
    assert load_aliases(tmp_path) == {}


def test_read_frames_returns_only_requested_live_frames(tmp_path):
    live, dead, unrequested = 100, 101, 102
    frames = [live_frame(live), dead_frame(dead), live_frame(unrequested)]
    game_dir = write_game(tmp_path, GAME, events={}, frames=frames)
    out = read_frames(game_dir, load_game(game_dir), {live, dead})
    assert set(out.frame) == {live}
    assert len(out) == PLAYERS_PER_FRAME
    assert out.is_detected.dtype == bool
    assert set(out.team_id) == {HOME, AWAY}
    assert list(out.columns) == [
        "frame", "team_id", "player_id", "x", "y", "pred_error", "is_detected",
    ]  # fmt: skip


def test_read_frames_applies_aliases(tmp_path):
    frame_idx, duplicate, canonical = 100, 1, 77
    game_dir = write_game(tmp_path, GAME, events={}, frames=[live_frame(frame_idx)])
    out = read_frames(game_dir, load_game(game_dir), {frame_idx}, aliases={duplicate: canonical})
    assert canonical in set(out.player_id) and duplicate not in set(out.player_id)


def test_read_frames_with_no_matching_frames_returns_empty_table_with_columns(tmp_path):
    game_dir = write_game(tmp_path, GAME, events={}, frames=[live_frame(5)])
    out = read_frames(game_dir, load_game(game_dir), {6})
    assert out.empty and "pred_error" in out.columns


def test_read_frames_raises_clear_error_on_lfs_pointer(tmp_path):
    game_dir = write_game(tmp_path, GAME, events={}, frames=[])
    pointer = "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n"
    (game_dir / f"{GAME}_tracking_data.jsonl.gz").write_text(pointer)
    with pytest.raises(DataNotDownloadedError, match="download_data.sh"):
        read_frames(game_dir, load_game(game_dir), {1})
