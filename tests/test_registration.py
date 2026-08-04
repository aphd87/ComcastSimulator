"""
Real click-through test for app.py's Team Registration flow.

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

Registration moved out of st.sidebar into the main content area on
2026-07-30 (the left sidebar was removed entirely -- see app.py), so this
now drives `at.text_input`/`at.button` directly instead of `at.sidebar.*`.
"""
from streamlit.testing.v1 import AppTest


def _fresh_app():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    return at


def _fill_and_submit(at, university="Test University", college="Test School of Business",
                      class_title="Media Strategy Sec A", semester="Fall 2026", team="Team Alpha"):
    at.text_input(key="university_input_field").set_value(university)
    at.text_input(key="college_input_field").set_value(college)
    at.text_input(key="class_title_input_field").set_value(class_title)
    at.text_input(key="semester_input_field").set_value(semester)
    at.text_input(key="team_input_field").set_value(team)
    at.button[0].click()
    at.run()
    return at


def test_registration_with_all_fields_succeeds():
    at = _fresh_app()
    assert not at.exception
    assert at.session_state["registered"] is False
    # University, School/College, Team Name, Class Title, Semester/Year,
    # Class Abbreviation (optional) -- Class Title/Semester split out of the
    # old merged "Class / Section" field 2026-08-04.
    assert len(at.text_input) == 6
    # Register Team + the "Just check the Leaderboard" shortcut added
    # 2026-07-30 -- button[0] (Register Team, rendered first) is what
    # _fill_and_submit clicks.
    assert len(at.button) == 2

    _fill_and_submit(at)
    assert not at.exception, f"Registration raised: {list(at.exception)}"
    assert not list(at.error)
    assert at.session_state["registered"] is True
    assert at.session_state["team_name"] == "Team Alpha"
    assert at.session_state["school"] == "Test School of Business, Test University"
    # class_section stays the combined identity-key string (semester + title)
    # under the hood even though Class Title/Semester are now separate boxes.
    assert at.session_state["class_section"] == "Fall 2026 — Media Strategy Sec A"
    # Class Abbreviation is optional -- left blank here, registration still succeeds.
    assert at.session_state["class_abbrev"] == ""


def test_registration_captures_class_abbreviation_when_filled_in():
    at = _fresh_app()
    at.text_input(key="university_input_field").set_value("Test University")
    at.text_input(key="college_input_field").set_value("Test School of Business")
    at.text_input(key="class_title_input_field").set_value("Media Strategy Sec A")
    at.text_input(key="semester_input_field").set_value("Fall 2026")
    at.text_input(key="class_abbrev_input_field").set_value("MBA6120")
    at.text_input(key="team_input_field").set_value("Team Alpha")
    at.button[0].click()
    at.run()

    assert not at.exception
    assert at.session_state["registered"] is True
    assert at.session_state["class_abbrev"] == "MBA6120"


def test_registration_shows_the_simulation_nav_afterward():
    # Seeded directly to the post-registration state with a single .run(),
    # rather than driving it via a button click -- the Register button's
    # handler calls st.rerun(), and re-querying at.text_input() on the same
    # AppTest object after that click hits the documented AppTest +
    # st.rerun() limitation (stale widget entries survive the rerun with no
    # value bound, see DESIGN_NOTES.md). Same workaround already used in
    # tests/test_simulation.py and tests/test_movies_page.py for phase
    # transitions -- a fresh, pre-seeded .run() is outside the harness's
    # documented "second interaction" breakage window.
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["registered"]    = True
    at.session_state["team_name"]     = "Team Alpha"
    at.session_state["school"]        = "Test School of Business, Test University"
    at.session_state["class_section"] = "Fall 2026 Sec A"
    at.run()

    assert not at.exception
    # Post-registration, the Team Registration form is replaced by the
    # Active Team card, and the App/Leaderboard/TV/Movies nav appears --
    # both gated behind `if ss.registered:` in app.py.
    assert len(at.text_input) == 0
    text = "\n".join(md.value for md in at.markdown)
    assert "Team Alpha" in text


def test_registration_blocks_on_missing_team_name():
    at = _fresh_app()
    at.text_input(key="university_input_field").set_value("Test University")
    at.text_input(key="college_input_field").set_value("Test School")
    at.text_input(key="class_title_input_field").set_value("Sec A")
    at.text_input(key="semester_input_field").set_value("Fall 2026")
    at.text_input(key="team_input_field").set_value("")   # left blank
    at.button[0].click()
    at.run()

    assert not at.exception
    assert at.session_state["registered"] is False
    errors = [e.value for e in at.error]
    assert any("team name" in e.lower() for e in errors)


def test_registration_blocks_on_missing_university():
    at = _fresh_app()
    at.text_input(key="university_input_field").set_value("")   # left blank
    at.text_input(key="college_input_field").set_value("Test School")
    at.text_input(key="class_title_input_field").set_value("Sec A")
    at.text_input(key="semester_input_field").set_value("Fall 2026")
    at.text_input(key="team_input_field").set_value("Team Alpha")
    at.button[0].click()
    at.run()

    assert not at.exception
    assert at.session_state["registered"] is False
    errors = [e.value for e in at.error]
    assert any("university" in e.lower() for e in errors)


def test_leaderboard_reachable_without_registering():
    # "Just check the Leaderboard" (sign-in screen, button[1]) sets
    # active_section="leaderboard" without ever setting ss.registered --
    # app.py's top-level branch has to let that win over the not-registered
    # gate, or an anonymous visitor would just see the sign-in form again.
    at = _fresh_app()
    assert at.button[1].label == "🏆 Just check the Leaderboard"
    at.button[1].click()
    at.run()

    assert not at.exception
    assert at.session_state["registered"] is False
    assert at.session_state["active_section"] == "leaderboard"
    # My Team Status is skipped for anonymous visitors (no team to show);
    # a way back to the sign-in form is offered instead.
    assert any("Back to Sign In" in b.label for b in at.button)
    text = "\n".join(md.value for md in at.markdown)
    assert "My Team Status" not in text
