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
# 2026-08-17, per explicit user question ("should Star Power be increased
# without impacting budget?"): it previously was -- a completely free
# slider delivering up to +30% opening lift at zero cost, which doesn't
# match how casting actually works (the teaching note's own "Profits"
# section: actors routinely get "$2 million upfront against 10% of gross,"
# talent take up to 30% of earnings before net income). Real casting is a
# real cost, added unconditionally in capital_at_risk() below -- this is a
# genuine recalibration of every existing project's economics, not an
# opt-in lever with a zero-effect default the way Concept Type/Source
# Material/etc. are, because Star Power was already a required field every
# project set to a real value -- there's no backward-compatible "off"
# position to default to.
STAR_POWER_COST_PER_POINT_M = 0.20   # $M per Star Power point -- maxing to 100 costs $20M in casting
MKT_LIFT_PER_M        = 0.006  # opening-weekend awareness lift per $1M P&A — gentle on purpose:
                                # this stacks with star power on the same opening-weekend number,
                                # so both together should move it moderately, not compound explosively
BASE_WINDOW_DAYS      = 90     # 2012-era theatrical exclusivity norm
WINDOW_SHRINK_PER_CYCLE_DAYS = 15   # real-world post-2012 compression, applied per cycle (1->2->3)
CYCLES_TOTAL          = 5
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
# its built-in audience, it just stops being a novelty). Explicit entries for
# cycles 4-5 (added when CYCLES_TOTAL grew to 5) hold the plateau at the same
# 1.05 floor rather than relying on .get()'s fallback -- a franchise doesn't
# keep fading indefinitely, it bottoms out.
SEQUEL_OPENING_BONUS_BY_CYCLE = {1: 1.25, 2: 1.15, 3: 1.05, 4: 1.05, 5: 1.05}

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


# ── Source Material — a third axis alongside Genre and Concept Type ────────
# 2026-08-17, per the teaching note's "Production" section: "up to 85% of
# contemporary content at any given time is derived from pre-existing
# intellectual property... [studios] may seek an advance... up to $5 million
# may be spent on acquiring a script, particularly when intense competition
# arises." This is genuinely separate from Concept Type (New IP/Sequel/etc.)
# -- Concept Type asks "is this a franchise entry," Source Material asks
# "where did the underlying story come from." A Sequel can be an original
# screenplay franchise (no acquisition cost) OR a Book Adaptation sequel
# (both apply). "Original Screenplay" is the true zero-effect baseline --
# every project built before this feature existed keeps its exact original
# calibrated economics, same posture as New IP/self_finance/standard/keep.
SOURCE_MATERIALS = ["Original Screenplay", "Book Adaptation", "Video Game Adaptation", "TV Show Adaptation"]

# Real cash paid upfront to option/acquire the underlying rights -- added on
# top of budget_m in capital_at_risk(), not discounted by financing
# structure or AI production tools (a rights fee isn't a production-cost
# efficiency the way VFX/scheduling savings are). Video Game Adaptation
# commands the highest premium -- real recent examples (major game-to-film
# deals) show publishers extracting significant option fees given an
# existing, proven global fanbase and tight IP-protection leverage over the
# adaptation's creative direction.
SOURCE_ACQUISITION_COST_M = {
    "Original Screenplay":   0.0,
    "Book Adaptation":       3.0,
    "TV Show Adaptation":    5.0,
    "Video Game Adaptation": 8.0,
}

# Built-in awareness from an existing fan base going into the opening
# weekend -- deliberately smaller than Sequel's franchise recognition
# (SEQUEL_OPENING_BONUS_BY_CYCLE), since this is the property's FIRST film,
# not a proven film franchise entry, but real: an adaptation of a beloved
# book/game/show starts with name recognition an original screenplay has to
# earn entirely through P&A and star power. Stacks with Concept Type's own
# opening boost (a Sequel to a prior game adaptation gets both).
SOURCE_OPENING_BOOST = {
    "Original Screenplay":   1.00,
    "Book Adaptation":       1.05,
    "TV Show Adaptation":    1.08,
    "Video Game Adaptation": 1.12,
}


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
# 2026-08-17: genre alone was the ONLY gate -- a brand-new, unproven "New IP"
# action movie got full theme-park/merch value, identical to an established
# Sequel in the same genre, which doesn't match how this actually works:
# rides and toy lines get built around PROVEN IP, and only once a movie has
# actually shown up at the box office and with critics. Three qualification
# layers now apply, in order:
#   1. Genre OR Concept Type eligibility (a genre-ineligible movie can still
#      qualify via Family/Kids -- merch is that concept type's whole draw,
#      independent of genre; see THEME_PARK_CONCEPT_MULT below).
#   2. A real box-office performance gate (THEME_PARK_BOX_OFFICE_GATE_MULT) —
#      the resolved/previewed scenario must clear the genre's own base case,
#      not just open. Applies during bear/base/bull PLANNING previews too
#      (not a leak -- the scenario multiplier itself, unlike critical
#      reception, is already visible information at that stage).
#   3. A critical-reception gate (THEME_PARK_CRITICAL_GATE), checked ONLY
#      once critical_score is actually resolved (None during planning
#      previews -- same "can't leak what a student doesn't know yet" posture
#      as awards_season_bump). A genre/concept-eligible movie that opens
#      well but gets panned still doesn't get a themed attraction built
#      around it.
THEME_PARK_ELIGIBLE_GENRES     = {"Action/Tentpole", "Sci-Fi/Fantasy", "Animated"}
THEME_PARK_REVENUE_RATE        = 0.03   # fraction of domestic box office
THEME_PARK_BOX_OFFICE_GATE_MULT = 1.0   # resolved scenario multiplier must be >= genre's own base-case
                                          # multiplier (1.0x of it) -- a bear-case underperformer doesn't
                                          # get a ride no matter how eligible the genre is
THEME_PARK_CRITICAL_GATE       = 40     # minimum resolved critical_score (0-100) to qualify -- a
                                          # critically panned movie doesn't get merch investment behind it

# Concept Type scales theme-park/merch value on top of the gates above --
# franchise status is a real, separate signal from genre alone (Universal
# doesn't greenlight a ride off a single unproven movie the way it will for
# an established franchise entry). Sequel gets the full rate (proven IP);
# New IP gets a reduced fraction (it has to prove itself this cycle, same as
# every other New IP effect in this file); Family/Kids gets its own
# independent qualifying path (see gate #1 above) at a fraction reflecting
# that a kids property's merch case is real but not guaranteed blockbuster-
# scale the way an eligible-genre tentpole's is. Indie-Horror isn't listed —
# it falls through to genre eligibility alone (Horror was never an eligible
# genre to begin with, so this never actually fires for Indie-Horror).
THEME_PARK_CONCEPT_MULT = {"Sequel": 1.0, "New IP": 0.4, "Family/Kids": 0.85}


