"""
Tests for THEORY_CONTENT (utils/game_state.py) and its rendering in app.py.

2026-08-05: THEORY_CONTENT was split into "tv" and "movies" categories and
_render_theory_grid() gained a category filter -- previously every Theory
tab (sign-in screen, TV tab, Movies tab) rendered the exact same 5 TV-only
cards, meaning the Movies Theory tab was showing actively wrong framing
(TV-style content amortization, which doesn't apply to Movies' front-
loaded, no-amortization cost structure at all). These tests exist so that
regression can't silently reappear.
"""
from streamlit.testing.v1 import AppTest

from utils.game_state import THEORY_CONTENT


class TestTheoryContentStructure:
    def test_every_entry_has_a_valid_category(self):
        for key, t in THEORY_CONTENT.items():
            assert t["category"] in ("tv", "movies"), f"{key} has an invalid category"

    def test_tv_and_movies_are_evenly_split(self):
        categories = [t["category"] for t in THEORY_CONTENT.values()]
        assert categories.count("tv") == 5
        assert categories.count("movies") == 5

    def test_titles_are_unique_across_both_categories(self):
        titles = [t["title"] for t in THEORY_CONTENT.values()]
        assert len(titles) == len(set(titles))

    def test_every_entry_has_icon_and_nonempty_brief(self):
        for key, t in THEORY_CONTENT.items():
            assert t["icon"], f"{key} missing an icon"
            assert len(t["brief"]) > 50, f"{key}'s brief looks too short"


def _fresh_app() -> AppTest:
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert not at.exception, f"Sign-in screen raised: {list(at.exception)}"
    return at


def _theory_titles(at) -> str:
    return "\n".join(md.value for md in at.markdown)


class TestTheoryGridOnSignInScreen:
    """The sign-in screen's "Strategic Foundation" section (category="all")
    -- a prospective visitor sees the full shared toolkit for both
    simulations before ever registering, grouped under labeled subtitles."""

    def test_shows_both_subtitles(self):
        at = _fresh_app()
        text = _theory_titles(at)
        assert "TV / Streaming" in text
        assert "Movies" in text

    def test_shows_all_ten_cards(self):
        at = _fresh_app()
        text = _theory_titles(at)
        for t in THEORY_CONTENT.values():
            assert t["title"] in text


def _registered_app(active_section: str) -> AppTest:
    """Seeds straight to a registered team on the given active_section,
    single .run(), no button click -- avoids the documented AppTest +
    st.rerun() limitation (see tests/test_registration.py)."""
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["registered"]    = True
    at.session_state["team_name"]     = "Team Alpha"
    at.session_state["school"]        = "Test School of Business, Test University"
    at.session_state["class_section"] = "Fall 2026 Sec A"
    at.session_state["active_section"] = active_section
    at.run()
    assert not at.exception, f"{active_section} tab raised: {list(at.exception)}"
    return at


class TestTvTheoryTabShowsOnlyTvContent:
    def test_tv_cards_present(self):
        at = _registered_app("tv")
        text = _theory_titles(at)
        for t in THEORY_CONTENT.values():
            if t["category"] == "tv":
                assert t["title"] in text

    def test_movies_cards_absent(self):
        # The actual regression this whole file guards against: before the
        # category filter existed, every Movies-only title (and the wrong
        # TV-style amortization framing) would have shown up here too.
        at = _registered_app("tv")
        text = _theory_titles(at)
        for t in THEORY_CONTENT.values():
            if t["category"] == "movies":
                assert t["title"] not in text


class TestMoviesTheoryTabShowsOnlyMoviesContent:
    def test_movies_cards_present(self):
        at = _registered_app("movies")
        text = _theory_titles(at)
        for t in THEORY_CONTENT.values():
            if t["category"] == "movies":
                assert t["title"] in text

    def test_tv_cards_absent(self):
        at = _registered_app("movies")
        text = _theory_titles(at)
        for t in THEORY_CONTENT.values():
            if t["category"] == "tv":
                assert t["title"] not in text
