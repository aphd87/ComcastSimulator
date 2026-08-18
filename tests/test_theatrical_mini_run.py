"""
Theatrical Mini-Run (Phase 1, 2026-08-18) -- see DESIGN_NOTES.md.

Two things this file exists to prove:
1. The continuous day-count run-length math (run_days_box_office_mult /
   MovieProject.window_days / MovieProject.domestic_box_office) reproduces
   the pre-existing Short/Standard/Extended tier calibration exactly at
   the three anchor day counts, and behaves sensibly off them.
2. The Theatrical Mini-Run's "resolve now, reuse later" design is
   PROVABLY consistent, not just probably -- _resolve_movie_outcome is the
   single function both the mini-run button and the final Simulate button
   call, so calling it twice for the same locked Greenlight inputs must
   return identical numbers.

See tests/test_movies_page.py's own module docstring for why the AppTest
interactions below are each a single, fresh `.run()` + one click -- a
second interaction after an earlier st.rerun()-triggered rerun is a known,
already-diagnosed AppTest limitation in this Streamlit version, unrelated
to this feature.
"""
import pytest
from streamlit.testing.v1 import AppTest

import utils.game_state as gs
from utils.movie_models import (
    MovieProject, THEATRICAL_RUN_LENGTHS, RUN_LENGTH_BOX_OFFICE_MULT,
    RUN_LENGTH_DAYS_MIN, RUN_LENGTH_DAYS_MAX, run_days_box_office_mult,
    PVOD_PRICE, pvod_price_band, PVOD_BAND_FLOOR_RANGE, PVOD_BAND_CEIL_RANGE,
    PVOD_MARKET_CHECK_MONTHS, PVOD_REJECT_CHANCE_AT_FLOOR, PVOD_REJECT_CHANCE_AT_CEILING,
    pvod_reject_chance, draw_pvod_market_rejection,
)
from app_pages.movies import _resolve_movie_outcome


@pytest.fixture(autouse=True)
def isolated_leaderboard(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    yield


# ── Continuous run-length math ──────────────────────────────────────────────
def test_run_days_box_office_mult_matches_tier_anchors_exactly():
    for tier, days in THEATRICAL_RUN_LENGTHS.items():
        assert run_days_box_office_mult(days) == pytest.approx(RUN_LENGTH_BOX_OFFICE_MULT[tier])


def test_run_days_box_office_mult_is_monotonic_between_anchors():
    vals = [run_days_box_office_mult(d) for d in range(RUN_LENGTH_DAYS_MIN, RUN_LENGTH_DAYS_MAX + 1)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))   # non-decreasing across the whole range


def test_run_days_box_office_mult_clamps_beyond_bounds():
    assert run_days_box_office_mult(1) == run_days_box_office_mult(RUN_LENGTH_DAYS_MIN)
    assert run_days_box_office_mult(9999) == run_days_box_office_mult(RUN_LENGTH_DAYS_MAX)


def _project(**overrides):
    kwargs = dict(title="T", genre="Drama", budget_m=40.0, pa_spend_m=30.0,
                  star_power=50, screens=3000, cycle=1)
    kwargs.update(overrides)
    return MovieProject(**kwargs)


def test_window_days_priority_days_over_tier_over_auto():
    auto = _project()
    tier = _project(theatrical_run_length="Extended")
    days = _project(theatrical_run_length="Extended", theatrical_run_days=21)   # days should win
    assert days.window_days() == 21
    assert tier.window_days() == THEATRICAL_RUN_LENGTHS["Extended"]
    assert auto.window_days() != 21 and auto.window_days() != THEATRICAL_RUN_LENGTHS["Extended"]


def test_domestic_box_office_days_matches_tier_at_each_anchor():
    for tier, days in THEATRICAL_RUN_LENGTHS.items():
        p_tier = _project(theatrical_run_length=tier)
        p_days = _project(theatrical_run_days=days)
        assert p_days.domestic_box_office("base") == pytest.approx(p_tier.domestic_box_office("base"))


