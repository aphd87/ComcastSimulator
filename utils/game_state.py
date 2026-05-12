"""
CableOS — Game State & Scoring Engine
FERPA-safe: no student names stored, only team names (student-chosen pseudonyms).
Leaderboard tracks: team_name, network_level, attempt_number, score, timestamp.
First attempt score is locked as the official score — subsequent attempts are practice only.
"""
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────
LEADERBOARD_FILE = Path("leaderboard.json")
MAX_ATTEMPTS     = 3          # After 3 fails, still unlock next level
PASS_THRESHOLD   = {          # Minimum OCF margin % to pass each level
    "bravo":   15.0,          # 15% OCF margin to pass Bravo
    "oxygen":  12.0,          # Slightly lower — tighter budget
    "peacock": 10.0,          # SVOD early days — thinner margins OK
}
SCORE_WEIGHTS = {
    "ocf_margin":    0.35,    # 35% — core financial health
    "roi_avg":       0.25,    # 25% — show portfolio efficiency
    "genre_mix":     0.15,    # 15% — diversification (HHI penalty)
    "renewal_pct":   0.10,    # 10% — sound renewal decisions
    "mkt_efficiency":0.15,    # 15% — marketing ROI
}

NETWORK_ORDER = ["oxygen", "bravo", "peacock"]

# ── Scoring ───────────────────────────────────────────────────────────────────
def compute_score(
    ocf_margin: float,
    avg_roi: float,
    genre_hhi: float,      # 0-1, lower = more diverse (good)
    renewal_pct: float,    # % of renewed shows that are ROI-positive
    mkt_efficiency: float, # ad rev per $M marketing
) -> dict:
    """
    Returns a score dict with component breakdown and total (0-100).
    All inputs normalized to 0-1 before weighting.
    """
    # Normalize each component to 0–1
    s_ocf  = min(max(ocf_margin / 40.0, 0), 1)       # 40% margin = perfect
    s_roi  = min(max((avg_roi + 20) / 80.0, 0), 1)   # -20% → 0, +60% → 1
    s_div  = max(1 - genre_hhi, 0)                    # lower HHI = higher score
    s_ren  = min(max(renewal_pct / 100.0, 0), 1)
    s_mkt  = min(max(mkt_efficiency / 30.0, 0), 1)   # $30M rev/$M mkt = perfect

    total = (
        s_ocf  * SCORE_WEIGHTS["ocf_margin"]    * 100 +
        s_roi  * SCORE_WEIGHTS["roi_avg"]        * 100 +
        s_div  * SCORE_WEIGHTS["genre_mix"]      * 100 +
        s_ren  * SCORE_WEIGHTS["renewal_pct"]    * 100 +
        s_mkt  * SCORE_WEIGHTS["mkt_efficiency"] * 100
    )

    return {
        "total":        round(total, 1),
        "ocf_margin":   round(s_ocf  * 100, 1),
        "roi":          round(s_roi  * 100, 1),
        "diversity":    round(s_div  * 100, 1),
        "renewal":      round(s_ren  * 100, 1),
        "marketing":    round(s_mkt  * 100, 1),
        "passed":       ocf_margin >= PASS_THRESHOLD.get("bravo", 15),  # updated per network
    }

def compute_score_for_network(network: str, ocf_margin: float, avg_roi: float,
                               genre_hhi: float, renewal_pct: float,
                               mkt_efficiency: float) -> dict:
    result = compute_score(ocf_margin, avg_roi, genre_hhi, renewal_pct, mkt_efficiency)
    result["passed"] = ocf_margin >= PASS_THRESHOLD.get(network, 12)
    return result

def hhi_from_genres(genre_costs: dict) -> float:
    """Herfindahl-Hirschman Index for genre concentration. 0=diverse, 1=monopoly."""
    total = sum(genre_costs.values())
    if not total: return 1.0
    shares = [v/total for v in genre_costs.values()]
    return sum(s**2 for s in shares)

# ── FERPA-Safe Leaderboard ────────────────────────────────────────────────────
def load_leaderboard() -> list[dict]:
    """Load leaderboard from JSON. Returns empty list if not found."""
    if LEADERBOARD_FILE.exists():
        try:
            return json.loads(LEADERBOARD_FILE.read_text())
        except Exception:
            return []
    return []

def save_leaderboard(board: list[dict]) -> None:
    LEADERBOARD_FILE.write_text(json.dumps(board, indent=2))

def record_attempt(team_name: str, network: str, attempt_num: int,
                   score: float, passed: bool, details: dict) -> dict:
    """
    Record one attempt. First attempt is always official.
    FERPA note: team_name is a student-chosen pseudonym — no PII stored.
    """
    board = load_leaderboard()

    entry = {
        "team_name":    team_name,
        "network":      network,
        "attempt":      attempt_num,
        "score":        round(score, 1),
        "passed":       passed,
        "timestamp":    int(time.time()),
        "is_official":  attempt_num == 1,   # first attempt locked as official
        "details":      details,
    }
    board.append(entry)
    save_leaderboard(board)
    return entry

