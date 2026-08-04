"""
The Slate — Financial engine & data model
All monetary values in $M unless noted.
"""
from __future__ import annotations   # list[...]/dict[...] type hints below need Python
                                       # 3.9+ without this — see utils/game_state.py
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

# ── Constants ────────────────────────────────────────────────────────────────
REV_PER_RATING_POINT = 7.0        # $M per 18-49 rating point (Bravo tier, 2012)
SUB_RATE_PER_MONTH   = 0.35       # $/subscriber/month (distribution fee)
BASE_SUBS_M          = 45.0       # Million cable subscribers, 2012
CORD_CUT_RATE        = 0.03       # Annual subscriber erosion
DISTRIB_ESC_RATE     = 0.05       # Annual affiliate fee escalation (caps Y5)
CONTENT_COST_ESC     = 0.05       # Per-show renewal escalation
BUDGET_GROWTH_RATE   = 0.03       # Annual total budget growth
BASE_BUDGET          = 220.0      # $M year-1 budget (Bravo base; Oxygen uses network_info)
MKT_ROI_PER_M        = 0.015      # Rating lift per $1M marketing
MIN_MARKETING_PER_SHOW_M = 3.0    # Zach Schlessel's feedback: "$3M marketing minimum for show viability"
SVOD_SUB_LTV_MO      = 8.0        # SVOD ARPU $/month
SVOD_MARGIN          = 0.15       # SVOD contribution margin
AMORT_MONTHS_LINEAR  = 12
AMORT_MONTHS_SVOD    = 36
TRUE_CRIME_AMORT_MONTHS = 24   # Zach Schlessel's feedback: True Crime gets its own, longer curve

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

# ── Primetime scheduling grid ───────────────────────────────────────────────────
# Real, teachable trade-off (2026-07-29, per user request): only 28 primetime
# slots exist (4 hours × 7 days), one show per slot, and slot quality genuinely
# moves the needle on that show's rating for the year — so a team can't just
# stack every show into "the best slot," and leaving a cash cow in a weak slot
# has a real cost. Hour weighting reuses HOURLY_INDEX (already calibrated,
# already peaks 8–10pm) rather than inventing a second set of numbers.
PRIMETIME_DAYS  = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
PRIMETIME_HOURS = ["7PM","8PM","9PM","10PM"]

# Real TV-scheduling convention: Tue/Wed/Thu are the strongest primetime
# nights; Friday and Saturday are the industry's well-known "death slot"
# nights (lowest live viewership — networks have avoided scheduling
# original tentpole content there for decades); Sunday sits in between
# (strong for broadcast/sports, softer for cable originals); Monday is
# solid but competes with appointment programming elsewhere.
DAY_OF_WEEK_MULT = {
    "Mon": 0.90, "Tue": 1.00, "Wed": 1.00, "Thu": 0.98,
    "Fri": 0.70, "Sat": 0.65, "Sun": 0.85,
}

# The raw day×hour product is compressed into this band before it touches
# rating, so a bad slot genuinely costs a show real revenue (a real
# trade-off, not decoration) without being able to single-handedly blow
# through a level's OCF-margin pass threshold the way an uncapped swing
# could. +/-15% is a deliberately real stake, sized against the existing
# +/-7% seeded rating variance in pages/simulation.py::_compute_year — a
# scheduling call matters at least as much as the luck draw, since it's a
# decision the student actually controls.
SLOT_MULT_FLOOR    = 0.85
SLOT_MULT_CEILING  = 1.15


def slot_rating_multiplier(day: str, hour: str) -> float:
    """Rating multiplier for a show placed in a given primetime (day, hour)
    slot. A show with no slot assigned gets the neutral 1.0 baseline —
    scheduling can only help or hurt relative to that, same "deliberate
    zero-effect baseline" pattern as movie_models.py's New IP concept
    type, so every show's original calibrated numbers stay intact until a
    student actually makes a scheduling choice."""
    hour_mult = HOURLY_INDEX[HOUR_LABELS.index(hour.lower())]
    day_mult  = DAY_OF_WEEK_MULT[day]
    raw       = hour_mult * day_mult

    all_raw = [HOURLY_INDEX[HOUR_LABELS.index(h.lower())] * DAY_OF_WEEK_MULT[d]
               for d in PRIMETIME_DAYS for h in PRIMETIME_HOURS]
    raw_min, raw_max = min(all_raw), max(all_raw)

    frac = (raw - raw_min) / (raw_max - raw_min) if raw_max > raw_min else 1.0
    return SLOT_MULT_FLOOR + (SLOT_MULT_CEILING - SLOT_MULT_FLOOR) * frac


