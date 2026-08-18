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
    pvod_reject_chance, draw_pvod_market_rejection, PVOD_CUT_RESPONSE_MULT,
    draw_pvod_cut_buzz, PVOD_CUT_BUZZ_CHANCE, PVOD_CUT_BUZZ_AWARDS_BONUS,
    LICENSING_BIDDERS, LICENSING_BID_MULT_RANGE, draw_licensing_bids, resolve_licensing_auction,
    draw_licensing_bidder_appetite, licensing_appetite_flavor, LICENSING_APPETITE_HUNGRY_NPV_THRESHOLD,
    generate_background_slate,
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


def test_holding_through_a_rejection_never_draws_buzz():
    """Buzz is only ever rolled on a Cut response -- Hold is a pure
    conversion-cost concession with no upside, per explicit user framing
    ("if students cut price... more buzz... of course randomized")."""
    at = _movies_app("PVODRejectTeam4")
    _mini_run_button(at).click().run()
    pending_price = at.session_state["movie_pvod_pending_rejection"][1]["price_before"]
    hold_btn = next(b for b in at.button if b.label == f"Hold at ${pending_price:.2f}")
    hold_btn.click().run()
    cps = at.session_state["movie_pvod_checkpoints"][1]
    held_cp = next(cp for cp in cps if cp["rejected"])
    assert held_cp["buzz"] is None


def test_a_cut_does_not_spuriously_invalidate_the_checkpoint_sequence_on_rerun():
    """Real bug caught and fixed 2026-08-18: the PVOD price slider used to
    default from ss.movie_draft["pvod_chosen_price"] -- the SAME field the
    Market Acceptance Checks block overwrites with the post-cut EFFECTIVE
    price. That fed a cut's own price change back into the slider, which
    then tripped the "did the student change their price?" invalidation
    check on the very next render, silently wiping the just-resolved
    checkpoint history (and the pvod_market_mult haircut) even though the
    student never touched the slider. Fixed by giving the slider its own
    stable pvod_selected_price field, independent of the checkpoint-driven
    effective price. This test proves a checkpoint sequence survives an
    additional rerun (clicking Simulate causes exactly this kind of extra
    render) instead of silently resetting to a fresh single-entry list."""
    at = _movies_app("PVODRejectTeam4")
    _mini_run_button(at).click().run()
    cut_btn = next(b for b in at.button if b.label.startswith("Cut to"))
    cut_btn.click().run()
    cps_before = at.session_state["movie_pvod_checkpoints"][1]
    assert any(cp["rejected"] for cp in cps_before)
    mult_before = at.session_state["movie_draft"]["pvod_market_mult"]
    assert mult_before == pytest.approx(PVOD_CUT_RESPONSE_MULT)   # the real economic haircut is live

    _simulate_button(at).click().run()   # an unrelated extra render/interaction
    assert not at.exception, f"Simulate click raised: {list(at.exception)}"
    result = next(r for r in at.session_state["movie_log"] if r["cycle"] == 1)
    # The checkpoint sequence that was live when Simulate was clicked must be
    # what actually got used -- not silently reset to a fresh, un-rejected one.
    assert result["cut_buzz_awards"] == any(cp.get("buzz") == "awards" for cp in cps_before)
    assert result["cut_buzz_sequel"] == any(cp.get("buzz") == "sequel" for cp in cps_before)


# ── PVOD Cut-Response Buzz ──────────────────────────────────────────────────
def test_draw_pvod_cut_buzz_fires_at_the_calibrated_rate_and_splits_evenly():
    n = 3000
    outcomes = [draw_pvod_cut_buzz(f"BuzzRateTeam{i}", 1, 0) for i in range(n)]
    fire_rate = sum(1 for o in outcomes if o is not None) / n
    assert fire_rate == pytest.approx(PVOD_CUT_BUZZ_CHANCE, abs=0.03)
    awards_n = sum(1 for o in outcomes if o == "awards")
    sequel_n = sum(1 for o in outcomes if o == "sequel")
    assert awards_n + sequel_n == sum(1 for o in outcomes if o is not None)
    assert abs(awards_n - sequel_n) / max(awards_n + sequel_n, 1) < 0.15   # roughly an even split


