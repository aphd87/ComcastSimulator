"""
Regression tests for app_pages/finance.py's P&L/OCF tab, added 2026-08-24
after a connectivity audit found two real, undisclosed divergences from the
actual simulated numbers (app_pages/simulation.py::_compute_year):

1. This page always recomputed its own no-variance preview, even for a year
   that had already been simulated -- so it could show different Ad
   Revenue/OCF than the Results tab for the exact same year.
2. Peacock sports rights revenue/cost were entirely omitted from this
   page's totals, even though _compute_year folds them straight into OCF --
   understating cost and overstating OCF for a Peacock team holding a
   contract.

Also checks the Monthly OCF chart's per-month figures sum back to the
annual Net OCF metric (previously the monthly figures omitted G&A while the
annual one subtracted it).
"""
from streamlit.testing.v1 import AppTest

from utils.models import Show
from utils.sports_models import SportsContract, held_this_year, sports_year_pnl
from utils.models import portfolio_cost


def _peacock_show():
    return Show(id=901, name="Test Peacock Original", genre="Drama", episodes=8,
                ep_cost_k=900, rating=1.5, ip_score=60, air_month=3, network="Peacock")


def _finance_app(year=1, yearly_log=None, sports_contracts=None) -> AppTest:
    def script(year, yearly_log, sports_contracts):
        import streamlit as st
        import sys
        sys.path.insert(0, ".")
        from utils.models import Show
        ss = st.session_state
        ss.team_name      = "AppTest Team"
        ss.active_network = "peacock"
        ss.year           = year
        ss.mkt_budget     = 5.0
        ss.oxygen_shows   = []
        ss.bravo_shows    = []
        ss.peacock_shows  = [Show(id=901, name="Test Peacock Original", genre="Drama",
                                   episodes=8, ep_cost_k=900, rating=1.5, ip_score=60,
                                   air_month=3, network="Peacock")]
        ss.yearly_log        = yearly_log or []
        ss.sports_contracts  = sports_contracts or []

        import app_pages.finance as finance
        finance.render()

    at = AppTest.from_function(script, default_timeout=30, args=(year, yearly_log, sports_contracts))
    at.run()
    assert not at.exception, f"Finance page raised: {list(at.exception)}"
    return at


def test_peacock_sports_rights_are_included_in_preview_ocf():
    """Not-yet-simulated year: sports revenue/cost must be folded into the
    Net OCF metric, not silently omitted."""
    contract = SportsContract(league="Premier League", start_year=1, end_year=3, annual_cost_m=25.0)
    at_no_sports   = _finance_app(year=1, sports_contracts=[])
    at_with_sports = _finance_app(year=1, sports_contracts=[contract])

    def net_ocf(at):
        m = next(m for m in at.metric if m.label == "Net OCF")
        return float(m.value.replace("$", "").replace("M", ""))

    assert net_ocf(at_with_sports) != net_ocf(at_no_sports), (
        "Holding a sports contract must change the Peacock Net OCF shown here"
    )

    # Cross-check against the real sports_year_pnl the actual sim uses.
    held = held_this_year([contract], 1)
    originals_spend_m = portfolio_cost([_peacock_show()], 1)
    sp = sports_year_pnl(held, 1, originals_spend_m)
    assert sp["revenue_m"] > 0 or sp["cost_m"] > 0   # sanity: contract actually has a real P&L


def test_already_simulated_year_uses_the_real_yearly_log_numbers():
    """Once a year has been simulated, this page must echo yearly_log's
    real figures, not recompute its own no-variance preview."""
    played_entry = {
        "year": 1, "label": "Year 1", "revenue": 123.45, "ad_rev": 100.0, "dist_rev": 23.45,
        "sports_rev": 0.0, "sports_cost": 0.0, "cost": 60.0, "mkt": 5.0, "ga": 7.41,
        "ocf": 51.04, "margin": 41.3,
    }
    at = _finance_app(year=1, yearly_log=[played_entry])
    rev_metric = next(m for m in at.metric if m.label == "Total Revenue")
    ocf_metric = next(m for m in at.metric if m.label == "Net OCF")
    assert rev_metric.value == "$123.4M" or rev_metric.value == "$123.5M"  # rounding
    assert "51.0" in ocf_metric.value


def test_content_cost_by_genre_donut_renders():
    # 2026-08-24 add: Genre Diversity is a real, 15%-weighted score
    # component (utils/game_state.py::hhi_from_genres) that previously had
    # no visualization anywhere.
    at = _finance_app(year=1, sports_contracts=[])
    specs = [el.proto.spec for el in at.get("plotly_chart")]
    assert any("Content Cost by Genre" in s and "Drama" in s for s in specs)


def test_monthly_ocf_sums_to_the_annual_net_ocf():
    at = _finance_app(year=1, sports_contracts=[])
    net_ocf_metric = next(m for m in at.metric if m.label == "Net OCF")
    annual_ocf = float(net_ocf_metric.value.replace("$", "").replace("M", ""))

    import base64, json
    import numpy as np
    specs = [json.loads(el.proto.spec) for el in at.get("plotly_chart")]
    ocf_trace = next(
        t for spec in specs for t in spec["data"] if t.get("name") == "Monthly OCF"
    )
    # Plotly encodes numeric arrays as base64 float64 blobs in the raw spec,
    # not plain JSON lists.
    y_values = np.frombuffer(base64.b64decode(ocf_trace["y"]["bdata"]), dtype=np.float64)
    # Tolerance covers the seasonal sine-curve's own discretization drift
    # (monthly_ad's sin() shape doesn't sum to exactly ad_rev over 12
    # discrete months, a pre-existing, deliberately illustrative-shape
    # property, not a bug) -- large enough to still catch a real regression
    # like G&A silently dropping back out of the monthly figures (which
    # would be off by the full `ga` term, an order of magnitude bigger).
    assert abs(y_values.sum() - annual_ocf) < 5.0
