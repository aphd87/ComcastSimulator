"""
Tests for the pure-logic pieces of pages/simulation.py (the annual turn
engine). Most of this module is Streamlit UI and isn't unit-testable in
isolation (see tests/test_movies_page.py's docstring for the standing
AppTest + st.rerun() limitation that applies here too) -- these cover the
one genuinely pure helper added alongside the Greenlighting roster wiring,
plus a Complete-phase smoke test that sidesteps the AppTest limitation by
seeding session_state before the first .run() (no button interaction,
the one combination the limitation doesn't affect -- see test_movies_page.py).
"""
import pytest
from streamlit.testing.v1 import AppTest

import utils.game_state as gs
from utils.models import Show
from utils.game_state import MAX_NEW_SHOWS_PER_YEAR
from pages.simulation import _remove_greenlit_shows


def _show(show_id: int, name: str = "Test") -> Show:
    return Show(id=show_id, name=name, genre="Reality", episodes=10, ep_cost_k=300,
                rating=1.0, ip_score=40, air_month=1, network="Oxygen")


class FakeSessionState(dict):
    """Minimal stand-in for st.session_state -- supports both dict-style
    and attribute-style access, matching how the real object is used."""
    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, value):
        self[key] = value


class TestRemoveGreenlitShows:
    def test_removes_matching_ids_from_the_correct_roster(self):
        ss = FakeSessionState(
            oxygen_shows=[_show(51), _show(52)],
            bravo_shows=[_show(53)],
            peacock_shows=[],
        )
        _remove_greenlit_shows(ss, {51})
        assert [s.id for s in ss["oxygen_shows"]] == [52]
        assert [s.id for s in ss["bravo_shows"]] == [53]   # untouched

    def test_searches_all_three_rosters_since_ids_are_globally_unique(self):
        ss = FakeSessionState(
            oxygen_shows=[_show(51)],
            bravo_shows=[_show(52)],
            peacock_shows=[_show(53)],
        )
        _remove_greenlit_shows(ss, {51, 52, 53})
        assert ss["oxygen_shows"] == []
        assert ss["bravo_shows"] == []
        assert ss["peacock_shows"] == []

    def test_empty_id_set_is_a_no_op(self):
        original = [_show(51)]
        ss = FakeSessionState(oxygen_shows=original, bravo_shows=[], peacock_shows=[])
        _remove_greenlit_shows(ss, set())
        assert ss["oxygen_shows"] == original

    def test_missing_roster_keys_dont_raise(self):
        # Defensive: called with .get(..., set()) fallbacks elsewhere, but
        # the function itself should tolerate an incomplete session state.
        ss = FakeSessionState()
        _remove_greenlit_shows(ss, {51})   # must not raise


class TestNewShowCap:
    def test_cap_constant_is_small_and_positive(self):
        # Real network development slates greenlight a handful of new
        # titles per season, not dozens -- sanity guard against an
        # accidental typo (e.g. 30 instead of 3) more than a business rule.
        assert 0 < MAX_NEW_SHOWS_PER_YEAR <= 10


