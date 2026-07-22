"""
Regression tests for utils/movie_models.py (Day 2 financial engine).

The first version of this engine ran without erroring but produced
unrealistic output: a $200M movie showed a $650M+ NPV and an IRR pinned at
the 500% search ceiling for every scenario (see DESIGN_NOTES.md's Day 2
"Working list" for the full story). These tests exist so a future change
can't silently reintroduce that class of bug — they check the *scale* and
*direction* of the numbers, not just that the functions execute.
"""
import math
import pytest

from utils.movie_models import (
    MovieProject, risk_adjusted_npv, capital_efficiency, strategic_fit_score,
    compute_movie_score, draw_actual_multiplier, nearest_scenario_label,
    genre_scenario_multipliers, SCENARIO_MULTIPLIERS, GENRE_VARIANCE_SPREAD,
    WINDOW_SHRINK_PER_CYCLE_DAYS, BASE_WINDOW_DAYS,
)


def _tentpole(cycle: int = 1, release_strategy: str = "wide_theatrical") -> MovieProject:
    return MovieProject(title="Test Tentpole", genre="Action/Tentpole", budget_m=120, pa_spend_m=80,
                         star_power=75, screens=3500, cycle=cycle, release_strategy=release_strategy)


def _indie(cycle: int = 1, release_strategy: str = "platform") -> MovieProject:
    return MovieProject(title="Indie Drama", genre="Drama", budget_m=15, pa_spend_m=10,
                         star_power=40, screens=800, cycle=cycle, release_strategy=release_strategy)


# ── Realistic-scale regression guards ──────────────────────────────────────────
class TestRealisticScale:
    """Pins the output of a $200M tentpole and a $25M indie to believable
    dollar ranges — the exact class of thing that was wrong before."""

    def test_tentpole_base_case_npv_is_realistic_not_absurd(self):
        npv = _tentpole().npv("base")
        # A successful $200M tentpole should look like a real hit ($100-300M
        # NPV), not a fictional blockbuster (the original bug produced $650M+).
        assert 50 < npv < 300

    def test_tentpole_bear_case_still_thinner_than_base(self):
        p = _tentpole()
        assert p.npv("bear") < p.npv("base") < p.npv("bull")

    def test_indie_platform_release_is_marginal_not_a_guaranteed_win(self):
        p = _indie()
        # A small specialty release should be a real bet, not a lock — base
        # case should be close to break-even, not comfortably positive.
        assert -20 < p.npv("base") < 20

    def test_opening_weekend_lands_in_realistic_per_screen_range(self):
        p = _tentpole()
        per_screen = p.opening_weekend() / p.screens
        # Real blockbuster per-screen opening averages run roughly $10-30K.
        assert 0.008 < per_screen < 0.035


# ── IRR honesty ──────────────────────────────────────────────────────────────
class TestIRR:
    """irr() must distinguish 'never recovers capital' from 'exceeds the
    search ceiling' from an actually-converged rate — silently returning the
    search boundary as if it were a real answer was the original bug."""

    def test_never_recovers_capital_returns_none(self):
        # A disastrous bear-case indie that doesn't even clear its budget.
        p = MovieProject(title="Flop", genre="Drama", budget_m=80, pa_spend_m=60,
                          star_power=10, screens=400, cycle=1, release_strategy="platform")
        assert p.irr("bear") is None

    def test_exceeds_ceiling_returns_inf_not_a_fake_precise_number(self):
        irr = _tentpole().irr("bull")
        assert irr == float("inf")

    def test_moderate_outcome_converges_to_a_real_number(self):
        # A case picked to sit inside the search bounds, not pinned at either end.
        irr = _tentpole().irr("bear")
        assert irr not in (None, float("inf"))
        assert -0.5 < irr < 5.0


# ── Directional correctness of the mechanics ───────────────────────────────────
class TestReleaseStrategyTradeoffs:
    def test_day_and_date_suppresses_theatrical_for_a_big_tentpole(self):
        """A mega-tentpole's per-screen pull is large enough that skipping
        wide theatrical isn't offset by subscriber value — day-and-date
        should net out worse for this kind of title."""
        wide = _tentpole(cycle=3, release_strategy="wide_theatrical")
        dad  = _tentpole(cycle=3, release_strategy="day_and_date")
        assert dad.npv("base") < wide.npv("base")

    def test_day_and_date_skips_pvod_entirely(self):
        p = _tentpole(release_strategy="day_and_date")
        assert p.pvod_revenue("base") == 0.0

    def test_day_and_date_drives_more_subscriber_value_than_wide(self):
        wide = _tentpole(release_strategy="wide_theatrical")
        dad  = _tentpole(release_strategy="day_and_date")
        # Same domestic box office input before the cannibalization factor
        # is applied differently — subscriber_value should still be higher
        # per dollar of box office for day-and-date due to the 1.7x boost.
        assert dad.subscriber_value("base") / dad.domestic_box_office("base") > \
               wide.subscriber_value("base") / wide.domestic_box_office("base")

    def test_window_shrinks_each_cycle_and_floors_at_17_days(self):
        p1, p2, p3 = _tentpole(cycle=1), _tentpole(cycle=2), _tentpole(cycle=3)
        assert p1.window_days() == BASE_WINDOW_DAYS
        assert p2.window_days() == BASE_WINDOW_DAYS - WINDOW_SHRINK_PER_CYCLE_DAYS
        assert p1.window_days() > p2.window_days() > p3.window_days()
        # Floor should hold even for a hypothetical much-later cycle.
        p_late = _tentpole(cycle=10)
        assert p_late.window_days() == 17


