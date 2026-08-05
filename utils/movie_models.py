"""
The Slate Day 2 — Movie/Theatrical financial engine ("Universal Pictures")
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
WINDOWING_UNLOCK_CYCLE = 3   # Zach Schlessel's brief: windowing is a "Year 3 Introduction" —
                              # cycles before this are wide-theatrical only, no strategy choice yet

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


# ── Concept Type — a second axis alongside Genre ────────────────────────────
# Franchise status + budget tier, layered on top of (not replacing) the
# genre-driven economics above — added 2026-07-27 per Zach Schlessel's
# "sequels/new-IP/kids/horror-indie" category rework ask. See
# DESIGN_NOTES.md's "Day 2" section for the reasoning behind each effect.
CONCEPT_TYPES = ["New IP", "Sequel", "Family/Kids", "Indie-Horror"]

# Sequel: built-in franchise awareness lifts the opening independent of star
# power/marketing — but the lift fades each successive cycle a team plays a
# sequel (real franchise fatigue), decaying toward a flat, modest bonus by
# cycle 3 rather than disappearing outright (a franchise never fully loses
# its built-in audience, it just stops being a novelty).
SEQUEL_OPENING_BONUS_BY_CYCLE = {1: 1.25, 2: 1.15, 3: 1.05}

# New IP: the neutral baseline — no built-in awareness bonus (unlike
# Sequel) and no long-tail bonus (unlike Family/Kids), so it carries zero
# adjustment of its own. That absence *is* the "leans harder on marketing"
# story: relative to Sequel's boosted opening, New IP has to earn every
# dollar of awareness through P&A rather than starting from a franchise
# head start. Also means every project built before this feature existed
# (default concept_type) keeps its exact original calibrated economics.

# Family/Kids: softer opening (family audiences build over weeks, not a
# single weekend) but a materially stronger long-tail — the real "vault"
# effect of family content's shelf life.
KIDS_OPENING_MULT  = 0.85
KIDS_LONGTAIL_MULT = 1.6

# Indie-Horror: budget-capped by design (that's what makes it "indie" — see
# INDIE_HORROR_BUDGET_CAP_M, enforced in the UI), and variance widens
# further on top of Horror-the-genre's already-wide spread — huge
# outperformers on tiny budgets are the entire economic case for the
# category. The model assumes the cap is respected; it doesn't enforce it.
INDIE_HORROR_BUDGET_CAP_M  = 25.0
INDIE_HORROR_VARIANCE_MULT = 1.3


def scenario_multipliers_for(genre: str, concept_type: str = "New IP") -> dict:
    """Bear/base/bull box-office multipliers adjusted for genre AND concept
    type. Concept type only ever widens/narrows further on top of the
    genre-level spread from genre_scenario_multipliers() — Indie-Horror is
    the only concept type that currently changes variance; everything else
    passes the genre bounds through unchanged."""
    bounds = genre_scenario_multipliers(genre)
    if concept_type != "Indie-Horror":
        return bounds
    base = bounds["base"]
    bear = base - (base - bounds["bear"]) * INDIE_HORROR_VARIANCE_MULT
    bull = base + (bounds["bull"] - base) * INDIE_HORROR_VARIANCE_MULT
    return {"bear": max(bear, 0.3), "base": base, "bull": bull}


# ── Critical reception / awards season ─────────────────────────────────────────
# Deliberately a *separate* risk axis from box-office performance, drawn off
# its own seed — a movie can open huge and get panned (box office good,
# reception bad) or open modestly and find critical acclaim (box office
# thin, reception great). Modeling them as independent draws is the point:
# they're genuinely uncorrelated in the real industry, and treating them as
# one signal would hide that.
# (worst-case, expected, best-case) critical-reception score, 0-100.
CRITICAL_RECEPTION_BOUNDS = {
    "Awards/Prestige":  (35, 68, 95),
    "Drama":            (25, 55, 88),
    "Animated":         (25, 52, 85),
    "Sci-Fi/Fantasy":   (20, 48, 82),
    "Comedy":           (15, 42, 78),
    "Horror":           (10, 40, 85),   # widest swing of any genre — cult-classic potential
    "Action/Tentpole":  (15, 38, 72),
}
# Only these genres realistically compete in awards season — an action
# tentpole doesn't get a specialty For-Your-Consideration rerelease no
# matter how well it's reviewed.
AWARDS_ELIGIBLE_GENRES = {"Awards/Prestige", "Drama"}
AWARDS_CONTENDER_THRESHOLD = 72   # critical score needed to trigger the rerelease bump

# Oscar Win — 2026-08-04, per user request to surface awards outcomes
# students can track year over year (mirrors real Oscars: a nomination
# doesn't guarantee a win). Deliberately reuses the same already-drawn
# critical_score rather than adding a second RNG draw -- a higher bar on
# the same signal, not an independent coin flip, so a team that clearly
# outperformed critically is the one that wins, not luck on top of luck.
AWARDS_WIN_THRESHOLD = 88

# Theme park / merchandise / Universal licensing — Zach Schlessel's brief:
# "genre determines theme park eligibility." Only genres with the scale and
# durability to support a themed attraction or a real merchandise line
# qualify; an awards drama or a comedy doesn't get a ride or a toy line.
THEME_PARK_ELIGIBLE_GENRES = {"Action/Tentpole", "Sci-Fi/Fantasy", "Animated"}
THEME_PARK_REVENUE_RATE    = 0.03   # fraction of domestic box office


def draw_critical_reception(team_name: str, cycle: int, genre: str) -> float:
    """Continuous, seeded, reproducible-per-team-per-cycle draw — same
    mechanism as draw_actual_multiplier, but a different seed offset so the
    two draws move independently rather than in lockstep."""
    lo, mode, hi = CRITICAL_RECEPTION_BOUNDS.get(genre, (15, 40, 80))
    seed = (abs(hash(team_name)) + cycle * 7919 + 31) % (2 ** 31)
    rng = np.random.default_rng(seed)
    return float(rng.triangular(lo, mode, hi))


# ── Production Trouble — a real, independent creative/talent risk axis ──────
# 2026-08-03, per user request: mirrors utils/models.py's TV-side
# draw_production_risk_event (talent/creative departures, own independent
# seed, rare) but sized for a movie's one-shot economics. TV can zero a
# single show's revenue for a year and the other ~19 shows in the portfolio
# absorb it; a movie IS the whole bet for that cycle, so a full zero would
# wipe out the entire cycle rather than dent a portfolio. Modeled instead as
# a moderate haircut on the resolved box-office multiplier — a troubled
# production still ships, just weaker: lost buzz, a compressed marketing
# runway, reshoot-drained momentum going into release.
PRODUCTION_TROUBLE_CHANCE        = 0.05   # ~5% per movie per cycle — rare, but real
PRODUCTION_TROUBLE_HAIRCUT_RANGE = (0.60, 0.85)   # multiplies the drawn box-office multiplier down
PRODUCTION_TROUBLE_REASONS = [
    "Lead actor injury forced a costly production shutdown",
    "The director exited over creative differences mid-shoot",
    "Reshoots blew the schedule and delayed the release window",
    "A key VFX vendor collapsed mid-production",
    "A producer dispute stalled the project for weeks",
]


def draw_production_trouble(team_name: str, cycle: int) -> Optional[tuple[str, float]]:
    """Rare, independent draw (own seed offset — doesn't perturb
    draw_actual_multiplier's or draw_critical_reception's sequences).
    Returns None most of the time; when it fires, returns
    (reason, haircut_multiplier) where haircut_multiplier < 1.0 is meant to
    be applied to the already-drawn box-office multiplier before computing
    the cycle's actual outcome."""
    seed = (abs(hash(team_name)) + cycle * 5563 + 97) % (2 ** 31)
    rng = np.random.default_rng(seed)
    if rng.random() > PRODUCTION_TROUBLE_CHANCE:
        return None
    reason = PRODUCTION_TROUBLE_REASONS[int(rng.integers(0, len(PRODUCTION_TROUBLE_REASONS)))]
    lo, hi = PRODUCTION_TROUBLE_HAIRCUT_RANGE
    return reason, float(rng.uniform(lo, hi))


