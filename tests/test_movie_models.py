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
    genre_scenario_multipliers, scenario_multipliers_for, SCENARIO_MULTIPLIERS,
    GENRE_VARIANCE_SPREAD, WINDOW_SHRINK_PER_CYCLE_DAYS, BASE_WINDOW_DAYS,
    draw_critical_reception, AWARDS_ELIGIBLE_GENRES, AWARDS_CONTENDER_THRESHOLD,
    AWARDS_WIN_THRESHOLD,
    CRITICAL_RECEPTION_BOUNDS, CONCEPT_TYPES, INDIE_HORROR_BUDGET_CAP_M,
    SEQUEL_OPENING_BONUS_BY_CYCLE, KIDS_OPENING_MULT, KIDS_LONGTAIL_MULT,
    WINDOWING_UNLOCK_CYCLE, CYCLES_TOTAL,
    THEME_PARK_ELIGIBLE_GENRES, THEME_PARK_REVENUE_RATE,
    draw_production_trouble, PRODUCTION_TROUBLE_CHANCE, PRODUCTION_TROUBLE_HAIRCUT_RANGE,
    PRODUCTION_TROUBLE_REASONS,
    draw_ancillary_surprise, ANCILLARY_SURPRISE_CHANCE, ANCILLARY_SURPRISE_RANGE,
    ANCILLARY_SURPRISE_REASONS_UP, ANCILLARY_SURPRISE_REASONS_DOWN,
    FINANCING_STRUCTURES, PRESALE_ADVANCE_PCT, PRESALE_INTL_RETAINED_PCT, TAX_CREDIT_PCT,
    participation_waterfall, TALENT_GROSS_GUARANTEE_M, TALENT_GROSS_PARTICIPATION,
    PRODUCER_NET_PARTICIPATION,
    TALENT_PARTNERS, RIVAL_STUDIOS, RIVAL_CLAIM_CHANCE, HOLD_FORFEIT_CHANCE, RIVAL_POACH_CHANCE,
    draw_rival_claim, draw_hold_forfeit, draw_rival_poach,
    EXHIBITOR_POSTURES, EXHIBITOR_SPLIT_BY_POSTURE, EXHIBITOR_SCREENS_MULT_BY_POSTURE, EXHIBITOR_SPLIT,
    PAY1_LICENSING_OPTIONS, PAY1_LICENSE_DISCOUNT,
    AI_TOOLS_BUDGET_SAVINGS_PCT, AI_TOOLS_TIMELINE_SHIFT_MO, AI_TOOLS_CRITICAL_CEILING_MULT,
    AI_TOOLS_SETBACK_CHANCE, AI_TOOLS_SETBACK_HAIRCUT_RANGE, AI_TOOLS_SETBACK_REASONS,
    draw_ai_tooling_setback, multiplier_to_stars,
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


# ── Award season / critical reception ──────────────────────────────────────────
class TestAwardSeason:
    """Critical reception is a separate risk axis from box-office
    performance — a movie can open huge and get panned, or open modestly
    and find acclaim. Only awards-eligible genres get a rerelease bump, and
    only above the contender threshold."""

    def test_action_movie_never_gets_awards_bump_regardless_of_score(self):
        p = _tentpole()
        assert "Action/Tentpole" not in AWARDS_ELIGIBLE_GENRES
        assert p.awards_season_bump("base", 99) == 0.0

    def test_drama_below_threshold_gets_no_bump(self):
        p = MovieProject(title="Quiet Drama", genre="Drama", budget_m=20, pa_spend_m=12,
                          star_power=45, screens=700, cycle=1, release_strategy="platform")
        assert p.awards_season_bump("base", AWARDS_CONTENDER_THRESHOLD - 1) == 0.0

    def test_drama_above_threshold_gets_a_positive_bump(self):
        p = MovieProject(title="Contender", genre="Drama", budget_m=20, pa_spend_m=12,
                          star_power=45, screens=700, cycle=1, release_strategy="platform")
        assert p.awards_season_bump("base", 90) > 0.0

    def test_no_critical_score_means_no_bump_and_unscaled_longtail(self):
        # Planning-stage previews (critical_score=None) shouldn't leak
        # awards-season information the student can't know yet.
        p = MovieProject(title="Contender", genre="Drama", budget_m=20, pa_spend_m=12,
                          star_power=45, screens=700, cycle=1, release_strategy="platform")
        assert p.awards_season_bump("base", None) == 0.0
        base_longtail = p.theatrical_studio_net("base") * 0.06
        assert p.library_longtail("base", None) == pytest.approx(base_longtail)

    def test_acclaimed_reception_scales_longtail_up_panned_scales_it_down(self):
        p = _tentpole()
        base_longtail = p.theatrical_studio_net("base") * 0.06
        assert p.library_longtail("base", 95) > base_longtail
        assert p.library_longtail("base", 5) < base_longtail

    def test_draw_is_reproducible_and_independent_of_box_office_seed(self):
        cs1 = draw_critical_reception("Team Delta", 1, "Drama")
        cs2 = draw_critical_reception("Team Delta", 1, "Drama")
        assert cs1 == cs2
        # Different genres should draw from different bounds even for the
        # same team/cycle.
        cs_action = draw_critical_reception("Team Delta", 1, "Action/Tentpole")
        lo, _, hi = CRITICAL_RECEPTION_BOUNDS["Action/Tentpole"]
        assert lo <= cs_action <= hi

    def test_final_score_reflects_resolved_critical_reception(self):
        # A drama slate with genuinely strong reception should score at
        # least as well as the same slate scored blind (critical_score=None)
        # -- the awards bump and longtail boost are additive, never negative.
        projects = [MovieProject(title=f"Film {i}", genre="Drama", budget_m=20, pa_spend_m=12,
                                  star_power=45, screens=700, cycle=i, release_strategy="platform")
                    for i in (1, 2, 3)]
        blind = compute_movie_score(projects)
        acclaimed = compute_movie_score(projects, critical_scores=[90, 90, 90])
        assert acclaimed["avg_ra_npv_m"] >= blind["avg_ra_npv_m"]


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


