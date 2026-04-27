"""
Tests for the modelling and value-detection logic.

These run end-to-end against synthetic data, so we can verify the
math is correct before we ever fetch real odds. Run with:
    python -m src.tests
"""

import sys

from . import devig
from . import model
from . import value


def test_poisson_basic():
    """Sanity check: a 2.5-goal expected total should give Over 2.5 ~ 50%."""
    home = model.TeamStrength(xg_for_per_game=1.5, xg_against_per_game=1.2, games_in_sample=10)
    away = model.TeamStrength(xg_for_per_game=1.4, xg_against_per_game=1.3, games_in_sample=10)
    league = model.LeagueContext(avg_goals_per_game=2.8, home_advantage=1.18, league_xg_for_baseline=1.40)

    probs = model.model_fixture(home, away, league)

    # All probabilities should be in [0, 1]
    for k, v in probs.items():
        assert 0 <= v <= 1, f"{k} = {v} out of range"

    # H/D/A should sum to ~1
    hda_sum = probs["home_win"] + probs["draw"] + probs["away_win"]
    assert abs(hda_sum - 1.0) < 0.01, f"H/D/A sum {hda_sum} != 1"

    # Over+Under should sum to ~1
    ou_sum = probs["over_2_5"] + probs["under_2_5"]
    assert abs(ou_sum - 1.0) < 0.01, f"O/U sum {ou_sum} != 1"

    print(f"  Over 2.5: {probs['over_2_5']:.3f}")
    print(f"  BTTS Yes: {probs['btts_yes']:.3f}")
    print(f"  Home win: {probs['home_win']:.3f}")
    print("  test_poisson_basic: PASSED")


def test_strong_attack_increases_btts():
    """BTTS should rise when both teams are attack-heavy."""
    league = model.LeagueContext(avg_goals_per_game=2.8, home_advantage=1.18, league_xg_for_baseline=1.40)
    weak = model.TeamStrength(xg_for_per_game=0.9, xg_against_per_game=1.5, games_in_sample=10)
    strong = model.TeamStrength(xg_for_per_game=2.0, xg_against_per_game=1.0, games_in_sample=10)

    weak_probs = model.model_fixture(weak, weak, league)
    strong_probs = model.model_fixture(strong, strong, league)

    assert strong_probs["btts_yes"] > weak_probs["btts_yes"], (
        f"BTTS should be higher for strong attacks: "
        f"{strong_probs['btts_yes']:.3f} vs {weak_probs['btts_yes']:.3f}"
    )
    print(f"  Weak BTTS:   {weak_probs['btts_yes']:.3f}")
    print(f"  Strong BTTS: {strong_probs['btts_yes']:.3f}")
    print("  test_strong_attack_increases_btts: PASSED")


def test_devig_two_way():
    """A book at 1.90/1.90 should de-vig to 50/50."""
    result = devig.devig_two_way(1.90, 1.90)
    assert abs(result["yes"] - 0.5) < 1e-6
    assert abs(result["no"] - 0.5) < 1e-6
    print(f"  1.90/1.90 -> {result}")

    # Asymmetric
    result = devig.devig_two_way(1.50, 2.50)
    # implied: 0.6667, 0.4. total 1.0667. devigged: 0.625, 0.375.
    assert abs(result["yes"] - 0.625) < 1e-3
    assert abs(result["no"] - 0.375) < 1e-3
    print(f"  1.50/2.50 -> {result}")
    print("  test_devig_two_way: PASSED")


def test_value_detection_finds_edge():
    """
    Construct a fixture where the model strongly disagrees with the book,
    verify a value bet is flagged.
    """
    league = model.LeagueContext(avg_goals_per_game=3.10, home_advantage=1.18, league_xg_for_baseline=1.55)
    # Both teams attack-heavy -> high BTTS, high Over 2.5
    home = model.TeamStrength(xg_for_per_game=2.1, xg_against_per_game=1.6, games_in_sample=10)
    away = model.TeamStrength(xg_for_per_game=1.9, xg_against_per_game=1.7, games_in_sample=10)

    probs = model.model_fixture(home, away, league)

    # Construct book odds where Over 2.5 is generously priced (book thinks
    # this is a lower-scoring game than it is)
    book_odds = {
        "totals_2_5": {
            "Pinnacle": {"over": 1.95, "under": 1.95},   # book at ~50/50
            "Sportsbet": {"over": 2.00, "under": 1.85},  # even better Over price
        },
        "btts": {
            "Pinnacle": {"yes": 1.75, "no": 2.10},
        },
    }

    bets = value.find_value_bets(
        fixture_label="Test Home vs Test Away",
        league="soccer_netherlands_eredivisie",
        kickoff="2026-04-28T19:00:00",
        model_probs=probs,
        book_odds=book_odds,
    )

    print(f"  Model says Over 2.5: {probs['over_2_5']:.3f}")
    print(f"  Bets flagged: {len(bets)}")
    for b in bets:
        print(f"    {b.selection} @ {b.best_odds} ({b.best_book}) "
              f"edge={b.edge:.3f} EV={b.expected_value:.3f}")

    assert len(bets) > 0, "Should have flagged at least one value bet"
    # The Sportsbet Over 2.5 at 2.00 should be the headline bet
    over_bets = [b for b in bets if b.selection == "Over 2.5 goals"]
    assert len(over_bets) == 1
    assert over_bets[0].best_book == "Sportsbet"
    assert over_bets[0].best_odds == 2.00
    print("  test_value_detection_finds_edge: PASSED")


def test_no_value_when_book_is_sharp():
    """
    If the book's de-vigged price matches the model, no bet should fire.
    """
    league = model.LeagueContext(avg_goals_per_game=2.8, home_advantage=1.18, league_xg_for_baseline=1.40)
    home = model.TeamStrength(xg_for_per_game=1.4, xg_against_per_game=1.4, games_in_sample=10)
    away = model.TeamStrength(xg_for_per_game=1.4, xg_against_per_game=1.4, games_in_sample=10)

    probs = model.model_fixture(home, away, league)
    over_prob = probs["over_2_5"]

    # Set odds so de-vigged price exactly matches the model probability
    fair_over = 1.0 / over_prob
    fair_under = 1.0 / (1 - over_prob)
    # Apply a small margin that keeps the model on the wrong side of the threshold
    over_odds = fair_over * 0.97
    under_odds = fair_under * 0.97

    book_odds = {
        "totals_2_5": {
            "Pinnacle": {"over": over_odds, "under": under_odds},
        },
    }

    bets = value.find_value_bets(
        fixture_label="Sharp vs Sharp",
        league="soccer_netherlands_eredivisie",
        kickoff="2026-04-28T19:00:00",
        model_probs=probs,
        book_odds=book_odds,
    )

    assert len(bets) == 0, f"Should have flagged 0 bets, got {len(bets)}"
    print("  test_no_value_when_book_is_sharp: PASSED")


def main() -> int:
    tests = [
        test_poisson_basic,
        test_strong_attack_increases_btts,
        test_devig_two_way,
        test_value_detection_finds_edge,
        test_no_value_when_book_is_sharp,
    ]
    failed = 0
    for t in tests:
        print(f"\n{t.__name__}:")
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  FAILED: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR: {type(e).__name__}: {e}")

    print()
    print("=" * 60)
    if failed:
        print(f"FAILED: {failed}/{len(tests)} tests")
        return 1
    print(f"PASSED: {len(tests)}/{len(tests)} tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