# ── Ancillary Markets Surprise — genuinely movie-industry-specific ──────────
# 2026-08-03, per user request ("is there randomness we can raise in movie
# industry that we can't elsewhere... windowing rentals and theme park
# stuff/merchandise"). TV/Streaming has no PVOD rental window and no theme
# park/merchandise line at all (utils/models.py has nothing analogous) — so
# unlike Production Trouble above (a movie-flavored version of a mechanic
# TV already has), this is a risk axis with literally no TV-side
# counterpart. Independent of both box-office performance and critical
# reception: a rental surge or a theme-park deal signing/falling-through is
# its own real-world story, not a downstream consequence of how the movie
# performed theatrically or reviewed. Can swing either direction, unlike
# Production Trouble's one-directional haircut.
ANCILLARY_SURPRISE_CHANCE = 0.12   # a bit more common than Production Trouble — lower stakes, not a crisis
ANCILLARY_SURPRISE_RANGE  = (0.60, 1.60)
ANCILLARY_SURPRISE_REASONS_UP = [
    "A surprise home-rental surge as word-of-mouth built after theatrical",
    "A theme park deal signed early, ahead of the usual licensing timeline",
    "A merchandise partner expanded the deal after strong early demand",
]
ANCILLARY_SURPRISE_REASONS_DOWN = [
    "PVOD demand came in soft as rental piracy ate into transactions",
    "A licensing partner delayed the theme park attraction rollout",
    "A merchandise deal fell through after a partner pulled out",
]