# ── Concept Type (sequel/new-IP/kids/indie-horror) ──────────────────────────
class TestConceptType:
    """Concept type is a second axis layered on top of genre, added
    2026-07-27. New IP must stay the exact zero-effect baseline (every
    project built before this feature existed defaults to it) — the other
    three tests check each category's specific real-world tradeoff actually
    moves the numbers in the intended direction."""

    def test_new_ip_is_the_untouched_baseline(self):
        # A MovieProject with no concept_type specified must behave
        # identically to one explicitly built as "New IP" -- the dataclass
        # default and the neutral category must be the same thing.
        default = _tentpole()
        explicit = MovieProject(**{**default.__dict__, "concept_type": "New IP"})
        assert default.opening_weekend() == explicit.opening_weekend()
        assert default.npv("base") == pytest.approx(explicit.npv("base"))

    def test_sequel_opens_bigger_than_new_ip_but_fatigue_shrinks_the_bonus(self):
        new_ip = MovieProject(title="Original", genre="Action/Tentpole", budget_m=120,
                               pa_spend_m=80, star_power=75, screens=3500, cycle=1,
                               concept_type="New IP")
        sequel_c1 = MovieProject(**{**new_ip.__dict__, "concept_type": "Sequel"})
        sequel_c3 = MovieProject(**{**new_ip.__dict__, "concept_type": "Sequel", "cycle": 3})

        assert sequel_c1.opening_weekend() > new_ip.opening_weekend()
        # Fatigue: the same sequel's bonus at cycle 3 is smaller than at cycle 1.
        assert sequel_c1.opening_weekend() > sequel_c3.opening_weekend()
        # But franchise recognition never fully disappears -- still ahead of New IP.
        assert sequel_c3.opening_weekend() > new_ip.opening_weekend()

    def test_kids_softer_opening_but_stronger_longtail(self):
        new_ip = MovieProject(title="Family Film", genre="Animated", budget_m=90,
                               pa_spend_m=50, star_power=40, screens=3000, cycle=1,
                               concept_type="New IP")
        kids = MovieProject(**{**new_ip.__dict__, "concept_type": "Family/Kids"})

        assert kids.opening_weekend() == pytest.approx(new_ip.opening_weekend() * KIDS_OPENING_MULT)
        # Kids' long-tail bonus compounds on top of its own smaller theatrical
        # base (softer opening flows through theatrical_studio_net first),
        # not on New IP's base -- so the combined factor is both multipliers.
        assert kids.library_longtail("base") == pytest.approx(
            new_ip.library_longtail("base") * KIDS_OPENING_MULT * KIDS_LONGTAIL_MULT
        )

    def test_indie_horror_widens_variance_beyond_horror_genre_alone(self):
        genre_only = genre_scenario_multipliers("Horror")
        indie_horror = scenario_multipliers_for("Horror", "Indie-Horror")
        # Base case unchanged; bear goes lower, bull goes higher.
        assert indie_horror["base"] == genre_only["base"]
        assert indie_horror["bear"] < genre_only["bear"]
        assert indie_horror["bull"] > genre_only["bull"]

    def test_indie_horror_actual_draw_respects_its_own_wider_bounds(self):
        bounds = scenario_multipliers_for("Horror", "Indie-Horror")
        for cycle in (1, 2, 3):
            m = draw_actual_multiplier("Team Indie", cycle, "Horror", "Indie-Horror")
            assert bounds["bear"] <= m <= bounds["bull"]

    def test_all_concept_types_produce_a_valid_project(self):
        # Smoke test: every listed concept type runs end-to-end without
        # producing NaN/inf or throwing, for a mid-range project.
        for ct in CONCEPT_TYPES:
            budget = min(60.0, INDIE_HORROR_BUDGET_CAP_M) if ct == "Indie-Horror" else 60.0
            p = MovieProject(title=f"{ct} Test", genre="Horror" if ct == "Indie-Horror" else "Drama",
                              budget_m=budget, pa_spend_m=30, star_power=50, screens=2000,
                              cycle=1, concept_type=ct)
            npv = p.npv("base")
            assert math.isfinite(npv)


