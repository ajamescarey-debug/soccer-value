"""
Configuration for the soccer value-betting system.

Edit this file to change leagues, edge thresholds, or flip to live mode.
Everything that's a "knob" lives here, not buried in code.
"""

# --- Mode ---
# Paper trading logs bets but moves no money. Flip to True only after
# we have at least 500 logged bets and positive closing-line value.
LIVE_MODE = False

# --- Leagues to model ---
# The Odds API league keys. Mid-tier European + a few non-European leagues
# where lines are softer than the top 5. We deliberately exclude EPL,
# La Liga, Bundesliga, Serie A, Ligue 1.
LEAGUES = [
    "soccer_netherlands_eredivisie",
    "soccer_belgium_first_div",
    "soccer_portugal_primeira_liga",
    "soccer_spl",                       # Scottish Premiership
    "soccer_usa_mls",
    "soccer_japan_j_league",
    "soccer_brazil_campeonato",
]

# --- Markets ---
# Goal markets are the focus. Match-result lines are too sharp.
MARKETS = ["totals", "btts"]

# --- Edge thresholds ---
# Minimum edge (model probability minus de-vigged book probability)
# required to flag a bet. 4% is conservative — at this threshold we'd
# expect ~2-5% ROI long-run if the model is calibrated.
MIN_EDGE = 0.04

# Maximum odds we'll bet. Above this, variance dominates and the model
# is probably wrong about the tail anyway.
MAX_ODDS = 3.50

# Minimum odds. Below this, the value gets eaten by margin even when
# we're right.
MIN_ODDS = 1.40

# --- Staking ---
# Flat $100 units in paper-trading. When we go live, switch to fractional
# Kelly (quarter-Kelly is the standard) — full Kelly is too aggressive
# given model uncertainty.
UNIT_SIZE = 100.0
KELLY_FRACTION = 0.25  # only used when LIVE_MODE = True

# --- Model ---
# Rolling window for team xG averages. 10 games balances recency and
# sample size. Weight decays exponentially: most recent game weighted 1.0,
# 10 games ago weighted ~0.5.
ROLLING_WINDOW = 10
RECENCY_DECAY = 0.93

# --- Kill switch ---
# After this many bets, if CLV is negative, the model doesn't work.
# We stop. No exceptions.
KILL_SWITCH_SAMPLE = 500

# --- Paths ---
DATA_DIR = "data"
RESULTS_DIR = "results"
PICKS_FILE = "results/picks.json"
HISTORY_FILE = "results/history.json"
CLV_FILE = "results/clv.json"