def draw_ancillary_surprise(team_name: str, cycle: int) -> Optional[tuple[str, float]]:
    """Rare, independent draw (own seed offset) affecting PVOD rental
    revenue and theme-park/merchandise value together — both are
    post-theatrical licensing/ancillary markets, distinct from the core
    theatrical performance. Returns None most of the time; when it fires,
    returns (reason, multiplier) where multiplier can be above or below 1.0."""
    seed = (abs(hash(team_name)) + cycle * 6229 + 149) % (2 ** 31)
    rng = np.random.default_rng(seed)
    if rng.random() > ANCILLARY_SURPRISE_CHANCE:
        return None
    lo, hi = ANCILLARY_SURPRISE_RANGE
    mult = float(rng.uniform(lo, hi))
    reasons = ANCILLARY_SURPRISE_REASONS_UP if mult >= 1.0 else ANCILLARY_SURPRISE_REASONS_DOWN
    reason = reasons[int(rng.integers(0, len(reasons)))]
    return reason, mult


# ── Talent Deals — Overall/First-Look Partnerships & Holding Deals ─────────
# 2026-08-04, per user request to build out talent-negotiation content from
# the Movie Business and Deal Mechanisms note, plus rival-studio competitive
# dynamics ("can you see how your choices impact rival studios?") -- mirrors
# utils/sports_models.py's seeded-rival-bidder precedent (real companies
# bidding against you for league rights), scoped down to talent scheduling.
#
# Partners are fictional, modeled on real archetypes (an action-forward
# producer-star collective, a prestige awards banner, a family-franchise
# banner, a horror specialist) rather than naming real individuals --
# distinct from Sports Rights' real company names or the Bravo/Oxygen/
# Peacock slates' real show titles, since a talent deal is inherently about
# an individual's persona/likeness, not a corporate brand or a title. Rival
# studio names are fictional for the same reason (a "rival beat you to a
# named real actor" framing would read as a claim about a real person).
TALENT_PARTNERS = {
    "meridian":   {"name": "Meridian Collective",  "specialty": "Action/Tentpole",
                    "overall_deal_cost_m": 25.0, "hold_cost_m": 4.0, "star_power_bonus": 15},
    "northbench": {"name": "Northbench Pictures",   "specialty": "Awards/Prestige",
                    "overall_deal_cost_m": 18.0, "hold_cost_m": 3.0, "critical_score_bonus": 8.0},
    "brightlane": {"name": "Brightlane Family",     "specialty": "Animated",
                    "overall_deal_cost_m": 15.0, "hold_cost_m": 2.5, "star_power_bonus": 10},
    "afterdark":  {"name": "Afterdark Studio",      "specialty": "Horror",
                    "overall_deal_cost_m": 10.0, "hold_cost_m": 2.0, "star_power_bonus": 8},
}

RIVAL_STUDIOS = ["Paragon Pictures", "Constellation Studios", "Anchor Bay Media", "Vantage Films"]
RIVAL_CLAIM_CHANCE  = 0.20   # chance a rival has already locked the talent's window when you try to hold it
HOLD_FORFEIT_CHANCE = 0.30   # chance a *successfully placed* hold still falls through by next cycle --
                              # "no guarantee the movie comes together in time" is the whole point of a hold
RIVAL_POACH_CHANCE  = 0.12   # per cycle, per unclaimed partner -- the cost of passing: a partner you
                              # could have signed doesn't just wait for you (per user request, 2026-08-04:
                              # "game theory should also come into movies that students pass on that may
                              # or may not be taken up by rival studios"). Once poached, permanently
                              # unavailable for the rest of the level -- real, not a warning shot.


def draw_rival_claim(team_name: str, cycle: int, partner_key: str) -> Optional[str]:
    """Resolved the instant a Holding Deal is placed -- a rival studio may
    have already locked up this partner's window before you got there.
    Seeded off (team, cycle, partner) so trying a different partner isn't
    correlated with a rival claim on the first one. Returns the rival's
    name if claimed, else None."""
    seed = (abs(hash(team_name)) + cycle * 8191 + abs(hash(partner_key)) % 4001 + 11) % (2 ** 31)
    rng = np.random.default_rng(seed)
    if rng.random() > RIVAL_CLAIM_CHANCE:
        return None
    return RIVAL_STUDIOS[int(rng.integers(0, len(RIVAL_STUDIOS)))]


def draw_hold_forfeit(team_name: str, cycle_placed: int, partner_key: str) -> Optional[str]:
    """Resolved at the START of the cycle *after* a hold was successfully
    placed (not rival-claimed) -- does the production actually come
    together in time? Own independent seed offset from draw_rival_claim, so
    clearing the rival-claim check doesn't correlate with clearing this
    one. Returns a forfeit reason if the hold falls through, else None."""
    seed = (abs(hash(team_name)) + cycle_placed * 5237 + abs(hash(partner_key)) % 4001 + 71) % (2 ** 31)
    rng = np.random.default_rng(seed)
    if rng.random() > HOLD_FORFEIT_CHANCE:
        return None
    reasons = [
        "The attached filmmaker exited over creative differences before the hold converted",
        "A scheduling conflict with another commitment made the window impossible to honor",
        "The project didn't clear financing in time and the hold lapsed",
        "Rewrites pushed past the held window and the talent moved on",
    ]
    return reasons[int(rng.integers(0, len(reasons)))]


