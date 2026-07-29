"""
Real click-through test for app.py's Team Registration flow (2026-07-29).

app.py is a bare top-level script (no render() function), so it must be
driven with AppTest.from_file, not AppTest.from_function(script) with an
`import app` inside -- the latter only executes app.py's top-level code
on the FIRST .run(), since Python caches the module import; every
subsequent .run() (e.g. after clicking a button) silently no-ops and the
whole render tree comes back empty with zero exception raised. That false
signal is exactly what looked like a real registration bug during manual
investigation before this test existed -- from_file re-executes the
actual script text every run, the way Streamlit's real script runner
does, and is the only way to trust a post-click assertion here.
"""
from streamlit.testing.v1 import AppTest


def _fresh_app():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    return at


def _fill_and_submit(at, university="Test University", college="Test School of Business",
                      class_section="Fall 2026 Sec A", team="Team Alpha"):
    at.sidebar.text_input(key="university_input_field").set_value(university)
    at.sidebar.text_input(key="college_input_field").set_value(college)
    at.sidebar.text_input(key="class_input_field").set_value(class_section)
    at.sidebar.text_input(key="team_input_field").set_value(team)
    at.sidebar.button[0].click()
    at.run()
    return at


def test_registration_with_all_fields_succeeds():
    at = _fresh_app()
    assert not at.exception
    assert at.session_state["registered"] is False
    assert len(at.sidebar.text_input) == 4
    assert len(at.sidebar.button) == 1

    _fill_and_submit(at)
    assert not at.exception, f"Registration raised: {list(at.exception)}"
    assert not list(at.error)
    assert at.session_state["registered"] is True
    assert at.session_state["team_name"] == "Team Alpha"
    assert at.session_state["school"] == "Test School of Business, Test University"
    assert at.session_state["class_section"] == "Fall 2026 Sec A"


def test_registration_shows_the_simulation_nav_afterward():
    at = _fill_and_submit(_fresh_app())
    assert not at.exception
    # Post-registration, the Team Registration form is replaced by the
    # Active Team card, and the App/Leaderboard/TV/Movies nav appears --
    # both gated behind `if ss.registered:` in app.py.
    assert len(at.sidebar.text_input) == 0
    text = "\n".join(md.value for md in at.sidebar.markdown)
    assert "Team Alpha" in text


def test_registration_blocks_on_missing_team_name():
    at = _fresh_app()
    at.sidebar.text_input(key="university_input_field").set_value("Test University")
    at.sidebar.text_input(key="college_input_field").set_value("Test School")
    at.sidebar.text_input(key="class_input_field").set_value("Sec A")
    at.sidebar.text_input(key="team_input_field").set_value("")   # left blank
    at.sidebar.button[0].click()
    at.run()

    assert not at.exception
    assert at.session_state["registered"] is False
    errors = [e.value for e in at.error]
    assert any("team name" in e.lower() for e in errors)


def test_registration_blocks_on_missing_university():
    at = _fresh_app()
    at.sidebar.text_input(key="university_input_field").set_value("")   # left blank
    at.sidebar.text_input(key="college_input_field").set_value("Test School")
    at.sidebar.text_input(key="class_input_field").set_value("Sec A")
    at.sidebar.text_input(key="team_input_field").set_value("Team Alpha")
    at.sidebar.button[0].click()
    at.run()

    assert not at.exception
    assert at.session_state["registered"] is False
    errors = [e.value for e in at.error]
    assert any("university" in e.lower() for e in errors)
