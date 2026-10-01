"""Peer Pitch Board (2026-10-01): pitches teams commit in TV and Movies are
shared with the rest of their class (and only their class)."""
from streamlit.testing.v1 import AppTest

import utils.game_state as gs
import utils.storage as storage


def _post(team, title, sim="tv", key="1", school="S", cls="C", **details):
    return gs.post_pitch(team, school, cls, sim, key, title, "Drama", f"{title} pitch text.", details)


def test_board_is_scoped_to_school_and_class_newest_first():
    _post("A", "First")
    _post("B", "Second")
    _post("Z", "Other class", cls="Different section")
    _post("Y", "Other school", school="Elsewhere")
    titles = [p["title"] for p in gs.class_pitches("S", "C")]
    assert titles == ["Second", "First"]


def test_reposting_the_same_key_replaces_the_earlier_post():
    _post("A", "Draft title", sim="movies", key="cycle-1")
    _post("A", "Final title", sim="movies", key="cycle-1", npv=12.0)
    board = gs.class_pitches("S", "C", sim="movies")
    assert [p["title"] for p in board] == ["Final title"]
    assert board[0]["details"]["npv"] == 12.0


def test_sim_filter():
    _post("A", "A show", sim="tv", key="oxygen-60")
    _post("A", "A film", sim="movies", key="cycle-1")
    assert [p["title"] for p in gs.class_pitches("S", "C", sim="tv")] == ["A show"]
    assert [p["title"] for p in gs.class_pitches("S", "C", sim="movies")] == ["A film"]


def test_pitches_survive_on_the_database_backend(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'slate.db').as_posix()}"
    monkeypatch.setattr(storage, "database_url", lambda: url)
    storage._engine.cache_clear()
    _post("A", "Stored in DB")
    storage._engine.cache_clear()
    assert [p["title"] for p in gs.class_pitches("S", "C")] == ["Stored in DB"]
    assert not (tmp_path / "pitch_board.json").exists()
    storage._engine.cache_clear()


def _greenlight_script():
    import copy
    import sys
    import streamlit as st
    sys.path.insert(0, ".")
    from utils.data import OXYGEN_SLATE
    ss = st.session_state
    if "oxygen_shows" not in ss:
        ss.registered, ss.team_name, ss.school, ss.class_section = True, "Team Pitch", "S", "C"
        ss.active_network, ss.year, ss.level_budget = "oxygen", 1, 95.0
        ss.oxygen_shows = copy.deepcopy(OXYGEN_SLATE)
    import app_pages.greenlight as greenlight
    greenlight.render()


def test_greenlighting_a_tv_show_posts_its_pitch():
    at = AppTest.from_function(_greenlight_script, default_timeout=30)
    at.run()
    at.text_input(key="gl_show_name").set_value("Harbor Lights").run()
    at.text_area(key="gl_pitch_text").set_value(
        "Retired detectives in a Maine harbor town reopen one cold case per episode.").run()
    at.button(key="gl_greenlight_manual").click().run()
    assert not at.exception, list(at.exception)
    board = gs.class_pitches("S", "C", sim="tv")
    assert len(board) == 1 and board[0]["title"] == "Harbor Lights"
    assert board[0]["details"]["network"] == "Oxygen"
    assert board[0]["details"]["year_label"] == "2012"


def test_board_shows_other_teams_and_marks_your_own():
    _post("Team Pitch", "My Show", key="oxygen-60")
    _post("Rival Team", "Their Show", key="oxygen-61")
    at = AppTest.from_function(_greenlight_script, default_timeout=30)
    at.run()
    assert not at.exception, list(at.exception)
    text = " ".join(m.value for m in at.markdown)
    assert "Their Show" in text and "Rival Team" in text
    assert "Team Pitch (your team)" in text


def test_simulating_a_film_posts_its_logline_and_result():
    from tests.test_theatrical_mini_run import _movies_app, _mini_run_button, _simulate_button
    at = _movies_app("Pitch Movie Team")
    _mini_run_button(at).click().run()
    _simulate_button(at).click().run()
    assert not at.exception, list(at.exception)
    board = gs.class_pitches("", "", sim="movies")
    assert len(board) == 1
    post = board[0]
    assert post["team_name"] == "Pitch Movie Team"
    assert "astronaut" in post["pitch"]
    assert isinstance(post["details"]["npv"], float)


def test_no_ai_features_remain():
    import pathlib
    for f in ["app_pages/greenlight.py", "app_pages/movies.py"]:
        src = pathlib.Path(f).read_text(encoding="utf-8")
        assert "ai_grading" not in src and "AI Pitch Feedback" not in src
    assert not pathlib.Path("utils/ai_grading.py").exists()
