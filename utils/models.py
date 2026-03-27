"""
CableOS — Financial engine & data model
All monetary values in $M unless noted.
"""
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
BASE_BUDGET          = 220.0      # $M year-1 budget
MKT_ROI_PER_M        = 0.015      # Rating lift per $1M marketing
SVOD_SUB_LTV_MO      = 8.0        # SVOD ARPU $/month
SVOD_MARGIN          = 0.15       # SVOD contribution margin
AMORT_MONTHS_LINEAR  = 12
AMORT_MONTHS_SVOD    = 36

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
    status: str = "Active"    # Active / Cancelled / Development

    # Derived — computed at runtime
    def total_cost(self, year: int = 1) -> float:
        """Amortized season cost in $M, with 5% annual escalation."""
        esc = (1 + CONTENT_COST_ESC) ** (year - 1)
        return self.ep_cost_k * self.episodes / 1000 * esc

    def monthly_amort(self, year: int = 1) -> float:
        return self.total_cost(year) / AMORT_MONTHS_LINEAR

    def ad_revenue(self, year: int = 1, mkt_boost_m: float = 0.0) -> float:
        """Ad revenue in $M for a season."""
        mkt_lift   = 1 + mkt_boost_m * MKT_ROI_PER_M
        cord_decay = (1 - CORD_CUT_RATE) ** (year - 1)
        return self.rating * REV_PER_RATING_POINT * mkt_lift * cord_decay

    def ocf(self, year: int = 1, mkt_boost_m: float = 0.0) -> float:
        return self.ad_revenue(year, mkt_boost_m) - self.total_cost(year)

    def roi(self, year: int = 1, mkt_boost_m: float = 0.0) -> float:
        cost = self.total_cost(year)
        return (self.ocf(year, mkt_boost_m) / cost * 100) if cost else 0.0

    def renewal_cost(self, year: int = 1) -> float:
        """Cost if renewed for the following year."""
        return self.total_cost(year + 1)

    def projected_rating(self, year: int = 1) -> float:
        """IP matures over time — ratings drift based on ip_score."""
        maturation = 1 + (self.ip_score / 100) * 0.06 - 0.02
        return self.rating * (maturation ** (year - 1))

    def cash_months(self, air_month: int, episodes: int) -> list[int]:
        """Which calendar months incur amortization cost (0-indexed)."""
        seasons_months = int(np.ceil(episodes / 2))
        return [(air_month - 1 + i) % 12 for i in range(seasons_months)]

    def premiere_day_analysis(self, launch_day: int, ad_rev_m: float) -> dict:
        """
        Compare Mar 1 vs Mar 30 cash position.
        launch_day: 1 or 30
        """
        monthly_cost = self.monthly_amort()
        days_in_march = 31
        revenue_days  = days_in_march - launch_day + 1
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
    return sum(s.total_cost(year) for s in shows)

def portfolio_ad_rev(shows: list[Show], year: int, mkt_total_m: float) -> float:
    per_show = mkt_total_m / max(len(shows), 1)
    return sum(s.ad_revenue(year, per_show) for s in shows)

def annual_budget(year: int) -> float:
    return BASE_BUDGET * (1 + BUDGET_GROWTH_RATE) ** (year - 1)

def cable_subs(year: int) -> float:
    return BASE_SUBS_M * (1 - CORD_CUT_RATE) ** (year - 1)

def distribution_revenue(year: int) -> float:
    """Distribution (affiliate) revenue in $M. subs in millions * $/mo * 12 months."""
    subs   = cable_subs(year)
    esc    = min(1 + DISTRIB_ESC_RATE * (year - 1), 1.25)
    return subs * SUB_RATE_PER_MONTH * 12 * esc  # $M directly

def portfolio_ocf(shows: list[Show], year: int, mkt_m: float, ga_pct: float = 0.06) -> float:
    rev     = portfolio_ad_rev(shows, year, mkt_m) + distribution_revenue(year)
    cost    = portfolio_cost(shows, year)
    ga      = rev * ga_pct
    return rev - cost - mkt_m - ga

def phase_label(year: int) -> str:
    if year <= 4:  return "Phase 1 — Bravo"
    if year <= 8:  return "Phase 2 — Bravo + Oxygen"
    return "Phase 3 — Full Portfolio"

def renewal_decision(show: Show, year: int, mkt_boost: float) -> str:
    r = show.roi(year, mkt_boost)
    if r > 20: return "✅ Renew"
    if r > 0:  return "⚠️ Watch"
    return "❌ Cancel"


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
def ten_year_sim(bravo: list[Show], oxygen: list[Show],
                 mkt_m: float, ga_pct: float = 0.06) -> pd.DataFrame:
    rows = []
    for y in range(1, 11):
        shows = bravo + (oxygen if y >= 5 else [])
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
