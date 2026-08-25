"""
Film Festival Acquisitions (Phase 7, 2026-08-18) -- see DESIGN_NOTES.md.

Per explicit user request: "is it possible to build in Sundance, TIFF and
Cannes film festival here... perhaps as a way to find movies to buy?" This
file proves the three things that make this feature genuinely different
from Scouted Concepts (its closest existing relative):
1. Critical reception is ALREADY REVEALED at slate-generation time, not
   drawn later at resolution.
2. The team is a real BUYER competing against rival bids (same shape as
   Sports Rights' resolve_auction), not a passive seller picking the best
   of incoming offers the way Pay-1 licensing is.
3. A won acquisition never touches ss.movie_log / compute_movie_score --
   a disclosed simplification, same posture as Talent Partnership spend.
"""
import pytest
from streamlit.testing.v1 import AppTest

import utils.game_state as gs
from utils.movie_models import (
    FESTIVALS, generate_festival_slate, festival_acquisition_anchor_m,
    draw_festival_acquisition_bids, resolve_festival_acquisition, resolve_festival_acquisition_outcome,
    draw_critical_reception, draw_licensing_bidder_appetite,
    RIVAL_STUDIOS, LICENSING_BIDDERS, MovieProject,
    FESTIVAL_CURATION_BONUS, SCREEN_COST_PER_SCREEN_M,
)


@pytest.fixture(autouse=True)
def isolated_leaderboard(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "LEADERBOARD_FILE", tmp_path / "leaderboard.json")
    yield


# ── generate_festival_slate ─────────────────────────────────────────────────
def test_generate_festival_slate_returns_one_per_festival_deterministically():
    slate = generate_festival_slate("Team", 1)
    assert len(slate) == len(FESTIVALS) == 3
    assert {f["festival"] for f in slate} == set(FESTIVALS.keys())
    slate2 = generate_festival_slate("Team", 1)
    assert [f["id"] for f in slate] == [f["id"] for f in slate2]
    assert [f["critical_score"] for f in slate] == [f["critical_score"] for f in slate2]


def test_generate_festival_slate_genres_respect_each_festivals_own_lean():
    slate = generate_festival_slate("LeanCheckTeam", 3)
    for film in slate:
        assert film["genre"] in FESTIVALS[film["festival"]]["genres"]
        assert film["concept_type"] in FESTIVALS[film["festival"]]["concept_types"]


def test_critical_reception_is_already_revealed_with_a_real_curation_bump():
    """The whole point of the feature: reception is KNOWN up front, and a
    curated festival selection should skew a real amount higher than an
    ordinary un-curated draw for the same inputs."""
    slate = generate_festival_slate("CurationTeam", 1)
    film = slate[0]
    seed_team = f"__festival__{film['id']}"
    raw = draw_critical_reception(seed_team, film["cycle"], film["genre"])
    assert film["critical_score"] == pytest.approx(min(100.0, raw + FESTIVAL_CURATION_BONUS))


# ── festival_acquisition_anchor_m ───────────────────────────────────────────
def test_festival_acquisition_anchor_m_scales_with_reception():
    lo_anchor = festival_acquisition_anchor_m(10.0, critical_score=0.0)
    hi_anchor = festival_acquisition_anchor_m(10.0, critical_score=100.0)
    assert hi_anchor > lo_anchor   # buzz already attached costs more
    assert lo_anchor > 0.0   # even a panned film has SOME distribution value


def test_festival_acquisition_anchor_m_scales_with_budget():
    small = festival_acquisition_anchor_m(5.0, critical_score=60.0)
    large = festival_acquisition_anchor_m(50.0, critical_score=60.0)
    assert large > small


# ── draw_festival_acquisition_bids ──────────────────────────────────────────
def test_draw_festival_acquisition_bids_only_uses_rival_studios():
    bids = draw_festival_acquisition_bids("Team", 1, "1_sundance", anchor_value_m=20.0)
    assert all(b["bidder"] in RIVAL_STUDIOS for b in bids)
    assert not any(b["bidder"] in LICENSING_BIDDERS for b in bids)   # a real, distinct buyer pool


def test_draw_festival_acquisition_bids_scales_with_the_anchor_value():
    n = 40
    lo_total = sum(sum(b["bid_m"] for b in draw_festival_acquisition_bids(f"T{i}", 1, "1_sundance", 5.0))
                   for i in range(n))
    hi_total = sum(sum(b["bid_m"] for b in draw_festival_acquisition_bids(f"T{i}", 1, "1_sundance", 50.0))
                   for i in range(n))
    assert hi_total > lo_total


