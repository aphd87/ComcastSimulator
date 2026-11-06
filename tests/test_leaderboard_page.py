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

    def test_emmy_wins_and_nominations_both_render(self):
        # 2026-08-05: TV-side parallel to the Movies Oscar badges, same
        # "wins and noms are independent counts, both can show" posture.
        html = _format_notables_badges({"emmy_wins": 2, "emmy_nominations": 5})
        assert "2 Emmy wins" in html
        assert "5 Emmy noms" in html

    def test_zero_emmy_counts_are_omitted_not_shown_as_zero(self):
        html = _format_notables_badges({"emmy_wins": 0, "emmy_nominations": 0})
        assert html == ""

    def test_singular_emmy_win_does_not_pluralize(self):
        html = _format_notables_badges({"emmy_wins": 1, "emmy_nominations": 0})
        assert "1 Emmy win" in html
        assert "1 Emmy wins" not in html


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


def test_leaderboard_renders_class_awards_with_no_exceptions(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    gs.record_attempt(
        team_name="Team Alpha", network="oxygen", attempt_num=1,
        score=60, passed=True, details={"total": 60},
        school="Kellogg", class_section="Sec A",
        notables={"total_revenue": 500.0, "emmy_wins": 0, "emmy_nominations": 2},
    )
    gs.record_attempt(
        team_name="Team Bravo", network="oxygen", attempt_num=1,
        score=90, passed=True, details={"total": 90},
        school="Kellogg", class_section="Sec A",
        notables={"total_revenue": 800.0, "emmy_wins": 1, "emmy_nominations": 1},
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
    assert "Class Awards" in text
    assert "Top Score" in text
    assert "Highest Revenue" in text
    assert "$800M" in text
    assert "Most Emmy Recognition" in text


# ── Instructor tools (2026-11-03) ────────────────────────────────────────────
def test_instructor_clear_archives_one_class(monkeypatch, tmp_path):
    for name, attr in (("leaderboard.json", "LEADERBOARD_FILE"), ("progress.json", "PROGRESS_FILE"),
                       ("pitch_board.json", "PITCH_BOARD_FILE")):
        monkeypatch.setattr(gs, attr, tmp_path / name)
    import utils.storage as storage
    for cls in ("A", "A", "B"):
        storage.append_entry(gs.LEADERBOARD_FILE, {"team_name": "t", "school": "UVA", "class_section": cls,
                                                   "network": "oxygen", "attempt": 1, "score": 50, "passed": True,
                                                   "is_official": True, "timestamp": 0})
    # Stored as "UVA", listed (and cleared) under the canonical spelling
    # (gs.canonical_school, 2026-11-05).
    uva = "University of Virginia"
    assert [s[:2] for s in gs.class_scopes()] == [(uva, "A"), (uva, "B")]
    assert len(gs.class_records(uva, "A")["leaderboard"]) == 2
    moved = gs.archive_and_clear_class(uva, "A")
    assert moved == {"leaderboard": 2, "progress": 0, "pitches": 0}
    assert [e["class_section"] for e in gs.load_leaderboard()] == ["B"]
    assert (tmp_path / "leaderboard_archive.json").exists()


def test_instructor_tools_locked_without_correct_password(monkeypatch):
    monkeypatch.setattr(gs, "instructor_password", lambda: "secret123")
    def script():
        import sys
        import streamlit as st
        sys.path.insert(0, ".")
        for k, v in {"team_name": "", "registered": False, "school": "", "class_section": ""}.items():
            st.session_state.setdefault(k, v)
        from app_pages.leaderboard import _render_instructor_tools
        _render_instructor_tools()
    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, list(at.exception)
    at.text_input(key="instructor_pw").set_value("wrong").run()
    assert any("Wrong password" in e.value for e in at.error)
    assert not any(b.key == "instructor_clear" for b in at.button)


def test_score_parts_use_labels_not_raw_keys():
    # 2026-11-05: rows printed raw keys and Movies $M fields as if scores.
    from app_pages.leaderboard import _score_parts_html
    tv = _score_parts_html({"total": 80, "passed": True, "ocf_margin": 90, "roi": 40,
                            "diversity": 50, "marketing": 70, "renewal": 100}, "oxygen")
    assert "Genre Mix <b>50</b>" in tv and "ocf_margin" not in tv and "passed" not in tv
    mv = _score_parts_html({"risk_adjusted_npv": 55, "avg_ra_npv_m": -12.0,
                            "portfolio_diversification": 100}, "movies")
    assert "NPV <b>55</b>" in mv and "avg_ra_npv_m" not in mv and "-12" not in mv
    assert _score_parts_html({}, "oxygen") == "<div></div>"


def test_board_with_three_teams_renders_pass_colored_chart(monkeypatch, tmp_path):
    # Score Distribution only draws at 3+ teams; it used to mark 70 points as
    # the pass line. Colors now follow each entry's real `passed`.
    for name, score, passed in [("A", 85, True), ("B", 72, False), ("C", 60, True)]:
        gs.record_attempt(team_name=name, network="oxygen", attempt_num=1, score=score, passed=passed,
                          details={"total": score, "ocf_margin": 90, "diversity": 50},
                          school="Darden School of Business, UVA", class_section="Sec A")
    path = str(tmp_path / "leaderboard.json")

    def _app(path):
        import streamlit as st
        import utils.game_state as gs
        from pathlib import Path
        gs.LEADERBOARD_FILE = Path(path)
        st.session_state.team_name = "A"
        st.session_state.school = "Darden School of Business, University of Virginia"
        st.session_state.class_section = "Sec A"
        st.session_state.registered = True
        from app_pages.leaderboard import render
        render()

    at = AppTest.from_function(_app, args=(path,)).run(timeout=60)
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "70-point pass line" not in md
