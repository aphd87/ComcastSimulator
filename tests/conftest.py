"""
Repo-wide test isolation: every test gets its own throwaway
leaderboard.json/team_state.json instead of touching the real files in the
project root.

Added 2026-08-07 alongside the Driver/Follow Along live-state sync: unlike
leaderboard writes (only reached by tests that explicitly submit a level),
save_live_state() fires on every Driver render -- so even a plain
registration smoke test now reaches it, and without this fixture would
leak a real team_state.json into the repo working directory on every test
run (caught manually: a stray team_state.json with "Team Alpha"/"Fall 2026
Sec A" entries -- other tests' registration defaults -- showed up in `git
status` after a full suite run, before this fixture existed).

Individual test files' own isolated_leaderboard-style fixtures (the same
monkeypatch, scoped locally) still work layered on top of this -- both
patch the same attributes to paths under the same per-test tmp_path, so
there's no conflict, just redundancy kept for those files' own
readability/history.
"""
import pytest

import utils.game_state as gs


@pytest.fixture(autouse=True)
def _isolate_state_files(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    monkeypatch.setattr(gs, "TEAM_STATE_FILE", tmp_path / "team_state.json")
    yield
