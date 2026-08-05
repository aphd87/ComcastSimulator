"""
Regression tests for utils/sports_models.py (Peacock-only sports rights
bidding engine, added 2026-08-04). Mirrors tests/test_models.py's posture:
guard against "runs without erroring but is quietly wrong," especially
around determinism (same world for every team) and the loss-leader framing
the whole feature exists to teach.
"""
import pytest

from utils.sports_models import (
    SPORTS_LEAGUES, RIVAL_BIDDERS, cycle_for_year, leagues_up_for_bid,
    draw_rival_bids, resolve_auction, SportsContract, is_games_year,
    retained_fraction, sports_year_pnl, held_this_year,
    RETENTION_SPEND_MULTIPLIER,
)

ANCHOR = 2020   # stand-in Peacock LEVEL_START_YEAR for these tests


# ── Auction cycles ────────────────────────────────────────────────────────────
class TestCycles:
    def test_first_cycle_always_starts_at_anchor_year(self):
        # Every league gets a real first auction at Peacock Year 1 for every
        # team, regardless of instructor-configured level length -- the
        # whole reason cycles are anchored to LEVEL_START_YEAR instead of a
        # fixed global calendar year (see module docstring).
        for league in SPORTS_LEAGUES:
            idx, start, end = cycle_for_year(league, ANCHOR, ANCHOR)
            assert idx == 0
            assert start == ANCHOR
            lo, hi = SPORTS_LEAGUES[league]["term_range"]
            assert lo <= (end - start + 1) <= hi

    def test_cycles_chain_with_no_gap_or_overlap(self):
        league = "NFL Sunday Night Football"
        _, s0, e0 = cycle_for_year(league, ANCHOR, ANCHOR)
        _, s1, e1 = cycle_for_year(league, e0 + 1, ANCHOR)
        assert s1 == e0 + 1   # next cycle starts immediately after, no gap

    def test_deterministic_across_calls(self):
        for league in SPORTS_LEAGUES:
            a = cycle_for_year(league, ANCHOR + 3, ANCHOR)
            b = cycle_for_year(league, ANCHOR + 3, ANCHOR)
            assert a == b

    def test_team_independent(self):
        # Deliberately no team_name in the seed anywhere in this module --
        # the rights market is the same world for every team in a deployment.
        # There's no team_name parameter to even pass, so this is really
        # just confirming the public API shape stays that way.
        import inspect
        for fn in (cycle_for_year, leagues_up_for_bid, draw_rival_bids):
            params = inspect.signature(fn).parameters
            assert "team_name" not in params

    def test_all_leagues_up_for_bid_at_anchor_year(self):
        up = leagues_up_for_bid(ANCHOR, ANCHOR)
        assert set(up) == set(SPORTS_LEAGUES.keys())

    def test_most_years_nothing_is_up_for_bid(self):
        # 5-7yr real contracts -- an annual re-bid on everything would
        # defeat the point. Sample a wide range and confirm most years are quiet.
        #
        # Found and fixed 2026-08-04 (incidental, while diagnosing an
        # unrelated hash-seed flakiness class in tests/test_movies_page.py):
        # this assertion compared quiet_years (counted from the 39-element
        # counts[1:] slice, deliberately excluding the anchor year) against
        # a threshold computed from len(counts) -- the full 40-element list
        # including the anchor. That off-by-one demanded >20/39 (53.8%+)
        # while the intent was "more than half of the non-anchor years,"
        # i.e. >19.5/39 -- a real, hash-seed-independent latent flakiness
        # bug (leagues_up_for_bid's cycle boundaries are seeded off
        # hash(league_key), which is itself per-process-randomized, so the
        # exact quiet-year count legitimately varies run to run and
        # occasionally landed on exactly 20/39, failing the too-strict
        # threshold). Verified robust across PYTHONHASHSEED 0-15 after the fix.
        years = range(ANCHOR, ANCHOR + 40)
        counts = [len(leagues_up_for_bid(y, ANCHOR)) for y in years]
        assert counts[0] == len(SPORTS_LEAGUES)          # anchor year is the exception
        non_anchor_years = counts[1:]
        quiet_years = sum(1 for c in non_anchor_years if c == 0)
        assert quiet_years > len(non_anchor_years) * 0.5