def test_draw_festival_acquisition_bids_differ_by_film_id_not_just_cycle():
    """Two films in the SAME cycle must not draw identical bids -- each
    festival's film needs its own independent roll."""
    a = draw_festival_acquisition_bids("Team", 1, "1_sundance", 20.0)
    b = draw_festival_acquisition_bids("Team", 1, "1_cannes", 20.0)
    assert a != b


def test_appetite_mult_reuses_the_same_licensing_bidder_appetite_function():
    """Phase 6's hot/hungry logic must be the SAME function, not a parallel
    one -- draw_licensing_bidder_appetite generalized to accept any bidder
    list (see its own docstring)."""
    strong_slate = [{"npv": 50.0}] * 3
    appetite = draw_licensing_bidder_appetite("Team", 1, strong_slate, bidders=RIVAL_STUDIOS)
    assert set(appetite.keys()) == set(RIVAL_STUDIOS)
    assert all(v["state"] in (None, "hot", "hungry") for v in appetite.values())
    # Backward compatibility: omitting bidders still defaults to LICENSING_BIDDERS.
    default_appetite = draw_licensing_bidder_appetite("Team", 1, strong_slate)
    assert set(default_appetite.keys()) == set(LICENSING_BIDDERS)


# ── resolve_festival_acquisition (buyer-side auction) ───────────────────────
def test_resolve_festival_acquisition_team_wins_with_the_highest_bid():
    rival_bids = [{"bidder": "Paragon Pictures", "bid_m": 10.0}, {"bidder": "Vantage Films", "bid_m": 8.0}]
    result = resolve_festival_acquisition(team_bid_m=15.0, rival_bids=rival_bids)
    assert result["team_won"] is True
    assert result["winner"] == "You"
    assert result["winning_bid_m"] == pytest.approx(15.0)   # pays its OWN bid, not the runner-up's


def test_resolve_festival_acquisition_team_loses_when_outbid():
    rival_bids = [{"bidder": "Paragon Pictures", "bid_m": 10.0}, {"bidder": "Vantage Films", "bid_m": 25.0}]
    result = resolve_festival_acquisition(team_bid_m=15.0, rival_bids=rival_bids)
    assert result["team_won"] is False
    assert result["winner"] == "Vantage Films"
    assert result["winning_bid_m"] == pytest.approx(25.0)


def test_resolve_festival_acquisition_team_wins_by_default_with_zero_rival_participants():
    """A real, valid 'pass' (team_bid_m=0.0) still wins if literally no
    rival shows up -- same honest sealed-bid mechanics as an unclaimed
    Sports Rights package, not special-cased away."""
    result = resolve_festival_acquisition(team_bid_m=0.0, rival_bids=[])
    assert result["team_won"] is True
    assert result["winning_bid_m"] == pytest.approx(0.0)


# ── resolve_festival_acquisition_outcome ────────────────────────────────────
def test_resolve_festival_acquisition_outcome_reuses_the_already_revealed_critical_score():
    film = generate_festival_slate("OutcomeTeam", 1)[0]
    outcome = resolve_festival_acquisition_outcome(film, winner_label="You", acquirer_bid_m=20.0)
    assert outcome["critical_score"] == pytest.approx(film["critical_score"])   # never re-drawn


def test_resolve_festival_acquisition_outcome_skips_production_budget():
    """No production budget applies -- MovieProject.budget_m becomes the
    acquirer's real cost basis (the winning bid), and star_power/source-
    material acquisition cost stay at their true zero-effect defaults so
    the acquirer never double-pays for casting or rights already priced
    into the winning bid."""
    film = generate_festival_slate("BudgetTeam", 1)[0]
    outcome = resolve_festival_acquisition_outcome(film, winner_label="You", acquirer_bid_m=12.5)
    kwargs = outcome["project_kwargs"]
    assert kwargs["budget_m"] == pytest.approx(12.5)
    assert kwargs["star_power"] == 0
    assert kwargs["source_material"] == "Original Screenplay"   # SOURCE_ACQUISITION_COST_M == 0.0 baseline
    project = MovieProject(**kwargs)
    assert project.capital_at_risk() == pytest.approx(
        kwargs["budget_m"] + kwargs["pa_spend_m"] + kwargs["screens"] * SCREEN_COST_PER_SCREEN_M
    )


def test_resolve_festival_acquisition_outcome_is_deterministic_for_the_same_winner():
    film = generate_festival_slate("DetTeam", 1)[0]
    a = resolve_festival_acquisition_outcome(film, "You", 10.0)
    b = resolve_festival_acquisition_outcome(film, "You", 10.0)
    assert a["multiplier"] == pytest.approx(b["multiplier"])
    assert a["npv"] == pytest.approx(b["npv"])


