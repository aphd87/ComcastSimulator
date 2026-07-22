"""
CableOS Day 2 — Movie/Theatrical financial engine ("Universal Pictures")
All monetary values in $M unless noted. Mirrors utils/models.py's structure
and conventions, but the underlying economics are deliberately different —
see DESIGN_NOTES.md's "Day 2" section for the full rationale:

  - Both production budget (P) and P&A/marketing spend (M) are cash out
    *before* any revenue visibility — no amortization curve softens this
    the way Day 1's Show.annual_amort_expense() does.
  - Revenue arrives as a windowed waterfall (domestic box office ->
    international -> PVOD -> Peacock streaming -> long-tail), not a smooth
    monthly stream.
  - The graded metric is risk-adjusted NPV, not an OCF margin — a single
    concentrated bet doesn't have a "margin," it has a return on capital
    at risk under uncertainty.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ── Constants ────────────────────────────────────────────────────────────────
EXHIBITOR_SPLIT      = 0.52   # studio's share of domestic box office (rentals), 2012-era average
COST_OF_CAPITAL       = 0.11   # annual discount rate for NPV — studio cost-of-capital proxy
PVOD_STUDIO_SHARE     = 0.80   # studio keeps ~80% of a PVOD transaction (vs. ~52% theatrical split)
PVOD_PRICE            = 19.99
SVOD_SUB_LTV_MO       = 8.0    # matches utils/models.py's SVOD_SUB_LTV_MO for consistency with Day 1
SVOD_MARGIN           = 0.15
BASE_PER_SCREEN_M     = 0.010  # $M ($10K) per screen — blockbuster-average opening baseline
STAR_POWER_BOOST_MAX  = 0.30   # max star power (100) adds up to +30% to opening, not a multiplier stack
MKT_LIFT_PER_M        = 0.006  # opening-weekend awareness lift per $1M P&A — gentle on purpose:
                                # this stacks with star power on the same opening-weekend number,
                                # so both together should move it moderately, not compound explosively
BASE_WINDOW_DAYS      = 90     # 2012-era theatrical exclusivity norm
WINDOW_SHRINK_PER_CYCLE_DAYS = 15   # real-world post-2012 compression, applied per cycle (1->2->3)
CYCLES_TOTAL          = 3
YEARS_PER_CYCLE        = 2

GENRES = ["Action/Tentpole", "Sci-Fi/Fantasy", "Animated", "Horror", "Comedy", "Drama", "Awards/Prestige"]

# International box-office multiplier on domestic gross — genre-dependent,
# tentpoles travel much further internationally than awards-season dramas.
GENRE_INTL_MULT = {
    "Action/Tentpole":  2.3, "Sci-Fi/Fantasy": 2.1, "Animated": 1.9,
    "Horror": 1.3, "Comedy": 1.1, "Drama": 1.0, "Awards/Prestige": 0.8,
}

# How well a genre converts theatrical awareness into Peacock subscriber
# value (0-100) — mirrors Day 1 greenlight's "Genre Appeal Score (SVOD)".
GENRE_SVOD_APPEAL = {
    "Action/Tentpole": 78, "Sci-Fi/Fantasy": 85, "Animated": 90,
    "Horror": 72, "Comedy": 62, "Drama": 58, "Awards/Prestige": 50,
}

RELEASE_STRATEGIES = ["wide_theatrical", "platform", "day_and_date"]

# Bull/base/bear multiplier on the box-office "multiplier" (opening weekend
# -> total domestic run) — this is deliberately where quality/word-of-mouth
# risk lives, not the opening weekend itself. Marketing buys an opening;
# it can't buy legs. See DESIGN_NOTES.md "Variance is graded, not hidden."
# This is the *baseline* spread — actual per-genre bounds are computed by
# genre_scenario_multipliers() below, since variance itself is genre-
# dependent (a horror movie can wildly over/underperform its budget in a
# way a franchise tentpole rarely does; an awards drama's audience is
# narrower but more predictable). Kept as a public constant since tests and
# UI code reference the un-adjusted baseline directly.
SCENARIO_MULTIPLIERS = {"bear": 1.8, "base": 2.8, "bull": 4.2}

# Widens (>1.0) or narrows (<1.0) the bear/bull distance from base, per
# genre — applied symmetrically around the shared base case so "base" stays
# comparable across genres and only the *risk band* changes. Horror is the
# textbook high-variance genre (huge outperformers on tiny budgets, but also
# routine flops); awards/prestige dramas have a narrower, more predictable
# specialty-audience range.
GENRE_VARIANCE_SPREAD = {
    "Horror": 1.6, "Comedy": 1.3, "Sci-Fi/Fantasy": 1.1, "Action/Tentpole": 1.0,
    "Animated": 0.9, "Drama": 0.85, "Awards/Prestige": 0.7,
}


def genre_scenario_multipliers(genre: str) -> dict:
    """Bear/base/bull box-office multipliers adjusted for this genre's
    variance profile. Base case is unchanged across genres; only how far
    bear/bull sit from it changes."""
    spread = GENRE_VARIANCE_SPREAD.get(genre, 1.0)
    base = SCENARIO_MULTIPLIERS["base"]
    bear = base - (base - SCENARIO_MULTIPLIERS["bear"]) * spread
    bull = base + (SCENARIO_MULTIPLIERS["bull"] - base) * spread
    return {"bear": max(bear, 0.5), "base": base, "bull": bull}


@dataclass
class MovieProject:
    title: str
    genre: str
    budget_m: float          # production budget (P)
    pa_spend_m: float        # marketing / P&A spend (M)
    star_power: int          # 0-100
    screens: int             # opening domestic screen count
    cycle: int                # 1, 2, or 3
    release_strategy: str = "wide_theatrical"   # "wide_theatrical" | "platform" | "day_and_date"

    def capital_at_risk(self) -> float:
        """Total upfront cash committed before any revenue arrives."""
        return self.budget_m + self.pa_spend_m

    def window_days(self) -> int:
        """Theatrical exclusivity window — shrinks each cycle, matching the
        real post-2012 compression (Universal/AMC 2020 deal, etc.)."""
        shrink = WINDOW_SHRINK_PER_CYCLE_DAYS * (self.cycle - 1)
        return max(BASE_WINDOW_DAYS - shrink, 17)   # 17 days = real 2021 post-COVID floor

    def awareness_lift(self) -> float:
        return 1 + self.pa_spend_m * MKT_LIFT_PER_M

    def opening_weekend(self) -> float:
        """$M opening weekend — scales with screen count off a fixed
        per-screen baseline, moderately boosted by star power and P&A
        awareness (additively, not stacked multiplicatively — real openings
        don't compound hype factors the way a naive product of boosts
        would). Platform releases open on far fewer screens by design
        (awards-qualifying rollout); day-and-date is unaffected here
        (theatrical suppression is applied to the multiplier instead, see
        cannibalization_factor)."""
        screens = self.screens if self.release_strategy != "platform" else min(self.screens, 600)
        star_boost = 1 + (self.star_power / 100) * STAR_POWER_BOOST_MAX
        return BASE_PER_SCREEN_M * screens * star_boost * self.awareness_lift()

    def cannibalization_factor(self) -> float:
        """Theatrical box-office suppression from the release-strategy
        decision. Day-and-date trades theatrical revenue for immediate
        streaming reach; platform trades opening scale for a slower,
        specialty rollout. Ballpark figures referenced against the real
        2021 WarnerMedia/HBO Max day-and-date experiment, not exact."""
        return {"wide_theatrical": 1.0, "platform": 0.85, "day_and_date": 0.55}[self.release_strategy]

    def domestic_box_office(self, scenario) -> float:
        """`scenario` is either a named key ("bear"/"base"/"bull", for
        planning-stage what-if previews — resolved against this project's
        own genre-adjusted variance band) or a raw float multiplier (for the
        actual drawn outcome — see draw_actual_multiplier below). Every
        other revenue/NPV/IRR method forwards its `scenario` argument here,
        so both call styles work everywhere without duplicating formulas."""
        if isinstance(scenario, str):
            multiplier = genre_scenario_multipliers(self.genre)[scenario]
        else:
            multiplier = scenario
        return self.opening_weekend() * multiplier * self.cannibalization_factor()

    def international_box_office(self, domestic_gross: float) -> float:
        return domestic_gross * GENRE_INTL_MULT.get(self.genre, 1.4)

    def theatrical_studio_net(self, scenario: str) -> float:
        """Studio's net rental after the exhibitor split, domestic + international."""
        dom = self.domestic_box_office(scenario)
        intl = self.international_box_office(dom)
        return (dom + intl) * EXHIBITOR_SPLIT

    def pvod_revenue(self, scenario: str) -> float:
        """Premium-rental window, sized off theatrical awareness — day-and-date
        skips this window (subscribers get it on Peacock instead, no separate
        rental transaction)."""
        if self.release_strategy == "day_and_date":
            return 0.0
        dom = self.domestic_box_office(scenario)
        est_transactions_m = (dom / PVOD_PRICE) * 0.35   # ~35% of theatrical audience converts to a rental
        return est_transactions_m * PVOD_PRICE * PVOD_STUDIO_SHARE

    def subscriber_value(self, scenario: str) -> float:
        """Dollarized Peacock subscriber-acquisition/retention value
        attributable to this title — same LTV logic Day 1 applies to SVOD
        shows (utils/models.py::SVOD_SUB_LTV_MO), scaled by a genre-specific
        streaming-conversion appeal score instead of a per-show rating."""
        dom = self.domestic_box_office(scenario)
        appeal = GENRE_SVOD_APPEAL.get(self.genre, 65) / 100
        sub_lift_m = (dom / 50.0) * appeal * 0.4
        if self.release_strategy == "day_and_date":
            sub_lift_m *= 1.7   # immediate/exclusive availability drives materially more sub value
        elif self.release_strategy == "platform":
            sub_lift_m *= 1.1
        return sub_lift_m * SVOD_SUB_LTV_MO * 12 * SVOD_MARGIN

    def library_longtail(self, scenario: str) -> float:
        """Small, deferred EST/library licensing tail — a fixed fraction of
        theatrical performance, arriving well after the windows above."""
        return self.theatrical_studio_net(scenario) * 0.06

    def windowed_cashflows(self, scenario: str) -> list[tuple[float, float]]:
        """Returns [(months_from_release, cash_m), ...] — the actual timing
        of each window's revenue, needed for discounting. Theatrical revenue
        is recognized at the midpoint of the run (~6 weeks in), not at
        release — a single cashflow parked at 2 weeks against an upfront
        cost produces an annualized IRR in the thousands of percent even for
        an ordinary hit, which isn't a meaningful number to hand a student."""
        theatrical = self.theatrical_studio_net(scenario)
        pvod       = self.pvod_revenue(scenario)
        sub_value  = self.subscriber_value(scenario)
        longtail   = self.library_longtail(scenario)
        window_mo  = self.window_days() / 30.0
        return [
            (1.5,                theatrical),               # midpoint of a ~12-week theatrical run
            (window_mo + 1.0,    pvod),                       # PVOD opens right after theatrical window
            (window_mo + 3.0,    sub_value),                  # Peacock exclusive window follows PVOD
            (24.0,               longtail),                   # library/EST tail, ~2 years out
        ]

    def npv(self, scenario: str, discount_rate: float = COST_OF_CAPITAL) -> float:
        cashflows = self.windowed_cashflows(scenario)
        pv = sum(cash / ((1 + discount_rate) ** (months / 12.0)) for months, cash in cashflows)
        return pv - self.capital_at_risk()

    def irr(self, scenario: str) -> Optional[float]:
        """Approximate IRR via a simple bisection search — front-loaded cost
        and back-loaded, windowed revenue means closed-form IRR isn't clean,
        and this doesn't need finance-library precision for a teaching sim.

        Returns None if capital is never recovered, float('inf') if the true
        IRR exceeds the search ceiling (a genuine outcome for a fast-payback
        hit, not a bug — display as ">500%"), otherwise the converged rate.
        Silently returning the search boundary as if it were a converged
        answer would look like a real number without being one."""
        cashflows = self.windowed_cashflows(scenario)
        total_in = sum(c for _, c in cashflows)
        if total_in <= self.capital_at_risk():
            return None   # never recovers capital — IRR undefined/negative-infinite

        def npv_at(rate: float) -> float:
            return sum(cash / ((1 + rate) ** (months / 12.0)) for months, cash in cashflows) - self.capital_at_risk()

        lo, hi = -0.5, 5.0
        if npv_at(hi) > 0:
            return float("inf")   # true IRR exceeds the 500% search ceiling
        mid = hi
        for _ in range(60):
            mid = (lo + hi) / 2
            if npv_at(mid) > 0:
                lo = mid
            else:
                hi = mid
        return mid

    def total_revenue(self, scenario: str) -> float:
        return sum(cash for _, cash in self.windowed_cashflows(scenario))


