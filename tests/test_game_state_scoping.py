"""
Tests for the multi-school/multi-class scoping added to
utils/game_state.py (2026-07-22). The core risk being tested: two
different schools (or two sections of the same school) each having a team
named "Team Alpha" must never share attempt history or leaderboard
position — a team's real identity is (school, class_section, team_name),
not team_name alone.
"""
import pytest

import utils.game_state as gs


@pytest.fixture(autouse=True)
def isolated_leaderboard(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    yield


def _record(team, school, cls, score, passed, attempt=1, network="oxygen"):
    return gs.record_attempt(team_name=team, network=network, attempt_num=attempt,
                              score=score, passed=passed, details={"total": score},
                              school=school, class_section=cls)


class TestIdentityIsolation:
    def test_same_team_name_different_schools_do_not_share_attempts(self):
        _record("Team Alpha", "Northwestern Kellogg", "Fall 2026 — Sec A", 80, True)
        # A same-named team at a different school should see zero attempts of their own.
        attempts = gs.get_team_attempts("Team Alpha", "oxygen", "Indiana Kelley", "Fall 2026 — Sec A")
        assert attempts == []

    def test_same_team_name_different_sections_same_school_do_not_collide(self):
        _record("Team Alpha", "Northwestern Kellogg", "Section A", 80, True)
        attempts = gs.get_team_attempts("Team Alpha", "oxygen", "Northwestern Kellogg", "Section B")
        assert attempts == []

    def test_correct_scope_sees_its_own_attempt(self):
        _record("Team Alpha", "Northwestern Kellogg", "Section A", 80, True)
        attempts = gs.get_team_attempts("Team Alpha", "oxygen", "Northwestern Kellogg", "Section A")
        assert len(attempts) == 1
        assert attempts[0]["score"] == 80

    def test_can_advance_scoped_correctly(self):
        _record("Team Alpha", "Kellogg", "Sec A", 90, True)
        assert gs.can_advance("Team Alpha", "oxygen", "Kellogg", "Sec A") is True
        # Different section, same name, never played — should not inherit advancement.
        assert gs.can_advance("Team Alpha", "oxygen", "Kellogg", "Sec B") is False


class TestNetworkLeaderboardScoping:
    def test_unfiltered_leaderboard_includes_every_school(self):
        _record("Team Alpha", "Kellogg", "Sec A", 90, True)
        _record("Team Bravo", "Kelley", "Sec 1", 85, True)
        board = gs.get_network_leaderboard("oxygen")
        assert len(board) == 2
        assert board[0]["team_name"] == "Team Alpha"   # higher score ranks first

    def test_school_filtered_leaderboard_excludes_other_schools(self):
        _record("Team Alpha", "Kellogg", "Sec A", 90, True)
        _record("Team Bravo", "Kelley", "Sec 1", 85, True)
        board = gs.get_network_leaderboard("oxygen", school="Kellogg")
        assert len(board) == 1
        assert board[0]["team_name"] == "Team Alpha"

    def test_class_filtered_leaderboard_excludes_other_sections(self):
        _record("Team Alpha", "Kellogg", "Sec A", 90, True)
        _record("Team Charlie", "Kellogg", "Sec B", 95, True)
        board = gs.get_network_leaderboard("oxygen", school="Kellogg", class_section="Sec A")
        assert len(board) == 1
        assert board[0]["team_name"] == "Team Alpha"

    def test_same_team_name_two_schools_both_rank_independently(self):
        _record("Team Alpha", "Kellogg", "Sec A", 90, True)
        _record("Team Alpha", "Kelley", "Sec 1", 70, True)
        board = gs.get_network_leaderboard("oxygen")   # cross-school view
        assert len(board) == 2   # not collapsed into one entry
        scores = sorted(e["score"] for e in board)
        assert scores == [70, 90]


class TestSchoolRollup:
    def test_single_school_returns_one_row(self):
        _record("Team Alpha", "Kellogg", "Sec A", 90, True)
        _record("Team Bravo", "Kellogg", "Sec B", 70, False)
        rollup = gs.get_school_rollup("oxygen")
        assert len(rollup) == 1
        assert rollup[0]["school"] == "Kellogg"
        assert rollup[0]["teams"] == 2
        assert rollup[0]["avg_score"] == 80.0
        assert rollup[0]["pass_rate"] == 50.0

    def test_two_schools_ranked_by_avg_score(self):
        _record("Team Alpha", "Kellogg", "Sec A", 90, True)
        _record("Team Bravo", "Kelley", "Sec 1", 60, False)
        rollup = gs.get_school_rollup("oxygen")
        assert len(rollup) == 2
        assert rollup[0]["school"] == "Kellogg"   # higher avg ranks first
        assert rollup[0]["rank"] == 1
        assert rollup[1]["school"] == "Kelley"
        assert rollup[1]["rank"] == 2

    def test_empty_board_returns_empty_rollup(self):
        assert gs.get_school_rollup("oxygen") == []


class TestSlateSummary:
    """slate_summary, added 2026-07-27 for the Leaderboard's competitor-
    slate comparison feature — stored as its own top-level field on the
    entry, deliberately separate from `details` (which pages/leaderboard.py
    iterates and number-formats wholesale; a list value there would break
    that loop)."""

    def test_slate_summary_round_trips_through_the_leaderboard(self):
        slate = [{"name": "Snapped", "genre": "True Crime", "network": "Oxygen", "rating": 0.8}]
        entry = gs.record_attempt(
            team_name="Team Alpha", network="oxygen", attempt_num=1,
            score=80, passed=True, details={"total": 80},
            school="Kellogg", class_section="Sec A", slate_summary=slate,
        )
        assert entry["slate_summary"] == slate
        stored = gs.get_team_attempts("Team Alpha", "oxygen", "Kellogg", "Sec A")[0]
        assert stored["slate_summary"] == slate

    def test_omitted_slate_summary_defaults_to_empty_list_not_none(self):
        # Older-entry compatibility: pages/leaderboard.py checks truthiness
        # of this field to decide whether to show a real slate or a
        # "not available" fallback -- must never be None (which is also
        # falsy but a different failure mode if something unwraps it).
        entry = _record("Team Bravo", "Kellogg", "Sec A", 70, False)
        assert entry["slate_summary"] == []
