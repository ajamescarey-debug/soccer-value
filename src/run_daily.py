"""
Daily pipeline entry point.

Run by GitHub Actions on cron. Steps:
  1. For each configured league:
     a. Fetch fixtures + odds via The Odds API
     b. Load cached team xG strengths
     c. For each fixture, run the model -> market probabilities
     d. Compare to book odds -> identify value bets
  2. Aggregate all value bets into today's picks file
  3. Log every taken bet to the CLV tracker
  4. Check the kill switch
  5. Write dashboard data

Run locally:
    python -m src.run_daily

Environment:
    ODDS_API_KEY  — set in GitHub Actions secrets
"""

import json
import os
import uuid
from datetime import datetime
from typing import List

from . import config
from . import clv
from . import data
from . import model
from . import value


def run() -> dict:
    odds_api_key = os.environ.get("ODDS_API_KEY", "STUB")
    all_bets: List[value.ValueBet] = []
    fixtures_processed = 0

    for league_key in config.LEAGUES:
        try:
            ctx = data.get_league_context(league_key)
        except KeyError:
            print(f"[skip] no league context for {league_key}")
            continue

        strengths = data.fetch_team_strengths(league_key)
        if not strengths:
            print(f"[skip] no team strengths cached for {league_key}")
            continue

        fixtures = data.fetch_odds_for_league(league_key, odds_api_key)
        for fx in fixtures:
            fixtures_processed += 1

            home_strength = strengths.get(fx.home)
            away_strength = strengths.get(fx.away)
            if not home_strength or not away_strength:
                # New team or name mismatch — skip rather than guess
                continue

            probs = model.model_fixture(home_strength, away_strength, ctx)
            bets = value.find_value_bets(
                fixture_label=f"{fx.home} vs {fx.away}",
                league=league_key,
                kickoff=fx.kickoff,
                model_probs=probs,
                book_odds=fx.book_odds,
            )

            for bet in bets:
                bet_id = str(uuid.uuid4())
                clv.append_taken(
                    bet_id=bet_id,
                    fixture=bet.fixture,
                    market=bet.market,
                    selection=bet.selection,
                    taken_odds=bet.best_odds,
                )
                all_bets.append(bet)

    # Write today's picks
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    picks_payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "mode": "LIVE" if config.LIVE_MODE else "PAPER",
        "fixtures_processed": fixtures_processed,
        "bets_flagged": len(all_bets),
        "bets": [b.__dict__ for b in all_bets],
    }
    with open(config.PICKS_FILE, "w") as f:
        json.dump(picks_payload, f, indent=2)

    # Kill-switch check
    clv_summary = clv.summary()
    if clv_summary["kill_switch_triggered"]:
        print("=" * 60)
        print("KILL SWITCH TRIGGERED")
        print(f"Sample size: {clv_summary['sample_size']}")
        print(f"Average CLV: {clv_summary['avg_clv_pct']}%")
        print("Model has no edge. Stopping.")
        print("=" * 60)

    return {
        "fixtures_processed": fixtures_processed,
        "bets_flagged": len(all_bets),
        "clv": clv_summary,
    }


if __name__ == "__main__":
    summary = run()
    print(json.dumps(summary, indent=2))
