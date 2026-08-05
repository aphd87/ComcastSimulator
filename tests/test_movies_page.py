"""
Headless test of pages/movies.py using Streamlit's official AppTest harness
(streamlit.testing.v1) — runs the real render() function through a
simulated script session, without a browser.

IMPORTANT — read before extending this file:
A full click-through (Decisions -> Results -> 3 cycles -> Complete ->
Submit) was attempted here and conclusively diagnosed as blocked by a
genuine Streamlit 1.59.2 AppTest limitation, not a bug in
pages/movies.py: any button handler that calls `st.rerun()` (the pattern
used consistently across this entire codebase — pages/simulation.py,
app.py, and pages/movies.py all do `if st.button(...): ss.x = y;
st.rerun()`) corrupts AppTest's widget-state tracking on the *second*
interaction after a phase transition, raising a spurious
KeyError("st.session_state has no key ...") for a widget from the
*previous* phase that's no longer being rendered. Confirmed via a minimal
synthetic repro: removing `st.rerun()` from the repro's button handlers
made the identical two-phase flow test cleanly; adding it back reproduced
the failure every time, regardless of click pattern (chained vs. separate
`.run()`, held references vs. always re-querying `at.button`, an extra
"settle" `.run()` pass, etc. — none of it helped). Changing the app's
`st.rerun()` usage to work around a test-harness bug would make
pages/movies.py inconsistent with the rest of the app for no real user-
facing benefit, so it wasn't changed.

Net effect: a single AppTest `.run()` with no interaction, OR exactly one
click that causes a phase transition (the FIRST interaction, not a
second one after an earlier transition), are the safe zone. The full
multi-cycle click-through still needs a human in a real browser — Claude
in Chrome was not connected for this entire effort (see DESIGN_NOTES.md).
If a future Streamlit upgrade fixes this AppTest bug, more interactive
tests are worth adding — the diagnostic script used to find this is
preserved in this file's git history (see the commit that reduced this
file to its then-current scope).
"""
import pytest
from streamlit.testing.v1 import AppTest

import utils.game_state as gs
from utils.movie_models import TALENT_PARTNERS, RIVAL_STUDIOS


@pytest.fixture(autouse=True)
def isolated_leaderboard(monkeypatch, tmp_path):
    """Never touch the real leaderboard.json from a test run."""
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    yield


def _movies_app() -> AppTest:
    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        st.session_state.team_name = "AppTest Team"
        import app_pages.movies as movies
        movies.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, f"Decisions phase raised: {list(at.exception)}"
    return at


def test_decisions_phase_renders_with_no_exceptions():
    at = _movies_app()
    assert not at.exception


def test_decisions_phase_starts_at_cycle_1():
    at = _movies_app()
    assert at.session_state["movie_phase"] == "decisions"
    assert at.session_state["movie_cycle"] == 1
    assert at.session_state["movie_log"] == []


def test_decisions_phase_has_expected_widgets():
    # Merged 2026-07-27: Greenlight + Release Strategy render on one
    # scrolling page now, ending in a single "Simulate" button. At Cycle
    # 1, windowing is still locked (WINDOWING_UNLOCK_CYCLE=3), so no
    # "Choose <strategy>" buttons are reachable yet. Talent Partnerships
    # (2026-08-04) adds a variable number of Sign/Place Hold buttons
    # (depends on the deterministic-but-not-obvious rival-poach roll for
    # this team/cycle) -- Simulate must still be present and last.
    at = _movies_app()
    assert len(at.number_input) == 3   # budget, P&A, screens
    # genre, concept type, financing structure, exhibitor posture (Greenlight)
    # + Pay-1 licensing (Release Strategy -- shown even at Cycle 1 since
    # "wide_theatrical" != "day_and_date")
    assert len(at.selectbox) == 5
    assert len(at.slider) == 1         # star power
    assert len(at.text_input) == 1     # title
    assert "Simulate" in at.button[-1].label


def test_decisions_phase_shows_bear_base_bull_preview():
    at = _movies_app()
    text = "\n".join(md.value for md in at.markdown)
    for label in ("bear case", "base case", "bull case"):
        assert label in text.lower()