# ── Portfolio / scoring helpers ────────────────────────────────────────────────
def risk_adjusted_npv(project: MovieProject, bear_weight: float = 0.5) -> float:
    """Weighted toward the bear case — rewards risk-aware greenlighting, not
    just an optimistic expected value. See DESIGN_NOTES.md 'Variance is
    graded, not hidden.'"""
    bear = project.npv("bear")
    base = project.npv("base")
    return bear_weight * bear + (1 - bear_weight) * base


def capital_efficiency(project: MovieProject, scenario: str = "base") -> float:
    """Total lifetime revenue per marketing dollar — penalizes 'just spend
    the max' P&A strategies the way Day 1's greenlight marketing-ROI table
    does. A healthy real-world P&A efficiency benchmark is roughly 3-6x;
    this uses total revenue (not just opening box office) since P&A drives
    awareness that pays off across every window, not only the premiere."""
    if project.pa_spend_m <= 0:
        return 0.0
    return project.total_revenue(scenario) / project.pa_spend_m


def strategic_fit_score(project: MovieProject) -> float:
    """0-100: did the release-strategy choice actually maximize combined
    theatrical + streaming value net of cannibalization, vs. what a naive
    'always go wide theatrical' default would have produced?"""
    actual_npv = risk_adjusted_npv(project)
    baseline = MovieProject(**{**project.__dict__, "release_strategy": "wide_theatrical"})
    baseline_npv = risk_adjusted_npv(baseline)
    if baseline_npv == 0:
        return 50.0
    delta_pct = (actual_npv - baseline_npv) / abs(baseline_npv)
    return float(min(max(50 + delta_pct * 100, 0), 100))