def draw_critical_reception(team_name: str, cycle: int, genre: str,
                             ai_production_tools: bool = False) -> float:
    """Continuous, seeded, reproducible-per-team-per-cycle draw — same
    mechanism as draw_actual_multiplier, but a different seed offset so the
    two draws move independently rather than in lockstep.

    ai_production_tools (2026-08-05, default False = original behavior
    unchanged) caps the ceiling of this draw via AI_TOOLS_CRITICAL_CEILING_
    MULT — the quality-risk edge of that lever's cost/timeline tradeoff. The
    mode is clamped to the new ceiling too (a triangular distribution needs
    lo <= mode <= hi); every genre's stored mode already sits well below its
    hi bound, so this only ever matters once ai_production_tools narrows hi
    down far enough to cross it."""
    lo, mode, hi = CRITICAL_RECEPTION_BOUNDS.get(genre, (15, 40, 80))
    if ai_production_tools:
        hi = lo + (hi - lo) * AI_TOOLS_CRITICAL_CEILING_MULT
        mode = min(mode, hi)
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


# ── eWOM & Piracy — independent post-release digital-revenue risk axis ─────
# 2026-08-05, Phase 4 item 10: swings PVOD rental transactions and owned
# Peacock subscriber value together (both are "digital" revenue, distinct
# from theatrical box office and from Ancillary Surprise's theme-park/
# merchandise licensing story) — deliberately NOT the same axis as
# draw_ancillary_surprise above, own independent seed offset, so a movie
# can catch a viral social wave AND still get hit by piracy leakage in
# principle (uncorrelated real-world forces). More common than Production
# Trouble/Ancillary Surprise (0.05/0.12) since social chatter and piracy
# leakage are everyday market forces, not rare production-side shocks.
# Deliberately excludes pay1_license_fee() — a real licensing deal is
# negotiated and priced before release, not indexed to how digital word-of-
# mouth or piracy actually plays out (same reasoning PAY1_LICENSE_DISCOUNT's
# docstring already gives for keeping that fee scenario-independent).
EWOM_PIRACY_CHANCE = 0.15
EWOM_PIRACY_RANGE  = (0.70, 1.35)
EWOM_REASONS_UP = [
    "A viral social clip drove a surge of organic digital demand after release",
    "Positive word-of-mouth on social platforms outpaced paid marketing reach",
    "A creator community's reaction videos extended digital interest for weeks",
]
PIRACY_REASONS_DOWN = [
    "Pirated copies leaked within days of release, cannibalizing digital transactions",
    "Social sentiment turned negative quickly, cutting off word-of-mouth momentum before it built",
    "A torrent/streaming-piracy surge measurably dented PVOD conversion",
]


def draw_ewom_piracy_swing(team_name: str, cycle: int) -> Optional[tuple[str, float]]:
    """Own independent seeded risk axis (own hash offset — never perturbs
    draw_actual_multiplier's, draw_critical_reception's, draw_production_
    trouble's, draw_ancillary_surprise's, or draw_ai_tooling_setback's
    sequences). Returns None most of the time; when it fires, returns
    (reason, multiplier) where multiplier can land above or below 1.0 —
    the whole point is this can genuinely swing either direction, unlike
    Production Trouble's one-directional haircut."""
    seed = (abs(hash(team_name)) + cycle * 7457 + 337) % (2 ** 31)
    rng = np.random.default_rng(seed)
    if rng.random() > EWOM_PIRACY_CHANCE:
        return None
    lo, hi = EWOM_PIRACY_RANGE
    mult = float(rng.uniform(lo, hi))
    reasons = EWOM_REASONS_UP if mult >= 1.0 else PIRACY_REASONS_DOWN
    reason = reasons[int(rng.integers(0, len(reasons)))]
    return reason, mult


# ── Talent Deals — Studio Partnerships (Overall/First-Look) & Holding Deals ──
# 2026-08-04, per user request to build out talent-negotiation content from
# the Movie Business and Deal Mechanisms note, plus rival-studio competitive
# dynamics ("can you see how your choices impact rival studios?") -- mirrors
# utils/sports_models.py's seeded-rival-bidder precedent (real companies
# bidding against you for league rights), scoped down to talent scheduling.
#
# 2026-08-18, real fix per explicit user catch: these are TWO genuinely
# different entity types, previously conflated into one shared dict/mechanic.
# The teaching note itself is explicit: "For high profile creatives, they
# may have overall deals or first-look deals in which studios pay them for
# the privilege of having first-look access to content they are working
# on. Currently, Ryan Reynolds' Maximum Effort production house has a deal
# with Paramount, and Margot Robbie's LuckyChap and Timothee Chalamet are
# both tied to Warner Bros." -- an Overall/First-Look Deal is a STUDIO-level
# relationship with a production banner/company (Maximum Effort, LuckyChap),
# not a direct signing of one individual actor. A Holding Deal, by contrast,
# genuinely is about one individual's calendar -- reserving a specific
# actor's window for a specific upcoming production.
#
# STUDIO_PARTNERS (Overall/First-Look Deal targets) -- fictional production
# banners/companies, a standing studio-level relationship independent of any
# one project, signed once and benefiting every remaining cycle whose genre
# matches. Fictional for the same reason RIVAL_STUDIOS is: a "you got beaten
# to a deal with [named real production company]" framing would read as a
# claim about a real company's actual business relationships.
STUDIO_PARTNERS = {
    "meridian":   {"name": "Meridian Collective",  "specialty": "Action/Tentpole",
                    "bio": "An action-forward producer-star collective — first-look access to "
                           "whatever they're developing next, in exchange for a standing studio deal.",
                    "deal_cost_m": 25.0, "star_power_bonus": 15},
    "northbench": {"name": "Northbench Pictures",   "specialty": "Awards/Prestige",
                    "bio": "A prestige awards banner with real critical pedigree across its slate.",
                    "deal_cost_m": 18.0, "critical_score_bonus": 8.0},
    "brightlane": {"name": "Brightlane Family",     "specialty": "Animated",
                    "bio": "A family-franchise production house with a track record of durable IP.",
                    "deal_cost_m": 15.0, "star_power_bonus": 10},
    "afterdark":  {"name": "Afterdark Studio",      "specialty": "Horror",
                    "bio": "A horror specialist production house known for punching above its budget.",
                    "deal_cost_m": 10.0, "star_power_bonus": 8},
}