def test_decisions_phase_shows_both_decisions_on_one_page():
    at = _movies_app()
    text = "\n".join(md.value for md in at.markdown)
    assert "Greenlight the Concept" in text
    assert "Release Strategy" in text


def _simulate_button(at):
    """The Simulate button's index shifts now that Talent Partnerships
    (2026-08-04) adds a variable number of Sign/Place Hold buttons before
    it -- find it by label rather than assuming position."""
    return next(b for b in at.button if "Simulate" in b.label)


def test_clicking_simulate_transitions_to_results_with_no_exceptions():
    # Exactly one click, from a fresh session -- the FIRST interaction,
    # not a second one after an earlier phase transition, so this is
    # inside the AppTest safe zone documented at the top of this file.
    at = _movies_app()
    _simulate_button(at).click().run()
    assert not at.exception, f"Simulate click raised: {list(at.exception)}"
    assert at.session_state["movie_phase"] == "results"
    assert len(at.session_state["movie_log"]) == 1
    assert at.session_state["movie_log"][0]["cycle"] == 1


def test_simulate_outcome_includes_financing_and_waterfall_fields():
    # 2026-08-04: default financing_structure (self_finance) and the deal
    # waterfall fields must be present on every real outcome, not just
    # backfilled test fixtures.
    at = _movies_app()
    _simulate_button(at).click().run()
    assert not at.exception
    outcome = at.session_state["movie_log"][0]
    assert outcome["project_kwargs"]["financing_structure"] == "self_finance"
    assert outcome["capital_at_risk"] == outcome["project_kwargs"]["budget_m"] + outcome["project_kwargs"]["pa_spend_m"]
    for key in ("oscar_win", "talent_take", "producer_take", "studio_residual"):
        assert key in outcome
    assert outcome["talent_take"] >= 0
    # residual must equal revenue minus every deducted component -- the
    # actual accounting identity the Deal Waterfall chart depends on.
    computed = (outcome["total_revenue"] - outcome["talent_take"]
                - outcome["capital_at_risk"] - outcome["producer_take"])
    assert outcome["studio_residual"] == pytest.approx(computed)


def test_simulate_outcome_includes_ewom_piracy_fields(monkeypatch):
    # 2026-08-05: every real outcome carries the eWOM & Piracy fields, and
    # ewom_mult must actually be threaded into the stored npv/total_revenue
    # (not just present-but-unused). Production Trouble/AI setback/Ancillary
    # Surprise are pinned to None so only the eWOM swing is in play, per this
    # file's established monkeypatch-the-draw_* convention (never hardcode
    # which way an unpinned hash()-seeded draw resolves for a literal team
    # name -- see the note at the top of this file).
    import app_pages.movies as movies_module
    from utils.movie_models import MovieProject
    monkeypatch.setattr(movies_module, "draw_production_trouble", lambda team, cycle: None)
    monkeypatch.setattr(movies_module, "draw_ancillary_surprise", lambda team, cycle: None)
    monkeypatch.setattr(movies_module, "draw_ewom_piracy_swing",
                         lambda team, cycle: ("A viral social clip drove a surge", 1.2))
    at = _movies_app()
    _simulate_button(at).click().run()
    assert not at.exception
    outcome = at.session_state["movie_log"][0]
    assert outcome["ewom_piracy_swing"] == "A viral social clip drove a surge"
    assert outcome["ewom_mult"] == 1.2
    project = MovieProject(**outcome["project_kwargs"])
    expected_npv = project.npv(outcome["multiplier"], outcome["critical_score"], ewom_mult=1.2)
    assert outcome["npv"] == pytest.approx(expected_npv)


