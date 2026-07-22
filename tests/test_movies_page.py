"""
Headless test of pages/movies.py using Streamlit's official AppTest harness
(streamlit.testing.v1) — runs the real render() function through a
simulated script session, without a browser.

IMPORTANT — read before extending this file:
A full click-through (Greenlight -> Release -> Results -> 3 cycles ->
Complete -> Submit) was attempted here and conclusively diagnosed as
blocked by a genuine Streamlit 1.59.2 AppTest limitation, not a bug in
pages/movies.py: any button handler that calls `st.rerun()` (the pattern
used consistently across this entire codebase — pages/simulation.py,
app.py, and pages/movies.py all do `if st.button(...): ss.x = y;
st.rerun()`) corrupts AppTest's widget-state tracking on the *second*
interaction after the phase transition, raising a spurious
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

Net effect: only the *first* phase (a single AppTest `.run()`, no
interaction) is safely testable this way. The full click-through still
needs a human in a real browser — Claude in Chrome was not connected for
this entire effort (see DESIGN_NOTES.md). If a future Streamlit upgrade
fixes this AppTest bug, the interactive tests are worth re-adding — the
diagnostic script used to find this is preserved in this file's git
history (see the commit that reduced this file to its current scope).
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
    assert not at.exception, f"Greenlight phase raised: {list(at.exception)}"
    return at


def test_greenlight_phase_renders_with_no_exceptions():
    at = _movies_app()
    assert not at.exception


def test_greenlight_phase_starts_at_cycle_1():
    at = _movies_app()
    assert at.session_state["movie_phase"] == "greenlight"
    assert at.session_state["movie_cycle"] == 1
    assert at.session_state["movie_log"] == []


def test_greenlight_phase_has_expected_widgets():
    at = _movies_app()
    assert len(at.number_input) == 3   # budget, P&A, screens
    assert len(at.selectbox) == 1      # genre
    assert len(at.slider) == 1         # star power
    assert len(at.text_input) == 1     # title
    assert any("Commit Capital" in b.label for b in at.button)


def test_greenlight_phase_shows_bear_base_bull_preview():
    at = _movies_app()
    text = "\n".join(md.value for md in at.markdown)
    for label in ("bear case", "base case", "bull case"):
        assert label in text.lower()