# ── Show dataclass ────────────────────────────────────────────────────────────
@dataclass
class Show:
    id: int
    name: str
    genre: str
    episodes: int
    ep_cost_k: float          # Cost per episode in $K
    rating: float             # Projected 18-49 rating
    ip_score: int             # 0-100 franchise value score
    air_month: int            # Month premiere airs (1-12)
    network: str = "Bravo"
    status: str = "Active"
    slot_day: Optional[str]  = None   # Primetime day assignment (PRIMETIME_DAYS), None = unassigned
    slot_hour: Optional[str] = None   # Primetime hour assignment (PRIMETIME_HOURS), None = unassigned

    def schedule_multiplier(self) -> float:
        """1.0 (neutral) until a student actually assigns a primetime slot —
        see slot_rating_multiplier() for the real trade-off math."""
        if not self.slot_day or not self.slot_hour:
            return 1.0
        return slot_rating_multiplier(self.slot_day, self.slot_hour)

    def effective_amort_months(self) -> int:
        """Amortization window — genre-based for linear content (Zach
        Schlessel's feedback, 2026-07-27: True Crime gets a longer curve
        than everything else, regardless of which linear network airs it —
        replaces the old network-based split, Oxygen=36mo/Bravo=12mo).
        Peacock/SVOD content keeps a uniform 36-month window: that's a
        distinct subscription-content accounting convention (matches
        AMORT_MONTHS_SVOD, the same constant Day 1's greenlight SVOD path
        uses), not a genre distinction, so it doesn't participate in the
        True-Crime split."""
        if self.network == "Peacock":
            return AMORT_MONTHS_SVOD
        return TRUE_CRIME_AMORT_MONTHS if self.genre == "True Crime" else AMORT_MONTHS_LINEAR

    def total_cost(self, year: int = 1) -> float:
        """Full production cost for the season in $M, with 5% annual escalation."""
        esc = (1 + CONTENT_COST_ESC) ** (year - 1)
        return self.ep_cost_k * self.episodes / 1000 * esc

    def annual_amort_expense(self, year: int = 1) -> float:
        """Annual P&L expense: production cost spread over the amortization period."""
        return self.total_cost(year) * 12 / self.effective_amort_months()

    def monthly_amort(self, year: int = 1) -> float:
        return self.total_cost(year) / self.effective_amort_months()

    def ad_revenue(self, year: int = 1, mkt_boost_m: float = 0.0) -> float:
        """Ad revenue in $M for a season. Folds in the primetime scheduling
        multiplier (1.0/neutral until a slot is actually assigned) so a
        student's day/hour choice is a real financial consequence for this
        season, not just a display-only grid."""
        mkt_lift   = 1 + mkt_boost_m * MKT_ROI_PER_M
        cord_decay = (1 - CORD_CUT_RATE) ** (year - 1)
        return (self.rating * REV_PER_RATING_POINT * mkt_lift * cord_decay
                * self.schedule_multiplier())

    def ocf(self, year: int = 1, mkt_boost_m: float = 0.0) -> float:
        return self.ad_revenue(year, mkt_boost_m) - self.annual_amort_expense(year)

    def roi(self, year: int = 1, mkt_boost_m: float = 0.0) -> float:
        cost = self.annual_amort_expense(year)
        return (self.ocf(year, mkt_boost_m) / cost * 100) if cost else 0.0

    def renewal_cost(self, year: int = 1) -> float:
        """Annual amort expense if renewed for the following year."""
        return self.annual_amort_expense(year + 1)

    def projected_rating(self, year: int = 1) -> float:
        """IP matures over time — ratings drift based on ip_score."""
        maturation = 1 + (self.ip_score / 100) * 0.06 - 0.02
        return self.rating * (maturation ** (year - 1))

    def cash_months(self, air_month: int, episodes: int) -> list[int]:
        """Which calendar months incur amortization cost (0-indexed)."""
        seasons_months = int(np.ceil(episodes / 2))
        return [(air_month - 1 + i) % 12 for i in range(seasons_months)]

    def premiere_day_analysis(self, launch_day: int, ad_rev_m: float) -> dict:
        monthly_cost  = self.monthly_amort()
        days_in_month = 31
        revenue_days  = days_in_month - launch_day + 1
        daily_rev     = ad_rev_m / 365
        march_rev     = daily_rev * revenue_days
        net           = march_rev - monthly_cost
        return {
            "launch_day":    launch_day,
            "monthly_cost":  monthly_cost,
            "revenue_days":  revenue_days,
            "march_rev":     march_rev,
            "net_position":  net,
        }