def test_ewom_piracy_card_renders_in_results_when_it_fires(monkeypatch):
    import app_pages.movies as movies_module
    monkeypatch.setattr(movies_module, "draw_production_trouble", lambda team, cycle: None)
    monkeypatch.setattr(movies_module, "draw_ancillary_surprise", lambda team, cycle: None)
    monkeypatch.setattr(movies_module, "draw_ewom_piracy_swing",
                         lambda team, cycle: ("Pirated copies leaked within days of release", 0.8))
    at = _movies_app()
    _simulate_button(at).click().run()
    assert not at.exception
    text = "\n".join(md.value for md in at.markdown)
    assert "eWOM &amp; Piracy" in text
    assert "Pirated copies leaked within days of release" in text


def test_financing_structure_selectbox_offers_all_three_options():
    at = _movies_app()
    fin_box = at.selectbox[2]   # genre, concept_type, financing_structure in that order
    # .options is the format_func-rendered display text (raw keys aren't
    # exposed there), so check count + the underlying selected value instead.
    assert len(fin_box.options) == 3
    assert fin_box.value == "self_finance"


# ── Research / Social Listening (Phase 4, 2026-08-05) ────────────────────────
def test_research_unpaid_shows_pay_button_not_the_signal():
    at = _movies_app()
    assert at.session_state["movie_research_paid"] == {}
    button_keys = [b.key for b in at.button if b.key]
    assert "movie_research_1" in button_keys
    text = "\n".join(md.value for md in at.markdown)
    assert "BOX-OFFICE SIGNAL" not in text


def test_paying_for_research_reveals_the_signal_and_costs_pa_spend():
    from app_pages.movies import RESEARCH_FEE_M
    at = _movies_app()
    pa_before = at.number_input[1].value   # budget, P&A, screens in that order
    at.button(key="movie_research_1").click().run()
    assert not at.exception, f"Research click raised: {list(at.exception)}"
    assert at.session_state["movie_research_paid"] == {1: True}
    assert at.session_state["movie_draft"]["pa_spend_m"] == pytest.approx(pa_before + RESEARCH_FEE_M)
    assert at.number_input[1].value == pytest.approx(pa_before + RESEARCH_FEE_M)
    text = "\n".join(md.value for md in at.markdown)
    assert "BOX-OFFICE SIGNAL" in text
    assert "SOCIAL / CRITICAL BUZZ" in text


def test_research_signal_matches_the_replayed_draws():
    from utils.movie_models import draw_actual_multiplier, draw_critical_reception, multiplier_to_stars
    at = _movies_app()
    genre_box, concept_box = at.selectbox[0], at.selectbox[1]
    at.button(key="movie_research_1").click().run()
    assert not at.exception
    expected_mult = draw_actual_multiplier("AppTest Team", 1, genre_box.value, concept_box.value)
    expected_stars = multiplier_to_stars(expected_mult, genre_box.value, concept_box.value)
    expected_cs = draw_critical_reception("AppTest Team", 1, genre_box.value, ai_production_tools=False)
    text = "\n".join(md.value for md in at.markdown)
    assert "⭐" * expected_stars in text
    assert f"{expected_cs:.0f}/100" in text


# ── Talent Partnerships (2026-08-04) ─────────────────────────────────────────
# IMPORTANT: draw_rival_claim/draw_hold_forfeit/draw_rival_poach are all
# seeded off Python's built-in hash() of the team name, which is
# PER-PROCESS-RANDOMIZED (PYTHONHASHSEED) unless pinned -- "AppTest Team"'s
# outcome for a given (cycle, partner) is reproducible *within* one process
# run but NOT across separate `python` invocations. These tests must
# therefore never hardcode "AppTest Team resolves to X" (verified once in a
# throwaway script, then baked into an assertion) -- that value silently
# drifts every time the test process restarts. Two safe patterns instead:
# (1) seed the relevant session_state directly (bypasses the draw entirely,
# tests the app's own resolution/rendering logic against known input), or
# (2) monkeypatch the draw_* function the click handler calls, so the real
# button-click code path still executes end-to-end against a controlled
# result. draw_* functions' actual odds/behavior are covered separately in
# tests/test_movie_models.py::TestRivalStudioDynamics.

