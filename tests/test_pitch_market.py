"""Competitor interest in the TV pitch marketplace (utils/pitch_market.py)."""

from streamlit.testing.v1 import AppTest

import utils.pitch_market as pm
from utils.models import TV_PITCH_CATALOG


class _SS(dict):
    """Minimal stand-in for st.session_state (attribute + key access)."""
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def test_only_flagged_pitches_carry_the_premium():
    assert pm.contested_fee(10.0, "the_estate") == 12.5
    assert pm.contested_fee(10.0, "cold_case_rotterdam") == 10.0
    assert set(pm.PITCH_RIVAL_INTEREST) <= set(TV_PITCH_CATALOG)


def test_draws_are_stable_and_only_for_contested_pitches():
    a = [pm.rival_signs_it("team", "the_estate", "oxygen", y) for y in range(2, 30)]
    b = [pm.rival_signs_it("team", "the_estate", "oxygen", y) for y in range(2, 30)]
    assert a == b                                    # same team, same outcome, every time
    assert 0.2 < sum(a) / len(a) < 0.8               # roughly the 50% chance, not always/never
    assert not any(pm.rival_signs_it("team", "after_hours", "oxygen", y) for y in range(2, 30))


def test_resolution_runs_once_per_year_and_never_in_year_one():
    ss = _SS()
    keys = list(TV_PITCH_CATALOG)
    assert pm.resolve_rival_signings(ss, "t", "oxygen", 1, keys) == {}
    first = {}
    for team in range(50):                           # find a team whose rival strikes in year 2
        ss = _SS()
        first = pm.resolve_rival_signings(ss, f"t{team}", "oxygen", 2, keys)
        if first:
            break
    assert first and all(pm.rival_for(k) for k in first)
    assert pm.resolve_rival_signings(ss, f"t{team}", "oxygen", 2, keys) == {}   # no re-roll on rerun/Redo
    assert ss.tv_pitches_lost.keys() == first.keys()


def _script(year, lost):
    import sys
    import streamlit as st
    sys.path.insert(0, ".")
    ss = st.session_state
    ss.team_name = "T"
    ss.active_network = "oxygen"
    ss.year = year
    ss.level_budget = 500.0
    if "oxygen_shows" not in ss:
        import copy
        from utils.data import OXYGEN_SLATE
        ss.oxygen_shows = copy.deepcopy(OXYGEN_SLATE)
    ss.tv_pitch_rival_checks = {("oxygen", year)}   # draws for this year already done
    ss.tv_pitches_lost = dict(lost)
    import app_pages.greenlight as greenlight
    greenlight.render()


def test_cards_flag_rivals_and_lost_pitches_leave_the_market():
    lost = {"the_estate": {"rival": "Northstar TV", "network": "oxygen", "year": 2}}
    at = AppTest.from_function(_script, args=(2, lost), default_timeout=30)
    at.run()
    assert not at.exception, list(at.exception)
    text = " ".join(m.value for m in at.markdown)
    assert "🔥 Competitor interest: Lumen Channel is bidding" in text
    assert "Signed by rival networks" in text and "The Estate" in text and "Northstar TV" in text
    keys = {b.key for b in at.button}
    assert "acquire_the_estate" not in keys          # gone for good
    assert "acquire_second_chance_kitchen" in keys
