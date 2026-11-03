"""Movies Follow Along (2026-11-03): the Driver's Movies state is saved under
its own key and a Follow Along viewer sees it read-only."""
import pytest
from streamlit.testing.v1 import AppTest

import utils.game_state as gs
from app_pages.movies_follow import _dec, _enc, apply_snapshot, build_snapshot


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    monkeypatch.setattr(gs, "TEAM_STATE_FILE", tmp_path / "team_state.json")
    yield


def test_encoding_round_trips_sets_tuples_and_int_keys():
    import json
    import numpy as np
    obj = {"a": {1, 2}, "b": (1, "x"), "c": {3: {"d": [np.float64(1.5)]}}, "e": None}
    back = _dec(json.loads(json.dumps(_enc(obj))))
    assert back == {"a": {1, 2}, "b": (1, "x"), "c": {3: {"d": [1.5]}}, "e": None}


def test_snapshot_only_carries_movie_state():
    ss = {"movie_cycle": 2, "movie_scouted_optioned": {"1_0"}, "movie_logline_2": "widget", "year": 3}
    snap = build_snapshot(ss)
    assert set(snap) == {"movie_cycle", "movie_scouted_optioned"}
    out = {}
    apply_snapshot(out, snap)
    assert out == {"movie_cycle": 2, "movie_scouted_optioned": {"1_0"}}


def _register_movies(at, role):
    at.text_input(key="university_input_field").set_value("Test University")
    at.text_input(key="college_input_field").set_value("Test School of Business")
    at.text_input(key="class_title_input_field").set_value("Media Strategy Sec A")
    at.text_input(key="semester_input_field").set_value("Fall 2026")
    at.text_input(key="team_input_field").set_value("Team Film")
    at.radio(key="role_input_field").set_value(role)
    at.button(key="register_team_button").click()
    at.run()
    next(b for b in at.button if b.label == "→ Start Movies").click()
    at.run()
    return at


def test_viewer_sees_drivers_movie_state_and_no_decision_widgets():
    driver = AppTest.from_file("app.py", default_timeout=60)
    driver.run()
    _register_movies(driver, "🎮 Driver — I'll make the decisions")
    assert not driver.exception, list(driver.exception)
    saved = gs.load_movie_live_state("Team Film", "Test School of Business, Test University",
                                     "Fall 2026 — Media Strategy Sec A")
    assert saved and saved["movie_cycle"] == 1
    # TV live state is a different key, so Movies never overwrites it.
    assert gs.load_live_state("Team Film", "Test School of Business, Test University",
                              "Fall 2026 — Media Strategy Sec A") is None

    viewer = AppTest.from_file("app.py", default_timeout=60)
    viewer.run()
    _register_movies(viewer, "👀 Follow Along — view only")
    assert not viewer.exception, list(viewer.exception)
    text = " ".join(m.value for m in viewer.markdown)
    assert "Follow Along mode" in text and "making decisions" in text
    assert not any("Simulate" in b.label for b in viewer.button)
    assert viewer.session_state["movie_cycle"] == 1


def test_viewer_before_driver_starts_shows_waiting_message():
    viewer = AppTest.from_file("app.py", default_timeout=60)
    viewer.run()
    _register_movies(viewer, "👀 Follow Along — view only")
    assert not viewer.exception, list(viewer.exception)
    assert any("hasn't opened the Movies simulation yet" in i.value for i in viewer.info)


def test_snapshot_of_a_real_simulated_film_is_json_safe_and_round_trips():
    import json
    from tests.test_movies_page import _movies_app, _simulate_button
    at = _movies_app()
    _simulate_button(at).click().run()
    assert at.session_state["movie_phase"] == "results"
    from app_pages.movies_follow import MOVIE_STATE_KEYS
    ss = {k: at.session_state[k] for k in MOVIE_STATE_KEYS if k in at.session_state}
    snap = json.loads(json.dumps(build_snapshot(ss)))
    out = {}
    apply_snapshot(out, snap)
    assert out["movie_log"][0]["npv"] == ss["movie_log"][0]["npv"]
    assert out["movie_phase"] == "results" and out["movie_cycle"] == ss["movie_cycle"]


def test_viewer_renders_results_of_a_real_film(tmp_path):
    import json
    from tests.test_movies_page import _movies_app, _simulate_button
    from app_pages.movies_follow import MOVIE_STATE_KEYS
    at = _movies_app()
    _simulate_button(at).click().run()
    snap = build_snapshot({k: at.session_state[k] for k in MOVIE_STATE_KEYS if k in at.session_state})
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(snap))

    def script(p):
        import json, sys
        import streamlit as st
        sys.path.insert(0, ".")
        from app_pages.movies_follow import apply_snapshot, render_viewer
        apply_snapshot(st.session_state, json.loads(open(p).read()))
        st.session_state.movie_follow_has_state = True
        st.session_state.setdefault("team_name", "T")
        render_viewer(st.session_state)
    v = AppTest.from_function(script, args=(str(path),), default_timeout=60)
    v.run()
    assert not v.exception, list(v.exception)
    text = " ".join(m.value for m in v.markdown)
    assert "Last Period's Actuals" in text and "looking at the results" in text
