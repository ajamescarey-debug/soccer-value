"""
Value detection.

Given a fixture, our model's market probabilities, and the bookmaker's
quoted odds across multiple books, find the bets where our edge exceeds
the threshold.

Edge = model_prob - devigged_book_prob. We want this positive.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import config
from . import devig


@dataclass
class ValueBet:
    """A flagged value bet, ready for logging or placement."""
    fixture: str
    league: str
    kickoff: str
    market: str
    selection: str
    best_odds: float
    best_book: str
    model_prob: float
    devigged_prob: float
    edge: float
    expected_value: float
    stake: float


def _ev_per_unit(prob: float, odds: float) -> float:
    """Expected return per $1 staked. 0.05 = 5% EV."""
    return prob * (odds - 1) - (1 - prob)


def _kelly_stake(prob: float, odds: float, bankroll: float) -> float:
    """
    Fractional Kelly stake. Multiplied by config.KELLY_FRACTION
    because full Kelly is too aggressive given model uncertainty.
    """
    b = odds - 1
    q = 1 - prob
    f = (b * prob - q) / b
    if f <= 0:
        return 0.0
    return bankroll * f * config.KELLY_FRACTION


def _opposite_side(side: str) -> str:
    """Return the opposite side label for two-way markets."""
    return {
        "over": "under",
        "under": "over",
        "yes": "no",
        "no": "yes",
    }[side]


def find_value_bets(
    fixture_label: str,
    league: str,
    kickoff: str,
    model_probs: Dict[str, float],
    book_odds: Dict[str, Dict[str, Dict[str, float]]],
    bankroll: float = 10000.0,
) -> List[ValueBet]:
    """
    For each market we model, check every book for a price that beats
    our model probability by config.MIN_EDGE.
    """
    value_bets: List[ValueBet] = []

    market_map = [
        ("totals_1_5", "over",  "over_1_5",  "Over 1.5 goals"),
        ("totals_1_5", "under", "under_1_5", "Under 1.5 goals"),
        ("totals_2_5", "over",  "over_2_5",  "Over 2.5 goals"),
        ("totals_2_5", "under", "under_2_5", "Under 2.5 goals"),
        ("totals_3_5", "over",  "over_3_5",  "Over 3.5 goals"),
        ("totals_3_5", "under", "under_3_5", "Under 3.5 goals"),
        ("btts",       "yes",   "btts_yes",  "Both Teams to Score - Yes"),
        ("btts",       "no",    "btts_no",   "Both Teams to Score - No"),
    ]

    for book_market, side, model_key, label in market_map:
        if book_market not in book_odds:
            continue

        opposite = _opposite_side(side)

        # Find best (highest) odds across books for this side
        best_odds = 0.0
        best_book: Optional[str] = None
        best_pair: Optional[Dict[str, float]] = None

        for book_name, prices in book_odds[book_market].items():
            if side not in prices or opposite not in prices:
                continue
            if prices[side] > best_odds:
                best_odds = prices[side]
                best_book = book_name
                best_pair = prices

        if not best_book or best_odds < config.MIN_ODDS or best_odds > config.MAX_ODDS:
            continue

        # De-vig using the same book's two-sided market
        try:
            devigged = devig.devig_two_way(best_pair[side], best_pair[opposite])
        except (ValueError, KeyError):
            continue

        devigged_prob = devigged["yes"] if side in ("over", "yes") else devigged["no"]
        model_prob = model_probs[model_key]
        edge = model_prob - devigged_prob

        if edge < config.MIN_EDGE:
            continue

        ev = _ev_per_unit(model_prob, best_odds)
        if config.LIVE_MODE:
            stake = _kelly_stake(model_prob, best_odds, bankroll)
        else:
            stake = config.UNIT_SIZE

        value_bets.append(ValueBet(
            fixture=fixture_label,
            league=league,
            kickoff=kickoff,
            market=model_key,
            selection=label,
            best_odds=round(best_odds, 3),
            best_book=best_book,
            model_prob=round(model_prob, 4),
            devigged_prob=round(devigged_prob, 4),
            edge=round(edge, 4),
            expected_value=round(ev, 4),
            stake=round(stake, 2),
        ))

    return value_bets