def get_team_attempts(team_name: str, network: str) -> list[dict]:
    board = load_leaderboard()
    return [e for e in board if e["team_name"] == team_name and e["network"] == network]

def get_official_score(team_name: str, network: str) -> Optional[dict]:
    """Returns the first (official) attempt for a team on a given network."""
    attempts = get_team_attempts(team_name, network)
    if not attempts: return None
    official = [a for a in attempts if a["is_official"]]
    return official[0] if official else attempts[0]

def get_attempt_count(team_name: str, network: str) -> int:
    return len(get_team_attempts(team_name, network))

def can_advance(team_name: str, current_network: str) -> bool:
    """
    Can advance if:
    - Passed on any attempt, OR
    - Failed attempt 1 and completed at least one retry (attempt 2+)
    Students must repeat a level once before graduating — no free pass on first fail.
    """
    attempts = get_team_attempts(team_name, current_network)
    if not attempts: return False
    passed_any = any(a["passed"] for a in attempts)
    repeated   = len(attempts) >= 2   # must retry before advancing
    return passed_any or repeated

def get_network_leaderboard(network: str) -> list[dict]:
    """
    Returns ranked leaderboard for a network using OFFICIAL (first attempt) scores.
    Ties broken by timestamp (earlier = better).
    """
    board = load_leaderboard()
    official = {}
    for entry in board:
        if entry["network"] != network or not entry["is_official"]:
            continue
        team = entry["team_name"]
        if team not in official or entry["timestamp"] < official[team]["timestamp"]:
            official[team] = entry

    ranked = sorted(official.values(), key=lambda x: (-x["score"], x["timestamp"]))
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    return ranked

def get_team_network_status(team_name: str) -> dict:
    """Returns which networks are unlocked and their status for a team."""
    status = {}
    prev_can_advance = True
    for i, net in enumerate(NETWORK_ORDER):
        attempts = get_team_attempts(team_name, net)
        official = get_official_score(team_name, net)
        locked   = not prev_can_advance and i > 0
        passed   = any(a["passed"] for a in attempts)
        used_all = len(attempts) >= MAX_ATTEMPTS
        status[net] = {
            "locked":       locked,
            "attempts":     len(attempts),
            "official_score": official["score"] if official else None,
            "passed":       passed,
            "can_retry":    len(attempts) < MAX_ATTEMPTS and not passed,
            "can_advance":  can_advance(team_name, net),
        }
        prev_can_advance = status[net]["can_advance"]
    return status

# ── Network identity ──────────────────────────────────────────────────────────
NETWORK_INFO = {
    "bravo": {
        "display_name": "Bravo",
        "tagline":      "Culture. Competition. Conversation.",
        "founded":      1980,
        "parent":       "NBCUniversal / Comcast",
        "hq":           "New York, NY",
        "demographics": "Adults 25–54, skewing female; affluent, educated",
        "avg_ep_cost":  "$650K–$900K (reality); $1.2M+ (scripted)",
        "hit_shows":    "Real Housewives franchise, Top Chef, Below Deck, Vanderpump Rules",
        "bio": (
            "Launched in 1980 as a performing arts channel, Bravo pivoted to reality "
            "and competition programming in the early 2000s under NBC's ownership. "
            "By 2012, it had become cable's premier destination for aspirational lifestyle "
            "content — a tight mix of Real Housewives franchises, culinary competition "
            "(Top Chef), and luxury reality. Its affluent, female-skewing demo commanded "
            "premium CPMs well above cable averages. The challenge in 2012: diversify the "
            "content mix beyond reality while cord-cutting begins eroding the subscriber base."
        ),
        "color":  "#c0392b",
        "color2": "#e74c3c",
        "emoji":  "📺",
        "budget_base": 220,
        "ep_cost_range": (400, 1200),
        "pass_threshold": 15.0,
        "logo_text": "BRAVO",
    },
    "oxygen": {
        "display_name": "Oxygen",
        "tagline":      "True Crime. Real Stories. Real Stakes.",
        "founded":      2000,
        "parent":       "NBCUniversal / Comcast",
        "hq":           "New York, NY",
        "demographics": "Women 25–54; true crime super-fans; strong streaming crossover",
        "avg_ep_cost":  "$250K–$350K (true crime doc); $400K (produced reality)",
        "hit_shows":    "Snapped, Cold Justice, Killer Motive, The Disappearance",
        "bio": (
            "Originally launched as a women's lifestyle channel in 2000, Oxygen was "
            "repositioned in 2017 as a true crime network — but even in 2012 it was "
            "finding its footing with lower-budget crime and justice programming. "
            "Oxygen's economics are fundamentally different from Bravo: cheaper content "
            "($250–350K/ep), shorter 3-year amortization curves, and a passionate niche "
            "audience with outsized digital engagement. Managing Oxygen alongside Bravo "
            "forces portfolio-level thinking: do you cross-promote? Share marketing budgets? "
            "Or run each P&L in isolation?"
        ),
        "color":  "#8e44ad",
        "color2": "#9b59b6",
        "emoji":  "🔮",
        "budget_base": 95,
        "ep_cost_range": (250, 400),
        "pass_threshold": 12.0,
        "logo_text": "OXYGEN",
    },
    "peacock": {
        "display_name": "Peacock",
        "tagline":      "Stream Free. Stream More. Stream Smarter.",
        "founded":      2020,
        "parent":       "NBCUniversal / Comcast",
        "hq":           "New York, NY",
        "demographics": "Broad 18–49; lapsed cable subs; SVOD switchers from Netflix",
        "avg_ep_cost":  "$1M–$3M (originals); library content at marginal cost",
        "hit_shows":    "The Office (library), Yellowstone (window), original NBCU content",
        "bio": (
            "Peacock represents the strategic bet that NBCU's linear library — The Office, "
            "Parks & Rec, decades of NBC catalog — could anchor a streaming service. "
            "In this simulation (set conceptually in 2012), 'Peacock' stands in for the "
            "inevitable SVOD play that every cable operator knew was coming. The economics "
            "are inverted from linear: you spend heavily upfront (subscriber acquisition, "
            "original content) for deferred subscription LTV. The green light model changes "
            "entirely — you're no longer optimizing for CPM and ratings, but for subscriber "
            "adds, churn reduction, and 36-month LTV. Every dollar spent on Peacock competes "
            "directly with dollars that would stabilize Bravo and Oxygen's declining linear base."
        ),
        "color":  "#1a6bb5",
        "color2": "#2980b9",
        "emoji":  "🦚",
        "budget_base": 150,
        "ep_cost_range": (800, 3000),
        "pass_threshold": 10.0,
        "logo_text": "PEACOCK",
    },
}

