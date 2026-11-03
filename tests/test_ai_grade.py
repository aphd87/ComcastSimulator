"""Optional AI concept grade (2026-11-03): hidden with no API key; with a key,
one click returns a grade card. The API call itself is mocked."""
from streamlit.testing.v1 import AppTest

GRADE = {"letter_grade": "B+", "score": 84, "network_fit": 22, "hook": 21, "audience": 20, "economics": 21,
         "strengths": ["Clear hook"], "risks": ["Cost is high for the rating"], "one_fix": "Trim to 8 episodes."}


def _app():
    def script():
        import sys
        import streamlit as st
        sys.path.insert(0, ".")
        defaults = {"active_network": "bravo", "year": 1, "level_budget": 220.0, "team_name": "T",
                    "school": "S", "class_section": "A", "oxygen_shows": [], "bravo_shows": [],
                    "peacock_shows": [], "gl_pitch_text": "A luxury wedding-planner competition where "
                    "six planners stage real weddings on impossible budgets."}
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v
        from app_pages.greenlight import render
        render()
    at = AppTest.from_function(script, default_timeout=60)
    at.run()
    assert not at.exception, list(at.exception)
    return at


def test_no_key_means_no_ai_section(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = _app()
    assert not any(b.key == "gl_ai_grade" for b in at.button)


def test_with_key_one_click_shows_grade(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import utils.ai_grading as ai
    calls = []
    monkeypatch.setattr(ai, "grade_concept", lambda net, c: calls.append((net, c)) or dict(GRADE))
    at = _app()
    at.button(key="gl_ai_grade").click().run()
    assert not at.exception, list(at.exception)
    assert len(calls) == 1 and calls[0][0] == "bravo"
    text = " ".join(m.value for m in at.markdown)
    assert "B+" in text and "Trim to 8 episodes." in text
    assert at.session_state["ai_grades_used"]["bravo_1"] == 1


def test_letter_always_matches_score():
    from utils.ai_grading import letter_for
    assert [letter_for(x) for x in (95, 91, 88, 84, 80, 78, 74, 70, 65, 40)] == \
        ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"]