def draw_rival_poach(team_name: str, partner_key: str, cycle: int) -> Optional[str]:
    """Per-(team, partner, cycle) chance a rival studio signs an EXCLUSIVE
    deal with a partner the team hasn't claimed by that cycle -- the actual
    game-theory answer: passing on a relationship isn't a neutral no-op,
    someone else can take it. Own independent seed offset from
    draw_rival_claim/draw_hold_forfeit. Callers should only roll this for
    partners not already claimed by the team (an already-claimed partner
    isn't up for grabs) and should treat a returned rival as permanent for
    the rest of the level, not re-rolled."""
    seed = (abs(hash(team_name)) + cycle * 3541 + abs(hash(partner_key)) % 4001 + 211) % (2 ** 31)
    rng = np.random.default_rng(seed)
    if rng.random() > RIVAL_POACH_CHANCE:
        return None
    return RIVAL_STUDIOS[int(rng.integers(0, len(RIVAL_STUDIOS)))]


# ── Financing Structure ──────────────────────────────────────────────────────
# 2026-08-04, per user request to build out the "raising funds" section of a
# Movie Business and Deal Mechanisms teaching note. self_finance is the
# original, unadjusted behavior every project used before this field
# existed (additive, not a replacement of the calibrated engine -- same
# posture as Concept Type). The other two are real, asymmetric trade-offs,
# not just discounts:
#   - presale: an international distributor advances part of the budget
#     before production even starts (the note's "bridging the gap"
#     framing) in exchange for owning those territories' box office
#     outright -- lower capital at risk now, capped international upside
#     later, which matters most for the wide-reach genres (GENRE_INTL_MULT).
#   - tax_incentive: a real, close-to-free cost reduction when available
#     (the note cites ~30% headline credits) -- deliberately NOT given an
#     artificial downside just to make three choices symmetric; the real
#     lesson is a studio should almost always take this when production
#     logistics allow it.
FINANCING_STRUCTURES = ["self_finance", "presale", "tax_incentive"]
PRESALE_ADVANCE_PCT       = 0.40   # fraction of production budget covered by the advance
PRESALE_INTL_RETAINED_PCT = 0.15   # studio's residual/overage share of the international b.o. it gave away
TAX_CREDIT_PCT            = 0.22   # net-of-discount effective credit (headline ~30%, but non-refundable
                                     # credits are commonly sold at a discount -- see the note)


# ── Exhibitor Split Negotiation ──────────────────────────────────────────────
# 2026-08-04, per the teaching note's exhibitor-relations section ("theaters
# prefer longer exclusive release windows, while studios aim to maximize the
# momentum... distributors typically receive 45-55% of ticket sales").
# "standard" reproduces the exact prior fixed EXHIBITOR_SPLIT/screens
# behavior every project used before this field existed. The other two are
# meant as a real, opposite-signed trade-off -- push harder on economics and
# exhibitors push back on placement, or vice versa.
#
# The screens multiplier is deliberately a SMALLER swing (±8%) than the
# split-rate swing (±11.5% relative) even though they're framed as
# opposite-and-equal in the UI copy -- caught during manual QA (2026-08-04):
# screens scale the box-office base (`dom`) that PVOD, subscriber value, and
# library longtail all derive from, while the split rate only touches
# theatrical net directly. An equal-magnitude screens swing therefore always
# swamped the split swing structurally (touches strictly more of total
# revenue), making "exhibitor_friendly" a near-dominant strategy regardless
# of project economics -- not a real choice. Verified via a manual sweep
# across a tentpole and an indie drama that ±8% keeps the spread modest
# (roughly ±5-7% NPV either direction from standard) without either
# alternative reading as an obvious win every time.
EXHIBITOR_POSTURES = ["standard", "aggressive", "exhibitor_friendly"]
EXHIBITOR_SPLIT_BY_POSTURE = {"standard": EXHIBITOR_SPLIT, "aggressive": 0.58, "exhibitor_friendly": 0.46}
EXHIBITOR_SCREENS_MULT_BY_POSTURE = {"standard": 1.0, "aggressive": 0.92, "exhibitor_friendly": 1.08}


