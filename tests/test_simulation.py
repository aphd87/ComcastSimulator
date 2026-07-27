"""
Tests for the pure-logic pieces of pages/simulation.py (the annual turn
engine). Most of this module is Streamlit UI and isn't unit-testable in
isolation (see tests/test_movies_page.py's docstring for the standing
AppTest + st.rerun() limitation that applies here too) -- these cover the
one genuinely pure helper added alongside the Greenlighting roster wiring.
"""
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
