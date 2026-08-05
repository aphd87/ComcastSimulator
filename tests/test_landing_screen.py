"""
Tests for app.py's "Choose Your Simulation" landing screen (registered
users, ss.active_section in (None, "app")). Gained a third Leaderboard
card 2026-08-05, matching the existing TV/Streaming and Movies cards'
visual treatment -- per user feedback that the sign-in page's "Just check
the Leaderboard" button (now retitled "View Leaderboard", still present
for anonymous pre-registration access) was an odd, orphaned home for a
registered user who's already past sign-in and just wants to check
standings before picking a simulation.
"""
from streamlit.testing.v1 import AppTest


def _landing_app() -> AppTest:
    """Seeds straight to a registered team on the landing screen, single
    .run(), no button click -- avoids the documented AppTest + st.rerun()
    limitation (see tests/test_registration.py)."""
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["registered"]     = True
    at.session_state["team_name"]      = "Team Alpha"
    at.session_state["school"]         = "Test School of Business, Test University"
    at.session_state["class_section"]  = "Fall 2026 Sec A"
    at.session_state["active_section"] = None
    at.run()
    assert not at.exception, f"Landing screen raised: {list(at.exception)}"
    return at


def test_landing_screen_shows_three_peer_cards():
    at = _landing_app()
    text = "\n".join(md.value for md in at.markdown)
    assert "TV / Streaming" in text
    assert "Movies" in text
    assert "Leaderboard" in text


def test_landing_screen_has_three_navigation_buttons():
    # Distinct from the top nav row's own "🏆 Leaderboard" button -- these
    # are the landing screen's own three peer-card CTAs.
    at = _landing_app()
    labels = [b.label for b in at.button]
    assert "→ Start TV / Streaming" in labels
    assert "→ Start Movies" in labels
    assert "→ View Leaderboard" in labels


def test_clicking_landing_screen_leaderboard_card_navigates_there():
    at = _landing_app()
    lb_button = next(b for b in at.button if b.label == "→ View Leaderboard")
    lb_button.click().run()
    assert not at.exception, f"Leaderboard click raised: {list(at.exception)}"
    assert at.session_state["active_section"] == "leaderboard"
