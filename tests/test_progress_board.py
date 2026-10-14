"""In-progress sub-leaderboards and university scope (2026-10-14)."""
from streamlit.testing.v1 import AppTest

import utils.game_state as gs


def _prog(team, done, metric, school="Darden, UVA", cls="Fall — Media", net="oxygen", total=5):
    gs.record_progress(team, school, cls, net, done, total, metric, "OCF margin so far (%)")


def test_progress_groups_by_years_done_and_ranks_within_group():
    _prog("A", 3, 10.0)
    _prog("B", 3, 14.0)
    _prog("C", 5, 2.0)
    groups = gs.get_progress_board("oxygen")
    assert list(groups) == [5, 3]                      # most-completed group first
    assert [r["team_name"] for r in groups[3]] == ["B", "A"]
    assert groups[3][0]["rank"] == 1


def test_team_stays_in_its_furthest_group_after_redo_but_latest_number_counts():
    _prog("A", 3, 10.0)
    _prog("A", 2, 50.0)          # e.g. restarted and replayed two years
    _prog("A", 3, 12.0)          # re-simulated year 3
    groups = gs.get_progress_board("oxygen")
    assert list(groups) == [3] and groups[3][0]["metric"] == 12.0


def test_progress_is_scoped_by_class_school_and_university():
    _prog("A", 2, 5.0, school="Darden, UVA", cls="X")
    _prog("B", 2, 6.0, school="Batten, UVA", cls="Y")
    _prog("C", 2, 7.0, school="Kellogg, Northwestern", cls="Z")
    uva = gs.get_progress_board("oxygen", school=gs.UNIVERSITY_SCOPE + "UVA")
    assert {r["team_name"] for r in uva[2]} == {"A", "B"}
    assert [r["team_name"] for r in gs.get_progress_board("oxygen", "Darden, UVA", "X")[2]] == ["A"]


def test_university_scope_applies_to_official_leaderboard():
    for team, school in (("A", "Darden, UVA"), ("B", "Batten, UVA"), ("C", "Kellogg, Northwestern")):
        gs.record_attempt(team_name=team, network="oxygen", attempt_num=1, score=70, passed=True,
                          details={}, school=school, class_section="S")
    board = gs.get_network_leaderboard("oxygen", school=gs.UNIVERSITY_SCOPE + "uva")
    assert {e["team_name"] for e in board} == {"A", "B"}


def test_leaderboard_page_renders_progress_view():
    _prog("A", 3, 10.0, school="Test School", cls="Sec A")

    def script():
        import streamlit as st, sys
        sys.path.insert(0, ".")
        st.session_state.update(registered=True, team_name="A", school="Test School", class_section="Sec A")
        from app_pages.leaderboard import render, BOARD_VIEWS
        st.session_state["lb_view_oxygen"] = BOARD_VIEWS[1]
        render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception, list(at.exception)
    assert any("3 of 5" in m.value for m in at.markdown)