# TALENT_PARTNERS (Holding Deal targets) -- fictional INDIVIDUAL actors/
# actresses, not real people, distinct from STUDIO_PARTNERS above the same
# way an individual's persona/likeness is distinct from a corporate banner.
# Rebuilt 2026-08-17 with real demographic/career profile fields (age,
# origin_medium, lifetime_box_office_m, social_followers_m, bio,
# best_genres) so students have something to actually weigh, not just a
# name and a bonus number. origin_medium is the deliberate teaching hook:
# WHERE a talent built their fame is a real casting tradeoff (a Film
# veteran is expensive but reliable; a Social Media creator is cheap with a
# huge built-in following but no proven dramatic track record) -- see
# ORIGIN_MEDIUM_SOURCE_SYNERGY below for how it interacts with Source
# Material. Re-keyed 2026-08-18 (was reusing STUDIO_PARTNERS' keys, which
# broke once the two rosters became genuinely separate) -- each individual
# still shares their old key's specialty genre, purely for thematic
# continuity, not a mechanical link between the two entity types.
TALENT_PARTNERS = {
    "vance": {
        "name": "Jordan Vance", "gender": "actor", "age": 41,
        "specialty": "Action/Tentpole", "best_genres": ["Action/Tentpole", "Sci-Fi/Fantasy"],
        "origin_medium": "Film",
        "bio": "A two-decade theatrical-franchise lead with three $500M+ openings on his résumé — "
               "the safest, most expensive bet on this list, with a proven track record and no "
               "crossover risk.",
        "lifetime_box_office_m": 4200.0, "social_followers_m": 18.0,
        "hold_cost_m": 4.0, "star_power_bonus": 15,
    },
    "okonkwo": {
        "name": "Adaeze Okonkwo", "gender": "actress", "age": 52,
        "specialty": "Awards/Prestige", "best_genres": ["Awards/Prestige", "Drama"],
        "origin_medium": "Television",
        "bio": "Built her name on a decade of acclaimed prestige-TV lead roles before crossing "
               "over to film — brings real critical credibility and a built-in Peacock-adjacent "
               "audience, but a smaller-screen pedigree doesn't always translate to opening-weekend "
               "box office.",
        "lifetime_box_office_m": 310.0, "social_followers_m": 6.5,
        "hold_cost_m": 3.0, "critical_score_bonus": 8.0,
    },
    "marsh": {
        "name": "Casey Marsh", "gender": "actor", "age": 29,
        "specialty": "Animated", "best_genres": ["Animated", "Comedy"],
        "origin_medium": "Video Games",
        "bio": "Broke out as the motion-capture lead and voice of a hit video-game franchise before "
               "moving into animated features — a natural, synergistic fit fronting a Video Game "
               "Adaptation specifically, less proven carrying a project with no game pedigree.",
        "lifetime_box_office_m": 640.0, "social_followers_m": 24.0,
        "hold_cost_m": 2.5, "star_power_bonus": 10,
    },
    "kade": {
        "name": "Reyna Kade", "gender": "actress", "age": 26,
        "specialty": "Horror", "best_genres": ["Horror", "Comedy"],
        "origin_medium": "Social Media",
        "bio": "A social-first creator with a massive, highly engaged following — cheap, with huge "
               "built-in awareness on day one, but no real dramatic track record yet, and that "
               "following is a bet on staying relevant, not a guarantee.",
        "lifetime_box_office_m": 45.0, "social_followers_m": 38.0,
        "hold_cost_m": 2.0, "star_power_bonus": 8,
    },
}

# Which Source Material a talent's origin medium most naturally leverages --
# casting FOR the adaptation (a game-famous actor fronting the actual game
# adaptation) is a real, teachable synergy, distinct from casting purely on
# raw bonus size. Film and Social Media don't map to a specific Source
# Material (a film veteran's value is genre-general reliability; a creator's
# value is raw awareness, not adaptation credibility) -- absence from this
# dict is deliberate, not an oversight.
ORIGIN_MEDIUM_SOURCE_SYNERGY = {
    "Television":   "TV Show Adaptation",
    "Video Games":  "Video Game Adaptation",
}
TALENT_SOURCE_SYNERGY_MULT = 1.5   # bonus multiplier when origin_medium's mapped Source Material
                                     # matches the project's actual source_material -- rewards casting
                                     # that's actually strategic, not just "sign whoever's cheapest/biggest"

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
#
# 2026-08-17, per the "Movie Business and Deal Mechanisms" teaching note's
# "Raising funds" section: a real global pre-sale isn't a direct
# studio-to-distributor handshake -- a sales agent brokers the territorial
# deals, collects the advances, and takes a real fee (the note: "10% to 30%
# with a portion often deferred until lenders are repaid") off the top
# before the studio ever sees the cash. PRESALE_SALES_AGENT_FEE_PCT models
# that real transaction cost -- previously the full PRESALE_ADVANCE_PCT
# reduced capital_at_risk as if the studio kept 100% of the advance, which
# understated what a global distribution deal actually costs to arrange.
FINANCING_STRUCTURES = ["self_finance", "presale", "tax_incentive"]
PRESALE_ADVANCE_PCT       = 0.40   # fraction of production budget the international advance covers, GROSS
                                     # (before the sales agent's fee -- see PRESALE_SALES_AGENT_FEE_PCT)
PRESALE_SALES_AGENT_FEE_PCT = 0.20   # mid-point of the note's real 10-30% range -- the sales agent's cut
                                       # of the advance, which never reaches the studio's own capital pool
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


# ── AI Production Tools ──────────────────────────────────────────────────────
# 2026-08-05, Phase 4 item 8: a cost/timeline lever in Greenlight, deliberately
# NOT a free efficiency win -- three real edges, two favorable and one
# unfavorable, same posture as every other lever in this file (Financing
# Structure, Exhibitor Posture). Cheaper AND faster (previz/scheduling/VFX-
# assist genuinely compress both budget and post-production time in the real
# industry right now), but capped creative ceiling (a heavily AI-assisted
# production tends toward the formulaic -- it rarely produces a transcendent
# one, even if it reliably avoids a disaster) and its own independent setback
# risk (tooling/guild/legal friction unique to this pipeline, not a
# generic "something went wrong" -- see draw_ai_tooling_setback). Default
# False reproduces every existing call site's exact original behavior.
AI_TOOLS_BUDGET_SAVINGS_PCT    = 0.15   # cuts the budget (not P&A) component of capital at risk
AI_TOOLS_TIMELINE_SHIFT_MO     = 1.5    # faster post-production pulls the whole cashflow timeline
                                          # forward -- same revenue, arrives sooner, so NPV improves
                                          # via less discounting, not bigger numbers