def test_theatrical_run_days_default_none_is_zero_effect():
    p_default = _project()
    p_explicit_none = _project(theatrical_run_length=None, theatrical_run_days=None)
    assert p_default.domestic_box_office("base") == p_explicit_none.domestic_box_office("base")
    assert p_default.window_days() == p_explicit_none.window_days()


# ── _resolve_movie_outcome determinism/reuse guarantee ──────────────────────
class _FakeSS(dict):
    """Minimal double supporting both dict-style and attribute-style
    access, same as Streamlit's real SessionState -- enough for
    _active_talent_bonus/_resolve_movie_outcome's own attribute accesses."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


def _fake_ss(team_name="ConsistencyTeam", cycle=1):
    return _FakeSS(team_name=team_name, movie_cycle=cycle, movie_overall_deal=None,
                   movie_talent_holds={}, movie_multi_picture_deals={}, movie_rival_exclusive={})


def test_resolve_movie_outcome_is_deterministic_across_calls():
    """The core proof the Theatrical Mini-Run -> Simulate flow is safe:
    calling _resolve_movie_outcome twice for the SAME locked Greenlight
    inputs (as the mini-run button and the Simulate button each do) must
    return identical numbers -- not just close, exactly equal, since every
    underlying draw is a pure function of these same inputs."""
    ss = _fake_ss()
    project = _project(genre="Action/Tentpole", concept_type="Sequel", ai_production_tools=True)
    first = _resolve_movie_outcome(ss, project)
    second = _resolve_movie_outcome(ss, project)
    assert first == second


def test_resolve_movie_outcome_locked_inputs_reflect_the_real_dependency_set():
    ss = _fake_ss()
    project = _project(genre="Horror", concept_type="New IP", ai_production_tools=False,
                        source_material="Book")
    result = _resolve_movie_outcome(ss, project)
    assert result["locked_inputs"] == {
        "genre": "Horror", "concept_type": "New IP",
        "ai_production_tools": False, "source_material": "Book",
    }


def test_resolve_movie_outcome_differs_across_different_teams():
    """Sanity check the draws are actually seeded off team_name -- not a
    hardcoded constant that would make the determinism test above vacuous."""
    project = _project()
    a = _resolve_movie_outcome(_fake_ss(team_name="Team Alpha"), project)
    b = _resolve_movie_outcome(_fake_ss(team_name="Team Beta"), project)
    assert (a["multiplier"], a["critical_score"]) != (b["multiplier"], b["critical_score"])


# ── AppTest: the actual UI gate (single-interaction, per this file's own
# documented AppTest limitation -- see module docstring) ───────────────────
def _movies_app_script(team_name):
    import streamlit as st
    import sys
    sys.path.insert(0, ".")
    st.session_state.team_name = team_name
    import app_pages.movies as movies
    movies.render()


def _movies_app(team_name="MiniRun AppTest Team") -> AppTest:
    at = AppTest.from_function(_movies_app_script, default_timeout=30, args=(team_name,))
    at.run()
    assert not at.exception, f"Decisions phase raised: {list(at.exception)}"
    return at


def _simulate_button(at):
    return next(b for b in at.button if "Simulate" in b.label and "Theatrical" not in b.label)


def _mini_run_button(at):
    return next(b for b in at.button if "Run Theatrical Simulation" in b.label)


def test_simulate_is_disabled_before_the_mini_run():
    at = _movies_app()
    assert at.session_state["movie_theatrical_resolved"] == {}
    assert _simulate_button(at).disabled is True


def test_running_the_mini_run_locks_in_a_result_and_unlocks_simulate():
    at = _movies_app()
    _mini_run_button(at).click().run()
    assert not at.exception, f"Mini-run click raised: {list(at.exception)}"
    resolved = at.session_state["movie_theatrical_resolved"].get(1)
    assert resolved is not None
    assert "multiplier" in resolved and "critical_score" in resolved
    assert _simulate_button(at).disabled is False


# ── PVOD Price Band (Phase 2) ────────────────────────────────────────────────
def test_pvod_price_band_matches_flat_baseline_at_reference_price():
    """A project with pvod_chosen_price == PVOD_PRICE must reproduce the
    original flat-price revenue exactly -- the new banded-pricing path
    should never silently drift for a student who happens to land there."""
    default = MovieProject(title="A", genre="Drama", budget_m=40, pa_spend_m=30,
                            star_power=50, screens=3000, cycle=1)
    at_ref = MovieProject(title="A", genre="Drama", budget_m=40, pa_spend_m=30,
                           star_power=50, screens=3000, cycle=1, pvod_chosen_price=PVOD_PRICE)
    assert default.pvod_revenue_tiers("base") == pytest.approx(at_ref.pvod_revenue_tiers("base"))


def test_pvod_price_band_ceiling_exceeds_floor_across_full_multiplier_range():
    bounds_probe = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, -0.5]   # includes out-of-band multipliers (clamped)
    for m in bounds_probe:
        lo, hi = pvod_price_band(m, "Drama")
        assert lo < hi
        assert PVOD_BAND_FLOOR_RANGE[0] <= lo <= PVOD_BAND_FLOOR_RANGE[1]
        assert PVOD_BAND_CEIL_RANGE[0] <= hi <= PVOD_BAND_CEIL_RANGE[1]


def test_pvod_price_band_widens_and_shifts_up_for_stronger_performance():
    from utils.movie_models import scenario_multipliers_for
    b = scenario_multipliers_for("Drama")
    lo_weak, hi_weak = pvod_price_band(b["bear"], "Drama")
    lo_strong, hi_strong = pvod_price_band(b["bull"], "Drama")
    assert lo_strong > lo_weak
    assert hi_strong > hi_weak


def test_pvod_chosen_price_higher_than_default_none_is_zero_effect():
    p = MovieProject(title="A", genre="Drama", budget_m=40, pa_spend_m=30,
                      star_power=50, screens=3000, cycle=1, pvod_chosen_price=None)
    p_explicit_default = MovieProject(title="A", genre="Drama", budget_m=40, pa_spend_m=30,
                                       star_power=50, screens=3000, cycle=1)
    assert p.pvod_revenue_tiers("base") == p_explicit_default.pvod_revenue_tiers("base")


def test_pvod_slider_appears_only_after_mini_run_resolves():
    at = _movies_app()
    assert not any("PVOD Rental Price" in s.label for s in at.slider)
    _mini_run_button(at).click().run()
    assert not at.exception, f"Mini-run click raised: {list(at.exception)}"
    assert any("PVOD Rental Price" in s.label for s in at.slider)


# ── Early Licensing Decision (Phase 3) ──────────────────────────────────────
def test_pay1_licensing_selectbox_appears_only_after_mini_run_resolves():
    at = _movies_app()
    assert not any("Pay-1 SVOD Window" in sb.label for sb in at.selectbox)
    _mini_run_button(at).click().run()
    assert not at.exception, f"Mini-run click raised: {list(at.exception)}"
    assert any("Pay-1 SVOD Window" in sb.label for sb in at.selectbox)


# ── PVOD Market Acceptance Checks (Phase 4) ─────────────────────────────────
def test_pvod_reject_chance_matches_calibrated_endpoints():
    assert pvod_reject_chance(0.0) == pytest.approx(PVOD_REJECT_CHANCE_AT_FLOOR)
    assert pvod_reject_chance(1.0) == pytest.approx(PVOD_REJECT_CHANCE_AT_CEILING)
    assert pvod_reject_chance(0.5) == pytest.approx(
        (PVOD_REJECT_CHANCE_AT_FLOOR + PVOD_REJECT_CHANCE_AT_CEILING) / 2)


def test_draw_pvod_market_rejection_rate_is_higher_near_ceiling():
    n = 2000
    lo_rate = sum(draw_pvod_market_rejection(f"LoTeam{i}", 1, 0, 0.0) for i in range(n)) / n
    hi_rate = sum(draw_pvod_market_rejection(f"HiTeam{i}", 1, 0, 1.0) for i in range(n)) / n
    assert lo_rate < 0.10
    assert hi_rate > 0.45
    assert hi_rate > lo_rate


def test_draw_pvod_market_rejection_deterministic_and_checkpoint_independent():
    a1 = draw_pvod_market_rejection("Team", 1, 0, 0.7)
    a2 = draw_pvod_market_rejection("Team", 1, 0, 0.7)
    assert a1 == a2   # deterministic
    # Not asserting the two checkpoints differ (they're independent rolls,
    # could coincidentally match) -- just that the function accepts a
    # distinct checkpoint_idx without erroring and stays deterministic.
    b1 = draw_pvod_market_rejection("Team", 1, 1, 0.7)
    b2 = draw_pvod_market_rejection("Team", 1, 1, 0.7)
    assert b1 == b2


def test_pvod_market_checks_accept_both_and_leave_simulate_enabled():
    """MiniRun AppTest Team is a verified deterministic double-accept case
    at this project's default (band-midpoint) starting price."""
    at = _movies_app("MiniRun AppTest Team")
    _mini_run_button(at).click().run()
    assert not at.exception, f"Mini-run click raised: {list(at.exception)}"
    cps = at.session_state["movie_pvod_checkpoints"][1]
    assert len(cps) == len(PVOD_MARKET_CHECK_MONTHS)
    assert all(not cp["rejected"] for cp in cps)
    assert at.session_state["movie_pvod_pending_rejection"].get(1) is None
    assert _simulate_button(at).disabled is False


