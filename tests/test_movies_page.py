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
    # "Choose <strategy>" buttons are reachable yet -- Simulate is the
    # only button on the page.
    at = _movies_app()
    assert len(at.number_input) == 3   # budget, P&A, screens
    assert len(at.selectbox) == 3      # genre, concept type, financing structure
    assert len(at.slider) == 1         # star power
    assert len(at.text_input) == 1     # title
    assert len(at.button) == 1
    assert "Simulate" in at.button[0].label


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


def test_clicking_simulate_transitions_to_results_with_no_exceptions():
    # Exactly one click, from a fresh session -- the FIRST interaction,
    # not a second one after an earlier phase transition, so this is
    # inside the AppTest safe zone documented at the top of this file.
    at = _movies_app()
    at.button[0].click().run()
    assert not at.exception, f"Simulate click raised: {list(at.exception)}"
    assert at.session_state["movie_phase"] == "results"
    assert len(at.session_state["movie_log"]) == 1
    assert at.session_state["movie_log"][0]["cycle"] == 1


def test_simulate_outcome_includes_financing_and_waterfall_fields():
    # 2026-08-04: default financing_structure (self_finance) and the deal
    # waterfall fields must be present on every real outcome, not just
    # backfilled test fixtures.
    at = _movies_app()
    at.button[0].click().run()
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


def test_financing_structure_selectbox_offers_all_three_options():
    at = _movies_app()
    fin_box = at.selectbox[2]   # genre, concept_type, financing_structure in that order
    # .options is the format_func-rendered display text (raw keys aren't
    # exposed there), so check count + the underlying selected value instead.
    assert len(fin_box.options) == 3
    assert fin_box.value == "self_finance"


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
