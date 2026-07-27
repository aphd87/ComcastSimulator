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
        import pages.movies as movies
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
    assert len(at.selectbox) == 2      # genre, concept type
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
        import pages.movies as movies
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