def test_pvod_market_checks_pause_and_gate_simulate_on_rejection():
    """PVODRejectTeam4 is a verified deterministic rejection case at this
    project's default (band-midpoint) starting price."""
    at = _movies_app("PVODRejectTeam4")
    _mini_run_button(at).click().run()
    assert not at.exception, f"Mini-run click raised: {list(at.exception)}"
    pending = at.session_state["movie_pvod_pending_rejection"].get(1)
    assert pending is not None
    assert _simulate_button(at).disabled is True
    assert any(b.label.startswith("Hold at") for b in at.button)
    assert any(b.label.startswith("Cut to") for b in at.button)


def test_holding_through_a_rejection_unlocks_simulate_and_keeps_original_price():
    at = _movies_app("PVODRejectTeam4")
    _mini_run_button(at).click().run()
    pending_price = at.session_state["movie_pvod_pending_rejection"][1]["price_before"]
    hold_btn = next(b for b in at.button if b.label == f"Hold at ${pending_price:.2f}")
    hold_btn.click().run()
    assert not at.exception, f"Hold click raised: {list(at.exception)}"
    assert at.session_state["movie_pvod_pending_rejection"].get(1) is None
    cps = at.session_state["movie_pvod_checkpoints"][1]
    held_cp = next(cp for cp in cps if cp["rejected"])
    assert held_cp["response"] == "hold"
    assert held_cp["price_after"] == pending_price   # holding never changes the price
    assert _simulate_button(at).disabled is False


def test_cutting_at_a_rejection_lowers_the_price_toward_the_floor():
    at = _movies_app("PVODRejectTeam4")
    _mini_run_button(at).click().run()
    pending_price = at.session_state["movie_pvod_pending_rejection"][1]["price_before"]
    cut_btn = next(b for b in at.button if b.label.startswith("Cut to"))
    cut_price = float(cut_btn.label.replace("Cut to $", ""))
    assert cut_price < pending_price   # a cut must actually lower the price
    cut_btn.click().run()
    assert not at.exception, f"Cut click raised: {list(at.exception)}"
    cps = at.session_state["movie_pvod_checkpoints"][1]
    cut_cp = next(cp for cp in cps if cp["rejected"])
    assert cut_cp["response"] == "cut"
    assert cut_cp["price_after"] == pytest.approx(cut_price)
    assert cut_cp["price_after"] < cut_cp["price_before"]
    assert _simulate_button(at).disabled is False