# ── Portfolio-level helpers ───────────────────────────────────────────────────
def portfolio_cost(shows: list[Show], year: int) -> float:
    return sum(s.annual_amort_expense(year) for s in shows)

def portfolio_ad_rev(shows: list[Show], year: int, mkt_total_m: float) -> float:
    per_show = mkt_total_m / max(len(shows), 1)
    return sum(s.ad_revenue(year, per_show) for s in shows)

def annual_budget(year: int) -> float:
    return BASE_BUDGET * (1 + BUDGET_GROWTH_RATE) ** (year - 1)

def cable_subs(year: int) -> float:
    return BASE_SUBS_M * (1 - CORD_CUT_RATE) ** (year - 1)

def distribution_revenue(year: int) -> float:
    """Distribution (affiliate) revenue in $M. subs in millions * $/mo * 12 months."""
    subs = cable_subs(year)
    esc  = min(1 + DISTRIB_ESC_RATE * (year - 1), 1.25)
    return subs * SUB_RATE_PER_MONTH * 12 * esc

def portfolio_ocf(shows: list[Show], year: int, mkt_m: float, ga_pct: float = 0.06) -> float:
    rev  = portfolio_ad_rev(shows, year, mkt_m) + distribution_revenue(year)
    cost = portfolio_cost(shows, year)
    ga   = rev * ga_pct
    return rev - cost - mkt_m - ga

def phase_label(year: int) -> str:
    if year <= 3:  return "Phase 1 — Oxygen"
    if year <= 7:  return "Phase 2 — Oxygen + Bravo"
    return "Phase 3 — Full Portfolio"

def renewal_decision(show: Show, year: int, mkt_boost: float) -> str:
    r = show.roi(year, mkt_boost)
    if r > 20: return "✅ Renew"
    if r > 0:  return "⚠️ Watch"
    return "❌ Cancel"


def performance_linked_growth(margin: float, threshold: float) -> float:
    """Multiplier applied to next year's budget based on this year's OCF
    margin vs. the level's pass threshold — replaces a flat annual growth
    rate with Zach Schlessel's (NBCUniversal) "good year = more budget, poor
    year = a cut" feedback (see DESIGN_NOTES.md). Single source of truth for
    both the real budget mechanic (pages/simulation.py) and Renewal's
    forward-looking estimate (pages/renewal.py)."""
    if margin >= threshold:
        return 1.08
    elif margin >= 0:
        return 1.03
    else:
        return 0.94


def preview_show_variance(team_name: str, year: int, shows: list, target_id: int) -> float:
    """Replicates the exact seeded RNG sequence pages/simulation.py's
    _compute_year() will use for `year`, returning the variance draw for
    `target_id` — a genuine preview of the actual upcoming outcome, not a
    decorative random number. Read-only: does not consume or advance any
    real game state, safe to call repeatedly. Powers the paid Research
    feature in pages/renewal.py.

    `shows` must be in the same order render() builds it in (oxygen + bravo
    + peacock, as applicable) — draws are consumed sequentially, one per
    show, same as the real computation."""
    seed = (abs(hash(team_name)) + year * 1337) % (2 ** 31)
    rng  = np.random.default_rng(seed)
    for s in shows:
        v = float(rng.uniform(0.93, 1.08))
        if s.id == target_id:
            return v
    return 1.0