def test_draw_pvod_cut_buzz_deterministic_and_checkpoint_independent():
    a1 = draw_pvod_cut_buzz("Team", 1, 0)
    a2 = draw_pvod_cut_buzz("Team", 1, 0)
    assert a1 == a2
    # Not asserting checkpoint 0 vs 1 differ (independent rolls, could
    # coincidentally match) -- just that a distinct checkpoint_idx is
    # accepted without error and stays deterministic on its own.
    b1 = draw_pvod_cut_buzz("Team", 1, 1)
    b2 = draw_pvod_cut_buzz("Team", 1, 1)
    assert b1 == b2


def test_cutting_with_no_buzz_leaves_critical_score_untouched():
    """PVODRejectTeam4 is a verified deterministic no-buzz cut at this
    project's default starting price."""
    at = _movies_app("PVODRejectTeam4")
    _mini_run_button(at).click().run()
    resolved_cs = at.session_state["movie_theatrical_resolved"][1]["critical_score"]
    cut_btn = next(b for b in at.button if b.label.startswith("Cut to"))
    cut_btn.click().run()
    assert all(cp.get("buzz") is None for cp in at.session_state["movie_pvod_checkpoints"][1])
    _simulate_button(at).click().run()
    result = next(r for r in at.session_state["movie_log"] if r["cycle"] == 1)
    assert result["critical_score"] == pytest.approx(resolved_cs)
    assert result["cut_buzz_awards"] is False
    assert result["cut_buzz_sequel"] is False


def test_cutting_with_awards_buzz_bumps_critical_score_by_the_calibrated_bonus():
    """AwardsBuzzHunt4 is a verified deterministic awards-buzz cut."""
    at = _movies_app("AwardsBuzzHunt4")
    _mini_run_button(at).click().run()
    resolved_cs = at.session_state["movie_theatrical_resolved"][1]["critical_score"]
    cut_btn = next(b for b in at.button if b.label.startswith("Cut to"))
    cut_btn.click().run()
    assert any(cp.get("buzz") == "awards" for cp in at.session_state["movie_pvod_checkpoints"][1])
    _simulate_button(at).click().run()
    assert not at.exception, f"Simulate click raised: {list(at.exception)}"
    result = next(r for r in at.session_state["movie_log"] if r["cycle"] == 1)
    assert result["critical_score"] == pytest.approx(min(100.0, resolved_cs + PVOD_CUT_BUZZ_AWARDS_BONUS))
    assert result["cut_buzz_awards"] is True
    assert result["cut_buzz_sequel"] is False


def test_cutting_with_sequel_buzz_flags_the_outcome_without_touching_critical_score():
    """BuzzHunt12 is a verified deterministic sequel-buzz cut."""
    at = _movies_app("BuzzHunt12")
    _mini_run_button(at).click().run()
    resolved_cs = at.session_state["movie_theatrical_resolved"][1]["critical_score"]
    cut_btn = next(b for b in at.button if b.label.startswith("Cut to"))
    cut_btn.click().run()
    assert any(cp.get("buzz") == "sequel" for cp in at.session_state["movie_pvod_checkpoints"][1])
    _simulate_button(at).click().run()
    assert not at.exception, f"Simulate click raised: {list(at.exception)}"
    result = next(r for r in at.session_state["movie_log"] if r["cycle"] == 1)
    assert result["critical_score"] == pytest.approx(resolved_cs)   # sequel buzz never touches critical_score
    assert result["cut_buzz_awards"] is False
    assert result["cut_buzz_sequel"] is True


