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


def test_unscheduled_shows_stay_neutral_after_a_no_op_render():
    at = AppTest.from_function(_script, default_timeout=30)
    at.run()
    assert not at.exception

    shows = at.session_state["oxygen_shows"]
    assert all(s.slot_day is None and s.slot_hour is None for s in shows)
    assert all(s.schedule_multiplier() == 1.0 for s in shows)


def test_grid_no_longer_requires_a_double_click():
    # Reworked 2026-09-22, per user request, after testing surfaced the
    # double-click SelectboxColumn as a real, silent trap (students
    # single-clicking and getting nothing to happen, confirmed by hand
    # during this session). The grid is now individual st.selectbox
    # widgets, one per (day, hour) cell, which open on a single click --
    # the same interaction every other dropdown in this app already uses.
    # This guards against reintroducing the old double-click-only widget
    # (and its now-inaccurate instructions) by mistake.
    at = AppTest.from_function(_script, default_timeout=30)
    at.run()
    text = "\n".join(md.value for md in at.markdown)
    assert "double-click" not in text.lower()
    assert "click a cell's dropdown" in text.lower()
    # 7 days x 4 hours of real selectbox widgets, not a data_editor grid.
    primetime_cells = [sb for sb in at.selectbox if sb.key.startswith("primetime_cell_")]
    assert len(primetime_cells) == 28


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


def _schedule_script():
    import streamlit as st
    import sys
    sys.path.insert(0, ".")
    from utils.models import Show
    defaults = {
        "active_network": "oxygen", "year": 1, "mkt_budget": 5.0,
        "cancelled_shows": set(), "renewal_decisions": {2: "Cancel"},
        "greenlit_ids_this_year": set(),
        "oxygen_shows": [
            Show(id=1, name="Show A", genre="Reality", episodes=10, ep_cost_k=300,
                 rating=1.0, ip_score=40, air_month=1, network="Oxygen"),
            Show(id=2, name="Show B", genre="True Crime", episodes=8, ep_cost_k=350,
                 rating=0.9, ip_score=45, air_month=3, network="Oxygen"),
            Show(id=3, name="Show C", genre="True Crime", episodes=10, ep_cost_k=400,
                 rating=1.2, ip_score=50, air_month=9, network="Oxygen"),
        ],
        "bravo_shows": [], "peacock_shows": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    import app_pages.schedule as schedule
    schedule.render()


def test_amortization_table_total_matches_the_pnl_content_cost():
    """2026-11-03: the amortization table's 'Charged This Year' total must be
    the same figure the P&L preview charges (simulation._annual_cost), incl.
    the 25% charge for a show cancelled this year."""
    from utils.models import Show
    from app_pages.simulation import _annual_cost
    at = AppTest.from_function(_schedule_script, default_timeout=30)
    at.run()
    assert not at.exception, f"Schedule page raised: {list(at.exception)}"
    shows = at.session_state["oxygen_shows"]
    expected = _annual_cost(shows, 1, set(), {2})
    text = "\n".join(md.value for md in at.markdown)
    assert f"<b>${expected:.1f}M</b> of that hits this year" in text
    assert "Key takeaway" in text


def test_payoff_schedule_this_year_matches_table_and_defers_true_crime():
    """2026-11-03: the Payoff Schedule's first year equals what the table
    charges this year (non-cancelled shows), and a True Crime show's
    remaining half shows up in the following year."""
    at = AppTest.from_function(_schedule_script, default_timeout=30)
    at.run()
    assert not at.exception, f"Schedule page raised: {list(at.exception)}"
    shows = at.session_state["oxygen_shows"]
    a, c = shows[0], shows[2]                     # show 2 is cancelled in the fixture
    now = a.annual_amort_expense(1) + c.annual_amort_expense(1)
    later = c.total_cost(1) - c.annual_amort_expense(1)
    text = "\n".join(md.value for md in at.markdown)
    assert f"<b>${now:.1f}M</b> of this season's cost is charged this year" in text
    assert f"<b>${later:.1f}M</b> rolls into the next two years" in text
