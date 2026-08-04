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


class TestOverallLeaderboard:
    """get_overall_leaderboard, added 2026-07-27 -- sums OFFICIAL scores
    across Oxygen/Bravo/Peacock per team. Movies is deliberately excluded
    (its own separate track, per explicit user request), and a team that
    hasn't reached every network yet must not be zero-padded -- only
    networks_completed should shrink, not total_score get penalized."""

    def test_sums_official_scores_across_networks(self):
        _record("Team Alpha", "Kellogg", "Sec A", 80, True, network="oxygen")
        _record("Team Alpha", "Kellogg", "Sec A", 90, True, network="bravo")
        board = gs.get_overall_leaderboard()
        assert len(board) == 1
        assert board[0]["total_score"] == 170.0
        assert board[0]["networks_completed"] == 2
        assert board[0]["breakdown"] == {"oxygen": 80, "bravo": 90}

    def test_team_with_fewer_networks_is_not_zero_padded(self):
        # A team that's only cleared Oxygen should show a real 80, not an
        # average or a total artificially dragged down by missing networks.
        _record("Team Alpha", "Kellogg", "Sec A", 80, True, network="oxygen")
        board = gs.get_overall_leaderboard()
        assert board[0]["total_score"] == 80.0
        assert board[0]["networks_completed"] == 1

    def test_movies_scores_are_excluded_from_overall(self):
        _record("Team Alpha", "Kellogg", "Sec A", 80, True, network="oxygen")
        _record("Team Alpha", "Kellogg", "Sec A", 999, True, network="movies")
        board = gs.get_overall_leaderboard()
        assert board[0]["total_score"] == 80.0   # the 999 from movies must not leak in
        assert board[0]["networks_completed"] == 1
        assert "movies" not in board[0]["breakdown"]

    def test_ranked_by_total_score_descending(self):
        _record("Team Alpha", "Kellogg", "Sec A", 80, True, network="oxygen")
        _record("Team Bravo", "Kellogg", "Sec A", 60, True, network="oxygen")
        _record("Team Bravo", "Kellogg", "Sec A", 60, True, network="bravo")
        board = gs.get_overall_leaderboard()
        assert board[0]["team_name"] == "Team Bravo"   # 120 > 80
        assert board[0]["rank"] == 1
        assert board[1]["team_name"] == "Team Alpha"
        assert board[1]["rank"] == 2

    def test_school_scoping_applies(self):
        _record("Team Alpha", "Kellogg", "Sec A", 80, True, network="oxygen")
        _record("Team Bravo", "Kelley", "Sec 1", 90, True, network="oxygen")
        board = gs.get_overall_leaderboard(school="Kellogg")
        assert len(board) == 1
        assert board[0]["team_name"] == "Team Alpha"

    def test_empty_board_returns_empty_list(self):
        assert gs.get_overall_leaderboard() == []


def _year_row(year, margin, ocf, genre_costs):
    """Builds a minimal yearly_log row matching pages/simulation.py::
    _compute_year's real shape -- only the fields compute_level_notables
    actually reads (year, label, margin, ocf, shows[].status/genre/cost)."""
    shows = [{"status": "active", "genre": genre, "cost": cost}
             for genre, cost in genre_costs.items()]
    return {"year": year, "label": f"Year {year}", "margin": margin, "ocf": ocf, "shows": shows}