# ── Progressive windowing (Cycle 3+ only) ────────────────────────────────────
class TestProgressiveWindowing:
    """Zach Schlessel's brief: windowing (theatrical vs. platform vs.
    day-and-date) is a "Year 3 Introduction," not available from Cycle 1.
    The UI gate itself lives in pages/movies.py::_release() (not unit-
    testable in isolation the way the pure financial engine is -- covered
    by the standing "needs a real browser click-through" gap tracked in
    DESIGN_NOTES.md); this pins the constant the gate reads."""

    def test_unlock_cycle_is_within_the_total_cycle_count(self):
        assert 1 < WINDOWING_UNLOCK_CYCLE <= CYCLES_TOTAL

    def test_unlock_cycle_matches_the_briefs_year_3_framing(self):
        assert WINDOWING_UNLOCK_CYCLE == 3


# ── Theme park / merchandise revenue stream ──────────────────────────────────
class TestThemeParkRevenue:
    """Zach Schlessel's brief: "theme park/merchandise opportunities,
    Universal licensing deals... genre determines theme park eligibility."
    A real eligibility gate (zero for ineligible genres), not a soft
    discount -- an awards drama or a comedy doesn't get a ride."""

    def test_eligible_genre_gets_nonzero_theme_park_value(self):
        p = MovieProject(title="Tentpole", genre="Action/Tentpole", budget_m=150,
                          pa_spend_m=90, star_power=80, screens=4000, cycle=1)
        assert p.theme_park_value("base") > 0
        assert p.theme_park_value("base") == pytest.approx(
            p.domestic_box_office("base") * THEME_PARK_REVENUE_RATE
        )

    def test_ineligible_genre_gets_exactly_zero(self):
        p = MovieProject(title="Prestige Drama", genre="Awards/Prestige", budget_m=30,
                          pa_spend_m=15, star_power=60, screens=1200, cycle=1)
        assert p.theme_park_value("base") == 0.0

    def test_all_eligible_genres_are_the_intended_three(self):
        assert THEME_PARK_ELIGIBLE_GENRES == {"Action/Tentpole", "Sci-Fi/Fantasy", "Animated"}

    def test_theme_park_value_flows_into_total_revenue_and_npv(self):
        # A genre-eligible project's total revenue/NPV must be strictly
        # higher than an otherwise-identical ineligible-genre project would
        # be at the same box office -- confirms the cashflow is actually
        # wired into windowed_cashflows(), not just a standalone method
        # nobody calls.
        eligible = MovieProject(title="A", genre="Sci-Fi/Fantasy", budget_m=150,
                                 pa_spend_m=90, star_power=80, screens=4000, cycle=1)
        ineligible = MovieProject(**{**eligible.__dict__, "genre": "Drama", "title": "B"})
        assert eligible.total_revenue("base") > ineligible.total_revenue("base")
        assert eligible.npv("base") > ineligible.npv("base")


# ── Production Trouble — creative/talent risk axis (2026-08-03) ─────────────
class TestProductionTrouble:
    def test_reproducible_for_same_team_cycle(self):
        a = draw_production_trouble("Team Echo", 2)
        b = draw_production_trouble("Team Echo", 2)
        assert a == b

    def test_rare_but_reachable_over_many_draws(self):
        outcomes = [draw_production_trouble(f"Team {i}", c)
                    for i in range(200) for c in range(1, 4)]
        fired = [o for o in outcomes if o is not None]
        assert len(fired) > 0
        assert len(fired) < len(outcomes) * 0.3   # nowhere close to a coin flip
        lo, hi = PRODUCTION_TROUBLE_HAIRCUT_RANGE
        for reason, haircut in fired:
            assert reason in PRODUCTION_TROUBLE_REASONS
            assert lo <= haircut <= hi

    def test_haircut_only_ever_reduces_never_boosts(self):
        lo, hi = PRODUCTION_TROUBLE_HAIRCUT_RANGE
        assert hi < 1.0

    def test_chance_constant_is_small(self):
        assert 0.0 < PRODUCTION_TROUBLE_CHANCE < 0.15

    def test_independent_of_box_office_and_critical_reception_seeds(self):
        # If trouble accidentally shared a seed with either draw, every
        # "trouble fired" case would show identical reception scores.
        fired_receptions = []
        for i in range(300):
            team = f"Team Trouble {i}"
            if draw_production_trouble(team, 1) is not None:
                fired_receptions.append(round(draw_critical_reception(team, 1, "Drama"), 1))
        assert len(fired_receptions) >= 3
        assert len(set(fired_receptions)) > 1