# ── Pay-1 Window Licensing ───────────────────────────────────────────────────
# 2026-08-04, per the teaching note's Pay-1/Pay-2/Pay-3 windowing section: a
# studio can keep its post-theatrical SVOD window exclusive on its own
# platform, or license it to a rival platform for a flat, pre-negotiated fee
# instead -- real cash, known before release, in exchange for giving up the
# subscriber-value upside (and the strategic value of owning that
# relationship). "keep" reproduces prior behavior exactly. Doesn't apply to
# day_and_date releases -- that strategy already commits the title to
# Peacock exclusivity as its core premise; licensing the same window away
# would contradict the choice that was just made, so windowed_cashflows()
# below ignores pay1_licensing for day_and_date regardless of what's set.
PAY1_LICENSING_OPTIONS = ["keep", "license_out"]
PAY1_LICENSE_DISCOUNT  = 0.55   # flat fee as a fraction of BASE-case subscriber value -- a real
                                  # licensing deal is negotiated before release, not indexed to
                                  # how the movie actually performs


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
    concept_type: str = "New IP"                # "New IP" | "Sequel" | "Family/Kids" | "Indie-Horror"
    financing_structure: str = "self_finance"   # "self_finance" | "presale" | "tax_incentive"
    exhibitor_posture: str = "standard"         # "standard" | "aggressive" | "exhibitor_friendly"
    pay1_licensing: str = "keep"                 # "keep" | "license_out"

    def capital_at_risk(self) -> float:
        """Total upfront cash committed before any revenue arrives --
        reduced by financing_structure's chosen structure (see
        FINANCING_STRUCTURES above); self_finance is the unadjusted
        budget_m + pa_spend_m baseline."""
        if self.financing_structure == "presale":
            return self.budget_m * (1 - PRESALE_ADVANCE_PCT) + self.pa_spend_m
        if self.financing_structure == "tax_incentive":
            return self.budget_m * (1 - TAX_CREDIT_PCT) + self.pa_spend_m
        return self.budget_m + self.pa_spend_m

    def window_days(self) -> int:
        """Theatrical exclusivity window — shrinks each cycle, matching the
        real post-2012 compression (Universal/AMC 2020 deal, etc.)."""
        shrink = WINDOW_SHRINK_PER_CYCLE_DAYS * (self.cycle - 1)
        return max(BASE_WINDOW_DAYS - shrink, 17)   # 17 days = real 2021 post-COVID floor

    def awareness_lift(self) -> float:
        return 1 + self.pa_spend_m * MKT_LIFT_PER_M

    def concept_opening_boost(self) -> float:
        """Sequel/Family-Kids adjustment to opening intensity — see
        SEQUEL_OPENING_BONUS_BY_CYCLE and KIDS_OPENING_MULT. New IP and
        Indie-Horror carry no opening-weekend adjustment of their own
        (Indie-Horror's effect is on variance, not the base opening)."""
        if self.concept_type == "Sequel":
            return SEQUEL_OPENING_BONUS_BY_CYCLE.get(self.cycle, 1.05)
        if self.concept_type == "Family/Kids":
            return KIDS_OPENING_MULT
        return 1.0

    def opening_weekend(self) -> float:
        """$M opening weekend — scales with screen count off a fixed
        per-screen baseline, moderately boosted by star power and P&A
        awareness (additively, not stacked multiplicatively — real openings
        don't compound hype factors the way a naive product of boosts
        would). Platform releases open on far fewer screens by design
        (awards-qualifying rollout); day-and-date is unaffected here
        (theatrical suppression is applied to the multiplier instead, see
        cannibalization_factor). exhibitor_posture scales the EFFECTIVE
        screen count actually granted -- self.screens stays the student's
        raw requested number (still used for the "unrealistic screen count"
        warning check in the UI), while a harder negotiating posture nets
        fewer screens than asked for and a friendlier one nets more."""
        screens = self.screens if self.release_strategy != "platform" else min(self.screens, 600)
        screens *= EXHIBITOR_SCREENS_MULT_BY_POSTURE.get(self.exhibitor_posture, 1.0)
        star_boost = 1 + (self.star_power / 100) * STAR_POWER_BOOST_MAX
        return BASE_PER_SCREEN_M * screens * star_boost * self.concept_opening_boost() * self.awareness_lift()

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
            multiplier = scenario_multipliers_for(self.genre, self.concept_type)[scenario]
        else:
            multiplier = scenario
        return self.opening_weekend() * multiplier * self.cannibalization_factor()

    def international_box_office(self, domestic_gross: float) -> float:
        """International box office the studio itself keeps. Under a
        Territorial Pre-Sales financing structure, most of this was already
        sold away to the distributor who fronted the advance (see
        capital_at_risk()) -- the studio retains only a small residual/
        overage share (PRESALE_INTL_RETAINED_PCT), not the full territory."""
        intl = domestic_gross * GENRE_INTL_MULT.get(self.genre, 1.4)
        if self.financing_structure == "presale":
            return intl * PRESALE_INTL_RETAINED_PCT
        return intl

    def theatrical_studio_net(self, scenario: str) -> float:
        """Studio's net rental after the exhibitor split, domestic +
        international -- split rate depends on exhibitor_posture (see
        EXHIBITOR_SPLIT_BY_POSTURE); "standard" reproduces the original
        fixed EXHIBITOR_SPLIT exactly."""
        dom = self.domestic_box_office(scenario)
        intl = self.international_box_office(dom)
        split = EXHIBITOR_SPLIT_BY_POSTURE.get(self.exhibitor_posture, EXHIBITOR_SPLIT)
        return (dom + intl) * split

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

    def is_licensing_out(self) -> bool:
        """Whether the Pay-1 SVOD window is actually being licensed away
        this project -- day_and_date overrides pay1_licensing to False
        regardless of what's set, since that release strategy already
        commits the title to Peacock exclusivity as its core premise."""
        return self.pay1_licensing == "license_out" and self.release_strategy != "day_and_date"

    def pay1_license_fee(self) -> float:
        """Flat, pre-negotiated fee for licensing the Pay-1 SVOD window to
        a rival platform instead of keeping it on Peacock -- computed off
        the BASE case regardless of the actual resolved scenario (a real
        licensing deal is negotiated before release, not indexed to how the
        movie actually performs). 0.0 when not licensing out."""
        if not self.is_licensing_out():
            return 0.0
        return self.subscriber_value("base") * PAY1_LICENSE_DISCOUNT

    def library_longtail(self, scenario: str, critical_score: Optional[float] = None) -> float:
        """Small, deferred EST/library licensing tail — a fixed fraction of
        theatrical performance, arriving well after the windows above. When
        a critical_score is supplied (i.e. the outcome has actually been
        resolved — see draw_critical_reception), scales the tail 0.7x-1.8x:
        critical reception has real, measurable effect on a film's enduring
        library value, independent of how it did theatrically. Family/Kids
        content carries an extra long-tail multiplier — the real "vault"
        shelf-life effect (see KIDS_LONGTAIL_MULT)."""
        base = self.theatrical_studio_net(scenario) * 0.06
        if self.concept_type == "Family/Kids":
            base *= KIDS_LONGTAIL_MULT
        if critical_score is None:
            return base
        quality_mult = 0.7 + (critical_score / 100) * 1.1
        return base * quality_mult

    def theme_park_value(self, scenario) -> float:
        """Theme park attraction / merchandise / Universal licensing value —
        Zach Schlessel's brief: "theme park/merchandise opportunities,
        Universal licensing deals ('pay yourself' model)... genre
        determines theme park eligibility." Only genres with the cultural
        footprint and IP durability to support a themed attraction or a
        real merchandise line qualify (see THEME_PARK_ELIGIBLE_GENRES) — an
        awards drama doesn't get a ride. Sized off domestic box office as a
        rough proxy for how big the IP actually landed; zero for
        ineligible genres, not a smaller fraction — this is a real
        eligibility gate, not a soft discount."""
        if self.genre not in THEME_PARK_ELIGIBLE_GENRES:
            return 0.0
        return self.domestic_box_office(scenario) * THEME_PARK_REVENUE_RATE

    def awards_season_bump(self, scenario: str, critical_score: Optional[float] = None) -> float:
        """A limited theatrical rerelease during awards season (For-Your-
        Consideration campaigns, expanded runs after nominations) — only
        applies to awards-eligible genres (see AWARDS_ELIGIBLE_GENRES) whose
        critical reception clears AWARDS_CONTENDER_THRESHOLD. A real, if
        modest, extra revenue window that a merely well-reviewed action
        movie doesn't get access to, no matter how good its reviews are."""
        if critical_score is None or self.genre not in AWARDS_ELIGIBLE_GENRES:
            return 0.0
        if critical_score < AWARDS_CONTENDER_THRESHOLD:
            return 0.0
        strength = (critical_score - AWARDS_CONTENDER_THRESHOLD) / (100 - AWARDS_CONTENDER_THRESHOLD)
        return self.domestic_box_office(scenario) * 0.08 * strength

    def windowed_cashflows(self, scenario: str, critical_score: Optional[float] = None,
                            pvod_mult: float = 1.0, theme_park_mult: float = 1.0) -> list[tuple[float, float]]:
        """Returns [(months_from_release, cash_m), ...] — the actual timing
        of each window's revenue, needed for discounting. Theatrical revenue
        is recognized at the midpoint of the run (~6 weeks in), not at
        release — a single cashflow parked at 2 weeks against an upfront
        cost produces an annualized IRR in the thousands of percent even for
        an ordinary hit, which isn't a meaningful number to hand a student.

        critical_score is None during planning-stage bear/base/bull previews
        (a student genuinely can't know reviews in advance — including it
        there would leak information they shouldn't have yet) and only
        supplied once the outcome is actually resolved at Results.

        pvod_mult/theme_park_mult (added 2026-08-03, default 1.0 = no-op for
        every existing caller): apply draw_ancillary_surprise()'s resolved
        swing to just these two windows — PVOD and theme-park/merchandise
        are their own independent real-world story, not a downstream
        consequence of box-office or critical performance."""
        theatrical = self.theatrical_studio_net(scenario)
        pvod       = self.pvod_revenue(scenario) * pvod_mult
        longtail   = self.library_longtail(scenario, critical_score)
        bump       = self.awards_season_bump(scenario, critical_score)
        theme_park = self.theme_park_value(scenario) * theme_park_mult
        window_mo  = self.window_days() / 30.0
        if self.is_licensing_out():
            # A flat licensing fee, paid alongside PVOD -- faster and known
            # in advance, vs. owned subscriber value's later, performance-
            # exposed window below.
            sub_value       = self.pay1_license_fee()
            sub_value_month = window_mo + 1.0
        else:
            sub_value       = self.subscriber_value(scenario)
            sub_value_month = window_mo + 3.0   # Peacock exclusive window follows PVOD
        flows = [
            (1.5,                theatrical),               # midpoint of a ~12-week theatrical run
            (window_mo + 1.0,    pvod),                       # PVOD opens right after theatrical window
            (sub_value_month,    sub_value),
            (24.0,               longtail),                   # library/EST tail, ~2 years out
        ]
        if bump > 0:
            flows.append((11.0, bump))   # awards season (~Jan-Feb), roughly 11 months after release
        if theme_park > 0:
            flows.append((30.0, theme_park))   # attractions/merchandise take real time to develop and license
        return flows

    def npv(self, scenario: str, critical_score: Optional[float] = None,
            discount_rate: float = COST_OF_CAPITAL,
            pvod_mult: float = 1.0, theme_park_mult: float = 1.0) -> float:
        cashflows = self.windowed_cashflows(scenario, critical_score, pvod_mult, theme_park_mult)
        pv = sum(cash / ((1 + discount_rate) ** (months / 12.0)) for months, cash in cashflows)
        return pv - self.capital_at_risk()

    def irr(self, scenario: str, critical_score: Optional[float] = None,
            pvod_mult: float = 1.0, theme_park_mult: float = 1.0) -> Optional[float]:
        """Approximate IRR via a simple bisection search — front-loaded cost
        and back-loaded, windowed revenue means closed-form IRR isn't clean,
        and this doesn't need finance-library precision for a teaching sim.

        Returns None if capital is never recovered, float('inf') if the true
        IRR exceeds the search ceiling (a genuine outcome for a fast-payback
        hit, not a bug — display as ">500%"), otherwise the converged rate.
        Silently returning the search boundary as if it were a converged
        answer would look like a real number without being one."""
        cashflows = self.windowed_cashflows(scenario, critical_score, pvod_mult, theme_park_mult)
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

    def total_revenue(self, scenario: str, critical_score: Optional[float] = None,
                       pvod_mult: float = 1.0, theme_park_mult: float = 1.0) -> float:
        return sum(cash for _, cash in
                    self.windowed_cashflows(scenario, critical_score, pvod_mult, theme_park_mult))