# ── Business theory content ────────────────────────────────────────────────────
THEORY_CONTENT = {
    "bcg": {
        "title": "BCG Portfolio Matrix",
        "icon": "📊",
        "brief": (
            "The BCG Growth-Share Matrix classifies business units (or shows) into four quadrants: "
            "**Stars** (high rating, high growth), **Cash Cows** (high rating, low growth), "
            "**Question Marks** (low rating, high growth potential), and **Dogs** (low rating, low growth). "
            "In cable programming, Real Housewives is the classic Cash Cow — high ratings, mature franchise, "
            "reliable OCF. A new scripted show is a Question Mark. Manage Cash Cows to fund Stars."
        ),
    },
    "hhi": {
        "title": "Herfindahl-Hirschman Index (Genre Diversification)",
        "icon": "🎯",
        "brief": (
            "The HHI measures content concentration. A portfolio of all reality shows scores ~1.0 (monopoly). "
            "A mix of reality, competition, scripted, and talk scores much lower. "
            "Regulators use HHI for M&A review; here it measures your resilience if one genre collapses. "
            "Bravo in 2012 was dangerously concentrated in reality — the simulation penalizes this."
        ),
    },
    "cord_cutting": {
        "title": "Diffusion of Innovation & Cord-Cutting S-Curve",
        "icon": "📉",
        "brief": (
            "Rogers' Diffusion curve predicts that cord-cutting would accelerate from early adopters (2010–2014) "
            "through early majority (2015–2019) to mass market (2020+). The simulation models this as a 3%/year "
            "subscriber erosion that accelerates. Networks that waited too long to launch SVOD were caught in "
            "the steep part of the S-curve. The Peacock level forces you to manage the cannibalization trade-off."
        ),
    },
    "amortization": {
        "title": "Content Amortization & Cash Flow Timing",
        "icon": "💸",
        "brief": (
            "Under ASC 926, TV content is amortized over its expected useful life — typically 12 months for "
            "linear series, 36 months for SVOD originals. You pay 1/12 of total season cost each month on air. "
            "This creates the premiere-day problem: launch on March 30 and you absorb a full monthly amortization "
            "payment with 2 days of ad revenue. Cash cows must fund new show launch gaps."
        ),
    },
    "ltv": {
        "title": "LTV / CAC Framework (SVOD Economics)",
        "icon": "📱",
        "brief": (
            "SVOD profitability hinges on Lifetime Value (LTV) vs. Customer Acquisition Cost (CAC). "
            "LTV = ARPU × retention months × margin. A $8/month sub retained 18 months at 15% margin = $21.60 LTV. "
            "If content costs $750K/ep and drives 50K new subs, CAC from content = $15/sub. "
            "The green light model forces you to compare this against linear's immediate CPM revenue."
        ),
    },
}
