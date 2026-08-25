"""
Regression test for app_pages/renewal.py, added 2026-08-24 after a QA pass
found the page built its entire working set (per-show decision cards, the
IP-Value-vs-OCF scatter, the Full Renewal Analysis Table, the Primetime
Scheduling dropdown) from the raw, UNFILTERED show roster -- a show
cancelled in an earlier year kept rendering a full interactive
Renew/Watch/Cancel card every year for the rest of the level, indistinguishable
from a live show. app_pages/simulation.py's Financing section already
filtered correctly; this page didn't.
"""
from streamlit.testing.v1 import AppTest

from utils.models import Show


def _renewal_app(cancelled_ids: set) -> AppTest:
    def script(cancelled_ids):
        import sys
        sys.path.insert(0, ".")
        import streamlit as st
        from utils.models import Show
        ss = st.session_state
        ss.team_name      = "AppTest Team"
        ss.active_network = "oxygen"
        ss.year           = 1
        ss.mkt_budget     = 5.0
        ss.oxygen_shows = [
            Show(id=1, name="Alive Show", genre="Reality", episodes=10, ep_cost_k=500,
                 rating=1.0, ip_score=50, air_month=1, network="Oxygen"),
            Show(id=2, name="Dead Show", genre="Reality", episodes=10, ep_cost_k=500,
                 rating=1.0, ip_score=50, air_month=1, network="Oxygen"),
        ]
        ss.bravo_shows       = []
        ss.level_budget      = 100.0
        ss.cancelled_shows   = cancelled_ids
        ss.renewal_decisions = {}
        ss.research_revealed = {}

        import app_pages.renewal as renewal
        renewal.render()

    at = AppTest.from_function(script, default_timeout=30, args=(cancelled_ids,))
    at.run()
    assert not at.exception, f"Renewal page raised: {list(at.exception)}"
    return at


def test_a_cancelled_show_no_longer_gets_a_renewal_decision_card():
    at = _renewal_app(cancelled_ids={2})
    text = "\n".join(md.value for md in at.markdown)
    assert "Alive Show" in text
    assert "Dead Show" not in text
    # No stray selectbox/select_slider keyed to the cancelled show's id.
    assert not any(sb.key == "ren_2" for sb in at.selectbox)


def test_no_shows_cancelled_both_shows_still_appear():
    at = _renewal_app(cancelled_ids=set())
    text = "\n".join(md.value for md in at.markdown)
    assert "Alive Show" in text
    assert "Dead Show" in text
