"""
Smoke tests for the TV Show Acquisition Marketplace (app_pages/greenlight.py),
added 2026-08-24 per user request: TV/Streaming only ever let a student build
a show concept from scratch -- this adds a second path, a fixed catalog of
already-pitched fictional shows (utils/models.py::TV_PITCH_CATALOG) a
student can acquire outright, each with a real origin (Domestic vs.
International Format) and an optional Brand Partnership subsidy.
"""
from streamlit.testing.v1 import AppTest

from utils.game_state import MAX_NEW_SHOWS_PER_YEAR
from utils.models import TV_PITCH_CATALOG, tv_pitch_acquisition_fee_m


def _greenlight_app(greenlit_count: int = 0, budget: float = 500.0) -> AppTest:
    def script(greenlit_count, budget):
        # Seed values only if absent -- AppTest re-executes this whole
        # function on every .run(), including reruns triggered by a widget
        # click, so an unconditional assignment here would wipe out any
        # mutation the click itself just made (e.g. an acquired show
        # appended to oxygen_shows) the moment the next .run() fires.
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        ss = st.session_state
        if "team_name" not in ss:
            ss.team_name = "AppTest Team"
            ss.active_network = "oxygen"
            ss.year = 1
            ss.oxygen_shows = []
            ss.bravo_shows = []
            ss.level_budget = budget
            ss.greenlit_ids_this_year = set(range(greenlit_count))
            ss.greenlit_ids_this_level = set()
            ss.total_shows_greenlit = 0

        import app_pages.greenlight as greenlight
        greenlight.render()

    at = AppTest.from_function(script, default_timeout=30, args=(greenlit_count, budget))
    at.run()
    assert not at.exception, f"Greenlight page raised: {list(at.exception)}"
    return at


def test_every_catalog_pitch_has_a_card_and_acquire_button():
    at = _greenlight_app()
    text = "\n".join(md.value for md in at.markdown)
    for pitch in TV_PITCH_CATALOG.values():
        assert pitch["name"] in text
    labels = [b.label for b in at.button]
    assert sum(1 for l in labels if l.startswith("Acquire ")) == len(TV_PITCH_CATALOG)


def test_acquiring_a_pitch_adds_it_to_the_roster_and_deducts_budget():
    at = _greenlight_app(budget=500.0)
    key = "peak_condition"
    pitch = TV_PITCH_CATALOG[key]
    fee = tv_pitch_acquisition_fee_m(pitch)
    season_cost = pitch["episodes"] * pitch["ep_cost_k"] / 1000

    at.button(key=f"acquire_{key}").click()
    at.run()
    assert not at.exception, f"Acquiring a pitch raised: {list(at.exception)}"

    ss = at.session_state
    names = [s.name for s in ss["oxygen_shows"]]
    assert pitch["name"] in names
    acquired_show = next(s for s in ss["oxygen_shows"] if s.name == pitch["name"])
    assert acquired_show.genre == pitch["genre"]
    assert acquired_show.ip_score == pitch["ip_score"]
    assert ss["level_budget"] == 500.0 - fee - season_cost
    assert key in ss["tv_pitches_acquired"]
    assert acquired_show.id in ss["greenlit_ids_this_year"]


def test_acquiring_a_pitch_applies_the_brand_partnership_rating_bonus():
    at = _greenlight_app(budget=500.0)
    key = "sunset_collective"
    pitch = TV_PITCH_CATALOG[key]
    bonus = pitch["brand_partner"]["rating_bonus"]

    at.button(key=f"acquire_{key}").click()
    at.run()
    assert not at.exception

    ss = at.session_state
    acquired_show = next(s for s in ss["oxygen_shows"] if s.name == pitch["name"])
    assert round(acquired_show.rating, 4) == round(pitch["rating"] + bonus, 4)


def test_an_acquired_pitch_is_no_longer_offered_again():
    at = _greenlight_app(budget=500.0)
    key = "peak_condition"
    at.button(key=f"acquire_{key}").click()
    at.run()
    assert not at.exception

    labels = [b.label for b in at.button]
    assert f"Acquire \"{TV_PITCH_CATALOG[key]['name']}\"" not in labels
    assert sum(1 for l in labels if l.startswith("Acquire ")) == len(TV_PITCH_CATALOG) - 1


def test_acquire_buttons_disabled_once_greenlight_slots_are_full():
    at = _greenlight_app(greenlit_count=MAX_NEW_SHOWS_PER_YEAR)
    labels = [b.label for b in at.button]
    assert not any(l.startswith("Acquire ") for l in labels)
    text = "\n".join(c.value for c in at.caption)
    assert "No greenlight slots left this year." in text
