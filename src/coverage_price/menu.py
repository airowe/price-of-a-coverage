"""Price the handler–screener pairs an offense could have run a ball screen with.

Every rate is points per direct pick from SkillCorner's season pick aggregates, pooled
over coverages and shrunk toward the league rate for the role. A pick yields 0, 2 or 3
points (SkillCorner's points are 2 x (score_2pt + assist_2pt) + 3 x (score_3pt +
assist_3pt)), which gives each role's per-pick spread.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from coverage_price.pricing import SEASON_TOTAL_TEAM

MIN_ROLE_PICKS = 30  # direct picks in a role before a player is offered in it
PRIOR_PICKS = 50  # shrinkage strength: pseudo-picks at the league rate
Z95 = 1.96
ROLES = ("handler", "screener")
_COUNTS = ("total_picks", "points", "score_2pt", "score_3pt", "assist_2pt", "assist_3pt")


@dataclass(frozen=True)
class League:
    handler_rate: float
    screener_rate: float
    handler_sd: float
    screener_sd: float
    assist_to_screener_rate: float
    points_per_screener_basket: float


def _players(picks_agg: pd.DataFrame, aliases: dict[int, int]) -> pd.DataFrame:
    """One summed row per canonical player; season-total rows for traded players dropped."""
    rows = picks_agg[picks_agg.team_name != SEASON_TOTAL_TEAM]
    columns = [f"{role}_{count}" for role in ROLES for count in _COUNTS]
    columns.append("handler_assist_to_screener")
    ids = rows.player_id.map(lambda v: aliases.get(v, v)).astype(int)
    return rows[columns].groupby(ids.rename("player_id")).sum()


def _sd(totals: pd.Series, role: str) -> float:
    picks = totals[f"{role}_total_picks"]
    if not picks:
        return 0.0
    twos = totals[f"{role}_score_2pt"] + totals[f"{role}_assist_2pt"]
    threes = totals[f"{role}_score_3pt"] + totals[f"{role}_assist_3pt"]
    mean = totals[f"{role}_points"] / picks
    return math.sqrt(max((4 * twos + 9 * threes) / picks - mean**2, 0.0))


def league_rates(picks_agg: pd.DataFrame) -> League:
    totals = _players(picks_agg, {}).sum()

    def per_pick(column: str, role: str) -> float:
        picks = totals[f"{role}_total_picks"]
        return float(totals[column] / picks) if picks else 0.0

    baskets = totals.screener_score_2pt + totals.screener_score_3pt
    return League(
        handler_rate=per_pick("handler_points", "handler"),
        screener_rate=per_pick("screener_points", "screener"),
        handler_sd=_sd(totals, "handler"),
        screener_sd=_sd(totals, "screener"),
        assist_to_screener_rate=per_pick("handler_assist_to_screener", "handler"),
        points_per_screener_basket=float(
            (2 * totals.screener_score_2pt + 3 * totals.screener_score_3pt) / baskets
        )
        if baskets
        else 0.0,
    )


def player_rates(
    picks_agg: pd.DataFrame, aliases: dict[int, int], prior_picks: float = PRIOR_PICKS
) -> pd.DataFrame:
    """Shrunk points per direct pick by role, its sd, and the handler's assists to the screener."""
    league, players = league_rates(picks_agg), _players(picks_agg, aliases)

    def shrunk(total: pd.Series, picks: pd.Series, prior_rate: float) -> pd.Series:
        return (total + prior_picks * prior_rate) / (picks + prior_picks)

    out = pd.DataFrame(index=players.index)
    for role in ROLES:
        picks = players[f"{role}_total_picks"]
        out[f"{role}_picks"] = picks.astype(int)
        out[f"{role}_rate"] = shrunk(
            players[f"{role}_points"], picks, getattr(league, f"{role}_rate")
        )
        out[f"{role}_sd"] = getattr(league, f"{role}_sd") / (picks + prior_picks) ** 0.5
    out["assist_to_screener_rate"] = shrunk(
        players.handler_assist_to_screener,
        players.handler_total_picks,
        league.assist_to_screener_rate,
    )
    return out


def role_rate(
    rates: pd.DataFrame, league: League, player_id: int, role: str
) -> tuple[float, float, int]:
    """(rate, sd, direct picks) for a player in a role; league values if he has no row."""
    if player_id in rates.index:
        row = rates.loc[player_id]
        return float(row[f"{role}_rate"]), float(row[f"{role}_sd"]), int(row[f"{role}_picks"])
    sd = getattr(league, f"{role}_sd") / math.sqrt(PRIOR_PICKS)
    return getattr(league, f"{role}_rate"), sd, 0


def pair_price(
    handler_rate: float,
    screener_rate: float,
    assist_to_screener_rate: float,
    points_per_screener_basket: float,
) -> float:
    """Points per direct pick for a pair; the screener baskets the handler assisted count once."""
    return handler_rate + screener_rate - assist_to_screener_rate * points_per_screener_basket


MENU_COLUMNS = [
    "handler_id", "screener_id", "price", "lo", "hi", "used", "below_volume", "best",
    "too_close_to_best",
]  # fmt: skip


Terms = dict[tuple[int, str], float]


def difference_sd(a: Terms, b: Terms) -> float:
    """Sd of one pair's price minus another's, from each pair's (player, role) -> sd terms.

    A player in the same role in both pairs adds the same estimate to each price, so his
    term cancels; every other term is an independent estimate and adds its variance.
    """
    unshared = (sd for key, sd in (a | b).items() if (key in a) != (key in b))
    return math.sqrt(sum(sd**2 for sd in unshared))


def too_close(gap: float, sd: float) -> bool:
    """A price gap inside the 95% interval of the difference (touching counts) cannot be
    told apart from zero."""
    return abs(gap) <= Z95 * sd


def build_menu(
    on_floor: Sequence[int], used: tuple[int, int], rates: pd.DataFrame, league: League
) -> pd.DataFrame:
    """Every plausible ordered pair among the players, priced, plus the pair actually used.

    Rows are sorted by price, best first. `too_close_to_best` includes the best itself.
    """
    players = sorted(set(on_floor) | set(used))
    rows = []
    for handler in players:
        h_rate, h_sd, h_picks = role_rate(rates, league, handler, "handler")
        assists = (
            float(rates.loc[handler, "assist_to_screener_rate"])
            if handler in rates.index
            else league.assist_to_screener_rate
        )
        for screener in players:
            if screener == handler:
                continue
            s_rate, s_sd, s_picks = role_rate(rates, league, screener, "screener")
            plausible = h_picks >= MIN_ROLE_PICKS and s_picks >= MIN_ROLE_PICKS
            is_used = (handler, screener) == tuple(used)
            if not (plausible or is_used):
                continue
            price = pair_price(h_rate, s_rate, assists, league.points_per_screener_basket)
            half = Z95 * math.hypot(h_sd, s_sd)
            terms = {(handler, "handler"): h_sd, (screener, "screener"): s_sd}
            rows.append((handler, screener, price, price - half, price + half, is_used,
                         not plausible, terms))  # fmt: skip
    menu = pd.DataFrame(rows, columns=[*MENU_COLUMNS[:7], "terms"])
    menu = menu.sort_values(["price", "handler_id", "screener_id"], ascending=[False, True, True])
    menu = menu.reset_index(drop=True)
    menu["best"] = menu.index == 0
    top = menu.iloc[0]
    menu["too_close_to_best"] = [
        too_close(top.price - price, difference_sd(top.terms, terms))
        for price, terms in zip(menu.price, menu.terms, strict=True)
    ]
    return menu[MENU_COLUMNS]