def _movies_app_no_poaching() -> AppTest:
    """Fresh Cycle 1 Decisions with rival-poaching pre-marked as already
    resolved through cycle 1 with nothing poached -- makes Sign/Hold tests
    deterministic regardless of hash randomization (see note above)."""
    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        st.session_state.team_name = "AppTest Team"
        st.session_state.movie_rival_exclusive = {}
        st.session_state.movie_rival_poach_checked_through = 1
        import app_pages.movies as movies
        movies.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, f"Decisions phase raised: {list(at.exception)}"
    return at


def test_poached_partner_is_shown_disabled_not_as_a_sign_or_hold_button():
    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        st.session_state.team_name = "AppTest Team"
        st.session_state.movie_rival_exclusive = {"northbench": "Paragon Pictures"}
        st.session_state.movie_rival_poach_checked_through = 1
        import app_pages.movies as movies
        movies.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception
    text = "\n".join(md.value for md in at.markdown)
    assert "Signed by Paragon Pictures" in text
    button_keys = [b.key for b in at.button if b.key]
    assert "sign_overall_northbench" not in button_keys
    assert "hold_northbench" not in button_keys
    # Untouched partners are still fully available.
    assert "sign_overall_meridian" in button_keys
    assert "hold_meridian" in button_keys


def test_signing_overall_deal_updates_state_and_tracks_spend():
    at = _movies_app_no_poaching()
    at.button(key="sign_overall_brightlane").click().run()
    assert not at.exception, f"Sign click raised: {list(at.exception)}"
    assert at.session_state["movie_overall_deal"] == "brightlane"
    assert at.session_state["movie_talent_total_spend"] == TALENT_PARTNERS["brightlane"]["overall_deal_cost_m"]


def test_holding_a_rival_claimed_partner_costs_the_fee_for_nothing(monkeypatch):
    import app_pages.movies as movies_module
    monkeypatch.setattr(movies_module, "draw_rival_claim", lambda team, cycle, key: "Paragon Pictures")
    at = _movies_app_no_poaching()
    at.button(key="hold_meridian").click().run()
    assert not at.exception, f"Hold click raised: {list(at.exception)}"
    hold = at.session_state["movie_talent_holds"]["meridian"]
    assert hold["status"] == "rival_claimed"
    assert hold["rival"] == "Paragon Pictures"
    assert at.session_state["movie_talent_total_spend"] == TALENT_PARTNERS["meridian"]["hold_cost_m"]


def test_holding_a_clear_partner_succeeds_as_pending(monkeypatch):
    import app_pages.movies as movies_module
    monkeypatch.setattr(movies_module, "draw_rival_claim", lambda team, cycle, key: None)
    at = _movies_app_no_poaching()
    at.button(key="hold_afterdark").click().run()
    assert not at.exception, f"Hold click raised: {list(at.exception)}"
    hold = at.session_state["movie_talent_holds"]["afterdark"]
    assert hold["status"] == "pending"
    assert hold["cycle_placed"] == 1
    assert at.session_state["movie_talent_total_spend"] == TALENT_PARTNERS["afterdark"]["hold_cost_m"]


def _movies_app_with_overall_deal(partner_key: str) -> AppTest:
    """Seeds an active Overall Deal directly rather than a live click --
    sidesteps the AppTest + st.rerun() 'second interaction' limitation
    documented at the top of this file (sign, then simulate, would be two
    live interactions). partner_key is passed via AppTest's own `args=`,
    not a default-argument closure -- AppTest.from_function re-execs the
    script via inspect.getsourcelines as standalone text, so neither a free
    variable nor a default expression referencing the enclosing scope
    survives (both raise NameError)."""
    def script(partner_key):
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        st.session_state.team_name = "AppTest Team"
        st.session_state.movie_overall_deal = partner_key
        st.session_state.movie_rival_exclusive = {}
        st.session_state.movie_rival_poach_checked_through = 1
        import app_pages.movies as movies
        movies.render()

    at = AppTest.from_function(script, default_timeout=30, args=(partner_key,))
    at.run()
    assert not at.exception, f"Decisions phase raised: {list(at.exception)}"
    return at