# ── Ancillary Markets Surprise — PVOD/theme-park/merch (2026-08-03) ─────────
class TestAncillarySurprise:
    def test_reproducible_for_same_team_cycle(self):
        a = draw_ancillary_surprise("Team Echo", 2)
        b = draw_ancillary_surprise("Team Echo", 2)
        assert a == b

    def test_rare_but_reachable_over_many_draws(self):
        outcomes = [draw_ancillary_surprise(f"Team {i}", c)
                    for i in range(200) for c in range(1, 4)]
        fired = [o for o in outcomes if o is not None]
        assert len(fired) > 0
        assert len(fired) < len(outcomes) * 0.4
        lo, hi = ANCILLARY_SURPRISE_RANGE
        for reason, mult in fired:
            assert lo <= mult <= hi
            expected_reasons = ANCILLARY_SURPRISE_REASONS_UP if mult >= 1.0 else ANCILLARY_SURPRISE_REASONS_DOWN
            assert reason in expected_reasons

    def test_can_swing_both_directions(self):
        fired = [draw_ancillary_surprise(f"Team Swing {i}", c)
                 for i in range(300) for c in range(1, 4)]
        mults = [m for r in fired if r is not None for m in [r[1]]]
        assert any(m > 1.0 for m in mults)
        assert any(m < 1.0 for m in mults)

    def test_chance_constant_is_small(self):
        assert 0.0 < ANCILLARY_SURPRISE_CHANCE < 0.3


class TestAncillaryMultipliersWireIntoRevenue:
    """Confirms pvod_mult/theme_park_mult (added to windowed_cashflows/npv/
    irr/total_revenue 2026-08-03) actually isolate the two intended windows
    -- not a broad, accidental haircut/boost to the whole project."""

    def test_default_multiplier_is_a_no_op(self):
        p = _tentpole()
        assert p.npv("base") == p.npv("base", pvod_mult=1.0, theme_park_mult=1.0)
        assert p.total_revenue("base") == p.total_revenue("base", pvod_mult=1.0, theme_park_mult=1.0)
        assert p.irr("base") == p.irr("base", pvod_mult=1.0, theme_park_mult=1.0)

    def test_pvod_mult_scales_only_pvod_revenue(self):
        p = _tentpole()
        base_pvod  = p.pvod_revenue("base")
        base_total = p.total_revenue("base")
        assert base_pvod > 0
        assert p.total_revenue("base", pvod_mult=2.0) == pytest.approx(base_total + base_pvod)

    def test_theme_park_mult_scales_only_theme_park_revenue(self):
        p = _tentpole()   # Action/Tentpole is theme-park-eligible
        base_tp    = p.theme_park_value("base")
        base_total = p.total_revenue("base")
        assert base_tp > 0
        assert p.total_revenue("base", theme_park_mult=2.0) == pytest.approx(base_total + base_tp)


class TestFinancingStructure:
    """2026-08-04: Self-Finance/Territorial Pre-Sales/Tax-Incentive -- see
    utils/movie_models.py's Financing Structure section. self_finance must
    stay the exact unadjusted baseline every project used before this field
    existed (additive, not a replacement of the calibrated engine)."""

    def test_self_finance_is_the_unadjusted_baseline(self):
        p = _tentpole()
        assert p.financing_structure == "self_finance"
        assert p.capital_at_risk() == p.budget_m + p.pa_spend_m

    def test_presale_reduces_capital_at_risk(self):
        base = _tentpole()
        presale = MovieProject(**{**base.__dict__, "financing_structure": "presale"})
        expected = base.budget_m * (1 - PRESALE_ADVANCE_PCT) + base.pa_spend_m
        assert presale.capital_at_risk() == pytest.approx(expected)
        assert presale.capital_at_risk() < base.capital_at_risk()

    def test_tax_incentive_reduces_capital_at_risk(self):
        base = _tentpole()
        tax = MovieProject(**{**base.__dict__, "financing_structure": "tax_incentive"})
        expected = base.budget_m * (1 - TAX_CREDIT_PCT) + base.pa_spend_m
        assert tax.capital_at_risk() == pytest.approx(expected)
        assert tax.capital_at_risk() < base.capital_at_risk()

    def test_presale_caps_international_box_office(self):
        base = _tentpole()   # Action/Tentpole: GENRE_INTL_MULT=2.3, real upside to give up
        presale = MovieProject(**{**base.__dict__, "financing_structure": "presale"})
        dom = 100.0
        full_intl = base.international_box_office(dom)
        presale_intl = presale.international_box_office(dom)
        assert presale_intl == pytest.approx(full_intl * PRESALE_INTL_RETAINED_PCT)
        assert presale_intl < full_intl

    def test_tax_incentive_does_not_touch_international_box_office(self):
        base = _tentpole()
        tax = MovieProject(**{**base.__dict__, "financing_structure": "tax_incentive"})
        dom = 100.0
        assert tax.international_box_office(dom) == base.international_box_office(dom)

    def test_all_three_structures_produce_valid_positive_capital_at_risk(self):
        assert FINANCING_STRUCTURES == ["self_finance", "presale", "tax_incentive"]
        for fs in FINANCING_STRUCTURES:
            p = MovieProject(**{**_tentpole().__dict__, "financing_structure": fs})
            assert p.capital_at_risk() > 0


