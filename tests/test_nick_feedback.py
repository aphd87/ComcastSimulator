"""Fixes from Nick's review of The Slate (2026-11-04), one test per point that
changed code, plus an automated replay of his Oxygen -> Bravo -> Peacock
click-through test script."""
import copy

import pytest
from streamlit.testing.v1 import AppTest

import utils.game_state as gs
from utils.data import OXYGEN_SLATE
from utils.models import portfolio_ad_rev


# ── #5 Marketing follows Zach's per-show model ────────────────────────────────
# Nick found the Financing text (network-wide, tapering past $16M) contradicted
# the code. Per Zach's brief ("$3M marketing minimum for show viability"), the
# per-show split in the code is the design; the text was fixed instead.
def test_marketing_is_split_evenly_across_shows():
    shows = copy.deepcopy(OXYGEN_SLATE)
    per_show = 20 / len(shows)
    expected = sum(s.ad_revenue(1, per_show) for s in shows)
    assert portfolio_ad_rev(shows, 1, 20) == pytest.approx(expected)


def test_financing_text_describes_the_per_show_model():
    src = open("app_pages/simulation.py", encoding="utf-8").read()
    assert "split evenly across your active shows" in src
    assert "Diminishing returns above $16M" not in src


# ── #7 Capitalization and spacing don't split a team ─────────────────────────
def test_retyped_identity_adopts_the_spelling_on_record():
    gs.save_live_state("Team 1", "Darden, UVa", "Fall 2026 — Media Strat", {"year": 1})
    # School resolves to its canonical spelling (2026-11-05), and the Driver's
    # state saved under the old spelling still loads.
    ident = gs.canonical_identity("team 1 ", "darden,  uva", "FALL 2026 — media strat")
    assert ident == ("Team 1", "Darden School of Business, University of Virginia", "Fall 2026 — Media Strat")
    assert gs.load_live_state(*ident) == {"year": 1}


def test_new_identity_is_left_alone():
    gs.save_live_state("Team 1", "Darden, UVa", "Fall 2026 — Media Strat", {"year": 1})
    assert gs.canonical_identity("Team 2", "Darden, UVa", "Fall 2026 — Media Strat")[0] == "Team 2"
    assert gs.canonical_identity("Team 1", "Wharton, Penn", "Fall 2026 — Media Strat") == \
        ("Team 1", "Wharton, Penn", "Fall 2026 — Media Strat")


# ── App-level helpers ─────────────────────────────────────────────────────────
def _register(team="Team 2", role="🎮 Driver — I'll make the decisions"):
    at = AppTest.from_file("app.py", default_timeout=90)
    at.run()
    at.text_input(key="university_input_field").set_value("UVa")
    at.text_input(key="college_input_field").set_value("Darden")
    at.text_input(key="class_title_input_field").set_value("Media Strat")
    at.text_input(key="semester_input_field").set_value("Fall 2026")
    at.text_input(key="team_input_field").set_value(team)
    at.radio(key="role_input_field").set_value(role)
    at.button(key="register_team_button").click()
    at.run()
    assert not at.exception, list(at.exception)
    return at


def _btn(at, text):
    return next(b for b in at.button if text in b.label)


def _to_network(at, net):
    _btn(at, "Start TV / Streaming").click()
    at.run()
    at.button(key=f"pick_net_{net}").click()
    at.run()
    assert not at.exception, list(at.exception)


def test_follow_along_finds_driver_despite_capitalization():
    driver = _register("Team 1")
    _to_network(driver, "oxygen")
    viewer = _register("team 1", role="👀 Follow Along — view only")
    assert viewer.session_state["team_name"] == "Team 1"


# ── #1/#2 Clicking the network you're on doesn't restart it ───────────────────
def test_clicking_current_network_keeps_the_run():
    at = _register()
    _to_network(at, "oxygen")
    at.slider(key="mkt_budget_slider").set_value(4.0)
    at.run()
    at.button(key="net_oxygen").click()
    at.run()
    assert not at.exception, list(at.exception)
    assert at.session_state["mkt_budget"] == 4.0
    assert at.session_state["active_network"] == "oxygen"