@pytest.fixture(autouse=True)
def isolated_leaderboard(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    yield


def _complete_sim_app() -> AppTest:
    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        from utils.models import Show

        st.session_state.team_name = "AppTest Team"
        st.session_state.school = "Test School"
        st.session_state.class_section = "Sec A"
        st.session_state.active_network = "oxygen"

        st.session_state.oxygen_shows = [
            Show(id=1, name="Show A", genre="Reality", episodes=10, ep_cost_k=300,
                 rating=1.0, ip_score=40, air_month=1, network="Oxygen"),
            Show(id=2, name="Show B", genre="True Crime", episodes=8, ep_cost_k=350,
                 rating=0.9, ip_score=45, air_month=3, network="Oxygen"),
        ]
        st.session_state.bravo_shows = []
        st.session_state.peacock_shows = []
        st.session_state.cancelled_shows = set()
        st.session_state.total_shows_greenlit = 1

        log = []
        for year, margin in enumerate([8.0, 12.0, -3.0, 20.0, 15.0], start=1):
            shows_this_year = [
                {"id": 1, "name": "Show A", "network": "Oxygen", "genre": "Reality",
                 "status": "active", "cost": 5.0},
            ]
            if year >= 3:
                shows_this_year.append(
                    {"id": 2, "name": "Show B", "network": "Oxygen", "genre": "True Crime",
                     "status": "active", "cost": 4.0})
            log.append({
                "year": year, "label": f"Year {year}",
                "revenue": 20.0, "ad_rev": 15.0, "dist_rev": 5.0,
                "cost": 9.0, "mkt": 3.0, "ga": 1.0,
                "ocf": margin / 100 * 20.0, "margin": margin,
                "new_cancellations": [], "shows": shows_this_year,
                "budget": 25.0,
            })
        st.session_state.yearly_log = log
        st.session_state.year = 5
        st.session_state.sim_phase = "complete"
        st.session_state.level_budget = 25.0

        import pages.simulation as simulation
        simulation.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, f"Complete phase raised: {list(at.exception)}"
    return at


def test_complete_phase_renders_level_notables_with_no_exceptions():
    at = _complete_sim_app()
    text = "\n".join(md.value for md in at.markdown)
    assert "Level Notables" in text
    assert "BEST YEAR" in text
    assert "SHOWS GREENLIT" in text


def _decisions_sim_app() -> AppTest:
    """A fresh Year 1 Decisions page -- the merged scrolling page
    (redesigned 2026-07-27, replacing the old 4-step Financing/Renewal/
    Greenlighting/Scheduling wizard) that renders all four sections at
    once. A single AppTest .run() with no interaction is the documented
    safe zone (see test_movies_page.py's docstring).

    Every seed line below is guarded (`if key not in st.session_state`)
    rather than an unconditional assignment -- a real bug caught while
    writing this test: clicking a button that calls st.rerun() makes
    AppTest re-execute this whole script() closure from the top, so an
    unconditional `st.session_state.yearly_log = []` would silently wipe
    out the entry the click just appended, making every post-click
    assertion fail for a reason that has nothing to do with the page
    under test. This mirrors app.py's own init_state() idiom."""
    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        from utils.models import Show

        defaults = {
            "team_name": "AppTest Team",
            "school": "Test School",
            "class_section": "Sec A",
            "active_network": "oxygen",
            "oxygen_shows": [
                Show(id=1, name="Show A", genre="Reality", episodes=10, ep_cost_k=300,
                     rating=1.0, ip_score=40, air_month=1, network="Oxygen"),
                Show(id=2, name="Show B", genre="True Crime", episodes=8, ep_cost_k=350,
                     rating=0.9, ip_score=45, air_month=3, network="Oxygen"),
            ],
            "bravo_shows": [],
            "peacock_shows": [],
            "cancelled_shows": set(),
            "renewal_decisions": {},
            "research_revealed": {},
            "yearly_log": [],
            "year": 1,
            "sim_phase": "decisions",
            "level_budget": 220.0,
            "mkt_budget": 5.0,
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v

        import pages.simulation as simulation
        simulation.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, f"Decisions phase raised: {list(at.exception)}"
    return at


def test_decisions_phase_renders_all_four_sections_on_one_page():
    at = _decisions_sim_app()
    text = "\n".join(md.value for md in at.markdown)
    assert "Financing" in text
    assert "Renewal" in text
    assert "Greenlighting" in text
    assert "Scheduling" in text


def test_decisions_phase_has_one_simulate_button():
    at = _decisions_sim_app()
    sim_buttons = [b for b in at.button if "Simulate Year" in b.label]
    assert len(sim_buttons) == 1


def test_clicking_simulate_transitions_to_results_with_no_exceptions():
    # Exactly one click, from a fresh session -- the FIRST interaction,
    # not a second one after an earlier phase transition, so this is
    # inside the AppTest safe zone (see test_movies_page.py's docstring).
    # This also regression-tests a real bug found while building this
    # page: the old code referenced a bare `net` name inside _decisions()
    # that was never passed in as a parameter, so clicking "End Year"
    # would have raised NameError in production -- nothing had ever
    # exercised that click path before this test existed.
    at = _decisions_sim_app()
    sim_button = next(b for b in at.button if "Simulate Year" in b.label)
    sim_button.click().run()
    assert not at.exception, f"Simulate click raised: {list(at.exception)}"
    assert at.session_state["sim_phase"] == "results"
    assert len(at.session_state["yearly_log"]) == 1
    assert at.session_state["yearly_log"][0]["year"] == 1
