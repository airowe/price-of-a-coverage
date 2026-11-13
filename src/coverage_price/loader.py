"""Read SkillCorner basketball open-data files into tables."""

import gzip
import json
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PLAYER_ID_COLUMNS = frozenset({
    "shooterId", "passerId", "blockerId", "closestDefId", "ballhandlerId", "screenerId",
    "ballhandlerDefId", "screenerDefId", "setterId", "receiverId", "setterDefId",
    "receiverDefId", "cutterId", "cutterDefId", "playerId", "defenderId",
})  # fmt: skip
PLAYER_LIST_COLUMNS = frozenset({"offPlayerIds", "defPlayerIds"})
FRAME_COLUMNS = ["frame", "team_id", "player_id", "x", "y", "pred_error", "is_detected"]
_GZIP_MAGIC = b"\x1f\x8b"
_FRAME_KEY = '"frameIdx":'


class DataNotDownloadedError(RuntimeError):
    """A tracking file is missing or is still a Git LFS pointer."""


@dataclass(frozen=True)
class Game:
    game_id: int
    home_team_id: int
    away_team_id: int
    players: pd.DataFrame


def list_games(data_dir: Path) -> list[Path]:
    """Game folders under `data_dir/data/matches`, ascending by game id."""
    matches = Path(data_dir) / "data" / "matches"
    return sorted((p for p in matches.iterdir() if p.is_dir()), key=lambda p: int(p.name))


def load_aliases(data_dir: Path) -> dict[int, int]:
    """Duplicate player id -> canonical player id. Empty when the file is absent."""
    path = Path(data_dir) / "data" / "player_id_aliases.csv"
    if not path.exists():
        return {}
    table = pd.read_csv(path)
    changed = table[table.player_id != table.canonical_player_id]
    return dict(
        zip(changed.player_id.astype(int), changed.canonical_player_id.astype(int), strict=True)
    )


def load_game(game_dir: Path) -> Game:
    game_dir = Path(game_dir)
    meta = json.loads((game_dir / f"{game_dir.name}_game_data.json").read_text())
    rows = [
        {
            "player_id": p["playerId"],
            "team_id": meta[side]["teamId"],
            "name": f"{p.get('firstName', '')} {p.get('lastName', '')}".strip(),
            "jersey": p.get("jersey"),
        }
        for side in ("homeTeam", "awayTeam")
        for p in meta[side]["players"]
    ]
    return Game(
        game_id=int(meta["gameId"]),
        home_team_id=int(meta["homeTeam"]["teamId"]),
        away_team_id=int(meta["awayTeam"]["teamId"]),
        players=pd.DataFrame(rows, columns=["player_id", "team_id", "name", "jersey"]),
    )


def load_events(game_dir: Path, aliases: dict[int, int] | None = None) -> dict[str, pd.DataFrame]:
    """One table per event family, keyed as in the JSON, with player ids de-duplicated."""
    game_dir = Path(game_dir)
    raw = json.loads((game_dir / f"{game_dir.name}_dynamic_events.json").read_text())
    tables = {family: pd.DataFrame(records) for family, records in raw.items()}
    if aliases:
        for table in tables.values():
            for column in PLAYER_ID_COLUMNS.intersection(table.columns):
                table[column] = table[column].map(lambda v: aliases.get(v, v))
            for column in PLAYER_LIST_COLUMNS.intersection(table.columns):
                table[column] = table[column].map(
                    lambda ids: [aliases.get(v, v) for v in ids] if isinstance(ids, list) else ids
                )
    return tables


def _requested_frames(game_dir: Path, frame_ids: Collection[int]):
    """Yield the parsed tracking frames whose index is in `frame_ids`.

    Only requested lines are parsed: a game is 30-46 MB compressed, mostly unneeded.
    """
    game_dir = Path(game_dir)
    path = game_dir / f"{game_dir.name}_tracking_data.jsonl.gz"
    if not path.exists() or path.open("rb").read(len(_GZIP_MAGIC)) != _GZIP_MAGIC:
        raise DataNotDownloadedError(
            f"{path} is missing or is a Git LFS pointer. Run scripts/download_data.sh "
            "to fetch the tracking files."
        )
    wanted = set(frame_ids)
    with gzip.open(path, "rt") as fh:
        for line in fh:
            start = line.find(_FRAME_KEY)
            if start >= 0 and int(line[start + len(_FRAME_KEY) : line.find(",", start)]) in wanted:
                yield json.loads(line)


def read_frames(
    game_dir: Path,
    game: Game,
    frame_ids: Collection[int],
    aliases: dict[int, int] | None = None,
) -> pd.DataFrame:
    """Long table of tracked players for the requested live frames.

    Frames with no players on either side (dead ball) are omitted.
    """
    aliases, rows = aliases or {}, []
    sides = (("homePlayers", game.home_team_id), ("awayPlayers", game.away_team_id))
    for frame in _requested_frames(game_dir, frame_ids):
        if not frame["homePlayers"] or not frame["awayPlayers"]:
            continue
        for key, team_id in sides:
            for p in frame[key]:
                rows.append((
                    frame["frameIdx"], team_id, aliases.get(p["playerId"], p["playerId"]),
                    p["xyz"][0], p["xyz"][1], p["predError"], bool(p["isDetected"]),
                ))  # fmt: skip
    return pd.DataFrame(rows, columns=FRAME_COLUMNS).astype({"is_detected": bool})


def read_ball(game_dir: Path, frame_ids: Collection[int]) -> pd.DataFrame:
    """Ball position for the requested live frames: frame, x, y, z (feet)."""
    rows = [
        (frame["frameIdx"], *frame["ball"]["xyz"])
        for frame in _requested_frames(game_dir, frame_ids)
        if frame.get("ball")
    ]
    return pd.DataFrame(rows, columns=["frame", "x", "y", "z"])
