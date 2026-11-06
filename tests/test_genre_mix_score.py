"""Brand-anchored Genre Mix (TV) and normalized Portfolio Diversification
(Movies), 2026-11-05. Student feedback: an all-True-Crime Oxygen slate
scored 0 on diversity with no warning; the instructor kept the 15% weight
but asked for a fair metric that still requires some range."""
import pytest

from utils.data import OXYGEN_SLATE, BRAVO_SLATE, PEACOCK_SLATE
from utils.game_state import (GENRE_BASELINE_HHI, genre_mix_score, genre_target_hhi,
                              hhi_from_genres, compute_score_for_network, SCORE_WEIGHTS)
from utils.movie_models import (MovieProject, portfolio_diversification_score,
                                MOVIE_SCORE_WEIGHTS, GENRES, CONCEPT_TYPES)
from utils.score_guide import tv_score_rows, movie_score_rows

SLATES = {"oxygen": OXYGEN_SLATE, "bravo": BRAVO_SLATE, "peacock": PEACOCK_SLATE}


def _slate_hhi(slate):
    g = {}
    for s in slate:
        g[s.genre] = g.get(s.genre, 0) + s.total_cost(1)
    return hhi_from_genres(g)


@pytest.mark.parametrize("net", ["oxygen", "bravo", "peacock"])
def test_baseline_matches_the_inherited_slate(net):
    assert GENRE_BASELINE_HHI[net] == pytest.approx(_slate_hhi(SLATES[net]), abs=0.002)


@pytest.mark.parametrize("net", ["oxygen", "bravo", "peacock"])
def test_anchor_points(net):
    base = GENRE_BASELINE_HHI[net]
    assert genre_mix_score(1.0, net) == 0.0                       # one genre: 0, even on-brand
    assert genre_mix_score(base, net) == pytest.approx(0.5)        # inherited brand mix: 50
    assert genre_mix_score(genre_target_hhi(net), net) == pytest.approx(1.0)
    assert genre_mix_score(0.0, net) == 1.0                        # capped


@pytest.mark.parametrize("net", ["oxygen", "bravo", "peacock"])
def test_monotonic_more_range_never_scores_lower(net):
    hs = [i / 50 for i in range(51)]
    scores = [genre_mix_score(h, net) for h in hs]
    assert all(a >= b for a, b in zip(scores, scores[1:]))


def test_every_network_starts_on_equal_footing():
    # Old raw 1-HHI: Oxygen 25, Bravo 60, Peacock 47 for doing nothing.
    starts = {n: compute_score_for_network(n, 20, 10, GENRE_BASELINE_HHI[n], 50, 10)["diversity"]
              for n in SLATES}
    assert set(starts.values()) == {50.0}


def test_all_true_crime_oxygen_still_scores_zero():
    assert compute_score_for_network("oxygen", 20, 10, 1.0, 50, 10)["diversity"] == 0.0


def test_score_guide_uses_live_weights():
    rows = dict((r[0], r[1]) for r in tv_score_rows("oxygen"))
    assert rows["Genre Mix"] == f"{SCORE_WEIGHTS['genre_mix'] * 100:.0f}%"
    assert sum(float(w.rstrip('%')) for w in rows.values()) == pytest.approx(100)
    mrows = [r[1] for r in movie_score_rows()]
    assert sum(float(w.rstrip('%')) for w in mrows) == pytest.approx(100)
    assert sum(MOVIE_SCORE_WEIGHTS.values()) == pytest.approx(1.0)


def _film(genre, concept):
    return MovieProject(title="t", genre=genre, concept_type=concept, budget_m=60, pa_spend_m=30,
                        star_power=0, screens=3000, cycle=1)


def test_movies_fully_diversified_slate_scores_100():
    films = [_film(g, c) for g, c in [("Drama", "New IP"), ("Comedy", "Sequel"), ("Animated", "Family/Kids")]]
    caps = {f.capital_at_risk() for f in films}
    assert portfolio_diversification_score(films) > (99 if len(caps) == 1 else 90)


def test_movies_one_genre_one_concept_scores_zero():
    films = [_film("Horror", "Sequel") for _ in range(3)]
    assert portfolio_diversification_score(films) == pytest.approx(0)


def test_movies_single_film_stays_neutral():
    assert portfolio_diversification_score([_film("Drama", "New IP")]) == 100.0
