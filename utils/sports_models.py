"""
The Slate — Sports Rights bidding engine (Peacock only)
All monetary values in $M unless noted.

Built 2026-08-04 per explicit user framing: originals aren't just a
subscriber-acquisition play, they're the actual profitability engine that
has to cover the structural loss sports rights create ("a surgically
created entertainment slate is critical as it is a loss leader that must
make up the profitability gap from sports"). So this module doesn't model
sports as a flat cost line — it models a real strategic lever (a sealed-bid
auction against seeded rival tech/media firms, real multi-year contracts,
a concentrated subscriber spike, and a churn tail that only a strong
originals slate can retain) whose whole point is to put a hole in
Peacock's P&L that the originals slate must outrun. See
utils/game_state.py's PASS_THRESHOLD — that check doesn't change; sports
just makes it genuinely harder to clear, on purpose.

Design decisions locked in with the user before building (2026-08-04):
- Bidding is a real annual opportunity, not a one-time Peacock-entry
  choice — but each league's contract runs 5-7 years once won (real rights
  deals aren't renegotiated annually), so a given league is only actually
  up for auction on cycle boundaries, not every single year.
- Multiple leagues/tiers (not one generic "sports" line), each with a
  distinct risk/spike/churn profile: NFL (premium, concentrated season,
  sharp churn), Premier League (mid, spread over most of the year, softer
  churn), Summer Olympics (prestige, long hold, rare-but-huge payoff —
  most years of the hold are pure carrying cost with zero direct revenue).
- Rival bidders are real tech/media firms, not an abstract clearing price
  — sealed-bid first-price (highest bid wins, pays *its own* bid, not the
  second-highest), so overpaying (the real "winner's curse") is a live
  risk, matching how these auctions actually work.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import Optional

# ── League/tier definitions ─────────────────────────────────────────────────
# A small curated set (same pattern as utils/models.py's REGIONS/GENRE_DEMOS)
# — illustrative, not an attempt to model real rights economics exactly.
# base_rights_cost_m anchors what rival bids cluster around (see
# draw_rival_bids); direct_revenue_m is the package's own ad/sub revenue
# before any originals-driven retention — deliberately calibrated below
# base_rights_cost_m for NFL/Premier League so winning at a competitive
# price is a structural loss on its own, per the brief's "sports as loss
# leader" framing. Olympics direct_revenue_m looks generous by comparison
# but only ever realizes in a Games year (see games_every_n_years) — every
# other year of the hold is pure carrying cost.
SPORTS_LEAGUES = {
    "NFL Sunday Night Football": {
        "tier":               "Premium",
        "base_rights_cost_m": 70.0,
        "term_range":         (5, 7),
        "season_months":      5,      # concentrated — real "spike then churn"
        "direct_revenue_m":   42.0,   # every year held
        "retention_floor":    0.30,   # kept passively even with zero originals push
        "games_every_n_years": None,
    },
    "Premier League": {
        "tier":               "Mid",
        "base_rights_cost_m": 30.0,
        "term_range":         (4, 6),
        "season_months":      9,      # spread over most of the year — softer churn
        "direct_revenue_m":   20.0,
        "retention_floor":    0.55,
        "games_every_n_years": None,
    },
    "Summer Olympics": {
        "tier":               "Prestige",
        "base_rights_cost_m": 35.0,
        "term_range":         (6, 7),
        "season_months":      1,
        "direct_revenue_m":   110.0,  # Games years only
        "retention_floor":    0.15,   # sharpest spike-then-churn of the three
        "games_every_n_years": 4,
    },
}

# Originals content-spend "enough to retain the spike" calibration — see
# retained_fraction(). 0.5 means spending half the season's direct revenue
# on Peacock originals this year fully retains it (up to 1.0); spending
# nothing still keeps each league's retention_floor passively.
RETENTION_SPEND_MULTIPLIER = 0.5

# Rival tech/media bidders — a small illustrative set (per explicit user
# request: "all tech/media firm rivals to bid too"), not an attempt to
# model any real company's actual sports-rights strategy. Each cycle, each
# rival independently may or may not participate (RIVAL_PARTICIPATION_CHANCE)
# and if it does, its bid is base_rights_cost_m scaled by a seeded random
# multiplier — see draw_rival_bids.
RIVAL_BIDDERS = ["Amazon", "Apple", "YouTube/Google", "Netflix", "ESPN/Disney", "Warner Bros. Discovery"]
RIVAL_PARTICIPATION_CHANCE = 0.6
RIVAL_BID_MULT_RANGE = (0.85, 1.35)


# ── Auction cycles ───────────────────────────────────────────────────────────
def _seeded_term(league_key: str, cycle_index: int, term_range: tuple[int, int]) -> int:
    """Deterministic, team-independent — the contract length for a given
    league's Nth auction cycle. Same world for every team in a deployment
    (no team_name in the seed), matching how real rights deals don't wait
    for any one team's convenience."""
    seed = (abs(hash(league_key)) + cycle_index * 7919) % (2 ** 31)
    rng  = np.random.default_rng(seed)
    lo, hi = term_range
    return int(rng.integers(lo, hi + 1))


