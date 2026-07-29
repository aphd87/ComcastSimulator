"""
Tests for app_pages/leaderboard.py. _format_notables_badges is a pure helper
(added 2026-07-27 alongside the Attempts-Used/Notables badge feature) and
gets real unit tests; render() itself gets one AppTest smoke test seeding
a real leaderboard.json (single .run(), no interaction -- see
test_movies_page.py's docstring for why that's the safe zone for AppTest).
"""
import pytest
from streamlit.testing.v1 import AppTest

import utils.game_state as gs
from app_pages.leaderboard import _format_notables_badges


@pytest.fixture(autouse=True)
def isolated_leaderboard(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    yield


class TestFormatNotablesBadges:
    def test_empty_notables_renders_nothing(self):
        assert _format_notables_badges({}) == ""

    def test_tv_shape_renders_best_year_and_shows_greenlit(self):
        notables = {
            "best_year": {"label": "Year 3", "margin": 22.0, "ocf": 4.4},
            "most_improved": 15.0, "consistency_score": 88.0,
            "diversity_trend": -0.2, "shows_greenlit": 2,
        }
        html = _format_notables_badges(notables)
        assert "Year 3" in html
        assert "+15.0 improvement" in html
        assert "88/100 consistency" in html
        assert "2 greenlit" in html
        assert "genre" not in html   # genre_variety is Movies-only, must not leak in

    def test_movies_shape_renders_best_cycle_and_genre_variety(self):
        notables = {
            "best_cycle": {"label": "Hit Movie", "npv": 50.0, "irr": 0.3},
            "most_improved": -10.0, "consistency_score": 60.0, "genre_variety": 3,
        }
        html = _format_notables_badges(notables)
        assert "Hit Movie" in html
        assert "-10.0 improvement" in html
        assert "60/100 consistency" in html
        assert "3 genres" in html
        assert "greenlit" not in html   # shows_greenlit is TV-only, must not leak in

    def test_zero_shows_greenlit_is_omitted_not_shown_as_zero(self):
        notables = {"best_year": None, "most_improved": None,
                     "consistency_score": None, "diversity_trend": None,
                     "shows_greenlit": 0}
        html = _format_notables_badges(notables)
        assert html == ""   # every field is falsy/None -- nothing to show

    def test_singular_genre_count_does_not_pluralize(self):
        html = _format_notables_badges({"genre_variety": 1})
        assert "1 genre" in html
        assert "1 genres" not in html


def test_leaderboard_renders_attempts_used_and_notables_with_no_exceptions(monkeypatch, tmp_path):
    # AppTest.from_function re-parses the script as standalone source, so it
    # can't close over Python objects from this scope (only literals survive
    # -- see test_movies_page.py's pattern) -- seed the leaderboard file
    # on disk instead and let the script re-derive its own LEADERBOARD_FILE
    # monkeypatch inside the isolated_leaderboard fixture's tmp_path.
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    gs.record_attempt(
        team_name="Team Alpha", network="oxygen", attempt_num=1,
        score=80, passed=True, details={"total": 80, "ocf_margin": 90},
        school="Kellogg", class_section="Sec A",
        notables={"best_year": {"label": "Year 2", "margin": 18.0, "ocf": 3.6},
                  "most_improved": 12.0, "consistency_score": 91.0,
                  "diversity_trend": -0.1, "shows_greenlit": 1},
    )

    def script():
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        st.session_state.team_name = "Team Alpha"
        st.session_state.school = "Kellogg"
        st.session_state.class_section = "Sec A"
        import app_pages.leaderboard as leaderboard
        leaderboard.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, f"Leaderboard render raised: {list(at.exception)}"
    text = "\n".join(md.value for md in at.markdown)
    assert "used" in text   # "N/MAX used" attempts-used string
    assert "Year 2" in text
    assert "1 greenlit" in text
