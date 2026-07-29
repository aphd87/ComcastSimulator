"""
Regression tests for utils/models.py (Day 1 TV/Streaming financial engine).

Historically this engine had no dedicated test file at all -- unlike
utils/movie_models.py, which has TestRealisticScale guarding against a real
calibration bug that shipped once. These tests exist so the same class of
mistake (numbers that run without erroring but are quietly wrong) doesn't
slip into Day 1 unnoticed, starting with the newest additions.
"""
import math
import pytest

from utils.models import (
    Show, preview_regional_signal, REGIONS, REGIONAL_SIGNAL_CHANCE,
    REGIONS_PER_SIGNAL_MAX, AMORT_MONTHS_LINEAR, AMORT_MONTHS_SVOD,
    TRUE_CRIME_AMORT_MONTHS, MIN_MARKETING_PER_SHOW_M,
    draw_production_risk_event, PRODUCTION_RISK_CHANCE, PRODUCTION_RISK_REASONS,
    draw_emergency_budget_shock, EMERGENCY_BUDGET_CHANCE, EMERGENCY_BUDGET_CUT_RANGE,
    slot_rating_multiplier, PRIMETIME_DAYS, PRIMETIME_HOURS,
    SLOT_MULT_FLOOR, SLOT_MULT_CEILING,
)


def _show(genre="True Crime", show_id=101) -> Show:
    return Show(id=show_id, name="Test Show", genre=genre, episodes=10,
                ep_cost_k=300, rating=0.8, ip_score=60, air_month=1, network="Oxygen")


# ── Regional / demographic research signal ──────────────────────────────────
class TestRegionalSignal:
    def test_reproducible_for_same_team_show_year(self):
        s = _show()
        a = preview_regional_signal("Team Alpha", 1, s)
        b = preview_regional_signal("Team Alpha", 1, s)
        assert a == b

    def test_varies_across_shows_and_years(self):
        # Different seeds should not all collapse to the same outcome --
        # sample enough draws that both "some None" and "some non-None"
        # are overwhelmingly likely if REGIONAL_SIGNAL_CHANCE is honored.
        outcomes = [
            preview_regional_signal("Team Beta", y, _show(show_id=100 + y))
            for y in range(1, 30)
        ]
        assert any(o is None for o in outcomes)
        assert any(o is not None for o in outcomes)

    def test_when_present_respects_region_count_and_known_names(self):
        for y in range(1, 40):
            result = preview_regional_signal("Team Gamma", y, _show(show_id=200 + y))
            if result is None:
                continue
            assert 1 <= len(result) <= REGIONS_PER_SIGNAL_MAX
            names = [r["region"] for r in result]
            assert len(names) == len(set(names))  # no duplicate regions in one signal
            for r in result:
                assert r["region"] in REGIONS
                assert r["fit"] in ("strong", "moderate")
                assert isinstance(r["median_age"], int)
                assert isinstance(r["household_income_k"], int)

    def test_genre_affinity_skews_toward_strong_fit_regions(self):
        # True Crime is only in a subset of REGIONS' affinity lists -- over
        # many independent draws, "strong" fit should appear noticeably
        # more often than a uniform draw would produce, since it's
        # explicitly weighted (3x) in preview_regional_signal().
        strong_count = 0
        total = 0
        for y in range(1, 200):
            result = preview_regional_signal("Team Delta", y, _show(genre="True Crime", show_id=300 + y))
            if result is None:
                continue
            for r in result:
                total += 1
                if r["fit"] == "strong":
                    strong_count += 1
        assert total > 20   # enough draws landed to make the assertion meaningful
        assert strong_count / total > 0.4   # noticeably above a naive uniform baseline

    def test_none_result_is_a_real_possibility_not_a_bug(self):
        # REGIONAL_SIGNAL_CHANCE < 1.0 means None must be reachable --
        # pin the constant's direction so a future edit can't silently
        # make every research buy always reveal a region.
        assert 0.0 < REGIONAL_SIGNAL_CHANCE < 1.0


