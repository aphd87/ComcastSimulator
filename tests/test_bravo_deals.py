"""Bravo brand partnerships + casting unknowns (2026-11-03)."""
import copy
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from utils.bravo_deals import (BRAND_CATALOG, CAST_POOL, brand_outcome, brand_terms, cast_lift_range,
                               cast_multiplier, rival_cast_bid, year_extras)
from utils.data import BRAVO_SLATE


def test_higher_paying_brands_fit_bravo_reality_worse():
    pays = sorted(BRAND_CATALOG, key=lambda k: BRAND_CATALOG[k]["pay_pct"])
    assert brand_terms(pays[0], 10, "Reality")["fit"] > brand_terms(pays[-1], 10, "Reality")["fit"]


def test_brand_outcome_is_stable_and_signed():
    a = brand_outcome("T", 1, 5, "titanfuel", 10.0, "Reality")
    assert a == brand_outcome("T", 1, 5, "titanfuel", 10.0, "Reality")
    t = brand_terms("titanfuel", 10.0, "Reality")
    assert a["net_m"] in (round(t["gain_m"], 2), round(-t["loss_m"], 2))


def test_flops_happen_and_land_at_roughly_the_fit_rate():
    landed = sum(brand_outcome(f"team{i}", 1, 1, "maison_verre", 10, "Reality")["landed"] for i in range(400))
    assert 0.70 < landed / 400 < 0.90          # fit 0.80


def test_cast_multiplier_within_range_and_chemistry():
    for k in CAST_POOL:
        lo, hi = cast_lift_range(k)
        m = cast_multiplier("T", 1, [k])
        assert 1 + lo - 1e-9 <= m <= 1 + hi + 1e-9
    assert cast_multiplier("T", 1, []) == 1.0


def test_rival_bid_is_stable_and_near_the_ask():
    for k, c in CAST_POOL.items():
        b, rival = rival_cast_bid("T", k)
        assert (b, rival) == rival_cast_bid("T", k)
        assert 0.85 * c["ask_m"] - 1e-9 <= b <= 1.5 * c["ask_m"] + 1e-9


class _SS(dict):
    __getattr__ = dict.get
    def __setattr__(self, k, v): self[k] = v


def test_year_extras_books_landed_as_revenue_and_flops_as_cost():
    shows = copy.deepcopy(BRAVO_SLATE)
    ss = _SS(team_name="T", brand_deals={"1": {str(s.id): "titanfuel" for s in shows[:6]}},
             cast_signings={}, cast_fees={"1": 0.5}, cast_lost={})
    ex = year_extras(ss, shows, 1, {s.id for s in shows})
    assert len(ex["brand_rows"]) == 6 and ex["cast_cost"] == 0.5
    assert abs(ex["brand_rev"] - sum(r["net_m"] for r in ex["brand_rows"] if r["landed"])) < 0.02
    assert abs(ex["brand_cost"] + sum(r["net_m"] for r in ex["brand_rows"] if not r["landed"])) < 0.02


def _bravo_app(extra=None):
    def script(extra):
        import copy, sys
        import streamlit as st
        sys.path.insert(0, ".")
        from utils.data import OXYGEN_SLATE, BRAVO_SLATE, PEACOCK_SLATE
        from utils.models import Show
        bravo = copy.deepcopy(BRAVO_SLATE)
        new = Show(id=60, name="Uptown Listings", genre="Reality", episodes=12, ep_cost_k=720,
                   rating=1.4, ip_score=66, air_month=3, network="Bravo")
        defaults = {
            "team_name": "Deal Team", "school": "S", "class_section": "A", "active_network": "bravo",
            "oxygen_shows": copy.deepcopy(OXYGEN_SLATE), "bravo_shows": bravo + [new],
            "peacock_shows": copy.deepcopy(PEACOCK_SLATE), "cancelled_shows": set(),
            "renewal_decisions": {}, "research_revealed": {}, "yearly_log": [], "year": 1,
            "sim_phase": "decisions", "level_budget": 220.0, "mkt_budget": 5.0,
            "sports_contracts": [], "sports_bid_log": {},
            "greenlit_ids_this_level": {60}, "greenlit_ids_this_year": {60}, "next_show_id": 61,
            **(extra or {}),
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v
        import app_pages.simulation as simulation
        simulation.render()
    at = AppTest.from_function(script, args=(extra,), default_timeout=60)
    at.run()
    assert not at.exception, list(at.exception)
    return at


def test_bravo_page_shows_brand_and_casting_sections():
    at = _bravo_app()
    text = " ".join(m.value for m in at.markdown)
    assert "Brand Partnerships" in text and "Bid on Unknowns" in text
    assert any(b.key == "cast_btn_priya_s" for b in at.button)


def test_winning_a_cast_bid_signs_them_and_charges_the_budget():
    # Pick someone whose rival bid is at or below the asking fee, so the
    # default bid (the ask) wins without a second interaction.
    key = next(k for k in CAST_POOL if rival_cast_bid("Deal Team", k)[0] <= CAST_POOL[k]["ask_m"])
    at = _bravo_app()
    at.button(key=f"cast_btn_{key}").click().run()
    assert not at.exception, list(at.exception)
    assert key in at.session_state["cast_signings"]["60"]
    assert abs(at.session_state["level_budget"] - (220.0 - CAST_POOL[key]["ask_m"])) < 1e-6
    assert abs(at.session_state["cast_fees"]["1"] - CAST_POOL[key]["ask_m"]) < 1e-6


def test_losing_a_cast_bid_sends_them_to_the_rival_at_no_cost():
    key = next(k for k in CAST_POOL if rival_cast_bid("Deal Team", k)[0] > CAST_POOL[k]["ask_m"])
    at = _bravo_app()
    at.button(key=f"cast_btn_{key}").click().run()
    assert not at.exception, list(at.exception)
    assert key in at.session_state["cast_lost"]
    assert at.session_state["level_budget"] == 220.0


def test_simulate_books_brand_deal_and_casting_fee():
    at = _bravo_app({"brand_deals": {"1": {"60": "maison_verre"}},
                     "cast_signings": {"60": ["priya_s", "dana_m"]},
                     "cast_fees": {"1": 0.7}, "cast_lost": {}})
    next(b for b in at.button if "Simulate Year" in b.label).click().run()
    assert not at.exception, list(at.exception)
    r = at.session_state["yearly_log"][-1]
    assert len(r["brand_rows"]) == 1 and r["cast_cost"] == 0.7
    row = next(x for x in r["shows"] if x["id"] == 60)
    from utils.bravo_deals import cast_multiplier
    assert cast_multiplier("Deal Team", 60, ["priya_s", "dana_m"]) != 1.0
    assert row["revenue"] > 0
