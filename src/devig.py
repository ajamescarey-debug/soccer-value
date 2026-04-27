"""
De-vigging: stripping bookmaker margin from quoted odds to get the
market's implied probability.

Quoted odds contain margin. If a 2-way market has both sides at $1.90,
the implied probabilities sum to 1.053, not 1.0. That 5.3% overround
is the book's edge. To compare the market's opinion to our model,
we have to strip it.
"""

from typing import Dict, List


def implied_from_decimal(odds: float) -> float:
    """1/odds. The book's quoted probability, including margin."""
    if odds <= 1.0:
        raise ValueError(f"Decimal odds must be > 1.0, got {odds}")
    return 1.0 / odds


def devig_proportional(odds_list: List[float]) -> List[float]:
    """
    Strip margin proportionally across all outcomes.
    For a 2-way market: p_true = (1/odds) / sum(1/odds_all).
    """
    implied = [implied_from_decimal(o) for o in odds_list]
    total = sum(implied)
    if total <= 0:
        raise ValueError("All odds invalid")
    return [p / total for p in implied]


def devig_two_way(odds_yes: float, odds_no: float) -> Dict[str, float]:
    """Convenience wrapper for 2-way markets like Over/Under or BTTS."""
    p_yes, p_no = devig_proportional([odds_yes, odds_no])
    return {"yes": p_yes, "no": p_no}


def margin(odds_list: List[float]) -> float:
    """
    Total overround. 0.05 means 5% margin.
    """
    return sum(implied_from_decimal(o) for o in odds_list) - 1.0