def draw_actual_multiplier(team_name: str, cycle: int, genre: str = "Drama") -> float:
    """Resolves the real box-office multiplier at 'release' time — a
    continuous draw (not just one of 3 buckets), seeded off team+cycle the
    same way pages/simulation.py seeds its quarterly rating variance, so a
    given team's outcome for a given cycle is reproducible but not
    guessable in advance. Triangular distribution peaked at 'base', bounded
    by this genre's own bear/bull spread (see GENRE_VARIANCE_SPREAD) —
    smoother than a 3-way coin flip, and a horror movie's draw genuinely
    swings wider than an awards drama's."""
    bounds = genre_scenario_multipliers(genre)
    seed = (abs(hash(team_name)) + cycle * 4201) % (2 ** 31)
    rng = np.random.default_rng(seed)
    return float(rng.triangular(bounds["bear"], bounds["base"], bounds["bull"]))


def nearest_scenario_label(multiplier: float, genre: str = "Drama") -> str:
    """Which named scenario the actual drawn outcome reads closest to, for
    narrative framing in the results screen (e.g. 'landed close to your Base
    Case') — compared against this genre's own adjusted bounds, not the
    flat global ones."""
    bounds = genre_scenario_multipliers(genre)
    return min(bounds, key=lambda k: abs(bounds[k] - multiplier))