def variance_to_stars(v: float) -> int:
    """Maps a [0.93, 1.08] variance draw to a 1-5 star research rating —
    Zach Schlessel's feedback: "1 star = 30% decline, 5 star = 10% growth"
    (here scaled to this engine's actual ±7%-ish variance band, not his
    example numbers verbatim, since our variance range is narrower)."""
    frac = (v - 0.93) / (1.08 - 0.93)
    return min(5, max(1, int(frac * 5) + 1))


# ── Regional / demographic research signal ──────────────────────────────────
# Zach Schlessel's feedback, added 2026-07-27: research should sometimes
# also reveal which region a show may play well in, with a basic illustrative
# demo profile (age, household income) — not a full market-research report,
# and deliberately only a few curated regions, never all of them. Fully
# automated: seeded per team+show+year, nothing hand-authored per show.
# Seeded independently of preview_show_variance() above (its own hash
# offset) so the regional signal is uncorrelated with the numeric rating
# draw — same reasoning as Day 2's critical-reception draw being
# independent of box office (see utils/movie_models.py).
REGIONS = {
    "Northeast US":  {"median_age": 41, "household_income_k": 78, "affinity": ["True Crime", "Drama", "Talk"]},
    "Southeast US":  {"median_age": 38, "household_income_k": 58, "affinity": ["Reality", "Competition", "True Crime"]},
    "West Coast US": {"median_age": 37, "household_income_k": 84, "affinity": ["Scripted", "Competition", "Comedy"]},
    "UK/Ireland":    {"median_age": 40, "household_income_k": 62, "affinity": ["True Crime", "Talk", "Drama"]},
    "Latin America": {"median_age": 33, "household_income_k": 34, "affinity": ["Reality", "Competition", "Comedy"]},
    "APAC":          {"median_age": 35, "household_income_k": 46, "affinity": ["Scripted", "Reality", "Drama"]},
}
REGIONAL_SIGNAL_CHANCE  = 0.5   # only sometimes reveals a regional signal, not every research buy
REGIONS_PER_SIGNAL_MAX  = 2     # 1-2 regions max, deliberately kept small


# ── Genre demo profile ────────────────────────────────────────────────────────
# A brief, always-visible "who actually watches this" line for the Renewal
# matrix — deliberately static/illustrative per genre (not seeded or randomized
# like REGIONS above, which is a paid-Research bonus signal). The point is a
# quick teaching moment that ad pricing runs on a flat 18-49 rating point
# (see REV_PER_RATING_POINT) even though real audiences skew older/younger
# and male/female differently by genre — nothing deeper than that.
GENRE_DEMOS = {
    "True Crime":  {"age": "25-54", "gender": "Skews Female", "reach": "National (US)"},
    "Reality":     {"age": "18-49", "gender": "Skews Female", "reach": "National (US)"},
    "Competition": {"age": "18-49", "gender": "Balanced",     "reach": "National (US)"},
    "Talk":        {"age": "35-64", "gender": "Skews Female", "reach": "National (US)"},
    "Scripted":    {"age": "18-49", "gender": "Balanced",     "reach": "Global"},
    "Drama":       {"age": "25-54", "gender": "Balanced",     "reach": "Global"},
}
GENRE_DEMO_DEFAULT = {"age": "18-49", "gender": "Balanced", "reach": "National (US)"}


def genre_demo(genre: str) -> dict:
    return GENRE_DEMOS.get(genre, GENRE_DEMO_DEFAULT)


