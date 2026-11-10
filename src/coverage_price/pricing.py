"""Season value of each ball-screen coverage, from SkillCorner's pick aggregates.

Limits of the source: only picks that led directly to a shot, assist or foul are
counted (about half of all picks), the data is offense-only, and a handler's coverage
cannot be crossed with the screener's.
"""

import numpy as np
import pandas as pd

from coverage_price.constants import COVERAGE_NAMES

HANDLER_COVERAGES = ("over", "under", "switch", "ice", "blitz")
SCREENER_COVERAGES = ("soft", "show", "switch", "ice", "blitz")
PRICE_COLUMNS = [
    "role", "coverage", "picks", "points_per_pick", "score_rate", "assist_rate", "turnover_rate",
]  # fmt: skip
SEASON_TOTAL_TEAM = "total"  # extra row SkillCorner adds for players traded mid-season


def price_by_coverage(picks_agg: pd.DataFrame) -> pd.DataFrame:
    """Points per pick and outcome rates by role and coverage, league-wide."""
    players = picks_agg[picks_agg.team_name != SEASON_TOTAL_TEAM]
    rows = []
    for role, sources in (("handler", HANDLER_COVERAGES), ("screener", SCREENER_COVERAGES)):
        for source in sources:

            def total(metric: str, role=role, source=source) -> float:
                return float(players[f"{role}_{metric}_vs_{source}"].sum())

            picks = total("picks")
            rates = [
                total(metric) / picks if picks else np.nan
                for metric in ("points", "score", "assist", "turnover")
            ]
            rows.append((role, COVERAGE_NAMES.get(source, source), int(picks), *rates))
    return pd.DataFrame(rows, columns=PRICE_COLUMNS)
