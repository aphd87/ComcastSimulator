"""Choose Your Network screen (app.py::_render_network_picker): entering
TV/Streaming for the first time must offer Oxygen, Bravo, and Peacock
instead of silently defaulting to Oxygen."""
from streamlit.testing.v1 import AppTest


def _to_tv(role="🎮 Driver — I'll make the decisions"):
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.text_input(key="university_input_field").set_value("Test University")
    at.text_input(key="college_input_field").set_value("Test School")
    at.text_input(key="class_title_input_field").set_value("Media Strategy")
    at.text_input(key="semester_input_field").set_value("Fall 2026")
    at.text_input(key="team_input_field").set_value("Team Picker")
    at.radio(key="role_input_field").set_value(role)
    at.button(key="register_team_button").click()
    at.run()
    next(b for b in at.button if b.label == "→ Start TV / Streaming").click()
    at.run()
    return at


def test_picker_offers_all_three_networks_before_any_simulation():
    at = _to_tv()
    assert not at.exception
    keys = {b.key for b in at.button}
    assert {"pick_net_oxygen", "pick_net_bravo", "pick_net_peacock"} <= keys
    assert at.session_state["tv_network_chosen"] is False
    # The simulation itself hasn't rendered yet
    assert not any(b.label.startswith("▶  Simulate Year") for b in at.button)


def test_picking_peacock_starts_peacock_not_oxygen():
    at = _to_tv()
    at.button(key="pick_net_peacock").click()
    at.run()
    assert not at.exception, list(at.exception)
    assert at.session_state["active_network"] == "peacock"
    assert at.session_state["tv_network_chosen"] is True
    assert at.session_state["year"] == 1


def test_follow_along_viewer_skips_picker():
    at = _to_tv(role="👀 Follow Along — view only")
    assert not at.exception
    assert not any((b.key or "").startswith("pick_net_") for b in at.button)
