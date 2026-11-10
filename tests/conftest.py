"""Synthetic SkillCorner-shaped games for tests."""

import gzip
import json
from pathlib import Path

HOME, AWAY, GAME = 10, 20, 999
HOME_IDS = (1, 2, 3, 4, 5)
AWAY_IDS = (11, 12, 13, 14, 15)
DEFAULT_PRED_ERROR = 1.0
# Players spread 10 ft apart; each away player stands 20 ft from its home counterpart.
DEFAULT_HOME_XY = tuple((-30.0, -20.0 + 10.0 * i) for i in range(5))
DEFAULT_AWAY_XY = tuple((-10.0, -20.0 + 10.0 * i) for i in range(5))


def _players(ids, xy, pred_error):
    return [
        {
            "xyz": [x, y, 0.0],
            "speed": 0.0,
            "jersey": str(pid),
            "playerId": pid,
            "isDetected": 1,
            "predError": pred_error.get(pid, DEFAULT_PRED_ERROR)
            if isinstance(pred_error, dict)
            else pred_error,
        }
        for pid, (x, y) in zip(ids, xy, strict=False)
    ]


def live_frame(frame_idx, home_xy=None, away_xy=None, pred_error=DEFAULT_PRED_ERROR):
    """One tracking frame. `pred_error` is a float or a {player_id: error} dict."""
    return {
        "frameIdx": frame_idx,
        "wallClock": frame_idx * 40,
        "gameClock": 600.0,
        "gameClockStopped": False,
        "period": 1,
        "homePlayers": _players(HOME_IDS, home_xy or DEFAULT_HOME_XY, pred_error),
        "awayPlayers": _players(AWAY_IDS, away_xy or DEFAULT_AWAY_XY, pred_error),
        "ball": {"xyz": [0.0, 0.0, 5.0], "speed": 0.0, "isDetected": 1.0, "predError": 1.0},
        "shotClock": 20.0,
    }


def dead_frame(frame_idx):
    frame = live_frame(frame_idx)
    frame.update(homePlayers=[], awayPlayers=[], ball={})
    return frame


def _roster(team_id, ids):
    return {
        "teamId": team_id,
        "teamName": f"Team {team_id}",
        "players": [
            {"playerId": p, "firstName": "P", "lastName": str(p), "jersey": str(p)} for p in ids
        ],
    }


def write_game(root: Path, game_id: int, events: dict, frames: list[dict]) -> Path:
    """Write a miniature game folder in SkillCorner's layout; returns the game folder."""
    game_dir = root / "data" / "matches" / str(game_id)
    game_dir.mkdir(parents=True)
    meta = {
        "gameId": game_id,
        "homeTeam": _roster(HOME, HOME_IDS),
        "awayTeam": _roster(AWAY, AWAY_IDS),
    }
    (game_dir / f"{game_id}_game_data.json").write_text(json.dumps(meta))
    (game_dir / f"{game_id}_dynamic_events.json").write_text(json.dumps(events))
    with gzip.open(game_dir / f"{game_id}_tracking_data.jsonl.gz", "wt") as fh:
        for frame in frames:
            fh.write(json.dumps(frame) + "\n")
    return game_dir


def to_table(frames: list[dict]):
    """The long frame table `loader.read_frames` would return for these frame dicts."""
    import pandas as pd

    from coverage_price.loader import FRAME_COLUMNS

    rows = [
        (f["frameIdx"], team, p["playerId"], p["xyz"][0], p["xyz"][1], p["predError"], True)
        for f in frames
        for key, team in (("homePlayers", HOME), ("awayPlayers", AWAY))
        for p in f[key]
    ]
    return pd.DataFrame(rows, columns=FRAME_COLUMNS)


def sides_table(frame_ids, off_team=HOME, def_team=AWAY):
    import pandas as pd

    return pd.DataFrame(
        {"frame": list(frame_ids), "off_team_id": off_team, "def_team_id": def_team}
    )