# ── Genre-based amortization (replaces the old network-based split) ─────────
class TestGenreBasedAmortization:
    """Zach Schlessel's feedback, 2026-07-27: amortization is genre-based
    for linear content now (True Crime vs. everything else), not
    network-based (Oxygen=36mo/Bravo=12mo as it used to be). Peacock/SVOD
    stays a uniform 36mo regardless of genre -- a distinct accounting
    convention, not a genre distinction."""

    def test_true_crime_linear_show_gets_the_true_crime_window(self):
        s = _show(genre="True Crime")
        assert s.effective_amort_months() == TRUE_CRIME_AMORT_MONTHS

    def test_non_true_crime_linear_show_gets_the_standard_linear_window(self):
        for genre in ("Reality", "Competition", "Talk", "Scripted", "Comedy", "Drama"):
            s = _show(genre=genre)
            assert s.effective_amort_months() == AMORT_MONTHS_LINEAR

    def test_peacock_show_stays_36_months_regardless_of_genre(self):
        for genre in ("True Crime", "Reality", "Scripted"):
            s = Show(id=1, name="Peacock Show", genre=genre, episodes=10, ep_cost_k=300,
                      rating=0.8, ip_score=60, air_month=1, network="Peacock")
            assert s.effective_amort_months() == AMORT_MONTHS_SVOD

    def test_annual_amort_expense_scales_with_the_effective_window(self):
        # $10M total production cost: over 24mo -> $5M/yr; over 12mo -> $10M/yr.
        true_crime = Show(id=1, name="TC", genre="True Crime", episodes=10, ep_cost_k=1000,
                            rating=1.0, ip_score=50, air_month=1, network="Oxygen")
        other = Show(id=2, name="Other", genre="Reality", episodes=10, ep_cost_k=1000,
                      rating=1.0, ip_score=50, air_month=1, network="Oxygen")
        assert true_crime.annual_amort_expense(1) == pytest.approx(5.0)
        assert other.annual_amort_expense(1) == pytest.approx(10.0)

    def test_oxygen_slate_amortization_change_leaves_a_large_margin_cushion(self):
        # Regression guard for the calibration check done before shipping
        # this change: Oxygen's amortization cost rose ~71% (True-Crime-
        # heavy slate moving from a uniform 36mo to a 24mo/12mo split), but
        # distribution_revenue() isn't network-scoped and dominates Oxygen's
        # P&L, so the actual OCF-margin impact is small relative to the 12%
        # pass threshold. This test pins that the margin stays comfortably
        # above threshold at realistic marketing spend -- if a future
        # change to the revenue model shrinks that cushion, this should
        # fail loudly rather than silently making Oxygen unpassable.
        from utils.data import OXYGEN_SLATE
        from utils.models import portfolio_ad_rev, distribution_revenue
        mkt = 5.0
        year = 1
        total_rev = portfolio_ad_rev(OXYGEN_SLATE, year, mkt) + distribution_revenue(year)
        cost = sum(s.annual_amort_expense(year) for s in OXYGEN_SLATE)
        ga = total_rev * 0.06
        margin = (total_rev - cost - mkt - ga) / total_rev * 100
        assert margin > 12.0 * 3   # comfortable cushion, not a knife-edge pass


class TestMinimumMarketing:
    def test_threshold_constant_is_reasonable(self):
        # Sanity guard, not a business-logic test -- catches an accidental
        # unit error (e.g. $3 instead of $3.0M) more than anything subtle.
        assert 0 < MIN_MARKETING_PER_SHOW_M < 50


# ── Production-risk event ────────────────────────────────────────────────────
class TestProductionRiskEvent:
    def test_reproducible_for_same_team_show_year(self):
        a = draw_production_risk_event("Team Echo", 2, 501)
        b = draw_production_risk_event("Team Echo", 2, 501)
        assert a == b

    def test_rare_but_reachable_over_many_draws(self):
        # PRODUCTION_RISK_CHANCE is small by design -- over enough
        # independent (team, year, show_id) combinations, both "no event"
        # and "an event" must be reachable, or the mechanic is either
        # broken (never fires) or miscalibrated (fires too often to be
        # "rare, but real").
        outcomes = [draw_production_risk_event("Team Foxtrot", y, sid)
                    for y in range(1, 6) for sid in range(1000, 1050)]
        fired = [o for o in outcomes if o is not None]
        assert len(fired) > 0
        assert len(fired) < len(outcomes) * 0.5   # nowhere close to a coin flip
        assert all(reason in PRODUCTION_RISK_REASONS for reason in fired)

    def test_independent_of_rating_variance_seed(self):
        # Different show IDs must be able to diverge in whether an event
        # fires, even in the same team/year -- confirms this doesn't
        # collapse onto a single shared draw per team+year the way the
        # rating-variance rng does.
        results = {sid: draw_production_risk_event("Team Golf", 1, sid)
                   for sid in range(2000, 2100)}
        assert len(set(results.values())) > 1

    def test_chance_constant_is_small(self):
        assert 0.0 < PRODUCTION_RISK_CHANCE < 0.15