def compute_movie_score(projects: list[MovieProject]) -> dict:
    """Composite score across a slate of MovieProjects (one per cycle
    played so far). Weights mirror utils/game_state.py::compute_score's
    pattern but with Day 2's own components — see DESIGN_NOTES.md."""
    if not projects:
        return {"total": 0.0, "risk_adjusted_npv": 0.0, "capital_efficiency": 0.0,
                 "strategic_fit": 0.0, "passed": False}

    ra_npvs = [risk_adjusted_npv(p) for p in projects]
    avg_ra_npv = sum(ra_npvs) / len(ra_npvs)
    avg_cap_eff = sum(capital_efficiency(p) for p in projects) / len(projects)
    avg_fit = sum(strategic_fit_score(p) for p in projects) / len(projects)

    # Normalize to 0-100 like Day 1's compute_score does. Bands calibrated
    # against this engine's own realistic output range (see the smoke test
    # in DESIGN_NOTES.md's working notes) — a -$100M disaster scores 0, a
    # +$200M risk-adjusted hit scores 100; a 6x P&A revenue return is a
    # strong real-world benchmark, treated as the ceiling.
    s_npv = min(max((avg_ra_npv + 100) / 300 * 100, 0), 100)    # -$100M -> 0, +$200M -> 100
    s_eff = min(max(avg_cap_eff / 6 * 100, 0), 100)               # 6x total revenue / P&A = perfect
    s_fit = avg_fit

    total = s_npv * 0.55 + s_eff * 0.20 + s_fit * 0.25

    return {
        "total":              round(total, 1),
        "risk_adjusted_npv":  round(s_npv, 1),
        "capital_efficiency": round(s_eff, 1),
        "strategic_fit":      round(s_fit, 1),
        "avg_ra_npv_m":       round(avg_ra_npv, 2),
        "passed":             avg_ra_npv > 0,   # pass/fail gate: positive risk-adjusted NPV, not a fixed margin %
    }
