"""
Closing Line Value (CLV) tracking.

CLV is the gap between the odds we took and the odds at kickoff.
If we consistently take prices better than the closing line, we are
moving in the same direction the sharp money does — i.e. we have edge.
This is true even when our short-term P&L is negative due to variance.

CLV is the only reliable signal at small samples. P&L over 100 bets
tells you essentially nothing. CLV over 100 bets tells you a lot.

Interpretation:
  +2% to +5% CLV: legitimate edge, professional grade
  0% to +2% CLV: weak edge, possibly real, possibly noise
  Negative CLV: model has no edge, regardless of P&L
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import List, Optional

from . import config


@dataclass
class CLVRecord:
    bet_id: str
    fixture: str
    market: str
    selection: str
    taken_odds: float
    closing_odds: Optional[float]
    clv_pct: Optional[float]
    timestamp: str


def compute_clv(taken_odds: float, closing_odds: float) -> float:
    """CLV as a percentage. +3.0 means we took 3% better than close."""
    if closing_odds <= 1.0:
        raise ValueError("Closing odds must be > 1.0")
    return (taken_odds / closing_odds - 1.0) * 100.0


def load_clv_log() -> List[CLVRecord]:
    if not os.path.exists(config.CLV_FILE):
        return []
    with open(config.CLV_FILE, "r") as f:
        raw = json.load(f)
    return [CLVRecord(**r) for r in raw]


def save_clv_log(records: List[CLVRecord]) -> None:
    os.makedirs(os.path.dirname(config.CLV_FILE), exist_ok=True)
    with open(config.CLV_FILE, "w") as f:
        json.dump([r.__dict__ for r in records], f, indent=2)


def append_taken(bet_id: str, fixture: str, market: str, selection: str, taken_odds: float) -> None:
    """Log a bet at the moment we flag it. Closing odds filled in later."""
    records = load_clv_log()
    records.append(CLVRecord(
        bet_id=bet_id,
        fixture=fixture,
        market=market,
        selection=selection,
        taken_odds=taken_odds,
        closing_odds=None,
        clv_pct=None,
        timestamp=datetime.utcnow().isoformat(),
    ))
    save_clv_log(records)


def update_closing(bet_id: str, closing_odds: float) -> None:
    """Fill in closing odds for an existing bet, compute CLV."""
    records = load_clv_log()
    for r in records:
        if r.bet_id == bet_id:
            r.closing_odds = closing_odds
            r.clv_pct = compute_clv(r.taken_odds, closing_odds)
            break
    save_clv_log(records)


def summary() -> dict:
    """Headline CLV stats. This is what we put on the dashboard."""
    records = [r for r in load_clv_log() if r.clv_pct is not None]
    if not records:
        return {"sample_size": 0, "avg_clv_pct": None, "kill_switch_triggered": False}

    avg = mean(r.clv_pct for r in records)
    return {
        "sample_size": len(records),
        "avg_clv_pct": round(avg, 3),
        "kill_switch_triggered": (
            len(records) >= config.KILL_SWITCH_SAMPLE and avg < 0
        ),
    }