def test_star_power_bonus_flows_into_the_resolved_outcome_when_genre_matches():
    # meridian's specialty is Action/Tentpole, GENRES[0] -- the default
    # Genre selectbox value -- so this Overall Deal applies without needing
    # to change any other widget.
    at = _movies_app_with_overall_deal("meridian")
    _simulate_button(at).click().run()
    assert not at.exception, f"Simulate click raised: {list(at.exception)}"
    outcome = at.session_state["movie_log"][0]
    assert outcome["project_kwargs"]["genre"] == "Action/Tentpole"
    assert outcome["project_kwargs"]["star_power"] == 50 + TALENT_PARTNERS["meridian"]["star_power_bonus"]
    assert outcome["talent_partner_bonus"] == TALENT_PARTNERS["meridian"]["name"]


def test_no_bonus_applied_when_no_overall_deal_or_hold_is_active():
    at = _movies_app_no_poaching()
    _simulate_button(at).click().run()
    assert not at.exception
    outcome = at.session_state["movie_log"][0]
    assert outcome["project_kwargs"]["star_power"] == 50   # unboosted default
    assert outcome["talent_partner_bonus"] is None


# ── Exhibitor Negotiation Posture + Pay-1 Window Licensing (2026-08-04) ──────

def test_exhibitor_posture_and_pay1_licensing_selectboxes_default_correctly():
    at = _movies_app()
    posture_box = at.selectbox[3]   # genre, concept_type, financing_structure, exhibitor_posture
    pay1_box = at.selectbox[4]      # Pay-1 licensing, rendered in Release Strategy
    assert posture_box.value == "standard"
    assert len(posture_box.options) == 3
    assert pay1_box.value == "keep"
    assert len(pay1_box.options) == 2


def test_pay1_licensing_selectbox_is_hidden_for_day_and_date():
    at = _movies_app_at_cycle_3()
    at.button(key="pick_day_and_date").click().run()
    assert not at.exception
    caption_text = "\n".join(c.value for c in at.caption)
    assert "Pay-1 licensing isn't available for Day-and-Date" in caption_text
    assert at.session_state["movie_draft"]["pay1_licensing"] == "keep"


def test_default_outcome_reflects_standard_posture_and_keep_licensing():
    at = _movies_app_no_poaching()
    _simulate_button(at).click().run()
    assert not at.exception
    kwargs = at.session_state["movie_log"][0]["project_kwargs"]
    assert kwargs["exhibitor_posture"] == "standard"
    assert kwargs["pay1_licensing"] == "keep"


def _results_app_with_outcome(outcome: dict) -> AppTest:
    """Seeds a single resolved outcome directly into movie_log and lands on
    the Results phase for it -- same 'seed state, single .run(), no
    interaction' pattern as _complete_movies_app, sidesteps the AppTest +
    st.rerun() limitation documented at the top of this file.

    Passed via AppTest's own `args=`, not a default-argument closure --
    AppTest.from_function re-execs the script via inspect.getsourcelines as
    standalone text, so neither a free variable nor a default expression
    referencing the enclosing scope survives (both raise NameError)."""
    def script(outcome):
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        st.session_state.team_name = "AppTest Team"
        st.session_state.movie_cycle = outcome["cycle"]
        st.session_state.movie_phase = "results"
        st.session_state.movie_log = [outcome]
        import app_pages.movies as movies
        movies.render()

    at = AppTest.from_function(script, default_timeout=30, args=(outcome,))
    at.run()
    assert not at.exception, f"Results phase raised: {list(at.exception)}"
    return at


def _full_outcome(**overrides) -> dict:
    """A complete, current-shape movie_log outcome (all keys _results()
    can possibly read), so tests only need to override what they care about."""
    base = {
        "cycle": 1,
        "project_kwargs": {"title": "Test Movie", "genre": "Awards/Prestige", "budget_m": 40,
                            "pa_spend_m": 20, "star_power": 60, "screens": 1500, "cycle": 1,
                            "release_strategy": "wide_theatrical", "concept_type": "New IP",
                            "financing_structure": "self_finance"},
        "multiplier": 2.8, "scenario_label": "base", "critical_score": 60.0,
        "awards_contender": False, "oscar_win": False,
        "production_trouble": None, "ancillary_surprise": None,
        "npv": 10.0, "irr": 0.2, "total_revenue": 80.0, "domestic_bo": 40.0,
        "theatrical_net": 30.0, "pvod": 10.0, "sub_value": 5.0, "longtail": 5.0,
        "awards_bump": 0.0, "theme_park": 0.0, "capital_at_risk": 60.0,
        "talent_take": 8.0, "producer_take": 2.0, "studio_residual": 10.0,
    }
    base.update(overrides)
    return base