def test_resolve_festival_acquisition_outcome_carries_no_compute_movie_score_hook():
    """A won festival film's outcome dict is real (has its own NPV etc.)
    but is a plain dict with no MovieProject/critical_score pairing that
    compute_movie_score (which takes explicit [MovieProject], [scores]
    lists) could ever be fed -- it structurally cannot reach the official
    score unless a caller deliberately reconstructs and passes it in,
    which app_pages/movies.py's real code never does (see ss.movie_
    festival_log staying entirely separate from ss.movie_log)."""
    film = generate_festival_slate("ScoreTeam", 1)[0]
    outcome = resolve_festival_acquisition_outcome(film, "You", 10.0)
    assert outcome["npv"] is not None
    assert "score" not in outcome and "movie_score" not in outcome


# ── UI integration (AppTest) ────────────────────────────────────────────────
def _movies_app_script(team_name):
    import streamlit as st
    import sys
    sys.path.insert(0, ".")
    st.session_state.team_name = team_name
    import app_pages.movies as movies
    movies.render()


def _movies_app(team_name="FestivalAppTest Team") -> AppTest:
    at = AppTest.from_function(_movies_app_script, default_timeout=30, args=(team_name,))
    at.run()
    assert not at.exception, f"Decisions phase raised: {list(at.exception)}"
    return at


def test_festival_section_renders_three_targets_with_revealed_reception():
    at = _movies_app()
    text = "\n".join(md.value for md in at.markdown)
    assert "Film Festival Acquisitions" in text
    assert "Critical Reception:" in text   # already shown, before any bid
    for fest in FESTIVALS.values():
        assert fest["name"] in text
    assert len(at.number_input) >= len(FESTIVALS)
    assert sum(1 for b in at.button if b.label == "Submit Bid") == len(FESTIVALS)


def test_bid_shows_live_ratio_against_the_asking_anchor():
    # 2026-08-24 add, found in a QA pass: previously there was no feedback
    # on how a bid compares to the asking anchor until AFTER submitting.
    # Overwriting the default (which starts equal to the anchor, a 1.0x
    # ratio) with a large bid should surface a live overpay signal.
    at = _movies_app()
    film_id = "1_sundance"
    bid_input = next(ni for ni in at.number_input if ni.key == f"festival_bid_{film_id}")
    anchor = bid_input.value   # default value is exactly the asking anchor
    bid_input.set_value(anchor * 2.0).run()
    assert not at.exception
    text = "\n".join(md.value for md in at.markdown)
    assert "2.0x the" in text
    assert "winner's-curse risk" in text


def test_submitting_a_bid_resolves_the_auction_one_way_or_the_other():
    at = _movies_app()
    film_id = "1_sundance"
    bid_input = next(ni for ni in at.number_input if ni.key == f"festival_bid_{film_id}")
    bid_input.set_value(500.0).run()   # an overwhelming bid should win almost always
    submit_btn = next(b for b in at.button if b.key == f"festival_submit_{film_id}")
    submit_btn.click().run()
    assert not at.exception, f"Submit Bid click raised: {list(at.exception)}"
    won = film_id in at.session_state["movie_festival_log"]
    lost = film_id in at.session_state["movie_festival_rival_log"]
    assert won != lost   # exactly one, never both, never neither
    if won:
        assert at.session_state["movie_festival_log"][film_id]["acquisition_cost_m"] == pytest.approx(500.0)
        assert "Acquired for" in "\n".join(s.value for s in at.success)
    else:
        assert "won at" in "\n".join(e.value for e in at.error)


def test_a_won_festival_film_never_lands_in_movie_log():
    at = _movies_app()
    film_id = "1_sundance"
    bid_input = next(ni for ni in at.number_input if ni.key == f"festival_bid_{film_id}")
    bid_input.set_value(5000.0).run()
    next(b for b in at.button if b.key == f"festival_submit_{film_id}").click().run()
    assert not at.exception
    if film_id in at.session_state["movie_festival_log"]:
        assert at.session_state["movie_log"] == []   # untouched -- separate collection entirely


def test_an_unbid_festival_film_auto_resolves_by_next_cycle_with_a_notice():
    """Mirrors Scouted Concepts' cross-cycle resolution: a film the team
    never bid on faces real, immediate consequence (a rival wins it) once
    the next cycle's Decisions render -- no separate poach-chance roll
    needed, the live auction resolves on its own."""
    at = _movies_app()
    at.session_state["movie_cycle"] = 2
    at.run()
    assert not at.exception, f"Cycle 2 decisions phase raised: {list(at.exception)}"
    assert at.session_state["movie_festival_resolved_through"] == 1
    # All three of cycle 1's films must have resolved one way or the other.
    resolved_ids = set(at.session_state["movie_festival_log"]) | set(at.session_state["movie_festival_rival_log"])
    assert resolved_ids == {"1_sundance", "1_cannes", "1_tiff"}