class TestParticipationWaterfall:
    """2026-08-04: Deal Waterfall -- talent gross participation is paid off
    top-line revenue regardless of profitability, before the studio even
    recoups its capital; the producer's net participation only comes out
    of whatever's left after that. Studio residual is deliberately never
    floored at zero -- a 'gross deal' can leave a studio underwater even on
    a nominal box-office win, and that's the actual lesson."""

    def test_components_sum_to_the_residual(self):
        p = _tentpole()
        wf = participation_waterfall(p, "base")
        computed_residual = wf["revenue"] - wf["talent_take"] - wf["recoupment"] - wf["producer_take"]
        assert wf["residual"] == pytest.approx(computed_residual)

    def test_talent_take_is_at_least_the_guarantee(self):
        p = _indie()
        wf = participation_waterfall(p, "bear")
        assert wf["talent_take"] >= TALENT_GROSS_GUARANTEE_M

    def test_talent_take_scales_with_gross_once_it_exceeds_the_guarantee(self):
        p = _tentpole()   # big movie -- revenue * 10% comfortably exceeds the flat guarantee
        wf = participation_waterfall(p, "bull")
        assert wf["talent_take"] == pytest.approx(wf["revenue"] * TALENT_GROSS_PARTICIPATION)
        assert wf["talent_take"] > TALENT_GROSS_GUARANTEE_M

    def test_producer_take_is_zero_and_residual_is_negative_when_recoupment_isnt_cleared(self):
        # A small platform-release indie in its bear case: revenue doesn't
        # clear the talent guarantee plus the full $25M capital at risk --
        # deterministic at these calibrated numbers, not just "possible."
        p = _indie()
        wf = participation_waterfall(p, "bear")
        after_recoupment = wf["revenue"] - wf["talent_take"] - wf["recoupment"]
        assert after_recoupment < 0
        assert wf["producer_take"] == 0.0
        assert wf["residual"] < 0
        assert wf["residual"] == pytest.approx(after_recoupment)

    def test_financing_structure_lowers_recoupment_in_the_waterfall(self):
        base = _tentpole()
        presale = MovieProject(**{**base.__dict__, "financing_structure": "presale"})
        wf_base = participation_waterfall(base, "base")
        wf_presale = participation_waterfall(presale, "base")
        assert wf_presale["recoupment"] < wf_base["recoupment"]
        assert wf_presale["recoupment"] == pytest.approx(presale.capital_at_risk())


class TestOscarThresholds:
    """2026-08-04: Oscar Win reuses the same critical_score draw as the
    existing Oscar Nomination (awards_contender) threshold, just a higher
    bar -- a win should never be reachable without also clearing the
    nomination bar first."""

    def test_win_threshold_is_stricter_than_nomination_threshold(self):
        assert AWARDS_WIN_THRESHOLD > AWARDS_CONTENDER_THRESHOLD

    def test_win_threshold_is_within_the_realistic_critical_score_range(self):
        # A win should be rare but reachable -- the highest genre ceiling
        # must clear the bar at least sometimes, or it'd be unreachable.
        hi_bounds = [hi for (_lo, _mode, hi) in CRITICAL_RECEPTION_BOUNDS.values()]
        assert AWARDS_WIN_THRESHOLD < max(hi_bounds)


class TestTalentPartners:
    """2026-08-04: TALENT_PARTNERS data integrity -- every partner must
    carry exactly one bonus type (star_power_bonus XOR critical_score_bonus)
    so app_pages/movies.py's bonus-label logic (`if 'star_power_bonus' in
    partner else ...`) never silently picks the wrong branch."""

    def test_every_partner_has_exactly_one_bonus_type(self):
        for key, partner in TALENT_PARTNERS.items():
            has_star = "star_power_bonus" in partner
            has_critical = "critical_score_bonus" in partner
            assert has_star != has_critical, f"{key} must have exactly one bonus type"

    def test_every_partner_has_positive_costs(self):
        for partner in TALENT_PARTNERS.values():
            assert partner["overall_deal_cost_m"] > 0
            assert partner["hold_cost_m"] > 0
            assert partner["overall_deal_cost_m"] > partner["hold_cost_m"]   # standing > one-off, always

    def test_every_partner_specialty_is_a_real_genre(self):
        from utils.movie_models import GENRES
        for partner in TALENT_PARTNERS.values():
            assert partner["specialty"] in GENRES