# ── Production-risk event ────────────────────────────────────────────────────
# Zach Schlessel's feedback: "Shows can fail for legitimate reasons (talent
# departure, poor script, etc.)" — a real, independent risk axis from the
# numeric rating variance above, same reasoning as Day 2's critical
# reception being drawn independently of box office (see
# utils/movie_models.py). Only applies to shows the student is actively
# running this year (not ones already cancelled) — see
# pages/simulation.py::_compute_year.
PRODUCTION_RISK_CHANCE  = 0.04   # ~4% per show per year — rare, but real
PRODUCTION_RISK_REASONS = [
    "Lead talent departed mid-production",
    "Scripts fell apart in the writers' room",
    "A key creative left for a competing project",
    "Post-production delays blew the release window",
    "A budget dispute halted production",
]


def draw_production_risk_event(team_name: str, year: int, show_id: int) -> Optional[str]:
    """Rare, independent draw — seeded on its own hash offset so it never
    perturbs the rating-variance RNG sequence preview_show_variance()
    replicates for the Research feature. Returns None almost all the time;
    when it doesn't, the reason string is what actually happened, not a
    generic "bad year" label."""
    seed = (abs(hash(team_name)) + show_id * 8191 + year * 613) % (2 ** 31)
    rng  = np.random.default_rng(seed)
    if rng.random() > PRODUCTION_RISK_CHANCE:
        return None
    return PRODUCTION_RISK_REASONS[int(rng.integers(0, len(PRODUCTION_RISK_REASONS)))]


# ── Mid-year emergency budget shift ──────────────────────────────────────────
# One of Zach Schlessel's brief's own "Open Simulation Decisions," never
# actually answered until now: "Should budget constraints shift mid-year
# (emergency cancellations)?" Implemented as a rare, automated, network-
# level shock (not per-show — corporate belt-tightening hits the whole
# level's budget, not one show at a time).
EMERGENCY_BUDGET_CHANCE     = 0.15          # per team+year
EMERGENCY_BUDGET_CUT_RANGE  = (0.10, 0.25)  # 10-25% cut when it fires


def draw_emergency_budget_shock(team_name: str, year: int) -> Optional[float]:
    """Returns None most years, or the fraction of this year's budget
    that's been cut (e.g. 0.15 = a 15% cut) when it fires. Seeded on its
    own hash offset, drawn once per team+year (network-level event, not
    per-show)."""
    seed = (abs(hash(team_name)) + year * 5303 + 17) % (2 ** 31)
    rng  = np.random.default_rng(seed)
    if rng.random() > EMERGENCY_BUDGET_CHANCE:
        return None
    lo, hi = EMERGENCY_BUDGET_CUT_RANGE
    return float(rng.uniform(lo, hi))


def preview_regional_signal(team_name: str, year: int, show: "Show") -> Optional[list[dict]]:
    """Sometimes reveals 1-2 regions (of REGIONS' small curated set) this
    show may play well in, each with an illustrative demo profile. Returns
    None most of the time (see REGIONAL_SIGNAL_CHANCE) — this is a bonus
    signal layered on top of the star rating, not guaranteed every time
    Research is purchased. Regions matching the show's genre are weighted
    more likely to surface ("strong" fit) but a non-matching region can
    still appear ("moderate" fit) — real audiences don't always follow the
    obvious genre lines."""
    seed = (abs(hash(team_name)) + show.id * 6151 + year * 271) % (2 ** 31)
    rng  = np.random.default_rng(seed)
    if rng.random() > REGIONAL_SIGNAL_CHANCE:
        return None

    names   = list(REGIONS.keys())
    weights = np.array([3.0 if show.genre in REGIONS[n]["affinity"] else 1.0 for n in names])
    weights = weights / weights.sum()
    n_pick  = min(REGIONS_PER_SIGNAL_MAX, len(names))
    chosen  = rng.choice(len(names), size=n_pick, replace=False, p=weights)

    return [
        {
            "region": names[i],
            "median_age": REGIONS[names[i]]["median_age"],
            "household_income_k": REGIONS[names[i]]["household_income_k"],
            "fit": "strong" if show.genre in REGIONS[names[i]]["affinity"] else "moderate",
        }
        for i in chosen
    ]