AI_TOOLS_CRITICAL_CEILING_MULT = 0.80   # caps how high critical reception can land (see
                                          # draw_critical_reception's ai_production_tools kwarg) --
                                          # the quality-risk edge of the tradeoff
AI_TOOLS_SETBACK_CHANCE        = 0.10   # only ever rolled for ai_production_tools=True projects --
                                          # a bit more common than Production Trouble's 0.05 since
                                          # this pipeline is newer and less battle-tested
AI_TOOLS_SETBACK_HAIRCUT_RANGE = (0.75, 0.92)   # milder than Production Trouble's (0.60, 0.85) --
                                                  # a narrower, more contained kind of setback
AI_TOOLS_SETBACK_REASONS = [
    "A visual-effects shot needed costly manual rework after an AI-generated pass failed quality review",
    "A guild dispute over AI tool usage stalled post-production for weeks",
    "Test audiences flagged an uncanny-valley digital double, forcing a late reshoot",
    "An AI-assisted schedule optimization missed a real logistics constraint, costing back the time it saved",
]


def draw_ai_tooling_setback(team_name: str, cycle: int) -> Optional[tuple[str, float]]:
    """Own independent seeded risk axis (own hash offset -- never perturbs
    draw_actual_multiplier's, draw_critical_reception's, draw_production_
    trouble's, or draw_ancillary_surprise's sequences), only ever meaningful
    to roll for a project with ai_production_tools=True. Returns None most
    of the time; when it fires, returns (reason, haircut_multiplier) applied
    the same way draw_production_trouble's haircut is -- multiplicatively on
    the resolved box-office multiplier."""
    seed = (abs(hash(team_name)) + cycle * 4657 + 233) % (2 ** 31)
    rng = np.random.default_rng(seed)
    if rng.random() > AI_TOOLS_SETBACK_CHANCE:
        return None
    reason = AI_TOOLS_SETBACK_REASONS[int(rng.integers(0, len(AI_TOOLS_SETBACK_REASONS)))]
    lo, hi = AI_TOOLS_SETBACK_HAIRCUT_RANGE
    return reason, float(rng.uniform(lo, hi))


# ── IMAX / Premium Large Format ─────────────────────────────────────────────
# 2026-08-18, per explicit user question ("is there any imax stuff we can
# include for some of the distribution?"). Real-world grounding: the U.S.
# has roughly 40,000 movie screens total (NATO estimate) but only ~700-900
# true large-format IMAX screens -- a genuinely scarce resource exhibitors
# allocate to their highest-confidence spectacle openings, and one that
# commands real premium ticket pricing (IMAX tickets typically run 1.5-2x a
# standard screen). Modeled as a flat opening-weekend boost from that
# pricing/event-appeal premium -- NOT additional screens (self.screens
# already represents the student's full requested screen count; IMAX
# doesn't add screens, it upgrades the economics of some of the ones you
# already have) -- plus a real flat cost (specialized prints/mastering,
# large-format marketing coordination). Only available for the genres that
# realistically warrant a premium-format push (same set as theme-park
# eligibility -- spectacle-scale tentpoles, not an awards drama) and only
# for a real theatrical run (day_and_date has no meaningful theatrical
# window to upgrade). Default False reproduces every existing project's
# exact original behavior -- a true zero-effect baseline, same posture as
# every other opt-in lever in this file.
IMAX_ELIGIBLE_GENRES  = THEME_PARK_ELIGIBLE_GENRES   # Action/Tentpole, Sci-Fi/Fantasy, Animated
IMAX_OPENING_BOOST_PCT = 0.12   # +12% opening weekend from premium pricing/event appeal
IMAX_COST_M            = 3.0    # flat cost: large-format prints/mastering, marketing coordination


# ── Seasonality / Debut Timing ───────────────────────────────────────────────
# 2026-08-05, Phase 5 (deliberately last among the Movies items — reshapes
# windowed_cashflows()'s previously-fixed month offsets and interacts with
# the awards-eligibility timing already built, the most delicate change in
# this backlog). Movies previously had no release-*timing* decision at all
# (only release *strategy* — wide/platform/day-and-date); this adds the real
# release-calendar tension the teaching note also covers: Summer/Holiday
# open bigger but crowd out awards recall; Fall/Awards opens softer but is
# the ideal on-ramp into the awards calendar (For-Your-Consideration
# campaigns are timed around exactly this). "Off-Peak" is the true neutral
# baseline — every effect below is a no-op for it (opening_mult=1.0, no
# genre synergy, full awards recall, the original hardcoded 11.0-month bump
# timing) — same "deliberate zero-effect default" posture as New IP/
# self_finance/standard/keep elsewhere in this file, so every existing call
# site keeps its exact original calibrated behavior. Framed honestly in the
# UI as a real strategy too, not a placeholder: many mid-budget films
# deliberately release in an unremarkable week specifically to dodge
# summer/holiday crowding.
DEBUT_SEASONS = ["Off-Peak", "Winter", "Spring", "Summer Tentpole", "Fall/Awards", "Holiday"]

SEASON_OPENING_MULT = {
    "Off-Peak": 1.00, "Winter": 0.90, "Spring": 0.95,
    "Summer Tentpole": 1.18, "Fall/Awards": 0.92, "Holiday": 1.12,
}

# Genre-season synergy: an extra opening-weekend bonus when a genre's real
# audience actually shows up that season — only the genres/seasons with a
# real-world pattern get an entry; everything else falls through to 1.0 via
# .get(). Off-Peak deliberately has no entries (part of its neutral-baseline
# guarantee, not an oversight).
SEASON_GENRE_SYNERGY = {
    "Summer Tentpole": {"Action/Tentpole": 1.10, "Sci-Fi/Fantasy": 1.10, "Animated": 1.05},
    "Holiday":          {"Animated": 1.15, "Comedy": 1.08},
    "Fall/Awards":      {"Awards/Prestige": 1.12, "Drama": 1.08},
}

# How much of awards_season_bump() actually lands, scaled by real-world
# awards-body recency bias — a summer tentpole released 8+ months before
# voting rarely gets recalled even with great reviews, while a Fall/Awards
# or Holiday release is deliberately timed to still be fresh in voters'
# minds. Off-Peak = 1.0 (neutral baseline, matches original behavior).
SEASON_AWARDS_RECALL = {
    "Off-Peak": 1.00, "Winter": 0.70, "Spring": 0.80,
    "Summer Tentpole": 0.40, "Fall/Awards": 1.00, "Holiday": 1.00,
}