# ── Deal Waterfall — Distribution & Participation ───────────────────────────
# 2026-08-04: windowed_cashflows()/total_revenue() already model WHERE money
# comes FROM (the theatrical->PVOD->Peacock->library waterfall); this models
# WHERE it goes once it arrives, per the teaching note's "Profits" section.
# The ordering below IS the lesson: gross participants (star talent) get
# paid off top-line revenue regardless of profitability, before the studio
# even recoups its own capital; net participants (the producer) only get
# paid out of whatever's left after recoupment. A "gross deal" can leave a
# studio with a thin or negative residual even on a nominal box-office win
# -- residual is deliberately not floored at zero, since that's real.
TALENT_GROSS_GUARANTEE_M   = 2.0    # lead-actor upfront guarantee -- the note's own example
TALENT_GROSS_PARTICIPATION = 0.10   # % of total revenue, above the guarantee
PRODUCER_NET_PARTICIPATION = 0.12   # % of net profit after recoupment, if any


def participation_waterfall(project: MovieProject, scenario, critical_score: Optional[float] = None,
                             pvod_mult: float = 1.0, theme_park_mult: float = 1.0) -> dict:
    """Distribution/participation breakdown for a resolved (or previewed)
    outcome. `scenario` follows the same named-string-or-raw-multiplier
    convention as MovieProject.total_revenue()."""
    revenue      = project.total_revenue(scenario, critical_score, pvod_mult, theme_park_mult)
    talent_take  = max(TALENT_GROSS_GUARANTEE_M, revenue * TALENT_GROSS_PARTICIPATION)
    after_talent = revenue - talent_take
    recoupment   = project.capital_at_risk()
    after_recoupment = after_talent - recoupment
    producer_take = max(0.0, after_recoupment) * PRODUCER_NET_PARTICIPATION
    residual      = after_recoupment - producer_take
    return {
        "revenue":       revenue,
        "talent_take":   talent_take,
        "recoupment":    recoupment,
        "producer_take": producer_take,
        "residual":      residual,
    }


