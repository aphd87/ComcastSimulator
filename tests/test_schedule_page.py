"""
Smoke test for app_pages/renewal.py's Primetime Scheduling grid.

Moved here 2026-08-03 (was app_pages/schedule.py's grid) per user request --
the grid now lives in Renewal, right after the Full Renewal Analysis Table,
alongside the rest of that year's real decisions. schedule.py is now
cash-flow/amortization reference only.

Single .run(), no interaction -- the documented AppTest + st.rerun() safe
zone this codebase already relies on elsewhere (see test_movies_page.py's
module docstring for the full diagnosis).
"""
from streamlit.testing.v1 import AppTest


def _script():
    import streamlit as st
    import sys
    sys.path.insert(0, ".")
    from utils.models import Show

    st.session_state.team_name        = "AppTest Team"
    st.session_state.active_network   = "oxygen"
    st.session_state.year             = 1
    st.session_state.mkt_budget       = 5.0
    st.session_state.level_budget     = 95.0
    st.session_state.cancelled_shows  = set()
    st.session_state.renewal_decisions= {}
    st.session_state.research_revealed= {}
    st.session_state.greenlit_ids_this_year = set()

    st.session_state.oxygen_shows = [
        Show(id=1, name="Show A", genre="Reality", episodes=10, ep_cost_k=300,
             rating=1.0, ip_score=40, air_month=1, network="Oxygen"),
        Show(id=2, name="Show B", genre="True Crime", episodes=8, ep_cost_k=350,
             rating=0.9, ip_score=45, air_month=3, network="Oxygen"),
    ]
    st.session_state.bravo_shows   = []
    st.session_state.peacock_shows = []

    import app_pages.renewal as renewal
    renewal.render()


def test_renewal_page_renders_primetime_grid_with_no_exceptions():
    at = AppTest.from_function(_script, default_timeout=30)
    at.run()
    assert not at.exception, f"Renewal page raised: {list(at.exception)}"

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