# Real-world awards season sits around Jan-Feb — how many months after
# release that actually is depends on when the movie came out. Off-Peak
# keeps the original flat 11.0-month assumption windowed_cashflows() always
# used before this feature existed.
SEASON_AWARDS_BUMP_MONTH = {
    "Off-Peak": 11.0, "Winter": 12.0, "Spring": 10.0,
    "Summer Tentpole": 8.0, "Fall/Awards": 3.0, "Holiday": 2.0,
}


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
    ai_production_tools: bool = False            # see AI_TOOLS_* below
    debut_season: str = "Off-Peak"                # see DEBUT_SEASONS above
    source_material: str = "Original Screenplay"  # see SOURCE_MATERIALS above
    imax_release: bool = False                     # see IMAX_* above

    def capital_at_risk(self) -> float:
        """Total upfront cash committed before any revenue arrives --
        reduced by financing_structure's chosen structure (see
        FINANCING_STRUCTURES above); self_finance is the unadjusted
        budget_m + pa_spend_m baseline. presale's effective advance is net
        of PRESALE_SALES_AGENT_FEE_PCT (2026-08-17) -- a global distribution
        deal is brokered by a sales agent who takes a real 10-30% fee before
        the studio ever sees the cash, so only the net amount actually
        reduces capital at risk. ai_production_tools (2026-08-05, see
        AI_TOOLS_BUDGET_SAVINGS_PCT below) applies its own discount on top
        of whatever financing_structure already produced -- the two levers
        are independent (a tax-incentive shoot can also lean on AI
        production tools), stacking multiplicatively on the budget
        component only, never on P&A. SOURCE_ACQUISITION_COST_M (2026-08-17)
        is added on top, unaffected by either discount -- a rights fee to
        option a book/game/show isn't a production-cost efficiency.
        STAR_POWER_COST_PER_POINT_M (2026-08-17) is also added on top,
        unconditionally -- casting a bigger star is a real cost, not a free
        lever (see the constant's own comment for why this is the one
        recalibration in this file with no backward-compatible zero-effect
        default)."""
        if self.financing_structure == "presale":
            effective_advance = self.budget_m * PRESALE_ADVANCE_PCT * (1 - PRESALE_SALES_AGENT_FEE_PCT)
            budget_component = self.budget_m - effective_advance
        elif self.financing_structure == "tax_incentive":
            budget_component = self.budget_m * (1 - TAX_CREDIT_PCT)
        else:
            budget_component = self.budget_m
        if self.ai_production_tools:
            budget_component *= (1 - AI_TOOLS_BUDGET_SAVINGS_PCT)
        acquisition_cost = SOURCE_ACQUISITION_COST_M.get(self.source_material, 0.0)
        star_power_cost = self.star_power * STAR_POWER_COST_PER_POINT_M
        imax_cost = IMAX_COST_M if self.is_imax_eligible() else 0.0
        return budget_component + self.pa_spend_m + acquisition_cost + star_power_cost + imax_cost

    def is_imax_eligible(self) -> bool:
        """Whether an IMAX/large-format release is actually in effect this
        project -- requires imax_release=True AND a genre with real
        large-format demand AND a real theatrical run (day_and_date has
        none to upgrade). False (the common case) means IMAX never touches
        capital_at_risk() or opening_weekend() at all."""
        return (self.imax_release and self.genre in IMAX_ELIGIBLE_GENRES
                and self.release_strategy != "day_and_date")

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

    def season_opening_mult(self) -> float:
        """Debut-season crowding/audience-fit effect on opening intensity —
        SEASON_OPENING_MULT (competitive crowding) times SEASON_GENRE_
        SYNERGY (does this genre's real audience actually show up that
        season). "Off-Peak" is the neutral 1.0x baseline for both."""
        return (SEASON_OPENING_MULT.get(self.debut_season, 1.0)
                * SEASON_GENRE_SYNERGY.get(self.debut_season, {}).get(self.genre, 1.0))

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
        fewer screens than asked for and a friendlier one nets more.
        debut_season applies its own crowding/genre-fit multiplier on top
        (see season_opening_mult) -- 1.0x for the "Off-Peak" baseline.
        source_material applies its own built-in-fanbase awareness boost
        (see SOURCE_OPENING_BOOST) -- 1.0x for "Original Screenplay". A real
        IMAX/large-format release (see is_imax_eligible) adds its own flat
        premium-pricing/event-appeal boost on top -- an upgrade to the
        screens you already have, not additional screens."""
        screens = self.screens if self.release_strategy != "platform" else min(self.screens, 600)
        screens *= EXHIBITOR_SCREENS_MULT_BY_POSTURE.get(self.exhibitor_posture, 1.0)
        star_boost = 1 + (self.star_power / 100) * STAR_POWER_BOOST_MAX
        source_boost = SOURCE_OPENING_BOOST.get(self.source_material, 1.0)
        imax_boost = 1 + IMAX_OPENING_BOOST_PCT if self.is_imax_eligible() else 1.0
        return (BASE_PER_SCREEN_M * screens * star_boost * self.concept_opening_boost()
                * self.awareness_lift() * self.season_opening_mult() * source_boost * imax_boost)

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

    def theme_park_value(self, scenario, critical_score: Optional[float] = None) -> float:
        """Theme park attraction / merchandise / Universal licensing value —
        Zach Schlessel's brief: "theme park/merchandise opportunities,
        Universal licensing deals ('pay yourself' model)... genre
        determines theme park eligibility." Three real qualification gates
        now apply (see the constants block above for the full rationale):
        genre-or-Family/Kids eligibility, a box-office performance floor
        (checked even during planning previews), and a critical-reception
        floor (checked only once critical_score is actually resolved — a
        planning-stage preview can't know reviews in advance). Sized off
        domestic box office as a rough proxy for how big the IP actually
        landed, then scaled by THEME_PARK_CONCEPT_MULT — a proven Sequel
        gets the full rate, an unproven New IP gets a fraction, Family/Kids
        gets its own independent rate. Zero for anything that fails a gate,
        not a smaller fraction — these are real eligibility gates."""
        genre_eligible   = self.genre in THEME_PARK_ELIGIBLE_GENRES
        concept_eligible = self.concept_type == "Family/Kids"
        if not (genre_eligible or concept_eligible):
            return 0.0

        bounds = scenario_multipliers_for(self.genre, self.concept_type)
        mult = bounds[scenario] if isinstance(scenario, str) else scenario
        if mult < bounds["base"] * THEME_PARK_BOX_OFFICE_GATE_MULT:
            return 0.0

        if critical_score is not None and critical_score < THEME_PARK_CRITICAL_GATE:
            return 0.0

        concept_mult = THEME_PARK_CONCEPT_MULT.get(self.concept_type, 1.0 if genre_eligible else 0.0)
        return self.domestic_box_office(scenario) * THEME_PARK_REVENUE_RATE * concept_mult

    def awards_season_bump(self, scenario: str, critical_score: Optional[float] = None) -> float:
        """A limited theatrical rerelease during awards season (For-Your-
        Consideration campaigns, expanded runs after nominations) — only
        applies to awards-eligible genres (see AWARDS_ELIGIBLE_GENRES) whose
        critical reception clears AWARDS_CONTENDER_THRESHOLD. A real, if
        modest, extra revenue window that a merely well-reviewed action
        movie doesn't get access to, no matter how good its reviews are.
        Scaled by SEASON_AWARDS_RECALL — a summer release rarely gets
        recalled by awards voters even with great reviews; a Fall/Awards or
        Holiday release is deliberately timed to still be fresh in their
        minds. "Off-Peak" recall is 1.0 (neutral baseline, matches original
        behavior)."""
        if critical_score is None or self.genre not in AWARDS_ELIGIBLE_GENRES:
            return 0.0
        if critical_score < AWARDS_CONTENDER_THRESHOLD:
            return 0.0
        strength = (critical_score - AWARDS_CONTENDER_THRESHOLD) / (100 - AWARDS_CONTENDER_THRESHOLD)
        recall = SEASON_AWARDS_RECALL.get(self.debut_season, 1.0)
        return self.domestic_box_office(scenario) * 0.08 * strength * recall

    def windowed_cashflows(self, scenario: str, critical_score: Optional[float] = None,
                            pvod_mult: float = 1.0, theme_park_mult: float = 1.0,
                            ewom_mult: float = 1.0) -> list[tuple[float, float]]:
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
        consequence of box-office or critical performance.

        ewom_mult (added 2026-08-05, default 1.0 = no-op): applies draw_
        ewom_piracy_swing()'s resolved swing to PVOD and OWNED subscriber
        value together (both are "digital" revenue) — a separate axis from
        pvod_mult/theme_park_mult above, own independent seed. Deliberately
        does NOT touch pay1_license_fee() when licensing out — that flat
        fee is negotiated and priced before release, not indexed to how
        digital word-of-mouth or piracy actually plays out."""
        theatrical = self.theatrical_studio_net(scenario)
        pvod       = self.pvod_revenue(scenario) * pvod_mult * ewom_mult
        longtail   = self.library_longtail(scenario, critical_score)
        bump       = self.awards_season_bump(scenario, critical_score)
        theme_park = self.theme_park_value(scenario, critical_score) * theme_park_mult
        window_mo  = self.window_days() / 30.0
        if self.is_licensing_out():
            # A flat licensing fee, paid alongside PVOD -- faster and known
            # in advance, vs. owned subscriber value's later, performance-
            # exposed window below. Not scaled by ewom_mult -- see docstring.
            sub_value       = self.pay1_license_fee()
            sub_value_month = window_mo + 1.0
        else:
            sub_value       = self.subscriber_value(scenario) * ewom_mult
            sub_value_month = window_mo + 3.0   # Peacock exclusive window follows PVOD
        flows = [
            (1.5,                theatrical),               # midpoint of a ~12-week theatrical run
            (window_mo + 1.0,    pvod),                       # PVOD opens right after theatrical window
            (sub_value_month,    sub_value),
            (24.0,               longtail),                   # library/EST tail, ~2 years out
        ]
        if bump > 0:
            # Real-world awards season sits around Jan-Feb -- how many
            # months after release that actually is depends on debut_season
            # (see SEASON_AWARDS_BUMP_MONTH). "Off-Peak" keeps the original
            # flat 11.0-month assumption.
            flows.append((SEASON_AWARDS_BUMP_MONTH.get(self.debut_season, 11.0), bump))
        if theme_park > 0:
            flows.append((30.0, theme_park))   # attractions/merchandise take real time to develop and license

        if self.ai_production_tools:
            # Faster post-production pulls the whole timeline forward --
            # same dollar amounts, arriving sooner, which raises NPV/IRR
            # through less discounting rather than bigger numbers. Floored
            # so nothing lands at or before time zero.
            flows = [(max(months - AI_TOOLS_TIMELINE_SHIFT_MO, 0.25), cash) for months, cash in flows]
        return flows

    def npv(self, scenario: str, critical_score: Optional[float] = None,
            discount_rate: float = COST_OF_CAPITAL,
            pvod_mult: float = 1.0, theme_park_mult: float = 1.0, ewom_mult: float = 1.0) -> float:
        cashflows = self.windowed_cashflows(scenario, critical_score, pvod_mult, theme_park_mult, ewom_mult)
        pv = sum(cash / ((1 + discount_rate) ** (months / 12.0)) for months, cash in cashflows)
        return pv - self.capital_at_risk()

    def irr(self, scenario: str, critical_score: Optional[float] = None,
            pvod_mult: float = 1.0, theme_park_mult: float = 1.0, ewom_mult: float = 1.0) -> Optional[float]:
        """Approximate IRR via a simple bisection search — front-loaded cost
        and back-loaded, windowed revenue means closed-form IRR isn't clean,
        and this doesn't need finance-library precision for a teaching sim.

        Returns None if capital is never recovered, float('inf') if the true
        IRR exceeds the search ceiling (a genuine outcome for a fast-payback
        hit, not a bug — display as ">500%"), otherwise the converged rate.
        Silently returning the search boundary as if it were a converged
        answer would look like a real number without being one."""
        cashflows = self.windowed_cashflows(scenario, critical_score, pvod_mult, theme_park_mult, ewom_mult)
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
                       pvod_mult: float = 1.0, theme_park_mult: float = 1.0, ewom_mult: float = 1.0) -> float:
        return sum(cash for _, cash in
                    self.windowed_cashflows(scenario, critical_score, pvod_mult, theme_park_mult, ewom_mult))


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
                             pvod_mult: float = 1.0, theme_park_mult: float = 1.0,
                             ewom_mult: float = 1.0) -> dict:
    """Distribution/participation breakdown for a resolved (or previewed)
    outcome. `scenario` follows the same named-string-or-raw-multiplier
    convention as MovieProject.total_revenue()."""
    revenue      = project.total_revenue(scenario, critical_score, pvod_mult, theme_park_mult, ewom_mult)
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