def test_results_phase_shows_deal_waterfall_when_fields_present():
    at = _results_app_with_outcome(_full_outcome())
    text = "\n".join(md.value for md in at.markdown)
    assert "Deal Waterfall" in text


def test_results_phase_skips_deal_waterfall_for_legacy_outcomes():
    # An outcome recorded before this feature existed -- no talent_take/
    # producer_take/studio_residual keys at all. Must render cleanly and
    # simply omit the new chart, not raise a KeyError.
    legacy = _full_outcome()
    for key in ("talent_take", "producer_take", "studio_residual"):
        del legacy[key]
    at = _results_app_with_outcome(legacy)
    text = "\n".join(md.value for md in at.markdown)
    assert "Deal Waterfall" not in text


def test_results_phase_shows_oscar_win_over_nomination_copy():
    at = _results_app_with_outcome(_full_outcome(
        awards_contender=True, oscar_win=True, critical_score=90.0))
    text = "\n".join(md.value for md in at.markdown)
    assert "Oscar Win" in text
    assert "Oscar Nomination" not in text


def test_results_phase_shows_oscar_nomination_when_not_a_win():
    at = _results_app_with_outcome(_full_outcome(
        awards_contender=True, oscar_win=False, critical_score=75.0))
    text = "\n".join(md.value for md in at.markdown)
    assert "Oscar Nomination" in text
    assert "Oscar Win" not in text