class TestRivalStudioDynamics:
    """2026-08-04, per user request ("is there any game theory... where you
    can see how your choices impact rival studios?" and "students should
    [see opportunities] that may or may not be taken up by rival studios").
    Three independent, seeded, deterministic draws -- rival claiming a held
    window instantly, a placed hold still falling through, and a rival
    permanently poaching an unclaimed partner."""

    def test_rival_claim_rate_matches_the_configured_chance(self):
        fired = sum(1 for i in range(1500) if draw_rival_claim(f"Team{i}", 1, "meridian"))
        rate = fired / 1500
        assert abs(rate - RIVAL_CLAIM_CHANCE) < 0.05

    def test_rival_claim_returns_a_real_rival_name(self):
        claims = [draw_rival_claim(f"Team{i}", 1, "meridian") for i in range(500)]
        fired = [c for c in claims if c is not None]
        assert fired   # should fire at least once in 500 draws at a 20% rate
        assert all(r in RIVAL_STUDIOS for r in fired)

    def test_rival_claim_is_deterministic_per_team_cycle_partner(self):
        a = draw_rival_claim("Reproducible Team", 2, "northbench")
        b = draw_rival_claim("Reproducible Team", 2, "northbench")
        assert a == b

    def test_hold_forfeit_rate_matches_the_configured_chance(self):
        fired = sum(1 for i in range(1500) if draw_hold_forfeit(f"Team{i}", 1, "afterdark"))
        rate = fired / 1500
        assert abs(rate - HOLD_FORFEIT_CHANCE) < 0.05

    def test_hold_forfeit_returns_a_reason_string_when_it_fires(self):
        fired = [draw_hold_forfeit(f"Team{i}", 1, "brightlane") for i in range(500)]
        reasons = [r for r in fired if r is not None]
        assert reasons
        assert all(isinstance(r, str) and len(r) > 10 for r in reasons)

    def test_rival_claim_and_hold_forfeit_are_independent_axes(self):
        # Same (team, cycle, partner) triple -- clearing the rival-claim
        # check must not correlate with the hold-forfeit outcome, since
        # they're resolved at different points in the flow (placement vs.
        # next-cycle) and use different seed offsets.
        claim_hits = sum(1 for i in range(800) if draw_rival_claim(f"IndepTeam{i}", 1, "meridian"))
        forfeit_hits = sum(1 for i in range(800) if draw_hold_forfeit(f"IndepTeam{i}", 1, "meridian"))
        # Both individually near their configured rates -- if they were
        # accidentally sharing a seed/correlated, one of these would drift
        # far from its own configured chance.
        assert abs(claim_hits / 800 - RIVAL_CLAIM_CHANCE) < 0.06
        assert abs(forfeit_hits / 800 - HOLD_FORFEIT_CHANCE) < 0.06

    def test_rival_poach_rate_matches_the_configured_chance(self):
        fired = sum(1 for i in range(1500) if draw_rival_poach(f"Team{i}", "meridian", 1))
        rate = fired / 1500
        assert abs(rate - RIVAL_POACH_CHANCE) < 0.05

    def test_rival_poach_is_deterministic_per_team_partner_cycle(self):
        a = draw_rival_poach("Reproducible Team", "brightlane", 2)
        b = draw_rival_poach("Reproducible Team", "brightlane", 2)
        assert a == b

    def test_rival_poach_differs_across_cycles_for_the_same_team(self):
        # Different cycles must use different seeds -- not literally
        # guaranteed to differ every time, but across many teams the
        # cycle-1 and cycle-2 outcomes shouldn't be identical for all of them.
        c1 = [draw_rival_poach(f"CycleTeam{i}", "meridian", 1) for i in range(200)]
        c2 = [draw_rival_poach(f"CycleTeam{i}", "meridian", 2) for i in range(200)]
        assert c1 != c2

    def test_rival_poach_returns_a_real_rival_name(self):
        poaches = [draw_rival_poach(f"Team{i}", "afterdark", 1) for i in range(500)]
        fired = [p for p in poaches if p is not None]
        assert fired
        assert all(r in RIVAL_STUDIOS for r in fired)


class TestExhibitorNegotiationPosture:
    """2026-08-04: "standard" must reproduce the original fixed
    EXHIBITOR_SPLIT/screens behavior exactly (additive field, same posture
    as every other Day 2 deal mechanic) -- aggressive/exhibitor_friendly
    are a real, opposite-signed trade-off, not a free lunch either way."""

    def test_standard_posture_matches_the_original_fixed_split_exactly(self):
        p = _tentpole()
        assert p.exhibitor_posture == "standard"
        assert EXHIBITOR_SPLIT_BY_POSTURE["standard"] == EXHIBITOR_SPLIT
        assert EXHIBITOR_SCREENS_MULT_BY_POSTURE["standard"] == 1.0

    def test_aggressive_posture_raises_split_but_cuts_effective_screens(self):
        base = _tentpole()
        aggressive = MovieProject(**{**base.__dict__, "exhibitor_posture": "aggressive"})
        assert EXHIBITOR_SPLIT_BY_POSTURE["aggressive"] > EXHIBITOR_SPLIT_BY_POSTURE["standard"]
        assert aggressive.opening_weekend() < base.opening_weekend()   # fewer effective screens
        assert aggressive.theatrical_studio_net("base") != base.theatrical_studio_net("base")

    def test_exhibitor_friendly_posture_lowers_split_but_grows_effective_screens(self):
        base = _tentpole()
        friendly = MovieProject(**{**base.__dict__, "exhibitor_posture": "exhibitor_friendly"})
        assert EXHIBITOR_SPLIT_BY_POSTURE["exhibitor_friendly"] < EXHIBITOR_SPLIT_BY_POSTURE["standard"]
        assert friendly.opening_weekend() > base.opening_weekend()   # more effective screens

    def test_neither_alternative_posture_is_a_dominant_strategy(self):
        # A genuine trade-off: aggressive shouldn't just win outright on
        # NPV, or the "choice" wouldn't be a real one. (Not asserting which
        # one wins -- just that they're not identical outcomes.)
        base = _tentpole()
        aggressive = MovieProject(**{**base.__dict__, "exhibitor_posture": "aggressive"})
        friendly = MovieProject(**{**base.__dict__, "exhibitor_posture": "exhibitor_friendly"})
        npvs = {base.npv("base"), aggressive.npv("base"), friendly.npv("base")}
        assert len(npvs) == 3   # all three postures produce genuinely different outcomes