def portfolio_diversification_score(projects: list[MovieProject]) -> float:
    """0-100: how diversified the slate is across Genre AND Concept Type,
    weighted by capital committed per project (capital_at_risk()) — mirrors
    utils/game_state.py's hhi_from_genres() for TV/Streaming's genre_mix
    scoring component (see SCORE_WEIGHTS there), extended to a second axis
    since a movie slate's franchise-fatigue risk (three Sequels in a row) is
    just as real as its genre concentration. Lower HHI (more diverse) ->
    higher score on each axis; the two axes are averaged, not multiplied,
    so a slate diversified on only one axis still gets partial credit.

    2026-08-17: this was previously a THEORY_CONTENT card only, describing
    a mechanic that didn't actually exist in compute_movie_score — a slate
    of 3 Sequels scored identically to a diversified one. This closes that
    gap.

    A slate with fewer than 2 projects returns a neutral 100 rather than
    the technically-correct HHI=1.0 (maximally concentrated) — there's
    nothing to diversify against yet after a single greenlight, and
    penalizing Cycle 1 for not yet being diversified would be unfair, not
    a real signal."""
    if len(projects) < 2:
        return 100.0

    def _hhi(key_fn) -> float:
        weights: dict = {}
        for p in projects:
            k = key_fn(p)
            weights[k] = weights.get(k, 0.0) + p.capital_at_risk()
        total = sum(weights.values())
        if not total:
            return 1.0
        return sum((w / total) ** 2 for w in weights.values())

    genre_hhi   = _hhi(lambda p: p.genre)
    concept_hhi = _hhi(lambda p: p.concept_type)
    return float(min(max((1 - genre_hhi) * 50 + (1 - concept_hhi) * 50, 0), 100))


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


