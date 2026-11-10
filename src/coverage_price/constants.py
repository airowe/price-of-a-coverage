"""Fixed quantities shared across modules. Distances are in feet."""

FPS = 25
# FIBA court: 28 m long, hoop centre 1.575 m from the baseline. In SkillCorner's
# normalised event frame the offensive hoop is on the negative-x side.
HOOP_XY = (-40.76, 0.0)
# Frames relative to an action at which openness is sampled: -1.0 s to +3.0 s, every 0.2 s.
OFFSETS = tuple(range(-25, 80, 5))
BASELINE_OFFSET = -15
MAX_PRED_ERROR_FT = 3.0
MIN_PLAYERS_PER_SIDE = 5
# SkillCorner label -> name used in every output.
COVERAGE_NAMES = {"soft": "drop"}