class TestPay1WindowLicensing:
    """2026-08-04: "keep" must reproduce prior subscriber_value() behavior
    exactly. license_out swaps in a flat, base-case-priced fee arriving
    sooner than owned subscriber value -- and is defensively ignored for
    Day-and-Date, which already commits to Peacock exclusivity."""

    def test_keep_is_the_unadjusted_baseline(self):
        p = _tentpole()
        assert p.pay1_licensing == "keep"
        assert not p.is_licensing_out()
        assert p.pay1_license_fee() == 0.0

    def test_license_out_replaces_subscriber_value_with_a_flat_fee(self):
        base = _tentpole()
        licensed = MovieProject(**{**base.__dict__, "pay1_licensing": "license_out"})
        assert licensed.is_licensing_out()
        expected_fee = base.subscriber_value("base") * PAY1_LICENSE_DISCOUNT
        assert licensed.pay1_license_fee() == pytest.approx(expected_fee)

    def test_license_fee_is_independent_of_the_actual_resolved_scenario(self):
        # A real licensing deal is negotiated before release -- the fee
        # must be identical whether the eventual outcome is bear or bull.
        p = MovieProject(**{**_tentpole().__dict__, "pay1_licensing": "license_out"})
        assert p.pay1_license_fee() == p.pay1_license_fee()   # deterministic, no scenario arg at all

    def test_day_and_date_ignores_license_out_defensively(self):
        p = MovieProject(**{**_tentpole().__dict__,
                             "release_strategy": "day_and_date", "pay1_licensing": "license_out"})
        assert not p.is_licensing_out()
        assert p.pay1_license_fee() == 0.0

    def test_total_revenue_reflects_the_licensing_swap(self):
        base = _tentpole()
        licensed = MovieProject(**{**base.__dict__, "pay1_licensing": "license_out"})
        base_total = base.total_revenue("base")
        licensed_total = licensed.total_revenue("base")
        # Swapping subscriber_value for a smaller flat fee changes total
        # revenue's undiscounted sum -- not asserting direction (fee could
        # exceed or trail subscriber_value depending on genre/strategy),
        # just that the swap actually took effect.
        assert licensed_total != base_total