def multiplier_to_stars(multiplier: float, genre: str, concept_type: str = "New IP") -> int:
    """Maps a resolved/previewed box-office multiplier to a 1-5 star
    signal, scaled against THIS genre+concept_type's own bear/bull band
    (see scenario_multipliers_for) — mirrors utils/models.py's TV-side
    variance_to_stars, but genre-aware since Movies' variance band isn't a
    single fixed global range the way TV's [0.93, 1.08] is. Powers the
    paid Research / Social Listening feature in app_pages/movies.py."""
    bounds = scenario_multipliers_for(genre, concept_type)
    frac = (multiplier - bounds["bear"]) / (bounds["bull"] - bounds["bear"])
    return min(5, max(1, int(frac * 5) + 1))


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
                 "strategic_fit": 0.0, "portfolio_diversification": 0.0, "passed": False}
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
    s_div = portfolio_diversification_score(projects)

    # 2026-08-17: added s_div as a real weighted component (previously a
    # THEORY_CONTENT card only, not scored) -- rebalanced from
    # 0.55/0.20/0.25 down proportionally rather than just appending 0.15 on
    # top, keeping NPV clearly dominant (matches TV/Streaming's own
    # genre_mix weight in utils/game_state.py::SCORE_WEIGHTS).
    total = s_npv * 0.45 + s_eff * 0.20 + s_fit * 0.20 + s_div * 0.15

    return {
        "total":                    round(total, 1),
        "risk_adjusted_npv":        round(s_npv, 1),
        "capital_efficiency":       round(s_eff, 1),
        "strategic_fit":            round(s_fit, 1),
        "portfolio_diversification": round(s_div, 1),
        "avg_ra_npv_m":             round(avg_ra_npv, 2),
        "passed":                   avg_ra_npv > 0,   # pass/fail gate: positive risk-adjusted NPV, not a fixed margin %
    }


# ── Background Studio Slate — non-interactive "rest of the studio" flavor ──
# 2026-08-18, per user request for a studio that feels alive year to year:
# "in year 1, there should be 5-10 movies already slated to go out that
# year... students get to review another 5-10 the following year... begin
# to see some of them bloom." Scoped down from a full portfolio rewrite
# (many simultaneous student-managed projects, a genuinely different turn
# engine) to a lightweight, PURELY non-interactive background layer,
# confirmed with the user: these movies are never decided by the student,
# never touch compute_movie_score, and exist only to populate the
# Distribution Pipeline scorecard so the studio's slate looks and feels
# busy around the one real bet the student is actually making each cycle.
# Fully deterministic (seeded off team_name+cycle, same posture as every
# other draw_* function in this file) -- no persistence needed, regenerable
# identically on every render.
BACKGROUND_SLATE_MIN = 5
BACKGROUND_SLATE_MAX = 10
# A small curated word bank for flavor titles -- deliberately generic/
# fictional-sounding (no real-movie-title collisions), same posture as
# TALENT_PARTNERS/RIVAL_STUDIOS being fictional.
BACKGROUND_TITLE_WORDS_A = ["Midnight", "Silver", "Crimson", "Iron", "Velvet", "Golden", "Broken",
                             "Northern", "Hollow", "Neon", "Static", "Echo", "Shadow", "Quiet"]
BACKGROUND_TITLE_WORDS_B = ["Horizon", "Protocol", "Harbor", "District", "Signal", "Legacy", "Current",
                             "Tide", "Frontier", "Anthem", "Pursuit", "Bloom", "Reckoning", "Static"]


def generate_background_slate(team_name: str, cycle: int) -> list[dict]:
    """Deterministic per-(team, cycle) list of 5-10 non-interactive 'rest of
    the studio's slate' movie summaries -- pure flavor/context, never
    scored. Reuses the real financial engine (MovieProject,
    draw_actual_multiplier, draw_critical_reception) so the numbers stay
    properly calibrated, but under its own seed namespace (a synthetic
    "__bg__<team>__<i>" team name) so it never perturbs the student's own
    draws for the same real cycle. Returns light dicts (title, genre,
    concept_type, npv, theme_park, cycle) -- not full outcome records,
    since nothing downstream needs IRR/waterfall/etc. for background flavor."""
    seed = (abs(hash(team_name)) + cycle * 9769 + 401) % (2 ** 31)
    rng = np.random.default_rng(seed)
    n = int(rng.integers(BACKGROUND_SLATE_MIN, BACKGROUND_SLATE_MAX + 1))

    slate = []
    for i in range(n):
        genre = GENRES[int(rng.integers(0, len(GENRES)))]
        concept_type = CONCEPT_TYPES[int(rng.integers(0, len(CONCEPT_TYPES)))]
        budget = float(rng.uniform(20, 200))
        pa = budget * float(rng.uniform(0.4, 0.9))
        star = int(rng.integers(20, 90))
        screens = int(rng.uniform(1200, 4200))
        title = (f"{BACKGROUND_TITLE_WORDS_A[int(rng.integers(0, len(BACKGROUND_TITLE_WORDS_A)))]} "
                 f"{BACKGROUND_TITLE_WORDS_B[int(rng.integers(0, len(BACKGROUND_TITLE_WORDS_B)))]}")
        project = MovieProject(title=title, genre=genre, budget_m=budget, pa_spend_m=pa,
                                star_power=star, screens=screens, cycle=cycle, concept_type=concept_type)
        bg_team = f"__bg__{team_name}__{i}"
        multiplier = draw_actual_multiplier(bg_team, cycle, genre, concept_type)
        critical_score = draw_critical_reception(bg_team, cycle, genre)
        slate.append({
            "cycle":         cycle,
            "title":         title,
            "genre":         genre,
            "concept_type":  concept_type,
            "npv":           project.npv(multiplier, critical_score),
            "theme_park":    project.theme_park_value(multiplier, critical_score),
            "window_days":   project.window_days(),
            "is_background": True,
        })
    return slate


