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

    # Guarded (`if key not in st.session_state`) rather than unconditional --
    # a real bug caught while adding the Auto-Fill click test below: a
    # button handler that calls st.rerun() makes AppTest re-execute this
    # whole script from the top, so an unconditional re-seed would silently
    # wipe out whatever that click just changed (same pattern documented in
    # tests/test_simulation.py and tests/test_movies_page.py).
    defaults = {
        "team_name": "AppTest Team",
        "active_network": "oxygen",
        "year": 1,
        "mkt_budget": 5.0,
        "level_budget": 95.0,
        "cancelled_shows": set(),
        "renewal_decisions": {},
        "research_revealed": {},
        "greenlit_ids_this_year": set(),
        "oxygen_shows": [
            Show(id=1, name="Show A", genre="Reality", episodes=10, ep_cost_k=300,
                 rating=1.0, ip_score=40, air_month=1, network="Oxygen"),
            Show(id=2, name="Show B", genre="True Crime", episodes=8, ep_cost_k=350,
                 rating=0.9, ip_score=45, air_month=3, network="Oxygen"),
        ],
        "bravo_shows": [],
        "peacock_shows": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

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


def test_directions_mention_double_click_to_assign_a_slot():
    # Added 2026-08-04 per user request -- students single-clicking a
    # SelectboxColumn cell and getting nothing to happen was a real point
    # of confusion; the directions now say so explicitly.
    at = AppTest.from_function(_script, default_timeout=30)
    at.run()
    text = "\n".join(md.value for md in at.markdown)
    assert "double-click" in text.lower()


def test_auto_fill_by_rating_assigns_every_show_to_a_distinct_slot():
    # Added 2026-08-04 per user request for a faster starting point than
    # clicking through the grid cell by cell (Streamlit's data_editor has
    # no drag-across-cells interaction) -- one click ranks shows by rating
    # and slots by slot_rating_multiplier() and pairs them off.
    at = AppTest.from_function(_script, default_timeout=30)
    at.run()
    auto_fill_buttons = [b for b in at.button if "Auto-Fill" in b.label]
    assert len(auto_fill_buttons) == 1

    auto_fill_buttons[0].click().run()
    assert not at.exception, f"Auto-Fill click raised: {list(at.exception)}"

    shows = at.session_state["oxygen_shows"]
    assert all(s.slot_day is not None and s.slot_hour is not None for s in shows)
    assigned = [(s.slot_day, s.slot_hour) for s in shows]
    assert len(assigned) == len(set(assigned))   # no two shows share a slot