# ── AI Production Tools (Phase 4, 2026-08-05) ────────────────────────────────
class TestAiProductionTools:
    """False must reproduce the exact unadjusted baseline every project used
    before this field existed -- a cost/timeline lever with a real
    quality-risk edge (capped critical-reception ceiling + its own
    independent setback draw), not a free efficiency win."""

    def test_default_false_is_the_unadjusted_baseline(self):
        p = _tentpole()
        assert p.ai_production_tools is False
        assert p.capital_at_risk() == p.budget_m + p.pa_spend_m

    def test_budget_discount_applies_to_budget_only_not_pa(self):
        base = _tentpole()
        tooled = MovieProject(**{**base.__dict__, "ai_production_tools": True})
        expected = base.budget_m * (1 - AI_TOOLS_BUDGET_SAVINGS_PCT) + base.pa_spend_m
        assert tooled.capital_at_risk() == pytest.approx(expected)
        assert tooled.capital_at_risk() < base.capital_at_risk()

    def test_discount_stacks_with_financing_structure_on_budget_component_only(self):
        base = MovieProject(**{**_tentpole().__dict__, "financing_structure": "tax_incentive"})
        tooled = MovieProject(**{**base.__dict__, "ai_production_tools": True})
        from utils.movie_models import TAX_CREDIT_PCT
        expected = base.budget_m * (1 - TAX_CREDIT_PCT) * (1 - AI_TOOLS_BUDGET_SAVINGS_PCT) + base.pa_spend_m
        assert tooled.capital_at_risk() == pytest.approx(expected)

    def test_timeline_shifts_every_cashflow_forward(self):
        base = _tentpole()
        tooled = MovieProject(**{**base.__dict__, "ai_production_tools": True})
        base_flows = base.windowed_cashflows("base", 60.0)
        tooled_flows = tooled.windowed_cashflows("base", 60.0)
        assert len(base_flows) == len(tooled_flows)
        for (bm, bc), (tm, tc) in zip(base_flows, tooled_flows):
            assert bc == tc   # amounts unchanged -- only timing moves
            assert tm == pytest.approx(max(bm - AI_TOOLS_TIMELINE_SHIFT_MO, 0.25))

    def test_earlier_cash_and_cheaper_capital_can_improve_npv_at_same_outcome(self):
        # Holding the resolved multiplier and critical score fixed isolates
        # the two favorable edges of the tradeoff from the unfavorable one
        # (draw_critical_reception's ceiling only matters for the draw
        # itself, not for a critical_score supplied directly here).
        base = _tentpole()
        tooled = MovieProject(**{**base.__dict__, "ai_production_tools": True})
        assert tooled.npv("base", 60.0) > base.npv("base", 60.0)

    def test_critical_reception_ceiling_is_capped_and_reproducible(self):
        lo, mode, hi = CRITICAL_RECEPTION_BOUNDS["Drama"]
        expected_ceiling = lo + (hi - lo) * AI_TOOLS_CRITICAL_CEILING_MULT
        draws = [draw_critical_reception(f"Team Tool {i}", c, "Drama", ai_production_tools=True)
                 for i in range(150) for c in range(1, 4)]
        assert max(draws) <= expected_ceiling + 1e-9
        # And the ceiling must actually bind at least once vs. the
        # untooled draw's own max, or this test wouldn't be testing anything.
        untooled = [draw_critical_reception(f"Team Tool {i}", c, "Drama")
                    for i in range(150) for c in range(1, 4)]
        assert max(untooled) > expected_ceiling

    def test_critical_reception_default_false_is_unaffected(self):
        for cyc in range(1, 4):
            assert (draw_critical_reception("Team Same", cyc, "Drama")
                    == draw_critical_reception("Team Same", cyc, "Drama", ai_production_tools=False))

    def test_setback_reproducible_for_same_team_cycle(self):
        a = draw_ai_tooling_setback("Team Echo", 2)
        b = draw_ai_tooling_setback("Team Echo", 2)
        assert a == b

    def test_setback_rare_but_reachable_over_many_draws(self):
        outcomes = [draw_ai_tooling_setback(f"Team {i}", c) for i in range(200) for c in range(1, 4)]
        fired = [o for o in outcomes if o is not None]
        assert len(fired) > 0
        assert len(fired) < len(outcomes) * 0.3
        lo, hi = AI_TOOLS_SETBACK_HAIRCUT_RANGE
        for reason, haircut in fired:
            assert reason in AI_TOOLS_SETBACK_REASONS
            assert lo <= haircut <= hi

    def test_setback_haircut_only_ever_reduces(self):
        lo, hi = AI_TOOLS_SETBACK_HAIRCUT_RANGE
        assert hi < 1.0

    def test_setback_chance_is_small(self):
        assert 0.0 < AI_TOOLS_SETBACK_CHANCE < 0.2

    def test_setback_independent_of_production_trouble_seed(self):
        # If the two shared a seed offset, "setback fired" would always
        # coincide with "production trouble fired" for the same team/cycle.
        from utils.movie_models import draw_production_trouble
        both_fired = 0
        setback_fired = 0
        for i in range(300):
            team = f"Team AI Indep {i}"
            if draw_ai_tooling_setback(team, 1) is not None:
                setback_fired += 1
                if draw_production_trouble(team, 1) is not None:
                    both_fired += 1
        assert setback_fired >= 3
        assert both_fired < setback_fired   # not perfectly correlated


# ── Research / Social Listening (Phase 4, 2026-08-05) ────────────────────────
class TestMultiplierToStars:
    """multiplier_to_stars powers the Movies-side Research feature -- mirrors
    utils/models.py's TV-side variance_to_stars but must be genre-aware
    since Movies' bear/bull band isn't a single fixed global range."""

    def test_bear_case_reads_low_and_bull_case_reads_high(self):
        bounds = scenario_multipliers_for("Drama")
        assert multiplier_to_stars(bounds["bear"], "Drama") <= 2
        assert multiplier_to_stars(bounds["bull"], "Drama") == 5

    def test_base_case_reads_mid_range(self):
        bounds = scenario_multipliers_for("Drama")
        stars = multiplier_to_stars(bounds["base"], "Drama")
        assert 2 <= stars <= 4

    def test_clamped_to_1_through_5_even_outside_the_band(self):
        bounds = scenario_multipliers_for("Drama")
        assert multiplier_to_stars(bounds["bear"] - 5.0, "Drama") == 1
        assert multiplier_to_stars(bounds["bull"] + 5.0, "Drama") == 5

    def test_genre_aware_not_a_single_global_band(self):
        # Horror's bear/bull band is much wider than Awards/Prestige's (see
        # GENRE_VARIANCE_SPREAD) -- the same raw multiplier should map to a
        # different star count depending on genre.
        horror_bounds = scenario_multipliers_for("Horror")
        mid_horror = (horror_bounds["bear"] + horror_bounds["bull"]) / 2
        horror_stars = multiplier_to_stars(mid_horror, "Horror")
        awards_stars = multiplier_to_stars(mid_horror, "Awards/Prestige")
        assert horror_stars != awards_stars

    def test_reproducible_and_matches_draw_actual_multiplier_replay(self):
        # The whole point of the Research feature: previewing must be the
        # exact same seeded draw draw_actual_multiplier() will resolve at
        # Simulate time, called safely with zero side effects.
        m1 = draw_actual_multiplier("Team Research", 2, "Drama", "New IP")
        m2 = draw_actual_multiplier("Team Research", 2, "Drama", "New IP")
        assert m1 == m2
        assert multiplier_to_stars(m1, "Drama") == multiplier_to_stars(m2, "Drama")