# ── Scouted Concepts — real competitive consequence for passing ────────────
# 2026-08-18, per explicit user request for real game theory around movie
# CONCEPTS, not just talent: "is there game theory in here? do we get
# updates... about rival studios buying movies we pass on?" Previously the
# only competitive-consequence mechanics were talent-side (STUDIO_PARTNERS
# poaching, TALENT_PARTNERS hold contests) -- there was structurally
# nothing to "pass on" at the concept level, since every cycle's movie is
# hand-built from raw sliders, never chosen from a menu. This closes that
# gap: each cycle, the studio's scouts surface SCOUTED_CONCEPTS_PER_CYCLE
# candidate concepts (genre/concept-type/source-material/logline/rough
# budget spec) the student can either Option (pre-fills the Greenlight
# draft) or let pass. A concept not optioned by the time the NEXT cycle
# begins faces a ONE-TIME chance (SCOUTED_POACH_CHANCE) of being picked up
# by a rival studio -- deliberately a single roll, not an ongoing per-cycle
# risk the way STUDIO_PARTNERS poaching is, so old unclaimed concepts don't
# accumulate indefinitely (matches "review a fresh batch each year," not
# "manage an ever-growing backlog"). A poached concept's fate resolves
# immediately (its own deterministic box-office/critical draw, same engine)
# so the Distribution Pipeline scorecard can show a real, visible
# consequence -- "you passed on this, a rival made it a hit."
SCOUTED_CONCEPTS_PER_CYCLE = 3
SCOUTED_POACH_CHANCE       = 0.35   # deliberately steep -- passing has a real, likely cost

SCOUTED_LOGLINE_BY_GENRE = {
    "Action/Tentpole":  "An elite operative races against a global threat only they can stop.",
    "Sci-Fi/Fantasy":   "A discovery on the edge of known space forces a reckoning with what's real.",
    "Animated":         "A misfit hero learns that belonging is worth the risk of being different.",
    "Horror":           "A remote community unravels as something in the dark refuses to stay buried.",
    "Comedy":           "Two rivals are forced together by circumstance and discover they need each other.",
    "Drama":            "A family confronts a long-buried truth that reshapes everyone's future.",
    "Awards/Prestige":  "A quiet act of conscience ripples outward, testing everyone it touches.",
}


def generate_scouted_concepts(team_name: str, cycle: int) -> list[dict]:
    """Deterministic per-(team, cycle) list of SCOUTED_CONCEPTS_PER_CYCLE
    candidate concepts -- the pool the student can Option (pre-fill their
    Greenlight draft from) or pass on this cycle. Each concept carries a
    stable id ("<cycle>_<i>") used to track optioned/poached status across
    cycles in ss.movie_scouted_optioned/ss.movie_scouted_poached. Reuses
    GENRES/CONCEPT_TYPES/SOURCE_MATERIALS so every concept is buildable
    with the real engine -- these aren't flavor-only like the Background
    Studio Slate, they're real starting points for the student's own
    project."""
    seed = (abs(hash(team_name)) + cycle * 6151 + 631) % (2 ** 31)
    rng = np.random.default_rng(seed)
    concepts = []
    for i in range(SCOUTED_CONCEPTS_PER_CYCLE):
        genre = GENRES[int(rng.integers(0, len(GENRES)))]
        concept_type = CONCEPT_TYPES[int(rng.integers(0, len(CONCEPT_TYPES)))]
        source_material = SOURCE_MATERIALS[int(rng.integers(0, len(SOURCE_MATERIALS)))]
        budget = float(rng.uniform(20, 150))
        concepts.append({
            "id":               f"{cycle}_{i}",
            "cycle":            cycle,
            "genre":            genre,
            "concept_type":     concept_type,
            "source_material":  source_material,
            "logline":          SCOUTED_LOGLINE_BY_GENRE.get(genre, "A bold new concept looking for a studio."),
            "budget_m":         round(budget, 0),
            "pa_spend_m":       round(budget * 0.5, 0),
            "star_power":       40,
            "screens":          2500,
        })
    return concepts


def draw_scouted_poach(team_name: str, concept_id: str) -> Optional[str]:
    """One-time chance a rival studio picks up a scouted concept the team
    never optioned -- own independent seed namespace (never perturbs
    draw_rival_poach's STUDIO_PARTNERS sequence, or anything else). Called
    exactly once per concept (by the caller's own checked_through gating,
    same posture as draw_rival_poach) -- this function itself doesn't track
    whether it's already been rolled. Returns the rival's name if poached,
    else None."""
    seed = (abs(hash(team_name)) + abs(hash(concept_id)) % 7919 + 4001) % (2 ** 31)
    rng = np.random.default_rng(seed)
    if rng.random() > SCOUTED_POACH_CHANCE:
        return None
    return RIVAL_STUDIOS[int(rng.integers(0, len(RIVAL_STUDIOS)))]


def resolve_scouted_outcome(concept: dict, rival: str) -> dict:
    """Once a scouted concept is confirmed poached, resolve its fate with
    the SAME financial engine every other movie uses -- own seed namespace
    (independent of the team's own draws and of generate_background_slate's)
    so a rival's fate for this concept is fixed the moment it's poached,
    not re-rolled on every render."""
    project = MovieProject(
        title=f"{concept['genre']} Project ({rival})", genre=concept["genre"],
        budget_m=concept["budget_m"], pa_spend_m=concept["pa_spend_m"],
        star_power=concept["star_power"], screens=concept["screens"], cycle=concept["cycle"],
        concept_type=concept["concept_type"], source_material=concept["source_material"],
    )
    seed_team = f"__scouted__{concept['id']}"
    multiplier = draw_actual_multiplier(seed_team, concept["cycle"], concept["genre"], concept["concept_type"])
    critical_score = draw_critical_reception(seed_team, concept["cycle"], concept["genre"])
    return {
        "concept_id": concept["id"],
        "rival":      rival,
        "cycle":      concept["cycle"],
        "title":      project.title,
        "genre":      concept["genre"],
        "concept_type": concept["concept_type"],
        "npv":        project.npv(multiplier, critical_score),
        "theme_park": project.theme_park_value(multiplier, critical_score),
        "window_days": project.window_days(),
    }