def cycle_for_year(league_key: str, year: int, anchor_year: int) -> tuple[int, int, int]:
    """Returns (cycle_index, start_year, end_year) covering `year`, chained
    forward from anchor_year (Peacock's own LEVEL_START_YEAR — same for
    every team in a deployment, guaranteeing every team's Year 1 at Peacock
    sees a real first auction on all three leagues, rather than depending
    on a global calendar a short level might never intersect)."""
    term_range = SPORTS_LEAGUES[league_key]["term_range"]
    y, idx = anchor_year, 0
    while True:
        term = _seeded_term(league_key, idx, term_range)
        end  = y + term - 1
        if y <= year <= end:
            return idx, y, end
        y   = end + 1
        idx += 1


def leagues_up_for_bid(year: int, anchor_year: int) -> list[str]:
    """Leagues whose auction cycle starts exactly this year — i.e., a real
    bidding opportunity exists. Most years this is empty; that's the point
    (5-7yr real contracts, not an annual re-bid)."""
    up = []
    for league_key in SPORTS_LEAGUES:
        _, start, _ = cycle_for_year(league_key, year, anchor_year)
        if start == year:
            up.append(league_key)
    return up


# ── Rival bidding & auction resolution ──────────────────────────────────────
def draw_rival_bids(league_key: str, cycle_index: int) -> list[dict]:
    """Seeded, team-independent rival bids for one auction cycle — every
    team in a deployment sees the same rivals bidding the same amounts for
    the same cycle, same reasoning as _seeded_term. Not every rival
    participates every cycle."""
    seed = (abs(hash(league_key)) + cycle_index * 104729 + 11) % (2 ** 31)
    rng  = np.random.default_rng(seed)
    base = SPORTS_LEAGUES[league_key]["base_rights_cost_m"]
    lo, hi = RIVAL_BID_MULT_RANGE
    bids = []
    for rival in RIVAL_BIDDERS:
        if rng.random() < RIVAL_PARTICIPATION_CHANCE:
            mult = float(rng.uniform(lo, hi))
            bids.append({"bidder": rival, "bid_m": round(base * mult, 1)})
    return bids


def resolve_auction(team_bid_m: float, rival_bids: list[dict]) -> dict:
    """Sealed-bid first-price: highest bid wins and pays its OWN bid (not
    the runner-up's) — the real 'winner's curse' risk of overpaying is
    live, not abstracted away. team_bid_m <= 0 means the team declined to
    bid this cycle."""
    all_bids = list(rival_bids)
    if team_bid_m > 0:
        all_bids.append({"bidder": "You", "bid_m": round(team_bid_m, 1)})
    if not all_bids:
        return {"winner": None, "won_by_team": False, "winning_bid_m": 0.0, "all_bids": []}
    ranked = sorted(all_bids, key=lambda b: -b["bid_m"])
    winner = ranked[0]
    return {
        "winner":        winner["bidder"],
        "won_by_team":   winner["bidder"] == "You",
        "winning_bid_m": winner["bid_m"],
        "all_bids":      ranked,
    }


# ── Contract & P&L ───────────────────────────────────────────────────────────
@dataclass
class SportsContract:
    league:          str
    start_year:      int
    end_year:        int
    annual_cost_m:   float   # the team's winning bid — paid every year of the hold


def is_games_year(league_key: str, contract_start_year: int, year: int) -> bool:
    """Olympics-only concept — see games_every_n_years. Every other league
    returns True unconditionally (they generate direct revenue every year
    held)."""
    n = SPORTS_LEAGUES[league_key]["games_every_n_years"]
    if n is None:
        return True
    return (year - contract_start_year) % n == 0


def retained_fraction(league_key: str, originals_spend_m: float) -> float:
    """How much of the season's direct revenue actually sticks as lasting
    value, given how much the team spent on Peacock originals THIS year.
    Floors at the league's passive retention_floor (some subs stick around
    with no help) and caps at 1.0 (can't retain more than the spike)."""
    league = SPORTS_LEAGUES[league_key]
    floor  = league["retention_floor"]
    if league["direct_revenue_m"] <= 0:
        return floor
    need = league["direct_revenue_m"] * RETENTION_SPEND_MULTIPLIER
    earned = originals_spend_m / need if need > 0 else 1.0
    return float(min(1.0, max(floor, earned)))


def sports_year_pnl(held: list[SportsContract], year: int, originals_spend_m: float) -> dict:
    """Peacock's sports-rights P&L contribution for one year: every held
    contract's annual cost hits regardless, direct revenue (tempered by
    how well the originals slate retained it) only counts in a year the
    league actually airs (see is_games_year). Returns the aggregate plus a
    per-league breakdown so the UI can show students exactly where the gap
    (or surplus) came from."""
    revenue_m, cost_m, rows = 0.0, 0.0, []
    for c in held:
        if not (c.start_year <= year <= c.end_year):
            continue
        cost_m += c.annual_cost_m
        games = is_games_year(c.league, c.start_year, year)
        if games:
            frac = retained_fraction(c.league, originals_spend_m)
            rev  = SPORTS_LEAGUES[c.league]["direct_revenue_m"] * frac
        else:
            frac, rev = 0.0, 0.0
        revenue_m += rev
        rows.append({
            "league": c.league, "cost_m": round(c.annual_cost_m, 1),
            "revenue_m": round(rev, 1), "net_m": round(rev - c.annual_cost_m, 1),
            "games_year": games, "retained_fraction": round(frac, 2),
        })
    return {
        "revenue_m": round(revenue_m, 2),
        "cost_m":    round(cost_m, 2),
        "net_m":     round(revenue_m - cost_m, 2),
        "rows":      rows,
    }


def held_this_year(contracts: list[SportsContract], year: int) -> list[SportsContract]:
    return [c for c in contracts if c.start_year <= year <= c.end_year]