# ── Rival bidding & auction resolution ──────────────────────────────────────
class TestAuction:
    def test_rival_bids_deterministic(self):
        a = draw_rival_bids("NFL Sunday Night Football", 0)
        b = draw_rival_bids("NFL Sunday Night Football", 0)
        assert a == b

    def test_rival_bids_only_named_bidders(self):
        for league in SPORTS_LEAGUES:
            for idx in range(3):
                bids = draw_rival_bids(league, idx)
                for b in bids:
                    assert b["bidder"] in RIVAL_BIDDERS
                    assert b["bid_m"] > 0

    def test_team_wins_with_highest_bid(self):
        rivals = [{"bidder": "Amazon", "bid_m": 50.0}, {"bidder": "Netflix", "bid_m": 40.0}]
        result = resolve_auction(100.0, rivals)
        assert result["won_by_team"] is True
        assert result["winner"] == "You"
        assert result["winning_bid_m"] == 100.0   # pays own bid, not runner-up's

    def test_team_loses_with_low_bid(self):
        rivals = [{"bidder": "Amazon", "bid_m": 80.0}]
        result = resolve_auction(20.0, rivals)
        assert result["won_by_team"] is False
        assert result["winner"] == "Amazon"
        assert result["winning_bid_m"] == 80.0

    def test_declining_to_bid(self):
        rivals = [{"bidder": "Apple", "bid_m": 60.0}]
        result = resolve_auction(0.0, rivals)
        assert result["won_by_team"] is False
        assert result["winner"] == "Apple"

    def test_no_bidders_at_all(self):
        result = resolve_auction(0.0, [])
        assert result["winner"] is None
        assert result["won_by_team"] is False


# ── Contract P&L / loss-leader framing ───────────────────────────────────────
class TestSportsPnL:
    def test_holding_costs_every_year_of_term(self):
        c = SportsContract(league="Premier League", start_year=2020, end_year=2023, annual_cost_m=25.0)
        for y in (2020, 2021, 2022, 2023):
            assert len(held_this_year([c], y)) == 1
        assert held_this_year([c], 2024) == []
        assert held_this_year([c], 2019) == []

    def test_zero_originals_spend_still_hits_retention_floor(self):
        for league in SPORTS_LEAGUES:
            frac = retained_fraction(league, originals_spend_m=0.0)
            assert frac == pytest.approx(SPORTS_LEAGUES[league]["retention_floor"])

    def test_heavy_originals_spend_caps_at_full_retention(self):
        for league, info in SPORTS_LEAGUES.items():
            need = info["direct_revenue_m"] * RETENTION_SPEND_MULTIPLIER
            frac = retained_fraction(league, originals_spend_m=need * 10)
            assert frac == 1.0

    def test_nfl_and_premier_league_are_loss_leaders_at_market_price(self):
        # The whole point: winning at roughly the market-clearing price
        # (base_rights_cost_m) should run at a structural loss even with
        # full retention -- originals have to make up the difference, not
        # the package itself. Olympics is deliberately excluded (its
        # loss-leader character comes from off-Games years, tested below).
        for league in ("NFL Sunday Night Football", "Premier League"):
            info = SPORTS_LEAGUES[league]
            c = SportsContract(league=league, start_year=2020, end_year=2020,
                               annual_cost_m=info["base_rights_cost_m"])
            heavy_spend = info["direct_revenue_m"] * RETENTION_SPEND_MULTIPLIER * 10
            pnl = sports_year_pnl([c], 2020, heavy_spend)
            assert pnl["net_m"] < 0

    def test_olympics_off_games_year_is_pure_cost(self):
        c = SportsContract(league="Summer Olympics", start_year=2020, end_year=2026, annual_cost_m=35.0)
        assert is_games_year("Summer Olympics", 2020, 2020) is True
        assert is_games_year("Summer Olympics", 2020, 2021) is False
        pnl_quiet = sports_year_pnl([c], 2021, originals_spend_m=1000.0)  # even huge spend can't matter
        assert pnl_quiet["revenue_m"] == 0.0
        assert pnl_quiet["cost_m"] == 35.0
        assert pnl_quiet["net_m"] == -35.0

    def test_olympics_games_year_generates_revenue(self):
        c = SportsContract(league="Summer Olympics", start_year=2020, end_year=2026, annual_cost_m=35.0)
        pnl = sports_year_pnl([c], 2020, originals_spend_m=1000.0)
        assert pnl["revenue_m"] > 0

    def test_pnl_only_counts_contracts_held_that_year(self):
        c = SportsContract(league="Premier League", start_year=2020, end_year=2022, annual_cost_m=25.0)
        pnl = sports_year_pnl([c], 2025, originals_spend_m=100.0)
        assert pnl == {"revenue_m": 0.0, "cost_m": 0.0, "net_m": 0.0, "rows": []}

    def test_multiple_held_contracts_sum(self):
        c1 = SportsContract(league="NFL Sunday Night Football", start_year=2020, end_year=2026, annual_cost_m=70.0)
        c2 = SportsContract(league="Premier League", start_year=2020, end_year=2025, annual_cost_m=30.0)
        pnl = sports_year_pnl([c1, c2], 2020, originals_spend_m=50.0)
        assert len(pnl["rows"]) == 2
        assert pnl["cost_m"] == pytest.approx(100.0)
