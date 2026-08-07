"""
Real click-through tests for the Driver/Follow Along live-state sync
(2026-08-07, see DESIGN_NOTES.md's "Homework/in-class split" entry and
utils/game_state.py's Live Team State section).

Uses AppTest.from_file the same way tests/test_registration.py does --
app.py is a bare top-level script, so from_function-with-import silently
no-ops on every .run() after the first (module caching). from_file
re-executes the real script text each run, matching Streamlit's real
script runner, which is required here since the whole point under test is
what app.py does across multiple runs (Driver saves, Viewer loads).
"""
import pytest
from streamlit.testing.v1 import AppTest

import utils.game_state as gs


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    monkeypatch.setattr(gs, "TEAM_STATE_FILE", tmp_path / "team_state.json")
    yield


def _register(at, role="🎮 Driver — I'll make the decisions", team="Team Sync",
              university="Test University", college="Test School of Business",
              class_title="Media Strategy Sec A", semester="Fall 2026"):
    """Registers and navigates to TV/Streaming. Registration alone lands on
    the "app" home cards (elif ss.active_section in (None, "app"): in
    app.py) -- the Driver/Viewer sync only lives in the "tv" dashboard
    branch, same as a real student clicking through, so every caller here
    needs the extra nav click to actually reach it."""
    at.text_input(key="university_input_field").set_value(university)
    at.text_input(key="college_input_field").set_value(college)
    at.text_input(key="class_title_input_field").set_value(class_title)
    at.text_input(key="semester_input_field").set_value(semester)
    at.text_input(key="team_input_field").set_value(team)
    at.radio(key="role_input_field").set_value(role)
    at.button[0].click()
    at.run()
    at.button(key="section_tv").click()
    at.run()
    return at


class TestRoleSelection:
    def test_default_registration_is_driver(self):
        at = AppTest.from_file("app.py", default_timeout=30)
        at.run()
        _register(at)
        assert not at.exception, f"Registration raised: {list(at.exception)}"
        assert at.session_state["team_role"] == "driver"

    def test_registering_follow_along_sets_viewer_role(self):
        at = AppTest.from_file("app.py", default_timeout=30)
        at.run()
        _register(at, role="👀 Follow Along — view only")
        assert not at.exception, f"Registration raised: {list(at.exception)}"
        assert at.session_state["team_role"] == "viewer"

    def test_viewer_with_no_driver_state_yet_does_not_crash(self):
        """A Follow Along teammate can register before their Driver has
        made any move at all -- load_live_state() returns None and the
        page should render the empty/default state, not throw."""
        at = AppTest.from_file("app.py", default_timeout=30)
        at.run()
        _register(at, role="👀 Follow Along — view only", team="Team NoDriverYet")
        assert not at.exception, f"Viewer render raised: {list(at.exception)}"


class TestLiveStateSync:
    def test_drivers_state_is_saved_after_registering(self):
        """Registering (role=driver) immediately renders the TV dashboard,
        which should trigger one save_live_state() call -- the team should
        show up in the shared store without any further interaction."""
        driver = AppTest.from_file("app.py", default_timeout=30)
        driver.run()
        _register(driver)
        assert not driver.exception, f"Driver render raised: {list(driver.exception)}"

        saved = gs.load_live_state("Team Sync", "Test School of Business, Test University",
                                    "Fall 2026 — Media Strategy Sec A")
        assert saved is not None
        assert saved["active_network"] == "oxygen"
        assert saved["year"] == 1
        assert len(saved["oxygen_shows"]) > 0

    def test_viewer_sees_drivers_saved_show_slate(self):
        """The real end-to-end path: Driver registers (saving state), then
        a separate Viewer session registering under the identical identity
        should hydrate its session_state from that saved snapshot."""
        driver = AppTest.from_file("app.py", default_timeout=30)
        driver.run()
        _register(driver)
        assert not driver.exception

        viewer = AppTest.from_file("app.py", default_timeout=30)
        viewer.run()
        _register(viewer, role="👀 Follow Along — view only")
        assert not viewer.exception, f"Viewer render raised: {list(viewer.exception)}"

        assert viewer.session_state["active_network"] == driver.session_state["active_network"]
        assert viewer.session_state["year"] == driver.session_state["year"]
        driver_names = sorted(s.name for s in driver.session_state["oxygen_shows"])
        viewer_names = sorted(s.name for s in viewer.session_state["oxygen_shows"])
        assert driver_names == viewer_names
        assert len(driver_names) > 0

    def test_viewer_never_writes_its_own_state_back(self):
        """A Follow Along session must never call save_live_state -- only
        the Driver's choices should ever count. Registering and rendering
        as viewer, then re-loading, should still show the Driver's
        untouched state (nothing the viewer rendered overwrote it)."""
        driver = AppTest.from_file("app.py", default_timeout=30)
        driver.run()
        _register(driver)
        driver_year = driver.session_state["year"]

        viewer = AppTest.from_file("app.py", default_timeout=30)
        viewer.run()
        _register(viewer, role="👀 Follow Along — view only")
        assert not viewer.exception

        saved = gs.load_live_state("Team Sync", "Test School of Business, Test University",
                                    "Fall 2026 — Media Strategy Sec A")
        assert saved["year"] == driver_year