# ── Scenario draw ────────────────────────────────────────────────────────────
class TestScenarioDraw:
    def test_reproducible_for_same_team_and_cycle(self):
        m1 = draw_actual_multiplier("Team Alpha", 1)
        m2 = draw_actual_multiplier("Team Alpha", 1)
        assert m1 == m2

    def test_different_cycles_can_draw_different_outcomes(self):
        draws = {draw_actual_multiplier("Team Alpha", c) for c in (1, 2, 3)}
        assert len(draws) > 1   # extremely unlikely to collide across 3 cycles if seeding works

    def test_draw_stays_within_bear_bull_bounds(self):
        for cycle in range(1, 4):
            m = draw_actual_multiplier("Team Beta", cycle)
            assert SCENARIO_MULTIPLIERS["bear"] <= m <= SCENARIO_MULTIPLIERS["bull"]

    def test_nearest_scenario_label_matches_exact_named_values(self):
        for label, mult in SCENARIO_MULTIPLIERS.items():
            assert nearest_scenario_label(mult) == label


# ── Genre-differentiated variance ──────────────────────────────────────────────
class TestGenreVariance:
    """Variance (bear-to-bull spread), not the base case itself, should
    differ by genre — a horror movie is famously more volatile relative to
    its budget than an awards drama, and the model should reflect that."""

    def test_base_case_multiplier_is_identical_across_genres(self):
        for genre in GENRE_VARIANCE_SPREAD:
            assert genre_scenario_multipliers(genre)["base"] == SCENARIO_MULTIPLIERS["base"]

    def test_horror_has_a_wider_spread_than_awards_drama(self):
        horror_bounds = genre_scenario_multipliers("Horror")
        prestige_bounds = genre_scenario_multipliers("Awards/Prestige")
        horror_spread = horror_bounds["bull"] - horror_bounds["bear"]
        prestige_spread = prestige_bounds["bull"] - prestige_bounds["bear"]
        assert horror_spread > prestige_spread

    def test_unknown_genre_falls_back_to_baseline_spread(self):
        bounds = genre_scenario_multipliers("Not A Real Genre")
        assert bounds == SCENARIO_MULTIPLIERS

    def test_draw_actual_multiplier_respects_genre_bounds(self):
        for genre in GENRE_VARIANCE_SPREAD:
            bounds = genre_scenario_multipliers(genre)
            m = draw_actual_multiplier("Team Gamma", 1, genre)
            assert bounds["bear"] <= m <= bounds["bull"]

    def test_horror_bear_case_can_go_lower_than_baseline_bear(self):
        # Wider spread means horror's bear case sits below the flat baseline bear.
        horror_bounds = genre_scenario_multipliers("Horror")
        assert horror_bounds["bear"] < SCENARIO_MULTIPLIERS["bear"]


# ── Scoring ───────────────────────────────────────────────────────────────────
class TestScoring:
    def test_empty_slate_scores_zero_and_fails(self):
        score = compute_movie_score([])
        assert score["total"] == 0.0
        assert score["passed"] is False

    def test_strong_slate_passes_with_positive_avg_npv(self):
        score = compute_movie_score([_tentpole(cycle=1), _tentpole(cycle=2), _tentpole(cycle=3)])
        assert score["passed"] is True
        assert score["avg_ra_npv_m"] > 0

    def test_score_components_are_clamped_to_0_100(self):
        for p in (_tentpole(), _indie()):
            score = compute_movie_score([p])
            for key in ("risk_adjusted_npv", "capital_efficiency", "strategic_fit"):
                assert 0 <= score[key] <= 100

    def test_wide_theatrical_scores_at_least_50_strategic_fit_against_itself(self):
        # strategic_fit_score compares actual vs. a wide-theatrical baseline
        # of the same project — a project that already IS wide theatrical
        # should score at (or extremely near) the neutral midpoint.
        p = _tentpole(release_strategy="wide_theatrical")
        assert strategic_fit_score(p) == pytest.approx(50.0, abs=1.0)