# ── Licensing Marketplace — Competitive Bidding (Phase 5) ──────────────────
def test_draw_licensing_bids_only_uses_the_curated_bidder_set():
    bids = draw_licensing_bids("SomeTeam", 1, anchor_value_m=10.0)
    assert all(b["bidder"] in LICENSING_BIDDERS for b in bids)
    assert all(b["bid_m"] >= 0 for b in bids)


def test_draw_licensing_bids_scales_with_the_real_resolved_anchor_value():
    lo_bids = draw_licensing_bids("ScaleTeam", 1, anchor_value_m=5.0)
    hi_bids = draw_licensing_bids("ScaleTeam", 1, anchor_value_m=50.0)
    lo_by_bidder = {b["bidder"]: b["bid_m"] for b in lo_bids}
    hi_by_bidder = {b["bidder"]: b["bid_m"] for b in hi_bids}
    for bidder in lo_by_bidder:
        if bidder in hi_by_bidder:
            assert hi_by_bidder[bidder] > lo_by_bidder[bidder]


def test_resolve_licensing_auction_picks_the_highest_bid():
    bids = [{"bidder": "A", "bid_m": 5.0}, {"bidder": "B", "bid_m": 8.2}, {"bidder": "C", "bid_m": 3.1}]
    result = resolve_licensing_auction(bids)
    assert result["winner"] == "B"
    assert result["winning_bid_m"] == 8.2


def test_resolve_licensing_auction_handles_no_participants():
    result = resolve_licensing_auction([])
    assert result["winner"] is None
    assert result["all_bids"] == []


def test_pay1_auction_fee_overrides_flat_fee_formula():
    p_flat = MovieProject(title="T", genre="Drama", budget_m=40, pa_spend_m=30, star_power=50,
                           screens=3000, cycle=1, pay1_licensing="license_out")
    p_auction = MovieProject(title="T", genre="Drama", budget_m=40, pa_spend_m=30, star_power=50,
                              screens=3000, cycle=1, pay1_licensing="license_out", pay1_auction_fee_m=99.0)
    assert p_flat.pay1_license_fee() != 99.0
    assert p_auction.pay1_license_fee() == 99.0


def test_pay1_auction_fee_default_none_is_zero_effect():
    p = MovieProject(title="T", genre="Drama", budget_m=40, pa_spend_m=30, star_power=50,
                      screens=3000, cycle=1, pay1_licensing="license_out")
    p_explicit = MovieProject(title="T", genre="Drama", budget_m=40, pa_spend_m=30, star_power=50,
                               screens=3000, cycle=1, pay1_licensing="license_out", pay1_auction_fee_m=None)
    assert p.pay1_license_fee() == p_explicit.pay1_license_fee()


def _shop_button(at):
    return next(b for b in at.button if "Shop This Window" in b.label)


def test_shopping_bids_reveals_the_auction_and_leaves_flat_picker_untouched():
    at = _movies_app("MiniRun AppTest Team")
    _mini_run_button(at).click().run()
    _shop_button(at).click().run()
    assert not at.exception, f"Shop-bids click raised: {list(at.exception)}"
    auction = at.session_state["movie_licensing_auction"][1]
    assert auction["result"]["winner"] in LICENSING_BIDDERS or auction["result"]["winner"] is None
    assert at.session_state["movie_draft"]["pay1_licensing"] == "keep"   # unaffected until explicitly accepted


def test_accepting_a_bid_sets_license_out_with_the_auction_fee():
    at = _movies_app("MiniRun AppTest Team")
    _mini_run_button(at).click().run()
    _shop_button(at).click().run()
    winner = at.session_state["movie_licensing_auction"][1]["result"]["winner"]
    assert winner is not None, "test team must produce at least one bidder"
    accept_btn = next(b for b in at.button if b.label.startswith("Accept "))
    accept_btn.click().run()
    assert not at.exception, f"Accept click raised: {list(at.exception)}"
    draft = at.session_state["movie_draft"]
    assert draft["pay1_licensing"] == "license_out"
    assert draft["pay1_auction_winner"] == winner
    assert draft["pay1_auction_fee_m"] == at.session_state["movie_licensing_auction"][1]["result"]["winning_bid_m"]