class TestComputeLevelNotables:
    """compute_level_notables, added 2026-07-27 for the end-of-level
    "Notables" summary (student-facing) and Leaderboard badges. Reads only
    yearly_log -- deliberately not the live roster, since cancellations and
    new greenlights can change the roster after a year was played."""

    def test_empty_log_returns_none_fields_but_keeps_shows_greenlit(self):
        notables = gs.compute_level_notables([], shows_greenlit=2)
        assert notables == {
            "best_year": None, "most_improved": None,
            "consistency_score": None, "diversity_trend": None,
            "shows_greenlit": 2,
        }

    def test_single_year_log_is_perfectly_consistent_with_no_improvement_delta(self):
        log = [_year_row(1, margin=10.0, ocf=5.0, genre_costs={"Reality": 100})]
        notables = gs.compute_level_notables(log, shows_greenlit=0)
        assert notables["best_year"] == {"label": "Year 1", "margin": 10.0, "ocf": 5.0}
        assert notables["most_improved"] == 0.0
        assert notables["consistency_score"] == 100.0
        assert notables["diversity_trend"] == 0.0   # same year vs. itself

    def test_best_year_is_the_highest_margin_not_the_last_year(self):
        log = [
            _year_row(1, margin=20.0, ocf=8.0, genre_costs={"Reality": 100}),
            _year_row(2, margin=5.0, ocf=1.0, genre_costs={"Reality": 100}),
        ]
        notables = gs.compute_level_notables(log)
        assert notables["best_year"]["label"] == "Year 1"
        assert notables["best_year"]["margin"] == 20.0

    def test_most_improved_is_last_margin_minus_first_margin(self):
        log = [
            _year_row(1, margin=5.0, ocf=1.0, genre_costs={"Reality": 100}),
            _year_row(2, margin=30.0, ocf=9.0, genre_costs={"Reality": 100}),
        ]
        notables = gs.compute_level_notables(log)
        assert notables["most_improved"] == 25.0

    def test_most_improved_can_be_negative(self):
        log = [
            _year_row(1, margin=30.0, ocf=9.0, genre_costs={"Reality": 100}),
            _year_row(2, margin=5.0, ocf=1.0, genre_costs={"Reality": 100}),
        ]
        notables = gs.compute_level_notables(log)
        assert notables["most_improved"] == -25.0

    def test_steady_margins_score_a_perfect_consistency(self):
        log = [_year_row(y, margin=10.0, ocf=2.0, genre_costs={"Reality": 100}) for y in (1, 2, 3)]
        notables = gs.compute_level_notables(log)
        assert notables["consistency_score"] == 100.0

    def test_volatile_margins_score_lower_consistency_than_steady_ones(self):
        steady = [_year_row(y, margin=10.0, ocf=2.0, genre_costs={"Reality": 100}) for y in (1, 2, 3)]
        volatile = [
            _year_row(1, margin=-20.0, ocf=-4.0, genre_costs={"Reality": 100}),
            _year_row(2, margin=40.0, ocf=8.0, genre_costs={"Reality": 100}),
            _year_row(3, margin=0.0, ocf=0.0, genre_costs={"Reality": 100}),
        ]
        steady_score = gs.compute_level_notables(steady)["consistency_score"]
        volatile_score = gs.compute_level_notables(volatile)["consistency_score"]
        assert volatile_score < steady_score

    def test_diversifying_slate_yields_a_negative_diversity_trend(self):
        # Year 1 all-in on one genre (HHI=1.0) -> Year 2 split across two
        # (HHI=0.5). HHI went down, i.e. the slate diversified, which the
        # function reports as a negative delta (first_hhi - last_hhi).
        log = [
            _year_row(1, margin=10.0, ocf=2.0, genre_costs={"Reality": 100}),
            _year_row(2, margin=10.0, ocf=2.0, genre_costs={"Reality": 50, "Drama": 50}),
        ]
        notables = gs.compute_level_notables(log)
        assert notables["diversity_trend"] == 0.5   # 1.0 - 0.5

    def test_years_with_no_active_shows_yield_a_none_diversity_trend(self):
        log = [
            _year_row(1, margin=0.0, ocf=0.0, genre_costs={}),
            _year_row(2, margin=0.0, ocf=0.0, genre_costs={}),
        ]
        notables = gs.compute_level_notables(log)
        assert notables["diversity_trend"] is None

    def test_shows_greenlit_passes_through_unchanged(self):
        log = [_year_row(1, margin=10.0, ocf=2.0, genre_costs={"Reality": 100})]
        assert gs.compute_level_notables(log, shows_greenlit=3)["shows_greenlit"] == 3

    def test_notables_round_trip_through_record_attempt(self):
        notables = {"best_year": {"label": "Year 2", "margin": 15.0, "ocf": 3.0},
                    "most_improved": 10.0, "consistency_score": 92.0,
                    "diversity_trend": 0.2, "shows_greenlit": 1}
        entry = gs.record_attempt(
            team_name="Team Alpha", network="oxygen", attempt_num=1,
            score=80, passed=True, details={"total": 80},
            school="Kellogg", class_section="Sec A", notables=notables,
        )
        assert entry["notables"] == notables
        stored = gs.get_team_attempts("Team Alpha", "oxygen", "Kellogg", "Sec A")[0]
        assert stored["notables"] == notables

    def test_omitted_notables_defaults_to_empty_dict_not_none(self):
        entry = _record("Team Bravo", "Kellogg", "Sec A", 70, False)
        assert entry["notables"] == {}


def _cycle_row(cycle, title, genre, npv, irr=0.15, awards_contender=False, oscar_win=False):
    """Minimal movie_log row matching pages/movies.py's real shape (only
    the fields compute_movie_notables reads: cycle, project_kwargs.title/
    genre, npv, irr, awards_contender, oscar_win). awards_contender/
    oscar_win default False so every pre-existing call site (written
    before Oscar tracking existed) keeps its original behavior."""
    return {"cycle": cycle, "project_kwargs": {"title": title, "genre": genre},
            "npv": npv, "irr": irr,
            "awards_contender": awards_contender, "oscar_win": oscar_win}


