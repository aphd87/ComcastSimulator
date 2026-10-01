"""AI Pitch Review (app_pages/greenlight.py::_render_pitch_review): a student
writes their own pitch, gets feedback plus an AI-estimated pitch card, and
can greenlight it with the AI's numbers (not their own sliders). The Claude
call is faked here; tests never hit the real API."""
from streamlit.testing.v1 import AppTest

import utils.ai_grading as ai_grading
from utils.ai_grading import ShowPitchEstimate, ShowPitchReview, clamp_estimate

CALLS = []


def _fake_review(show_name, genre, pitch, origin, format_source, network_display,
                 ep_cost_range_k, calibration):
    CALLS.append({"origin": origin, "format_source": format_source, "calibration": calibration})
    return ShowPitchReview(
        originality_score=18, market_fit_score=20, feasibility_score=17, presentation_score=19,
        feedback="Solid hook.", strengths=["Clear audience"], risks=["Crowded genre"],
        research_recommended=False, research_rationale="Predictable format.",
        estimate=ShowPitchEstimate(
            demo_age="25-54", demo_gender="Skews Female", demo_reach="National (US)",
            episodes=10, ep_cost_k=310, rating=1.0, svod_appeal=58, ip_score=62,
            rationale="Cheap docuseries format with a loyal niche.",
        ),
    )


def _app(monkeypatch, budget=95.0):
    CALLS.clear()
    monkeypatch.setattr(ai_grading, "api_key_configured", lambda: True)
    monkeypatch.setattr(ai_grading, "review_show_pitch", _fake_review)

    def script(budget):
        import copy
        import sys
        import streamlit as st
        sys.path.insert(0, ".")
        from utils.data import OXYGEN_SLATE
        ss = st.session_state
        if "oxygen_shows" not in ss:
            ss.team_name = "AppTest Team"
            ss.active_network = "oxygen"
            ss.year = 1
            ss.level_budget = budget
            ss.oxygen_shows = copy.deepcopy(OXYGEN_SLATE)
        import app_pages.greenlight as greenlight
        greenlight.render()

    at = AppTest.from_function(script, default_timeout=30, args=(budget,))
    at.run()
    assert not at.exception, list(at.exception)
    return at


def _review(at, pitch="A Dutch cold-case docuseries format, re-cut for US true-crime fans.",
            origin="Domestic Original", source="", name="Harbor Lights"):
    at.text_input(key="gl_show_name").set_value(name)
    at.selectbox(key="gl_genre").set_value("True Crime")
    at.text_area(key="gl_pitch_text").set_value(pitch)
    at.radio(key="gl_pitch_origin").set_value(origin)
    at.run()
    if source:
        at.text_input(key="gl_pitch_format_source").set_value(source)
    at.button(key="gl_grade_button").click()
    at.run()
    assert not at.exception, list(at.exception)
    return at


def _page_text(at) -> str:
    return " ".join(m.value for m in at.markdown)


def test_review_shows_feedback_and_estimated_card(monkeypatch):
    at = _review(_app(monkeypatch))
    text = _page_text(at)
    assert "Pitch score: 74/100" in text
    assert "AI-ESTIMATED PITCH CARD" in text
    assert "Demo: 25-54 · Skews Female · National (US)" in text
    assert "rating 1.0" in text and "IP Score 62" in text
    assert "No rights fee (in-house original)" in text
    assert "Cold Case Files: Rotterdam" in CALLS[0]["calibration"]   # catalog passed in for scale


def test_greenlight_uses_ai_numbers_not_sliders(monkeypatch):
    at = _review(_app(monkeypatch))
    at.slider(key="gl_rating").set_value(3.5)                 # student tries to claim a mega-hit
    at.run()
    at = _review(at)                                          # inputs unchanged -> review still current
    at.button(key="gl_greenlight_ai").click()
    at.run()
    assert not at.exception, list(at.exception)
    ss = at.session_state
    new = ss["oxygen_shows"][-1]
    assert new.name == "Harbor Lights"
    assert new.rating == 1.0 and new.ip_score == 62 and new.ep_cost_k == 310
    assert abs(ss["level_budget"] - (95.0 - 3.10)) < 1e-6     # production cost only, no fee
    assert ss["gl_ai_review"] is None


def test_international_format_pays_the_marketplace_rights_fee(monkeypatch):
    at = _review(_app(monkeypatch), origin="International Format", source="Netherlands")
    assert CALLS[-1]["origin"] == "International Format" and CALLS[-1]["format_source"] == "Netherlands"
    text = _page_text(at)
    assert "International Format (Netherlands)" in text
    assert "Rights fee: <b>$2.79M</b> + $3.10M season production cost" in text   # same as the catalog card
    at.button(key="gl_greenlight_ai").click()
    at.run()
    assert abs(at.session_state["level_budget"] - (95.0 - 2.79 - 3.10)) < 1e-6


def test_editing_the_pitch_marks_the_review_stale(monkeypatch):
    at = _review(_app(monkeypatch))
    at.text_area(key="gl_pitch_text").set_value("A totally different idea.")
    at.run()
    assert "changed since the last review" in " ".join(c.value for c in at.caption)
    assert not any(b.key == "gl_greenlight_ai" for b in at.button)


def test_load_into_concept_inputs_sets_sliders(monkeypatch):
    at = _review(_app(monkeypatch))
    at.button(key="gl_load_ai_estimates").click()
    at.run()
    assert not at.exception, list(at.exception)
    assert at.number_input(key="gl_eps").value == 10
    assert at.number_input(key="gl_ep_cost").value == 310
    assert at.slider(key="gl_appeal").value == 58


def test_no_api_key_shows_instructor_message(monkeypatch):
    monkeypatch.setattr(ai_grading, "api_key_configured", lambda: False)

    def script():
        import sys
        import streamlit as st
        sys.path.insert(0, ".")
        st.session_state.team_name = "T"
        st.session_state.active_network = "oxygen"
        st.session_state.year = 1
        import app_pages.greenlight as greenlight
        greenlight.render()

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert "enable AI pitch review" in _page_text(at)
    assert not any(b.key == "gl_grade_button" for b in at.button)


def test_clamp_keeps_absurd_estimates_inside_the_game_economy():
    est = ShowPitchEstimate(demo_age="18-49", demo_gender="Balanced", demo_reach="Global",
                            episodes=200, ep_cost_k=99999, rating=9.7, svod_appeal=500,
                            ip_score=-5, rationale="x")
    d = clamp_estimate(est)
    assert (d["episodes"], d["ep_cost_k"], d["rating"], d["svod_appeal"], d["ip_score"]) == (24, 5000, 2.5, 100, 20)


def test_marketplace_title_is_rejected(monkeypatch):
    at = _review(_app(monkeypatch), name="Cold Case Files: Rotterdam")
    assert not CALLS, "the AI should not be called for a taken title"
    assert any("already exists" in w.value for w in at.warning)
