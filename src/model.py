"""
Bivariate Poisson goal model.

For each fixture, we estimate expected goals for home and away based on:
  - Each team's recent attacking output (xG for, weighted by recency)
  - Each team's recent defensive output (xG against)
  - League-wide home advantage
  - League-wide scoring baseline

We then build a joint probability distribution over scorelines (0-0, 1-0, 0-1, ...)
up to a reasonable max (we use 8 goals each side; probability beyond is negligible).

From that distribution we derive market probabilities for Over/Under, BTTS, etc.

Why bivariate Poisson rather than two independent Poissons:
  - Real soccer scorelines have a slight positive correlation between team
    goal counts (open games tend to be high-scoring on both sides)
  - Independent Poisson systematically under-prices BTTS Yes and over-prices
    1-0 / 0-1 scorelines
  - Karlis & Ntzoufras (2003) is the standard reference; we use their
    parameterisation
"""

import math
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class TeamStrength:
    """Rolling-window attacking and defensive ratings, in xG terms."""
    xg_for_per_game: float
    xg_against_per_game: float
    games_in_sample: int


@dataclass
class LeagueContext:
    """League-wide baselines used to normalise team ratings."""
    avg_goals_per_game: float
    home_advantage: float          # multiplicative, typically 1.10-1.30
    league_xg_for_baseline: float  # for normalising team attack strength


def _poisson_pmf(k: int, lam: float) -> float:
    """Standard Poisson PMF. Guards against lam=0."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def expected_goals(
    home: TeamStrength,
    away: TeamStrength,
    league: LeagueContext,
) -> Tuple[float, float]:
    """
    Compute expected goals for home and away teams.

    The intuition: a team's attack rating is its xG_for relative to league
    average. A team's defence rating is its xG_against relative to league
    average. Expected goals in a fixture = (home attack) * (away defence)
    * league baseline * home advantage adjustment.
    """
    # Attack and defence indices (1.0 = league average)
    home_attack = home.xg_for_per_game / league.league_xg_for_baseline
    home_defence = home.xg_against_per_game / league.league_xg_for_baseline
    away_attack = away.xg_for_per_game / league.league_xg_for_baseline
    away_defence = away.xg_against_per_game / league.league_xg_for_baseline

    half_baseline = league.avg_goals_per_game / 2.0

    # Home advantage multiplies home's expected goals and divides away's
    # (a small symmetric effect — home teams attack more and concede less)
    ha = league.home_advantage
    lambda_home = home_attack * away_defence * half_baseline * math.sqrt(ha)
    lambda_away = away_attack * home_defence * half_baseline / math.sqrt(ha)

    return lambda_home, lambda_away


def scoreline_distribution(
    lambda_home: float,
    lambda_away: float,
    correlation: float = 0.10,
    max_goals: int = 8,
) -> Dict[Tuple[int, int], float]:
    """
    Build a joint probability distribution over scorelines using a
    simplified bivariate Poisson.

    `correlation` is a small positive shared-component term. 0.10 is a
    reasonable empirical value across European leagues; we could fit it
    per-league later but the gain is marginal.

    Returns a dict {(home_goals, away_goals): probability}.
    """
    lam3 = correlation * min(lambda_home, lambda_away)
    lam1 = max(lambda_home - lam3, 1e-6)
    lam2 = max(lambda_away - lam3, 1e-6)

    distribution: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            # Bivariate Poisson PMF: sum over the shared component
            p = 0.0
            for k in range(min(h, a) + 1):
                p += (
                    _poisson_pmf(h - k, lam1)
                    * _poisson_pmf(a - k, lam2)
                    * _poisson_pmf(k, lam3)
                )
            distribution[(h, a)] = p
            total += p

    # Renormalise — we truncated at max_goals, so the tail is missing.
    # The tail is tiny but renormalising keeps probabilities clean.
    if total > 0:
        for key in distribution:
            distribution[key] /= total

    return distribution


def market_probabilities(
    scorelines: Dict[Tuple[int, int], float],
) -> Dict[str, float]:
    """
    Collapse the scoreline distribution into market-level probabilities.

    Returns probabilities for the markets we'll actually bet:
      - over_1_5, over_2_5, over_3_5
      - under_1_5, under_2_5, under_3_5
      - btts_yes, btts_no
      - home_win, draw, away_win  (computed but not bet — for sanity-checking)
    """
    over_1_5 = sum(p for (h, a), p in scorelines.items() if h + a > 1)
    over_2_5 = sum(p for (h, a), p in scorelines.items() if h + a > 2)
    over_3_5 = sum(p for (h, a), p in scorelines.items() if h + a > 3)
    btts_yes = sum(p for (h, a), p in scorelines.items() if h > 0 and a > 0)
    home_win = sum(p for (h, a), p in scorelines.items() if h > a)
    draw = sum(p for (h, a), p in scorelines.items() if h == a)
    away_win = sum(p for (h, a), p in scorelines.items() if h < a)

    return {
        "over_1_5": over_1_5,
        "under_1_5": 1 - over_1_5,
        "over_2_5": over_2_5,
        "under_2_5": 1 - over_2_5,
        "over_3_5": over_3_5,
        "under_3_5": 1 - over_3_5,
        "btts_yes": btts_yes,
        "btts_no": 1 - btts_yes,
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
    }


def model_fixture(
    home: TeamStrength,
    away: TeamStrength,
    league: LeagueContext,
) -> Dict[str, float]:
    """End-to-end: take team strengths, return market probabilities."""
    lh, la = expected_goals(home, away, league)
    dist = scoreline_distribution(lh, la)
    return market_probabilities(dist)