def _movies_app_at_cycle_3() -> AppTest:
    """Cycle 3 -- windowing unlocks here (WINDOWING_UNLOCK_CYCLE=3), so
    the "Choose <strategy>" cards become real clickable buttons instead
    of a locked info banner. Guards every seed line (`if key not in
    st.session_state`) rather than unconditional assignment -- a real
    test-harness bug caught while writing tests/test_simulation.py's
    equivalent: st.rerun() inside a click handler makes AppTest
    re-execute this whole script() closure, so an unconditional seed
    would silently clobber whatever the click just changed."""
    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        defaults = {
            "team_name": "AppTest Team",
            "movie_cycle": 3,
            "movie_phase": "decisions",
            "movie_log": [],
            "movie_draft": {},
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v
        import app_pages.movies as movies
        movies.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, f"Cycle 3 decisions phase raised: {list(at.exception)}"
    return at


def test_windowing_unlocked_at_cycle_3_shows_choose_strategy_buttons():
    at = _movies_app_at_cycle_3()
    choose_buttons = [b for b in at.button if b.key and b.key.startswith("pick_")]
    assert len(choose_buttons) == 3   # wide_theatrical, platform, day_and_date


def test_clicking_choose_strategy_updates_the_draft_with_no_exceptions():
    at = _movies_app_at_cycle_3()
    day_and_date_button = next(b for b in at.button if b.key == "pick_day_and_date")
    day_and_date_button.click().run()
    assert not at.exception, f"Choose-strategy click raised: {list(at.exception)}"
    assert at.session_state["movie_draft"]["release_strategy"] == "day_and_date"
    assert at.session_state["movie_phase"] == "decisions"   # no phase transition, just a selection


def _complete_movies_app() -> AppTest:
    """Seeds movie_log/movie_phase directly (session_state set before the
    first .run(), no button interaction) rather than clicking through
    3 real cycles -- sidesteps the AppTest + st.rerun() limitation
    documented at the top of this file, which only bites on a *second*
    interaction after a phase transition."""
    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        from utils.movie_models import (
            MovieProject, draw_actual_multiplier, draw_critical_reception,
            AWARDS_ELIGIBLE_GENRES, AWARDS_CONTENDER_THRESHOLD,
        )
        st.session_state.team_name = "AppTest Team"
        st.session_state.school = "Test School"
        st.session_state.class_section = "Sec A"
        log = []
        for cycle, (title, genre) in enumerate(
            [("First Movie", "Drama"), ("Second Movie", "Comedy"), ("Third Movie", "Action/Tentpole")],
            start=1,
        ):
            project = MovieProject(title=title, genre=genre, budget_m=80, pa_spend_m=40,
                                    star_power=60, screens=3000, cycle=cycle,
                                    release_strategy="wide_theatrical", concept_type="New IP")
            multiplier = draw_actual_multiplier("AppTest Team", cycle, project.genre, project.concept_type)
            critical_score = draw_critical_reception("AppTest Team", cycle, project.genre)
            awards_eligible = project.genre in AWARDS_ELIGIBLE_GENRES
            log.append({
                "cycle": cycle, "project_kwargs": dict(project.__dict__),
                "multiplier": multiplier, "scenario_label": "base",
                "critical_score": critical_score,
                "awards_contender": awards_eligible and critical_score >= AWARDS_CONTENDER_THRESHOLD,
                "npv": project.npv(multiplier, critical_score),
                "irr": project.irr(multiplier, critical_score),
                "total_revenue": project.total_revenue(multiplier, critical_score),
                "domestic_bo": project.domestic_box_office(multiplier),
                "theatrical_net": project.theatrical_studio_net(multiplier),
                "pvod": project.pvod_revenue(multiplier),
                "sub_value": project.subscriber_value(multiplier),
                "longtail": project.library_longtail(multiplier, critical_score),
                "awards_bump": project.awards_season_bump(multiplier, critical_score),
                "theme_park": project.theme_park_value(multiplier),
                "capital_at_risk": project.capital_at_risk(),
            })
        st.session_state.movie_log = log
        st.session_state.movie_cycle = 3
        st.session_state.movie_phase = "complete"
        import app_pages.movies as movies
        movies.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, f"Complete phase raised: {list(at.exception)}"
    return at


def test_complete_phase_renders_slate_notables_with_no_exceptions():
    at = _complete_movies_app()
    text = "\n".join(md.value for md in at.markdown)
    assert "Slate Notables" in text
    assert "BEST CYCLE" in text
    assert "GENRE VARIETY" in text


# ── Last Cycle recap (2026-08-03) ────────────────────────────────────────────
def _movies_app_at_cycle_2_with_prior_log() -> AppTest:
    """Seeds a real Cycle 1 outcome directly into movie_log, then lands on
    Cycle 2's Decisions phase -- the Movies-side equivalent of
    tests/test_simulation.py's prev-year-recap fixtures. Deliberately omits
    production_trouble/ancillary_surprise from the seeded entry (both
    default to None if absent) to double as a backward-compatibility check
    for log entries recorded before those fields existed."""
    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        from utils.movie_models import (
            MovieProject, draw_actual_multiplier, draw_critical_reception,
        )
        defaults = {
            "team_name": "AppTest Team",
            "movie_phase": "decisions",
            "movie_draft": {},
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v

        if "movie_log" not in st.session_state:
            project = MovieProject(title="First Movie", genre="Drama", budget_m=80,
                                    pa_spend_m=40, star_power=60, screens=3000, cycle=1,
                                    release_strategy="wide_theatrical", concept_type="New IP")
            multiplier = draw_actual_multiplier("AppTest Team", 1, project.genre, project.concept_type)
            critical_score = draw_critical_reception("AppTest Team", 1, project.genre)
            st.session_state.movie_log = [{
                "cycle": 1, "project_kwargs": dict(project.__dict__),
                "multiplier": multiplier, "scenario_label": "base",
                "critical_score": critical_score, "awards_contender": False,
                "npv": project.npv(multiplier, critical_score),
                "irr": project.irr(multiplier, critical_score),
                "total_revenue": project.total_revenue(multiplier, critical_score),
                "domestic_bo": project.domestic_box_office(multiplier),
                "theatrical_net": project.theatrical_studio_net(multiplier),
                "pvod": project.pvod_revenue(multiplier),
                "sub_value": project.subscriber_value(multiplier),
                "longtail": project.library_longtail(multiplier, critical_score),
                "awards_bump": 0.0,
                "theme_park": project.theme_park_value(multiplier),
                "capital_at_risk": project.capital_at_risk(),
            }]
        if "movie_cycle" not in st.session_state:
            st.session_state.movie_cycle = 2

        import app_pages.movies as movies
        movies.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, f"Cycle 2 decisions phase raised: {list(at.exception)}"
    return at


def test_last_cycle_recap_shows_at_cycle_2_with_prior_outcome():
    at = _movies_app_at_cycle_2_with_prior_log()
    text = "\n".join(md.value for md in at.markdown)
    assert "Last Cycle's Actuals" in text
    assert "First Movie" in text


def test_last_cycle_recap_absent_at_cycle_1_with_no_prior_outcome():
    at = _movies_app()
    text = "\n".join(md.value for md in at.markdown)
    assert "Last Cycle's Actuals" not in text


# ── Progress chart (2026-08-04) ──────────────────────────────────────────────
def _movies_app_at_cycle_3_with_two_prior_logs() -> AppTest:
    """Cycle 3 Decisions with two real cycle outcomes (1, 2) already in
    ss.movie_log -- the multi-cycle _progress_chart (added 2026-08-04,
    the Movies-side parallel to pages/simulation.py's _progress_chart)
    only renders once len(movie_log) >= 2, so this is the fixture that
    exercises it. Reuses _complete_movies_app's log-entry shape."""
    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        from utils.movie_models import (
            MovieProject, draw_actual_multiplier, draw_critical_reception,
        )
        defaults = {
            "team_name": "AppTest Team",
            "movie_phase": "decisions",
            "movie_draft": {},
            "movie_cycle": 3,
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v

        if "movie_log" not in st.session_state:
            log = []
            for cycle, title in [(1, "First Movie"), (2, "Second Movie")]:
                project = MovieProject(title=title, genre="Drama", budget_m=80,
                                        pa_spend_m=40, star_power=60, screens=3000, cycle=cycle,
                                        release_strategy="wide_theatrical", concept_type="New IP")
                multiplier = draw_actual_multiplier("AppTest Team", cycle, project.genre, project.concept_type)
                critical_score = draw_critical_reception("AppTest Team", cycle, project.genre)
                log.append({
                    "cycle": cycle, "project_kwargs": dict(project.__dict__),
                    "multiplier": multiplier, "scenario_label": "base",
                    "critical_score": critical_score, "awards_contender": False,
                    "npv": project.npv(multiplier, critical_score),
                    "irr": project.irr(multiplier, critical_score),
                    "total_revenue": project.total_revenue(multiplier, critical_score),
                    "domestic_bo": project.domestic_box_office(multiplier),
                    "theatrical_net": project.theatrical_studio_net(multiplier),
                    "pvod": project.pvod_revenue(multiplier),
                    "sub_value": project.subscriber_value(multiplier),
                    "longtail": project.library_longtail(multiplier, critical_score),
                    "awards_bump": 0.0,
                    "theme_park": project.theme_park_value(multiplier),
                    "capital_at_risk": project.capital_at_risk(),
                })
            st.session_state.movie_log = log

        import app_pages.movies as movies
        movies.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, f"Cycle 3 decisions phase raised: {list(at.exception)}"
    return at


def test_progress_chart_renders_at_cycle_3_with_two_prior_cycles():
    at = _movies_app_at_cycle_3_with_two_prior_logs()
    specs = [el.proto.spec for el in at.get("plotly_chart")]
    assert any("Your Progress So Far" in s for s in specs)


def test_progress_chart_absent_at_cycle_1_with_no_prior_cycles():
    at = _movies_app()
    specs = [el.proto.spec for el in at.get("plotly_chart")]
    assert not any("Your Progress So Far" in s for s in specs)
