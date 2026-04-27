"""
Data fetching layer.

Two sources we need:
  1. Odds — from The Odds API (your existing key).
  2. Team xG ratings — from FBref or Understat. Cached daily.

This module keeps external calls behind small functions so we can swap
data sources without touching the model. The actual HTTP calls are
stubbed for now — the GitHub Actions runtime will inject real data
once we wire up the scrapers in the next step.
"""

import json
import os
from dataclasses import dataclass
from typing import Dict, List

from . import config
from .model import TeamStrength, LeagueContext


# ---------------------------------------------------------------------------
# Odds API
# ---------------------------------------------------------------------------

@dataclass
class FixtureOdds:
    fixture_id: str
    home: str
    away: str
    league: str
    kickoff: str
    book_odds: Dict[str, Dict[str, Dict[str, float]]]


def fetch_odds_for_league(league_key: str, api_key: str) -> List[FixtureOdds]:
    """
    Fetch odds from The Odds API for one league.

    Real implementation will call:
      https://api.the-odds-api.com/v4/sports/{league_key}/odds
        ?apiKey={key}&regions=au,uk,eu&markets=totals,btts&oddsFormat=decimal

    Stubbed here so the pipeline runs cleanly. When we wire it up, the
    function returns a list of FixtureOdds. Returning an empty list is
    a valid no-op state — pipeline just reports zero fixtures.
    """
    return []


# ---------------------------------------------------------------------------
# Team xG ratings
# ---------------------------------------------------------------------------

def fetch_team_strengths(league_key: str) -> Dict[str, TeamStrength]:
    """
    Fetch rolling xG ratings per team from FBref / Understat.

    Cached daily. Reads from data/{league_key}_strengths.json if present.
    Returns empty dict when no cache exists, which the pipeline handles
    cleanly (it skips the league rather than crashing).
    """
    cache_path = f"{config.DATA_DIR}/{league_key}_strengths.json"
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            raw = json.load(f)
        return {team: TeamStrength(**stats) for team, stats in raw.items()}
    return {}


def save_team_strengths(league_key: str, strengths: Dict[str, TeamStrength]) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    cache_path = f"{config.DATA_DIR}/{league_key}_strengths.json"
    with open(cache_path, "w") as f:
        json.dump(
            {team: ts.__dict__ for team, ts in strengths.items()},
            f,
            indent=2,
        )


# ---------------------------------------------------------------------------
# League context
# ---------------------------------------------------------------------------

# Hardcoded per-league baselines. Stable enough that hardcoding is fine;
# we'll refresh once a season from FBref aggregates.
LEAGUE_CONTEXTS: Dict[str, LeagueContext] = {
    "soccer_netherlands_eredivisie": LeagueContext(
        avg_goals_per_game=3.10, home_advantage=1.18, league_xg_for_baseline=1.55
    ),
    "soccer_belgium_first_div": LeagueContext(
        avg_goals_per_game=2.95, home_advantage=1.20, league_xg_for_baseline=1.48
    ),
    "soccer_portugal_primeira_liga": LeagueContext(
        avg_goals_per_game=2.55, home_advantage=1.22, league_xg_for_baseline=1.28
    ),
    "soccer_spl": LeagueContext(
        avg_goals_per_game=2.85, home_advantage=1.15, league_xg_for_baseline=1.43
    ),
    "soccer_usa_mls": LeagueContext(
        avg_goals_per_game=2.95, home_advantage=1.25, league_xg_for_baseline=1.48
    ),
    "soccer_japan_j_league": LeagueContext(
        avg_goals_per_game=2.60, home_advantage=1.12, league_xg_for_baseline=1.30
    ),
    "soccer_brazil_campeonato": LeagueContext(
        avg_goals_per_game=2.40, home_advantage=1.30, league_xg_for_baseline=1.20
    ),
}


def get_league_context(league_key: str) -> LeagueContext:
    return LEAGUE_CONTEXTS[league_key]
