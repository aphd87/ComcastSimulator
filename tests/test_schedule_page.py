"""
Smoke test for app_pages/schedule.py's Primetime Scheduling grid
(2026-07-29 rework: was a static, illustrative, auto-assigned table;
now a real st.data_editor grid whose placements feed Show.ad_revenue
via schedule_multiplier -- see utils/models.py::slot_rating_multiplier).

Single .run(), no interaction -- the documented AppTest + st.rerun()
safe zone this codebase already relies on elsewhere (see
test_movies_page.py's module docstring for the full diagnosis).
"""
from streamlit.testing.v1 import AppTest


def _script():
    import streamlit as st
    import sys
    sys.path.insert(0, ".")
    from utils.models import Show

    st.session_state.team_name      = "AppTest Team"
    st.session_state.active_network = "oxygen"
    st.session_state.year           = 1
    st.session_state.mkt_budget     = 5.0

    st.session_state.oxygen_shows = [
        Show(id=1, name="Show A", genre="Reality", episodes=10, ep_cost_k=300,
             rating=1.0, ip_score=40, air_month=1, network="Oxygen"),
        Show(id=2, name="Show B", genre="True Crime", episodes=8, ep_cost_k=350,
             rating=0.9, ip_score=45, air_month=3, network="Oxygen"),
    ]
    st.session_state.bravo_shows   = []
    st.session_state.peacock_shows = []

    import app_pages.schedule as schedule
    schedule.render()


def test_schedule_page_renders_grid_with_no_exceptions():
    at = AppTest.from_function(_script, default_timeout=30)
    at.run()
    assert not at.exception, f"Schedule page raised: {list(at.exception)}"

    text = "\n".join(md.value for md in at.markdown)
    assert "trade-off" in text.lower()
    assert "death slot" in text.lower()
    # AppTest's public API (this Streamlit version) has no dedicated
    # data_editor accessor -- the no-exception assertion above is what
    # actually confirms the grid mounted and rendered cleanly.


def test_unscheduled_shows_stay_neutral_after_a_no_op_render():
    at = AppTest.from_function(_script, default_timeout=30)
    at.run()
    assert not at.exception

    shows = at.session_state["oxygen_shows"]
    assert all(s.slot_day is None and s.slot_hour is None for s in shows)
    assert all(s.schedule_multiplier() == 1.0 for s in shows)