# ── #6 Financing's Ad Revenue preview excludes cancelled shows ─────────────────
def test_financing_ad_revenue_excludes_cancelled_shows():
    def script():
        import copy, sys
        import streamlit as st
        sys.path.insert(0, ".")
        from utils.data import OXYGEN_SLATE, BRAVO_SLATE, PEACOCK_SLATE
        defaults = {
            "team_name": "Preview Team", "school": "S", "class_section": "C", "active_network": "oxygen",
            "oxygen_shows": copy.deepcopy(OXYGEN_SLATE), "bravo_shows": copy.deepcopy(BRAVO_SLATE),
            "peacock_shows": copy.deepcopy(PEACOCK_SLATE),
            "cancelled_shows": {OXYGEN_SLATE[0].id}, "renewal_decisions": {}, "research_revealed": {},
            "yearly_log": [], "year": 2, "sim_phase": "decisions", "level_budget": 95.0, "mkt_budget": 5.0,
            "sports_contracts": [], "sports_bid_log": {},
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v
        import app_pages.simulation as simulation
        simulation.render()

    at = AppTest.from_function(script, default_timeout=60)
    at.run()
    assert not at.exception, list(at.exception)
    shown = next(m for m in at.metric if "Ad Revenue" in m.label).value
    active = [s for s in OXYGEN_SLATE if s.id != OXYGEN_SLATE[0].id]
    assert shown == f"${portfolio_ad_rev(active, 2, 5.0):.1f}M"


# ── Nick's click-through test, automated ──────────────────────────────────────
# Followed step for step. His script predates one-network-per-level (11/3):
# Cold Justice, Sunset Collective and Cold Case Files: Rotterdam are Oxygen
# content, so Bravo and Peacock use their own first show / pitch instead.
def _set_builder(at, name, pitch):
    at.text_input(key="gl_show_name").set_value(name)
    at.selectbox(key="gl_genre").set_value("Reality")
    at.number_input(key="gl_eps").set_value(10)
    at.number_input(key="gl_ep_cost").set_value(750)
    at.slider(key="gl_rating").set_value(1.2)
    at.slider(key="gl_mkt_spend").set_value(2.0)
    at.slider(key="gl_appeal").set_value(72)
    at.select_slider(key="gl_air_month").set_value("3 · Mar")
    at.number_input(key="gl_svod_prem").set_value(8.0)
    at.text_area(key="gl_pitch_text").set_value(pitch)
    at.run()
    at.button(key="gl_greenlight_manual").click()
    at.run()
    assert not at.exception, list(at.exception)


def _acquire_first(at, wanted=None):
    keys = [b.key for b in at.button if (b.key or "").startswith("acquire_") and not b.disabled]
    key = f"acquire_{wanted}" if wanted and f"acquire_{wanted}" in keys else keys[0]
    pk = key[len("acquire_"):]
    month = [s for s in at.select_slider if s.key == f"acquire_month_{pk}"]
    if month:
        month[0].set_value("3 · Mar")
        at.run()
    at.button(key=key).click()
    at.run()
    assert not at.exception, list(at.exception)
    return pk


def _skip_stale_widgets(monkeypatch):
    """AppTest quirk: after a button handler's st.rerun() (Simulate, Start Year),
    the element tree can still hold keyed widgets from the page being left
    while Streamlit has already dropped their state, so the next click fails
    to serialize them. A real browser only sends widgets on screen, so skip
    the stale ones the same way (the real app is unaffected)."""
    import streamlit.testing.v1.element_tree as et
    original = et.get_widget_state

    def tolerant(node):
        try:
            return original(node)
        except KeyError:
            return None
    monkeypatch.setattr(et, "get_widget_state", tolerant)


def _play_four_years(at, net):
    for year in range(1, 5):
        _btn(at, f"Simulate Year {year}").click()
        at.run()
        assert not at.exception, (net, year, list(at.exception))
        assert at.session_state["yearly_log"][-1]["year"] == year
        if year < 4:
            _btn(at, "Start Year").click()
            at.run()
    _btn(at, "View Final Results").click()
    at.run()
    assert not at.exception, list(at.exception)
    official = gs.get_official_score("Team 2", net, at.session_state["school"], at.session_state["class_section"])
    assert official, f"{net}: no official score recorded"
    return official


def test_nick_click_through_replay(monkeypatch):
    _skip_stale_widgets(monkeypatch)
    at = _register()
    _to_network(at, "oxygen")
    scores = {}

    # 1 Oxygen
    at.slider(key="mkt_budget_slider").set_value(4.0)
    at.run()
    snapped = next(s for s in at.session_state["oxygen_shows"] if s.name == "Snapped")
    at.selectbox(key=f"ren_{snapped.id}").set_value("Renew")
    at.run()
    _btn(at, "Auto-Fill by Rating").click()
    at.run()
    _acquire_first(at, "peak_condition")
    _set_builder(at, "Skriloff World", "Autobiography of the Skriloff family.")
    scores["oxygen"] = _play_four_years(at, "oxygen")
    _btn(at, "Advance to Bravo").click()
    at.run()
    assert at.session_state["active_network"] == "bravo" and at.session_state["year"] == 1

    # 2 Bravo
    at.slider(key="mkt_budget_slider").set_value(12.0)
    at.run()
    first = at.session_state["bravo_shows"][0]
    at.selectbox(key=f"ren_{first.id}").set_value("Cancel")
    at.run()
    _btn(at, "Auto-Fill by Rating").click()
    at.run()
    _acquire_first(at)
    _set_builder(at, "Bravo Side Door",
                 "Up-and-coming designers transform overlooked rooms under tight budgets and impossible deadlines.")
    scores["bravo"] = _play_four_years(at, "bravo")
    _btn(at, "Advance to Peacock").click()
    at.run()
    assert at.session_state["active_network"] == "peacock"

    # 3 Peacock
    at.slider(key="mkt_budget_slider").set_value(15.0)
    at.run()
    bnw = next(s for s in at.session_state["peacock_shows"] if s.name == "Brave New World")
    at.selectbox(key=f"ren_{bnw.id}").set_value("Cancel")
    at.run()
    _btn(at, "Auto-Fill by Rating").click()
    at.run()
    for ni in [n for n in at.number_input if (n.key or "").startswith("sports_bid_1_")][:3]:
        ni.set_value(1.0)   # entered, not submitted, per the script
    at.run()
    _acquire_first(at)
    _set_builder(at, "Peacock Signal",
                 "A data analyst begins receiving broadcasts that predict crimes one day before they happen.")
    scores["peacock"] = _play_four_years(at, "peacock")

    # 4 Pitch board and official scores
    pitches = {p["title"] for p in gs.class_pitches(at.session_state["school"], at.session_state["class_section"])}
    assert {"Skriloff World", "Bravo Side Door", "Peacock Signal"} <= pitches, pitches
    for net, off in scores.items():
        assert off.get("team_name") == "Team 2", (net, off)