# ── Portfolio / scoring helpers ────────────────────────────────────────────────
def risk_adjusted_npv(project: MovieProject, critical_score: Optional[float] = None,
                       bear_weight: float = 0.5) -> float:
    """Weighted toward the bear case — rewards risk-aware greenlighting, not
    just an optimistic expected value. See DESIGN_NOTES.md 'Variance is
    graded, not hidden.' critical_score, when the outcome has actually been
    resolved, folds in the real (already-known) reception rather than
    scoring purely on hypothetical box-office scenarios."""
    bear = project.npv("bear", critical_score)
    base = project.npv("base", critical_score)
    return bear_weight * bear + (1 - bear_weight) * base


def capital_efficiency(project: MovieProject, scenario: str = "base",
                        critical_score: Optional[float] = None) -> float:
    """Total lifetime revenue per marketing dollar — penalizes 'just spend
    the max' P&A strategies the way Day 1's greenlight marketing-ROI table
    does. A healthy real-world P&A efficiency benchmark is roughly 3-6x;
    this uses total revenue (not just opening box office) since P&A drives
    awareness that pays off across every window, not only the premiere."""
    if project.pa_spend_m <= 0:
        return 0.0
    return project.total_revenue(scenario, critical_score) / project.pa_spend_m


def strategic_fit_score(project: MovieProject, critical_score: Optional[float] = None) -> float:
    """0-100: did the release-strategy choice actually maximize combined
    theatrical + streaming value net of cannibalization, vs. what a naive
    'always go wide theatrical' default would have produced?"""
    actual_npv = risk_adjusted_npv(project, critical_score)
    baseline = MovieProject(**{**project.__dict__, "release_strategy": "wide_theatrical"})
    baseline_npv = risk_adjusted_npv(baseline, critical_score)
    if baseline_npv == 0:
        return 50.0
    delta_pct = (actual_npv - baseline_npv) / abs(baseline_npv)
    return float(min(max(50 + delta_pct * 100, 0), 100))


