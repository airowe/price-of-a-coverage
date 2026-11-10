"""Redraw one action from the tracking as moving dots on a half court."""

from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import animation, patches  # noqa: E402

from coverage_price.actions import collect_actions  # noqa: E402
from coverage_price.constants import FPS, HOOP_XY  # noqa: E402
from coverage_price.depth import x_sign  # noqa: E402
from coverage_price.loader import load_events, load_game, read_ball, read_frames  # noqa: E402

REPLAY_COLUMNS = ["offset", "player_id", "role", "x", "y"]
REPLAY_OFFSETS = tuple(range(-25, 76, 2))  # -1 s to +3 s at 12.5 frames a second
BALL_ID = -1
# FIBA half court in feet: 28 m x 15 m court, 4.9 m x 5.8 m key, 6.75 m arc, 0.9 m corners.
BASELINE_X, HALF_WIDTH = -45.93, 24.61
KEY_HALF_WIDTH, KEY_LENGTH = 8.04, 19.03
ARC_RADIUS, CORNER_Y = 22.15, 21.65
_STYLE = {  # role -> (colour, size, label)
    "handler": ("#c2410c", 150, "Ball handler"),
    "screener": ("#f59e0b", 150, "Screener"),
    "offence": ("#fdba74", 90, "Offence"),
    "screener_defender": ("#1d4ed8", 150, "Screener's defender"),
    "defence": ("#93c5fd", 90, "Defence"),
    "ball": ("#111827", 35, "Ball"),
}


def typical_pick(
    space: pd.DataFrame, coverage: str, role: str = "team_mean", offset: int = 25
) -> str:
    """The pick whose space created is nearest the median for its coverage: a
    representative example, not a flattering one."""
    cell = space[
        (space.kind == "pick")
        & (space.second_cov == coverage)
        & (space.role == role)
        & (space.offset == offset)
    ]
    if cell.empty:
        raise KeyError(f"no picks with coverage {coverage!r}")
    return str(cell.loc[(cell.delta_ft - cell.delta_ft.median()).abs().idxmin(), "action_id"])


def court_frames(
    game_dir: Path,
    aliases: dict[int, int],
    action_id: str,
    offsets: Sequence[int] = REPLAY_OFFSETS,
) -> pd.DataFrame:
    """Player and ball positions around one action, in the event frame (offensive hoop
    on the negative-x side), one row per player per offset."""
    game = load_game(game_dir)
    actions = collect_actions(load_events(game_dir, aliases), game.game_id)
    match = actions[actions.action_id == action_id]
    if match.empty:
        raise KeyError(action_id)
    action = match.iloc[0]
    wanted = {int(action.frame) + o: o for o in offsets}
    players = read_frames(game_dir, game, wanted.keys(), aliases)
    ball = read_ball(game_dir, wanted.keys()).assign(player_id=BALL_ID, team_id=-1)
    at_action = players[(players.frame == action.frame) & (players.player_id == action.second_id)]
    flip = 1
    if not at_action.empty and not pd.isna(action.loc_x):
        flip = x_sign(at_action.x.iloc[0], action.loc_x)

    named = {action.main_id: "handler", action.second_id: "screener", action.second_def_id: "screener_defender"}  # fmt: skip
    table = pd.concat([players, ball], ignore_index=True)
    team_role = np.where(table.team_id == action.off_team_id, "offence", "defence")
    table["role"] = np.where(table.player_id == BALL_ID, "ball", team_role)
    table["role"] = table.player_id.map(named).fillna(table.role)
    table["offset"] = table.frame.map(wanted)
    table["x"], table["y"] = flip * table.x, -table.y  # tracking y is the event y negated
    return table[REPLAY_COLUMNS].sort_values(["offset", "player_id"]).reset_index(drop=True)


def _draw_court(ax) -> None:
    line = {"color": "#6b7280", "lw": 1.2, "fill": False}
    ax.add_patch(patches.Rectangle((BASELINE_X, -HALF_WIDTH), -BASELINE_X, 2 * HALF_WIDTH, **line))
    ax.add_patch(
        patches.Rectangle((BASELINE_X, -KEY_HALF_WIDTH), KEY_LENGTH, 2 * KEY_HALF_WIDTH, **line)
    )
    ax.add_patch(patches.Circle(HOOP_XY, 0.75, color="#c2410c", lw=1.5, fill=False))
    corner = np.degrees(np.arcsin(CORNER_Y / ARC_RADIUS))
    ax.add_patch(patches.Arc(HOOP_XY, 2 * ARC_RADIUS, 2 * ARC_RADIUS, theta1=-corner, theta2=corner,
                             color="#6b7280", lw=1.2))  # fmt: skip
    arc_start_x = HOOP_XY[0] + np.sqrt(ARC_RADIUS**2 - CORNER_Y**2)
    for y in (-CORNER_Y, CORNER_Y):
        ax.plot([BASELINE_X, arc_start_x], [y, y], color="#6b7280", lw=1.2)
    ax.set_xlim(BASELINE_X - 2, 4)
    ax.set_ylim(-HALF_WIDTH - 2, HALF_WIDTH + 2)
    ax.set_aspect("equal")
    ax.axis("off")


def render(frames: pd.DataFrame, path: Path, title: str = "") -> None:
    """Write the clip as a GIF, or an MP4 if `path` ends in .mp4 (needs ffmpeg)."""
    offsets = sorted(frames.offset.unique())
    step = int(np.median(np.diff(offsets))) if len(offsets) > 1 else 1
    fig, ax = plt.subplots(figsize=(6.4, 6.4))
    _draw_court(ax)
    dots = {
        role: ax.scatter([], [], s=size, color=colour, label=label, zorder=3, edgecolors="white")
        for role, (colour, size, label) in _STYLE.items()
    }
    clock = ax.text(0.5, 0.97, "", transform=ax.transAxes, fontsize=12, ha="center", va="top")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=3, frameon=False, fontsize=9)
    ax.set_title(title)

    def draw(offset):
        now = frames[frames.offset == offset]
        for role, dot in dots.items():
            dot.set_offsets(now.loc[now.role == role, ["x", "y"]].to_numpy().reshape(-1, 2))
        seconds = offset / FPS + 0.0  # avoid "-0.0"
        clock.set_text(f"{seconds:+.1f} s from the screen")
        return [*dots.values(), clock]

    clip = animation.FuncAnimation(fig, draw, frames=offsets, blit=False)
    fps = FPS / step
    writer = (
        animation.FFMpegWriter(fps=fps)
        if str(path).endswith(".mp4")
        else animation.PillowWriter(fps=fps)
    )
    clip.save(path, writer=writer, dpi=110)
    plt.close(fig)