# ── Green Light model ─────────────────────────────────────────────────────────
def greenlight_linear(episodes: int, ep_cost_k: float, rating: float,
                      mkt_m: float, year: int) -> dict:
    cost     = episodes * ep_cost_k / 1000
    mkt_lift = 1 + mkt_m * MKT_ROI_PER_M
    decay    = (1 - CORD_CUT_RATE) ** (year - 1)
    rev      = rating * REV_PER_RATING_POINT * mkt_lift * decay
    ocf      = rev - cost - mkt_m
    roi      = (ocf / cost * 100) if cost else 0
    payback  = "< 1 season" if ocf > 0 else "> 3 seasons"
    return dict(cost=cost, revenue=rev, ocf=ocf, roi=roi,
                payback=payback, amort_months=AMORT_MONTHS_LINEAR)

def greenlight_svod(episodes: int, ep_cost_k: float, rating: float,
                    appeal: int, mkt_m: float, year: int) -> dict:
    cost       = episodes * ep_cost_k / 1000
    mkt_lift   = 1 + mkt_m * MKT_ROI_PER_M
    sub_lift   = rating * 0.3 * (appeal / 100) * mkt_lift
    ltv_3yr    = sub_lift * SVOD_SUB_LTV_MO * 12 * SVOD_MARGIN * 3
    rev_y1     = ltv_3yr / 3
    ocf        = rev_y1 - cost - mkt_m
    roi        = (ocf / cost * 100) if cost else 0
    engagement = rating * (appeal / 100) * 0.6
    return dict(cost=cost, revenue=rev_y1, ltv_3yr=ltv_3yr, ocf=ocf,
                roi=roi, sub_lift=sub_lift, engagement=engagement,
                amort_months=AMORT_MONTHS_SVOD)

def ltv_curve(linear: dict, svod: dict, months: int = 36) -> pd.DataFrame:
    rows = []
    for m in range(1, months + 1):
        lin_cumul  = linear["revenue"] / 12 * m
        svod_cumul = svod["ltv_3yr"] / 36 * m
        rows.append({"Month": m, "Linear (cumul.)": lin_cumul,
                     "SVOD LTV (cumul.)": svod_cumul})
    return pd.DataFrame(rows)


# ── 10-year simulation ────────────────────────────────────────────────────────
def ten_year_sim(oxygen: list[Show], bravo: list[Show],
                 mkt_m: float, ga_pct: float = 0.06) -> pd.DataFrame:
    """Oxygen launches Y1; Bravo added Y4; full portfolio Y8+."""
    rows = []
    for y in range(1, 11):
        shows = oxygen[:] + (bravo if y >= 4 else [])
        ad    = portfolio_ad_rev(shows, y, mkt_m)
        dist  = distribution_revenue(y)
        cost  = portfolio_cost(shows, y)
        ga    = (ad + dist) * ga_pct
        ocf   = ad + dist - cost - mkt_m - ga
        rows.append({
            "Year":              y,
            "Calendar Year":     2011 + y,
            "Ad Revenue":        round(ad, 2),
            "Distribution Rev":  round(dist, 2),
            "Total Revenue":     round(ad + dist, 2),
            "Content Cost":      round(cost, 2),
            "Marketing":         round(mkt_m, 2),
            "G&A":               round(ga, 2),
            "OCF":               round(ocf, 2),
            "Cable Subs (M)":    round(cable_subs(y), 2),
            "Phase":             phase_label(y),
            "Active Shows":      len(shows),
        })
    return pd.DataFrame(rows)


# ── Hourly revenue index ──────────────────────────────────────────────────────
HOURLY_INDEX = [
    0.05,0.03,0.02,0.02,0.03,0.05,  # 12–6am
    0.12,0.20,0.25,0.30,0.35,0.40,  # 6am–12pm
    0.50,0.55,0.60,0.65,0.70,0.80,  # 12–6pm
    0.85,0.90,1.00,0.95,0.80,0.60,  # 6pm–12am (peak 8–10pm)
]
HOUR_LABELS = [
    "12am","1am","2am","3am","4am","5am",
    "6am","7am","8am","9am","10am","11am",
    "12pm","1pm","2pm","3pm","4pm","5pm",
    "6pm","7pm","8pm","9pm","10pm","11pm",
]
