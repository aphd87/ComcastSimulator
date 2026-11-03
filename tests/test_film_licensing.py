"""Peacock film licensing (2026-11-03)."""
import copy
import pytest
from streamlit.testing.v1 import AppTest

from utils.film_licensing import (FILM_CATALOG, films_offered, resolve_film_bid, rival_bid_m, true_value_m,
                                  year_film_pnl)


def test_offers_cover_the_catalog_and_are_stable():
    seen = [k for y in range(1, 5) for k in films_offered(y)]
    assert set(seen) == set(FILM_CATALOG) and films_offered(2) == films_offered(2)


def test_first_price_sealed_bid():
    k = "the_long_table"
    rb, _ = rival_bid_m(k)
    assert resolve_film_bid(k, rb)["won"] and not resolve_film_bid(k, rb - 0.01)["won"]
    assert not resolve_film_bid(k, 0)["won"]


class _SS(dict):
    __getattr__ = dict.get
    def __setattr__(self, k, v): self[k] = v


def test_pnl_only_counts_years_in_term_and_gives_retention_credit():
    ss = _SS(film_licenses=[{"film": "paper_crowns", "start": 2, "end": 4, "annual_cost_m": 13.0}], film_bid_log={})
    assert year_film_pnl(ss, 1)["film_cost"] == 0
    p = year_film_pnl(ss, 3)
    assert p["film_cost"] == 13.0 and p["film_rev"] == true_value_m("paper_crowns")
    assert p["retention_credit_m"] == pytest.approx(6.5)


def _peacock_app(extra=None):
    def script(extra):
        import copy, sys
        import streamlit as st
        sys.path.insert(0, ".")
        from utils.data import OXYGEN_SLATE, BRAVO_SLATE, PEACOCK_SLATE
        d = {"team_name": "Film Team", "school": "S", "class_section": "A", "active_network": "peacock",
             "oxygen_shows": copy.deepcopy(OXYGEN_SLATE), "bravo_shows": copy.deepcopy(BRAVO_SLATE),
             "peacock_shows": copy.deepcopy(PEACOCK_SLATE), "cancelled_shows": set(), "renewal_decisions": {},
             "research_revealed": {}, "yearly_log": [], "year": 1, "sim_phase": "decisions",
             "level_budget": 150.0, "mkt_budget": 5.0, "sports_contracts": [], "sports_bid_log": {},
             **(extra or {})}
        for k, v in d.items():
            if k not in st.session_state:
                st.session_state[k] = v
        import app_pages.simulation as simulation
        simulation.render()
    at = AppTest.from_function(script, args=(extra,), default_timeout=60)
    at.run()
    assert not at.exception, list(at.exception)
    return at


def test_peacock_page_shows_film_offers_and_submit():
    at = _peacock_app()
    assert any(b.key == "film_submit_1" for b in at.button)
    assert any(n.key == f"film_bid_1_{films_offered(1)[0]}" for n in at.number_input)


def test_submitting_zero_bids_records_passes():
    at = _peacock_app()
    at.button(key="film_submit_1").click().run()
    assert not at.exception, list(at.exception)
    log = at.session_state["film_bid_log"]["1"]
    assert set(log) == set(films_offered(1)) and not any(r["won"] for r in log.values())


def test_simulate_books_a_held_film_license():
    lic = [{"film": "starfall", "start": 1, "end": 2, "annual_cost_m": 12.0}]
    at = _peacock_app({"film_licenses": lic, "film_bid_log": {"1": {}}})
    next(b for b in at.button if "Simulate Year" in b.label).click().run()
    assert not at.exception, list(at.exception)
    r = at.session_state["yearly_log"][-1]
    assert r["film_cost"] == 12.0 and r["film_rev"] == true_value_m("starfall", "Film Team")


def test_hidden_values_differ_by_team():
    """2026-11-03: one team's results aren't the answer key for another."""
    from utils.sports_models import draw_rival_bids
    assert any(true_value_m(k, "Team A") != true_value_m(k, "Team B") for k in FILM_CATALOG)
    assert any(rival_bid_m(k, "Team A") != rival_bid_m(k, "Team B") for k in FILM_CATALOG)
    assert draw_rival_bids("Premier League", 0, "Team A") != draw_rival_bids("Premier League", 0, "Team B")
    assert true_value_m("starfall", "Team A") == true_value_m("starfall", "Team A")
