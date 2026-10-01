"""utils/storage.py: many teams saving at once must never lose or clobber
each other's data, on either backend (local files, or a database)."""
import json
import threading

import pytest

import utils.game_state as gs
import utils.storage as storage


def _hammer(fn, n_threads=20, per_thread=10):
    errors = []
    start = threading.Barrier(n_threads)

    def worker(t):
        try:
            start.wait()
            for i in range(per_thread):
                fn(t, i)
        except Exception as e:      # surface any thread failure in the test
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert not errors, errors


# ── File backend ─────────────────────────────────────────────────────────────
def test_simultaneous_submissions_are_all_kept(tmp_path):
    path = tmp_path / "leaderboard.json"
    _hammer(lambda t, i: storage.append_entry(path, {"team": t, "i": i}))
    board = storage.load_entries(path)
    assert len(board) == 200
    assert {(e["team"], e["i"]) for e in board} == {(t, i) for t in range(20) for i in range(10)}
    assert not list(tmp_path.glob(".*.tmp")), "temp files left behind"


def test_eighteen_drivers_saving_state_at_once_keep_every_team(tmp_path):
    path = tmp_path / "team_state.json"
    _hammer(lambda t, i: storage.save_state(path, f"team-{t}", {"click": i}), n_threads=18)
    for t in range(18):
        assert storage.load_state(path, f"team-{t}") == {"click": 9}


def test_unreadable_file_is_preserved_never_overwritten(tmp_path):
    path = tmp_path / "leaderboard.json"
    path.write_text('[{"team_name": "A", "score": 7', encoding="utf-8")   # truncated JSON
    with pytest.raises(storage.StorageError):
        storage.append_entry(path, {"team_name": "B"})
    assert path.read_text(encoding="utf-8") == '[{"team_name": "A", "score": 7'
    assert list(tmp_path.glob("leaderboard.json.unreadable-*")), "no backup copy was saved"
    assert storage.load_entries(path) == []   # display path degrades gracefully


def test_record_attempt_round_trip_on_files():
    gs.record_attempt("Team A", "oxygen", 1, 71.4, True, {"total": 71.4},
                      school="S", class_section="C")
    off = gs.get_official_score("Team A", "oxygen", "S", "C")
    assert off["score"] == 71.4 and off["is_official"]


# ── Database backend (SQLite stands in for Postgres) ─────────────────────────
@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'slate.db').as_posix()}"
    monkeypatch.setattr(storage, "database_url", lambda: url)
    storage._engine.cache_clear()
    yield url
    storage._engine.cache_clear()


def test_database_round_trip_and_survives_restart(sqlite_db, tmp_path):
    gs.record_attempt("Team A", "bravo", 1, 64.0, True, {"total": 64.0},
                      school="S", class_section="C")
    gs.save_live_state("Team A", "S", "C", {"year": 3})
    assert not (tmp_path / "leaderboard.json").exists(), "DB mode must not write the local file"

    storage._engine.cache_clear()            # simulate an app reboot: brand-new connection pool
    assert gs.get_official_score("Team A", "bravo", "S", "C")["score"] == 64.0
    assert gs.load_live_state("Team A", "S", "C") == {"year": 3}


def test_database_keeps_simultaneous_submissions(sqlite_db):
    _hammer(lambda t, i: storage.append_entry(gs.LEADERBOARD_FILE, {"team": t, "i": i}),
            n_threads=8, per_thread=5)
    assert len(gs.load_leaderboard()) == 40


def test_backend_name_reflects_configuration(sqlite_db):
    assert storage.backend_name() == "database"
