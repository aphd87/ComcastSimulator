"""
Smoke tests for app_pages/greenlight.py's AI Pitch Generator slot-gating,
added 2026-08-04 per user request: students should be able to keep asking
for another AI-proposed pitch idea until they've filled their remaining
greenlight slots for the year, not indefinitely (there's no point pitching
concepts that can't be greenlit until next year).

api_key_configured() is monkeypatched to True here since the AI Pitch
Generator block is entirely skipped otherwise (no ANTHROPIC_API_KEY in the
test environment) -- these tests exist specifically to exercise that block.
"""
from streamlit.testing.v1 import AppTest

import utils.ai_grading as ai_grading
from utils.ai_grading import ShowPitchIdea
from utils.game_state import MAX_NEW_SHOWS_PER_YEAR


def _fake_pitches(network_context: str, n: int = 3) -> list[ShowPitchIdea]:
    return [
        ShowPitchIdea(
            show_name=f"Test Pitch Show {i}", genre="Reality", pitch="A test pitch.",
            suggested_episodes=10, suggested_ep_cost_k=500,
            suggested_rating=1.2, suggested_svod_appeal=70,
        )
        for i in range(n)
    ]


def _greenlight_app(monkeypatch, greenlit_count: int) -> AppTest:
    monkeypatch.setattr(ai_grading, "api_key_configured", lambda: True)
    monkeypatch.setattr(ai_grading, "generate_show_pitches", _fake_pitches)

    def script(greenlit_count):
        # AppTest.from_function re-execs this via inspect.getsourcelines as a
        # standalone module, not a real closure -- neither a free variable
        # nor a default-argument expression referencing one survives that
        # (both raise NameError, since the enclosing scope's bytecode isn't
        # there, only the literal source text is). Passing the value in via
        # AppTest's own `args=` is the one path that actually works.
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        st.session_state.team_name = "AppTest Team"
        st.session_state.active_network = "oxygen"
        st.session_state.year = 1
        st.session_state.greenlit_ids_this_year = set(range(greenlit_count))

        import app_pages.greenlight as greenlight
        greenlight.render()

    at = AppTest.from_function(script, default_timeout=30, args=(greenlit_count,))
    at.run()
    assert not at.exception, f"Greenlight page raised: {list(at.exception)}"
    return at


def test_pitch_button_shown_with_slots_remaining(monkeypatch):
    at = _greenlight_app(monkeypatch, greenlit_count=0)
    labels = [b.label for b in at.button]
    assert any("Get 3 AI Pitch Ideas" in l for l in labels)
    text = "\n".join(md.value for md in at.markdown)
    assert f"{MAX_NEW_SHOWS_PER_YEAR} of {MAX_NEW_SHOWS_PER_YEAR}" in text   # all 3 slots still open
    assert "slots left this year" in text


def test_pitch_button_hidden_once_slots_are_full(monkeypatch):
    at = _greenlight_app(monkeypatch, greenlit_count=MAX_NEW_SHOWS_PER_YEAR)
    labels = [b.label for b in at.button]
    assert not any("Pitch" in l for l in labels)
    text = "\n".join(md.value for md in at.markdown)
    assert "filled all your greenlight slots" in text


def test_generating_pitches_shows_a_card_per_idea(monkeypatch):
    at = _greenlight_app(monkeypatch, greenlit_count=0)
    at.button(key="gl_generate_pitch").click()
    at.run()
    assert not at.exception, f"Generating pitches raised: {list(at.exception)}"
    text = "\n".join(md.value for md in at.markdown)
    assert text.count("Test Pitch Show") == 3
    assert any("Use This Pitch" in b.label for b in at.button)


def test_using_a_pitch_autofills_the_concept_builder(monkeypatch):
    at = _greenlight_app(monkeypatch, greenlit_count=0)
    at.button(key="gl_generate_pitch").click()
    at.run()
    at.button(key="gl_use_pitch_1_Test Pitch Show 1").click()
    at.run()
    assert not at.exception, f"Using a pitch raised: {list(at.exception)}"
    assert at.session_state["gl_show_name"] == "Test Pitch Show 1"
    assert at.session_state["gl_ep_cost"] == 500
    text = "\n".join(md.value for md in at.markdown)
    assert "Loaded pitch" in text