def draw_actual_multiplier(team_name: str, cycle: int, genre: str = "Drama",
                            concept_type: str = "New IP") -> float:
    """Resolves the real box-office multiplier at 'release' time — a
    continuous draw (not just one of 3 buckets), seeded off team+cycle the
    same way pages/simulation.py seeds its quarterly rating variance, so a
    given team's outcome for a given cycle is reproducible but not
    guessable in advance. Triangular distribution peaked at 'base', bounded
    by this genre+concept-type's own bear/bull spread (see
    GENRE_VARIANCE_SPREAD, INDIE_HORROR_VARIANCE_MULT) — smoother than a
    3-way coin flip, and a horror movie's draw genuinely swings wider than
    an awards drama's (and an indie-horror one wider still)."""
    bounds = scenario_multipliers_for(genre, concept_type)
    seed = (abs(hash(team_name)) + cycle * 4201) % (2 ** 31)
    rng = np.random.default_rng(seed)
    return float(rng.triangular(bounds["bear"], bounds["base"], bounds["bull"]))


def nearest_scenario_label(multiplier: float, genre: str = "Drama",
                            concept_type: str = "New IP") -> str:
    """Which named scenario the actual drawn outcome reads closest to, for
    narrative framing in the results screen (e.g. 'landed close to your Base
    Case') — compared against this genre+concept-type's own adjusted
    bounds, not the flat global ones."""
    bounds = scenario_multipliers_for(genre, concept_type)
    return min(bounds, key=lambda k: abs(bounds[k] - multiplier))


def compute_movie_score(projects: list[MovieProject], critical_scores: Optional[list] = None) -> dict:
    """Composite score across a slate of MovieProjects (one per cycle
    played so far). Weights mirror utils/game_state.py::compute_score's
    pattern but with Day 2's own components — see DESIGN_NOTES.md.

    critical_scores, when given, must be the same length as projects (the
    already-resolved reception per cycle — see draw_critical_reception) so
    the final score reflects real awards-season/library value actually
    earned, not just the hypothetical bear/base box-office scenarios."""
    if not projects:
        return {"total": 0.0, "risk_adjusted_npv": 0.0, "capital_efficiency": 0.0,
                 "strategic_fit": 0.0, "passed": False}
    if critical_scores is None:
        critical_scores = [None] * len(projects)

    ra_npvs = [risk_adjusted_npv(p, cs) for p, cs in zip(projects, critical_scores)]
    avg_ra_npv = sum(ra_npvs) / len(ra_npvs)
    avg_cap_eff = sum(capital_efficiency(p, critical_score=cs)
                       for p, cs in zip(projects, critical_scores)) / len(projects)
    avg_fit = sum(strategic_fit_score(p, cs) for p, cs in zip(projects, critical_scores)) / len(projects)

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