# ── Mid-year emergency budget shift ──────────────────────────────────────────
class TestEmergencyBudgetShock:
    def test_reproducible_for_same_team_year(self):
        a = draw_emergency_budget_shock("Team Hotel", 3)
        b = draw_emergency_budget_shock("Team Hotel", 3)
        assert a == b

    def test_rare_but_reachable_and_bounded(self):
        outcomes = [draw_emergency_budget_shock("Team India", y) for y in range(1, 200)]
        fired = [o for o in outcomes if o is not None]
        assert len(fired) > 0
        assert len(fired) < len(outcomes) * 0.4
        lo, hi = EMERGENCY_BUDGET_CUT_RANGE
        assert all(lo <= v <= hi for v in fired)

    def test_is_a_network_level_event_not_per_show(self):
        # No show_id parameter at all -- signature-level guard that this
        # stays a once-per-team-per-year draw, not accidentally rolled per
        # show the way production-risk events are.
        import inspect
        params = list(inspect.signature(draw_emergency_budget_shock).parameters)
        assert params == ["team_name", "year"]

    def test_chance_constant_is_small(self):
        assert 0.0 < EMERGENCY_BUDGET_CHANCE < 0.3


# ── Primetime scheduling — real ratings trade-off (2026-07-29) ──────────────
class TestPrimetimeScheduling:
    def test_every_slot_within_bounds(self):
        for d in PRIMETIME_DAYS:
            for h in PRIMETIME_HOURS:
                mult = slot_rating_multiplier(d, h)
                assert SLOT_MULT_FLOOR <= mult <= SLOT_MULT_CEILING

    def test_best_and_worst_slot_hit_the_exact_band_edges(self):
        # The normalization is a linear rescale of the full grid's raw
        # day x hour spread, so the single best combo must hit the ceiling
        # exactly and the single worst must hit the floor exactly.
        vals = [slot_rating_multiplier(d, h) for d in PRIMETIME_DAYS for h in PRIMETIME_HOURS]
        assert max(vals) == pytest.approx(SLOT_MULT_CEILING)
        assert min(vals) == pytest.approx(SLOT_MULT_FLOOR)

    def test_weeknight_primetime_beats_friday_saturday(self):
        # Tue/Wed/Thu 8-9PM should outscore the real "death slot" nights at
        # the same hour -- the actual pedagogical point being taught.
        for h in PRIMETIME_HOURS:
            weeknight_best = max(slot_rating_multiplier(d, h) for d in ("Tue", "Wed", "Thu"))
            weekend_worst  = min(slot_rating_multiplier(d, h) for d in ("Fri", "Sat"))
            assert weeknight_best > weekend_worst

    def test_show_defaults_to_unscheduled_and_neutral(self):
        s = _show()
        assert s.slot_day is None and s.slot_hour is None
        assert s.schedule_multiplier() == 1.0

    def test_schedule_multiplier_matches_slot_rating_multiplier_once_assigned(self):
        s = _show()
        s.slot_day, s.slot_hour = "Tue", "8PM"
        assert s.schedule_multiplier() == slot_rating_multiplier("Tue", "8PM")

    def test_ad_revenue_unaffected_when_unscheduled(self):
        # Backward-compatibility guard: every show built before this feature
        # existed keeps its exact original ad_revenue -- same "zero-effect
        # baseline" precedent as movie_models.py's New IP concept type.
        s = _show()
        baseline = s.rating * 7.0  # REV_PER_RATING_POINT, year 1, no mkt boost
        assert s.ad_revenue(year=1) == pytest.approx(baseline)

    def test_ad_revenue_scales_with_assigned_slot(self):
        s_good = _show(show_id=1)
        s_good.slot_day, s_good.slot_hour = "Tue", "8PM"   # best slot
        s_bad = _show(show_id=2)
        s_bad.slot_day, s_bad.slot_hour = "Sat", "10PM"    # worst slot
        s_none = _show(show_id=3)

        assert s_good.ad_revenue(year=1) > s_none.ad_revenue(year=1) > s_bad.ad_revenue(year=1)
        assert s_good.ad_revenue(year=1) == pytest.approx(s_none.ad_revenue(year=1) * SLOT_MULT_CEILING)
        assert s_bad.ad_revenue(year=1) == pytest.approx(s_none.ad_revenue(year=1) * SLOT_MULT_FLOOR)

    def test_double_booking_a_show_is_representable_but_last_write_wins(self):
        # The grid UI (app_pages/schedule.py) detects and warns on double
        # bookings; at the model level a show simply has one slot at a time,
        # so re-assigning it just overwrites the previous slot cleanly.
        s = _show()
        s.slot_day, s.slot_hour = "Fri", "7PM"
        first = s.schedule_multiplier()
        s.slot_day, s.slot_hour = "Tue", "8PM"
        second = s.schedule_multiplier()
        assert second > first