class TestComputeMovieNotables:
    """compute_movie_notables, added 2026-07-27 -- the Movies-track
    equivalent of compute_level_notables. Movies only run CYCLES_TOTAL=3
    cycles and each cycle is exactly one project, so genre_variety (count
    of distinct genres attempted) stands in for the TV side's per-year
    diversity_trend, which isn't meaningful when a single cycle is always
    one genre."""

    def test_empty_log_returns_none_fields(self):
        assert gs.compute_movie_notables([]) == {
            "best_cycle": None, "most_improved": None,
            "consistency_score": None, "genre_variety": None,
            "oscar_nominations": None, "oscar_wins": None,
        }

    def test_single_cycle_is_perfectly_consistent_with_no_improvement_delta(self):
        log = [_cycle_row(1, "Sunset Drive", "Drama", npv=20.0)]
        notables = gs.compute_movie_notables(log)
        assert notables["best_cycle"] == {"label": "Sunset Drive", "npv": 20.0, "irr": 0.15}
        assert notables["most_improved"] == 0.0
        assert notables["consistency_score"] == 100.0
        assert notables["genre_variety"] == 1

    def test_best_cycle_is_highest_npv_not_last_cycle(self):
        log = [
            _cycle_row(1, "Hit Movie", "Comedy", npv=50.0),
            _cycle_row(2, "Flop Movie", "Drama", npv=-10.0),
        ]
        notables = gs.compute_movie_notables(log)
        assert notables["best_cycle"]["label"] == "Hit Movie"

    def test_most_improved_is_last_npv_minus_first_npv(self):
        log = [
            _cycle_row(1, "First", "Drama", npv=5.0),
            _cycle_row(2, "Second", "Comedy", npv=40.0),
        ]
        notables = gs.compute_movie_notables(log)
        assert notables["most_improved"] == 35.0

    def test_genre_variety_counts_distinct_genres_not_cycles(self):
        log = [
            _cycle_row(1, "First", "Drama", npv=5.0),
            _cycle_row(2, "Second", "Drama", npv=10.0),
            _cycle_row(3, "Third", "Comedy", npv=15.0),
        ]
        notables = gs.compute_movie_notables(log)
        assert notables["genre_variety"] == 2   # Drama, Drama, Comedy -> 2 distinct

    def test_oscar_nominations_and_wins_are_counted_across_the_slate(self):
        log = [
            _cycle_row(1, "Bomb", "Drama", npv=5.0, awards_contender=False, oscar_win=False),
            _cycle_row(2, "Nominee", "Drama", npv=10.0, awards_contender=True, oscar_win=False),
            _cycle_row(3, "Winner", "Awards/Prestige", npv=15.0, awards_contender=True, oscar_win=True),
        ]
        notables = gs.compute_movie_notables(log)
        assert notables["oscar_nominations"] == 2   # both awards_contender=True rows
        assert notables["oscar_wins"] == 1

    def test_oscar_fields_default_to_zero_not_none_when_no_movie_won_or_was_nominated(self):
        log = [_cycle_row(1, "Ordinary", "Comedy", npv=5.0)]
        notables = gs.compute_movie_notables(log)
        assert notables["oscar_nominations"] == 0
        assert notables["oscar_wins"] == 0

    def test_oscar_fields_default_to_zero_for_pre_feature_log_entries(self):
        # Entries recorded before Oscar tracking existed carry neither key
        # at all -- must not raise, must read as 0, not None/missing.
        legacy_row = {"cycle": 1, "project_kwargs": {"title": "Old Movie", "genre": "Drama"},
                      "npv": 5.0, "irr": 0.1}
        notables = gs.compute_movie_notables([legacy_row])
        assert notables["oscar_nominations"] == 0
        assert notables["oscar_wins"] == 0

    def test_volatile_npvs_score_lower_consistency_than_steady_ones(self):
        steady = [_cycle_row(y, f"Movie {y}", "Drama", npv=10.0) for y in (1, 2, 3)]
        volatile = [
            _cycle_row(1, "Bomb", "Drama", npv=-80.0),
            _cycle_row(2, "Smash", "Comedy", npv=120.0),
            _cycle_row(3, "Mid", "Family/Kids", npv=10.0),
        ]
        steady_score = gs.compute_movie_notables(steady)["consistency_score"]
        volatile_score = gs.compute_movie_notables(volatile)["consistency_score"]
        assert volatile_score < steady_score

    def test_notables_round_trip_through_record_attempt(self):
        notables = {"best_cycle": {"label": "Hit Movie", "npv": 50.0, "irr": 0.3},
                    "most_improved": 20.0, "consistency_score": 88.0, "genre_variety": 2}
        entry = gs.record_attempt(
            team_name="Team Alpha", network="movies", attempt_num=1,
            score=80, passed=True, details={"total": 80},
            school="Kellogg", class_section="Sec A", notables=notables,
        )
        assert entry["notables"] == notables