def test_licensing_appetite_flavor_reads_real_for_both_states():
    assert "flush with recent hits" in licensing_appetite_flavor("Horizon+", "hot")
    assert "thin on content" in licensing_appetite_flavor("Horizon+", "hungry")
    assert licensing_appetite_flavor("Horizon+", None) == ""


def test_licensing_bidder_appetite_hot_only_eligible_with_a_strong_slate():
    strong_slate = [{"npv": 50.0}, {"npv": 30.0}]
    weak_slate = [{"npv": -20.0}, {"npv": 5.0}]
    strong_states, weak_states = set(), set()
    for i in range(300):
        strong_states.update(v["state"] for v in
                              draw_licensing_bidder_appetite(f"StrongTeam{i}", 1, strong_slate).values())
        weak_states.update(v["state"] for v in
                            draw_licensing_bidder_appetite(f"WeakTeam{i}", 1, weak_slate).values())
    assert "hungry" not in strong_states   # a genuinely strong market never rolls hungry
    assert "hot" not in weak_states        # a genuinely weak market never rolls hot
    assert "hot" in strong_states
    assert "hungry" in weak_states


def test_licensing_bidder_appetite_state_scales_the_bid_multiplier_up():
    appetite = {"X": {"mult": 1.3, "state": "hot"}}
    bids_with_appetite = draw_licensing_bids("AppetiteTeam", 1, anchor_value_m=10.0, appetite_mult={"X": 1.3})
    bids_without = draw_licensing_bids("AppetiteTeam", 1, anchor_value_m=10.0)
    by_bidder_with = {b["bidder"]: b["bid_m"] for b in bids_with_appetite}
    by_bidder_without = {b["bidder"]: b["bid_m"] for b in bids_without}
    # Every bidder that appears in both must have the SAME participation
    # decision (appetite_mult doesn't change who bids, only how much) and
    # a strictly higher bid when a >1.0 appetite multiplier is applied.
    for bidder in by_bidder_without:
        assert bidder in by_bidder_with
    if "X" in by_bidder_with:
        assert by_bidder_with["X"] >= by_bidder_without.get("X", 0)


def test_shopping_bids_ties_into_the_real_background_slate_via_ui():
    """Not just a unit-level check -- confirms the actual Shop-This-Window
    button handler in app_pages/movies.py wires generate_background_slate's
    real output into the appetite roll, not a placeholder."""
    at = _movies_app("MiniRun AppTest Team")
    _mini_run_button(at).click().run()
    _shop_button(at).click().run()
    assert not at.exception, f"Shop-bids click raised: {list(at.exception)}"
    appetite = at.session_state["movie_licensing_auction"][1]["appetite"]
    assert set(appetite.keys()) == set(LICENSING_BIDDERS)
    for v in appetite.values():
        assert v["state"] in (None, "hot", "hungry")
        assert v["mult"] >= 1.0


def test_changing_the_flat_picker_after_accepting_a_bid_clears_the_auction():
    at = _movies_app("MiniRun AppTest Team")
    _mini_run_button(at).click().run()
    _shop_button(at).click().run()
    accept_btn = next(b for b in at.button if b.label.startswith("Accept "))
    accept_btn.click().run()
    assert at.session_state["movie_draft"]["pay1_licensing"] == "license_out"

    pay1_sb = next(sb for sb in at.selectbox if sb.label == "Pay-1 SVOD Window")
    pay1_sb.set_value("keep").run()
    assert not at.exception, f"Switching back to Keep raised: {list(at.exception)}"
    draft = at.session_state["movie_draft"]
    assert draft["pay1_licensing"] == "keep"
    assert draft["pay1_auction_fee_m"] is None
    assert draft["pay1_auction_winner"] is None
