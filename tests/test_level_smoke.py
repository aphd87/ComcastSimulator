"""Full-slate smoke test per level (2026-11-03): each network's decisions page
renders with its real starting slate and one Simulate Year click works, now
that Bravo and Peacock each run only their own shows."""
import pytest
from streamlit.testing.v1 import AppTest


def _app(net):
    def script(net):
        import copy, sys
        import streamlit as st
        sys.path.insert(0, ".")
        from utils.data import OXYGEN_SLATE, BRAVO_SLATE, PEACOCK_SLATE
        from utils.game_state import NETWORK_INFO
        defaults = {
            "team_name": "Smoke Team", "school": "Test School", "class_section": "Sec A",
            "active_network": net,
            "oxygen_shows": copy.deepcopy(OXYGEN_SLATE), "bravo_shows": copy.deepcopy(BRAVO_SLATE),
            "peacock_shows": copy.deepcopy(PEACOCK_SLATE),
            "cancelled_shows": set(), "renewal_decisions": {}, "research_revealed": {},
            "yearly_log": [], "year": 1, "sim_phase": "decisions",
            "level_budget": float(NETWORK_INFO[net]["budget_base"]), "mkt_budget": 5.0,
            "sports_contracts": [], "sports_bid_log": {},
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v
        import app_pages.simulation as simulation
        simulation.render()
    at = AppTest.from_function(script, args=(net,), default_timeout=60)
    at.run()
    return at


@pytest.mark.parametrize("net", ["oxygen", "bravo", "peacock"])
def test_level_renders_and_simulates_with_its_own_slate(net):
    at = _app(net)
    assert not at.exception, list(at.exception)
    text = "\n".join(m.value for m in at.markdown)
    if net == "bravo":
        assert "Cold Case" not in text and "(True Crime)" not in text
    sim = [b for b in at.button if "Simulate Year" in b.label]
    assert sim
    sim[0].click().run()
    assert not at.exception, list(at.exception)
    assert at.session_state["sim_phase"] == "results"
