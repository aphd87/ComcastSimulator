"""
Day 2 — Movies tab ("Universal Pictures")
Turn engine mirroring pages/simulation.py's Decisions -> Results pattern,
scaled to 3 greenlight-to-release cycles (see DESIGN_NOTES.md "Day 2").
Each cycle: Greenlight (production concept + P&A commit, cash out, no
revenue visibility yet) -> Release Strategy (the linear-vs-SVOD tension
from Day 1's Green Light tab, extended to theatrical/day-and-date/platform)
-> Results (actual outcome resolves against a hidden bull/base/bear draw).
"""
from dataclasses import replace
from html import escape

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from utils.movie_models import (
    MovieProject, GENRES, GENRE_INTL_MULT, GENRE_SVOD_APPEAL, RELEASE_STRATEGIES,
    SCENARIO_MULTIPLIERS, CYCLES_TOTAL, YEARS_PER_CYCLE, risk_adjusted_npv, capital_efficiency,
    strategic_fit_score, compute_movie_score, draw_actual_multiplier, nearest_scenario_label,
    draw_critical_reception, AWARDS_ELIGIBLE_GENRES, AWARDS_CONTENDER_THRESHOLD, AWARDS_WIN_THRESHOLD,
    CONCEPT_TYPES, INDIE_HORROR_BUDGET_CAP_M, WINDOWING_UNLOCK_CYCLE,
    SOURCE_MATERIALS, SOURCE_ACQUISITION_COST_M, SOURCE_OPENING_BOOST, STAR_POWER_COST_PER_POINT_M,
    IMAX_ELIGIBLE_GENRES, IMAX_OPENING_BOOST_PCT, IMAX_COST_M,
    generate_background_slate,
    generate_scouted_concepts, draw_scouted_poach, resolve_scouted_outcome, SCOUTED_POACH_CHANCE,
    SCOUTED_CONCEPTS_PER_CYCLE,
    LICENSING_PLATFORMS, DEFAULT_LICENSING_PLATFORM,
    PAY2_LICENSING_OPTIONS, PAY2_WINDOW_MONTH, PAY2_VALUE_PCT_OF_PAY1,
    THEATRICAL_RUN_LENGTHS, RUN_LENGTH_BOX_OFFICE_MULT,
    run_days_box_office_mult, RUN_LENGTH_DAYS_MIN, RUN_LENGTH_DAYS_MAX,
    pvod_price_band, PVOD_MARKET_CHECK_MONTHS, PVOD_CUT_STEP_FRAC,
    PVOD_HOLD_THROUGH_REJECTION_MULT, PVOD_CUT_RESPONSE_MULT, draw_pvod_market_rejection,
    draw_pvod_cut_buzz, PVOD_CUT_BUZZ_AWARDS_BONUS,
    LICENSING_BIDDERS, draw_licensing_bids, resolve_licensing_auction,
    PAY1_REVERSION_SHARE, LICENSING_RESHOP_MULT_RANGE, LICENSING_MAX_ROUNDS,
    draw_licensing_bidder_appetite, licensing_appetite_flavor,
    PVOD_PRICE_PREMIUM, PVOD_PRICE_DISCOUNT,
    SCREEN_COST_PER_SCREEN_M, MULTI_PICTURE_DEAL_CYCLES,
    STUDIO_ANNUAL_BUDGET_START_M, next_studio_budget,
    draw_production_trouble, draw_ancillary_surprise,
    FINANCING_STRUCTURES, PRESALE_OVERAGE_SHARE, PRESALE_SALES_AGENT_FEE_PCT, GENRE_TYPICAL_BUDGET_M, GENRE_SCREEN_DEMAND, MOVIE_LUCK_WEIGHT, TAX_CREDIT_PCT, participation_waterfall,
    TALENT_PARTNERS, STUDIO_PARTNERS, RIVAL_STUDIOS, draw_rival_claim, draw_hold_forfeit, draw_rival_poach,
    ORIGIN_MEDIUM_SOURCE_SYNERGY, TALENT_SOURCE_SYNERGY_MULT,
    EXHIBITOR_POSTURES, PAY1_LICENSING_OPTIONS, PAY1_LICENSE_DISCOUNT,
    AI_TOOLS_BUDGET_SAVINGS_PCT, AI_TOOLS_TIMELINE_SHIFT_MO, AI_TOOLS_CRITICAL_CEILING_MULT,
    draw_ai_tooling_setback, multiplier_to_stars, draw_ewom_piracy_swing,
    DEBUT_SEASONS, SEASON_OPENING_MULT, SEASON_GENRE_SYNERGY, SEASON_AWARDS_RECALL,
    FESTIVALS, generate_festival_slate, festival_acquisition_anchor_m,
    draw_festival_acquisition_bids, resolve_festival_acquisition, resolve_festival_acquisition_outcome,
    describe_pipeline_movie, STAR_POWER_BOOST_MAX, THEME_PARK_CRITICAL_GATE,
    UNIVERSAL_LIBRARY_IP, library_ip_opening_boost, TALENT_BASE_STAR_POWER,
    draw_pay2_revival, draw_pay2_offer_mults, pay2_revival_quantiles,
    festival_breakeven_bids, festival_interest,
    scout_read, SCOUTED_HOT_POACH_CHANCE,
    partner_renewal_fee, draw_partner_release_poach, PARTNER_RENEWAL_HIT_MULT, PARTNER_RELEASE_POACH_CHANCE,
    THEME_PARK_ELIGIBLE_GENRES,
)
from utils.game_state import (
    record_attempt, get_attempt_count, get_official_score, MAX_ATTEMPTS,
    compute_movie_notables, render_vs_competitors_board,
)
from utils.charts import base_layout, waterfall_chart, donut_chart, SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2

MOVIE_NETWORK_KEY = "movies"   # leaderboard/attempt-tracking key — same FERPA-safe infra as Day 1
RESEARCH_FEE_M = 4.0   # $M -- Movies-side parallel to TV's RESEARCH_FEE (app_pages/renewal.py),
                         # pricier since it's the whole cycle's one concentrated bet, not a
                         # portfolio line item
RELEASE_LABELS = {
    "wide_theatrical": "Wide Theatrical",
    "platform":         "Platform / Limited",
    "day_and_date":     "Day-and-Date (Peacock)",
}


# ── Session state init ─────────────────────────────────────────────────────────
def _init(ss):
    if ss.get("movie_cycle") is None:
        ss.movie_cycle = 1
    if ss.get("movie_phase") not in ("decisions", "results", "complete"):
        ss.movie_phase = "decisions"
    if not isinstance(ss.get("movie_log"), list):
        ss.movie_log = []          # finished cycles: [{project_kwargs, multiplier, npv, irr, ...}, ...]
    if not isinstance(ss.get("movie_draft"), dict):
        ss.movie_draft = {}        # in-progress project kwargs for the current cycle
    # Talent Deals (2026-08-04) -- ss.movie_overall_deal: partner_key or None,
    # a standing relationship for the rest of the level. ss.movie_talent_holds:
    # {partner_key: {"status": "pending"|"succeeded"|"failed"|"rival_claimed", ...}}.
    # ss.movie_rival_exclusive: {partner_key: rival_name} for partners a rival
    # studio has permanently signed while unclaimed by the team.
    if "movie_overall_deal" not in ss:
        ss.movie_overall_deal = None
    # Renewals (2026-10-05): the cycle the current banner deal was signed, and
    # the last cycle it was renewed through. Sessions that signed before this
    # existed count as signed this cycle, so nobody is asked mid-cycle.
    if "movie_overall_deal_signed_cycle" not in ss:
        ss.movie_overall_deal_signed_cycle = ss.get("movie_cycle", 1) if ss.get("movie_overall_deal") else None
    if "movie_overall_renewed_through" not in ss:
        ss.movie_overall_renewed_through = 0
    if not isinstance(ss.get("movie_partner_releases"), dict):
        ss.movie_partner_releases = {}   # {cycle: {"partner": key, "rival": name or None}}
    if not isinstance(ss.get("movie_talent_holds"), dict):
        ss.movie_talent_holds = {}
    if not isinstance(ss.get("movie_rival_exclusive"), dict):
        ss.movie_rival_exclusive = {}
    if "movie_rival_poach_checked_through" not in ss:
        ss.movie_rival_poach_checked_through = 0
    if "movie_talent_total_spend" not in ss:
        ss.movie_talent_total_spend = 0.0
    if not isinstance(ss.get("movie_research_paid"), dict):
        ss.movie_research_paid = {}   # {cycle: True} once paid -- see _decisions()'s Research section
    # Scouted Concepts (2026-08-18) -- ss.movie_scouted_optioned: set of
    # concept ids ("<cycle>_<i>") the team has ever optioned. ss.movie_
    # scouted_poached: {concept_id: resolve_scouted_outcome() dict} for
    # concepts a rival picked up after the team passed. ss.movie_scouted_
    # resolved_through: last PAST cycle whose unclaimed concepts have
    # already had their one-time poach roll -- see _resolve_scouted_
    # concept_transitions.
    if not isinstance(ss.get("movie_scouted_optioned"), set):
        ss.movie_scouted_optioned = set()
    if not isinstance(ss.get("movie_scouted_poached"), dict):
        ss.movie_scouted_poached = {}
    if "movie_scouted_resolved_through" not in ss:
        ss.movie_scouted_resolved_through = 0
    # Multi-Picture Talent Deal (2026-08-18) -- ss.movie_multi_picture_deals:
    # {talent_key: cycle_signed}, active through cycle_signed +
    # MULTI_PICTURE_DEAL_CYCLES - 1 inclusive. Real negotiation depth beyond
    # Holding: expensive-and-safe (no rival-claim/forfeit risk, locked for
    # multiple cycles) vs. Holding's cheap-and-risky one-shot booking.
    if not isinstance(ss.get("movie_multi_picture_deals"), dict):
        ss.movie_multi_picture_deals = {}
    # Studio Annual Budget (2026-08-18) -- a real, performance-linked
    # capital pool that explains and sizes the Background Studio Slate.
    # See next_studio_budget()/generate_background_slate's studio_budget_m
    # param.
    if "movie_studio_budget_m" not in ss:
        ss.movie_studio_budget_m = STUDIO_ANNUAL_BUDGET_START_M
    if "movie_studio_budget_updated_through" not in ss:
        ss.movie_studio_budget_updated_through = 0
    # Theatrical Mini-Run (2026-08-18) -- ss.movie_theatrical_resolved:
    # {cycle: {..resolved outcome.., "locked_inputs": {...}}} once the
    # student clicks "Run Theatrical Simulation" for that cycle. See
    # _resolve_movie_outcome()'s docstring for why this is safe to resolve
    # before PVOD/licensing decisions exist.
    if not isinstance(ss.get("movie_theatrical_resolved"), dict):
        ss.movie_theatrical_resolved = {}
    # PVOD Market Acceptance Checks (2026-08-18) -- ss.movie_pvod_checkpoints:
    # {cycle: [{"month", "price_before", "rejected", "response", "price_after"}, ...]},
    # resolved in order, at most len(PVOD_MARKET_CHECK_MONTHS) per cycle.
    # ss.movie_pvod_pending_rejection: {cycle: {"month", "price_before"}} when
    # a checkpoint just rejected and is awaiting the student's hold/cut choice.
    if not isinstance(ss.get("movie_pvod_checkpoints"), dict):
        ss.movie_pvod_checkpoints = {}
    if not isinstance(ss.get("movie_pvod_pending_rejection"), dict):
        ss.movie_pvod_pending_rejection = {}
    # Licensing Marketplace — Competitive Bidding (2026-08-18) --
    # ss.movie_licensing_auction: {cycle: {"bids": [...], "accepted": bool}}
    if not isinstance(ss.get("movie_licensing_auction"), dict):
        ss.movie_licensing_auction = {}
    # Film Festival Acquisitions (2026-08-18) -- ss.movie_festival_log:
    # {film_id: resolve_festival_acquisition_outcome() dict} for films the
    # TEAM won -- a real, visible pipeline addition, deliberately kept out
    # of ss.movie_log (never touches compute_movie_score, see the
    # utils/movie_models.py module comment above FESTIVALS). ss.movie_
    # festival_rival_log: {film_id: ...} for films a rival won instead
    # (either outbid, or the team never bid at all). ss.movie_festival_
    # resolved_through: last PAST cycle whose un-bid festival films have
    # already auto-resolved (team_bid_m=0, "passed") -- see
    # _resolve_festival_transitions.
    if not isinstance(ss.get("movie_festival_log"), dict):
        ss.movie_festival_log = {}
    if not isinstance(ss.get("movie_festival_rival_log"), dict):
        ss.movie_festival_rival_log = {}
    if "movie_festival_resolved_through" not in ss:
        ss.movie_festival_resolved_through = 0


# ── Small helpers ────────────────────────────────────────────────────────────
def _fmt_money(v: float) -> str:
    return f"−${abs(v):.1f}M" if v < 0 else f"${v:.1f}M"


def _bear_base_bull_chart(bear_npv: float, base_npv: float, bull_npv: float,
                          actual_npv: float | None = None, title: str = "Projected NPV Range") -> go.Figure:
    """Bear/base/bull range as an actual chart, not three text rows
    (2026-08-24, per a QA-pass finding: this is the sim's own stated
    central pedagogical device -- variance is graded, not hidden -- and was
    the least visually reinforced thing on the whole Greenlight screen).
    Reused at Results with actual_npv set so the real resolved outcome
    plots directly on the same range it was drawn from."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[bear_npv, base_npv, bull_npv], y=[0, 0, 0],
        mode="lines", line=dict(color=TEXT2, width=2), showlegend=False, hoverinfo="skip",
    ))
    vals   = [bear_npv, base_npv, bull_npv]
    colors = [SUCCESS if v >= 0 else DANGER for v in vals]
    fig.add_trace(go.Scatter(
        x=vals, y=[0, 0, 0], mode="markers+text",
        marker=dict(size=[16, 22, 16], color=colors, line=dict(width=2, color="#12141a")),
        text=["Bear", "Base", "Bull"], textposition="top center",
        textfont=dict(color="#ffffff", size=12),
        hovertemplate="%{text}: $%{x:.1f}M<extra></extra>",
        showlegend=False,
    ))
    if actual_npv is not None:
        fig.add_trace(go.Scatter(
            x=[actual_npv], y=[0], mode="markers+text",
            marker=dict(size=24, symbol="diamond", color=ACCENT, line=dict(width=2, color="#12141a")),
            text=["Actual"], textposition="bottom center",
            textfont=dict(color="#ffffff", size=12),
            hovertemplate="Actual: $%{x:.1f}M<extra></extra>",
            showlegend=False,
        ))
    fig.add_vline(x=0, line_dash="dash", line_color=WARN, opacity=0.4)
    fig.update_layout(**base_layout(title, height=170))
    fig.update_yaxes(visible=False, showgrid=False, range=[-1, 1])
    return fig


def _irr_label(irr) -> str:
    if irr is None:
        return "never recovers capital"
    if irr == float("inf"):
        return "> 500%"
    return f"{irr * 100:.0f}%"


def _cycle_year_range(cycle: int) -> tuple:
    """(start_year, end_year) this cycle spans, 1-indexed -- e.g. cycle 1 ->
    (1, 2), cycle 2 -> (3, 4), matching YEARS_PER_CYCLE's real 18-24-month
    greenlight-to-release production lead time. 2026-08-18, per explicit
    user request: student-facing copy should read in years, not the
    internal 'cycle' unit the turn engine is actually built around."""
    start = (cycle - 1) * YEARS_PER_CYCLE + 1
    end = cycle * YEARS_PER_CYCLE
    return start, end


def _cycle_years_label(cycle: int) -> str:
    start, end = _cycle_year_range(cycle)
    return f"Year {start}" if start == end else f"Years {start}-{end}"


def _current_distribution_window(window_days: int, months_elapsed: float, is_licensed_out: bool = False) -> str:
    """Which real distribution window a resolved movie is sitting in RIGHT
    NOW, given how many months have elapsed since its own release -- reuses
    the exact window boundaries MovieProject.windowed_cashflows() already
    computes (window_days()-derived theatrical exclusivity, then PVOD, then
    Pay-1 streaming/library), so this never drifts out of sync with the
    real financial engine. Takes window_days/is_licensed_out directly
    (rather than a full MovieProject) so it works identically for the
    student's own reconstructed project AND the lightweight background-
    slate dicts from generate_background_slate(), neither of which need to
    share a type. 2026-08-18, per explicit user request for a slate-wide
    scorecard showing where each movie actually is in its distribution run."""
    window_mo = window_days / 30.0
    if months_elapsed < 1.5:
        return "🎬 Theatrical (Opening)"
    if months_elapsed < window_mo + 1.0:
        return "🎬 Theatrical"
    if months_elapsed < window_mo + 3.0:
        return "📀 PVOD / Premium Rental"
    if months_elapsed < 24.0:
        return "📡 Licensed Out (Pay-1)" if is_licensed_out else "📡 Pay-1 Streaming (Peacock)"
    return "🗄️ Library / Deep Catalog"


def _active_talent_bonus(ss, genre: str, source_material: str = None) -> dict:
    """Combines whichever talent-relationship bonuses apply to this genre --
    2026-08-18, real fix: a standing Studio Partnership (Overall/First-Look
    Deal, ss.movie_overall_deal, STUDIO_PARTNERS) and a Holding Deal
    actually available this cycle (ss.movie_talent_holds, TALENT_PARTNERS)
    are genuinely different relationships and can both apply to the same
    project at once -- a studio can have both a standing banner deal AND a
    specific actor locked for the same movie. Previously these shared one
    dict and one either/or lookup, which was wrong on two counts: it
    conflated a studio-level relationship with an individual actor signing
    (the teaching note is explicit that Overall/First-Look Deals are with
    production banners, e.g. Ryan Reynolds' Maximum Effort with Paramount,
    not individual actors), and it silently dropped one bonus if both
    happened to apply. Same-kind bonuses (star_power_bonus /
    critical_score_bonus) now sum instead.

    source_material (default None): when a Holding Deal's origin_medium
    maps to this project's actual source_material (see
    ORIGIN_MEDIUM_SOURCE_SYNERGY), ITS bonus is amplified by
    TALENT_SOURCE_SYNERGY_MULT -- casting FOR the adaptation is a real
    strategic choice. Studio Partnership bonuses are never affected by this
    synergy -- a banner relationship isn't tied to any one actor's medium.

    Returns {} when nothing applies."""
    star_bonus, crit_bonus = 0.0, 0.0
    partner_names = []
    synergy = False

    studio_key = ss.get("movie_overall_deal")
    if studio_key:
        studio = STUDIO_PARTNERS[studio_key]
        if studio["specialty"] == genre:
            star_bonus += studio.get("star_power_bonus", 0)
            crit_bonus += studio.get("critical_score_bonus", 0.0)
            partner_names.append(studio["name"])

    # Active talent sources this cycle: a succeeded Holding Deal (one-shot,
    # already resolved for THIS cycle) and/or a Multi-Picture Deal (signed
    # once, active for MULTI_PICTURE_DEAL_CYCLES cycles from signing --
    # 2026-08-18, see MULTI_PICTURE_DEAL_CYCLES's own comment). A talent
    # could in principle satisfy both (UI gating discourages it, doesn't
    # forbid it) -- bonuses still just sum, same posture as Studio+Holding above.
    active_talent_keys = set()
    for k, h in ss.get("movie_talent_holds", {}).items():
        if h.get("status") == "succeeded" and h.get("available_cycle") == ss.movie_cycle:
            active_talent_keys.add(k)
    for k, signed_cycle in ss.get("movie_multi_picture_deals", {}).items():
        if signed_cycle <= ss.movie_cycle < signed_cycle + MULTI_PICTURE_DEAL_CYCLES:
            active_talent_keys.add(k)

    # 2026-10-05: a held/signed actor's bonus applies only when that actor is
    # actually CAST as this film's lead (see _contracted_talent and the Lead
    # Actor pick in Greenlight), in one of their best genres.
    lead_actor = ss.get("movie_draft", {}).get("lead_actor")
    for talent_key in active_talent_keys:
        talent = TALENT_PARTNERS[talent_key]
        if talent_key == lead_actor and genre in talent.get("best_genres", [talent["specialty"]]):
            t_star = talent.get("star_power_bonus", 0)
            t_crit = talent.get("critical_score_bonus", 0.0)
            synergy_material = ORIGIN_MEDIUM_SOURCE_SYNERGY.get(talent.get("origin_medium"))
            if synergy_material and synergy_material == source_material:
                t_star *= TALENT_SOURCE_SYNERGY_MULT
                t_crit *= TALENT_SOURCE_SYNERGY_MULT
                synergy = True
            star_bonus += t_star
            crit_bonus += t_crit
            partner_names.append(talent["name"])

    if not partner_names:
        return {}
    bonus = {"partner_name": " & ".join(partner_names), "synergy": synergy}
    if star_bonus:
        bonus["star_power_bonus"] = star_bonus
    if crit_bonus:
        bonus["critical_score_bonus"] = crit_bonus
    return bonus


def _step_status(ss) -> list:
    """Every required step of a cycle, in page order, as (label, anchor,
    done, todo) -- 2026-10-05, per explicit user request that Partnerships,
    Scouted Concepts, Festivals and Holding Deals are required, not
    optional ("no passing"). Drives both the step bar at the top of
    Decisions and the Simulate gate at the bottom. Each step is only
    required while it's actually possible (e.g. every banner already
    poached, or no next film to hold an actor for)."""
    cyc = ss.movie_cycle
    partnerships = ((bool(ss.movie_overall_deal) and not _partner_renewal_due(ss))
                    or all(k in ss.movie_rival_exclusive for k in STUDIO_PARTNERS))
    scouted = any(str(cid).startswith(f"{cyc}_") for cid in ss.movie_scouted_optioned)
    fest_ids = {f["id"] for f in generate_festival_slate(ss.team_name, cyc)}
    festivals = any(i in ss.movie_festival_log or i in ss.movie_festival_rival_log for i in fest_ids)
    logline = ss.get(f"movie_logline_{cyc}", ss.movie_draft.get("logline", ""))
    greenlight = len((logline or "").strip()) >= 20
    final_film = cyc >= CYCLES_TOTAL
    holding = (final_film
               or any(h.get("cycle_placed") == cyc for h in ss.movie_talent_holds.values())
               or any(signed <= cyc + 1 < signed + MULTI_PICTURE_DEAL_CYCLES
                      for signed in ss.movie_multi_picture_deals.values()))
    release = ss.movie_theatrical_resolved.get(cyc) is not None
    pay2 = [("Pay-2 (earlier films)", "release", False,
             "choose Pay-2 for each earlier film in the Release Plan table")] \
        if _pending_pay2_films(ss) else []
    return [
        ("Partnerships", "talent", partnerships,
         "renew or replace your Studio Partnership" if ss.get("movie_overall_deal")
         else "sign a Studio Partnership"),
        ("Scouted Concepts", "scouted", scouted, "option at least one Scouted Concept"),
        ("Festivals", "festivals", festivals, "bid on at least one festival film"),
        ("Greenlight", "greenlight", greenlight, "write your pitch / logline"),
        ("Holding Deals", "holding", holding, "place a Holding Deal or sign a Multi-Picture Deal"),
    ] + pay2 + [
        ("Release", "release", release, "run the Theatrical Simulation"),
    ]


def _partner_renewal_due(ss) -> bool:
    """A signed banner asks for renewal every cycle after the one it was
    signed in, until renewed for this cycle (2026-10-05)."""
    signed = ss.get("movie_overall_deal_signed_cycle")
    return (bool(ss.get("movie_overall_deal")) and signed is not None and signed < ss.movie_cycle
            and ss.get("movie_overall_renewed_through", 0) < ss.movie_cycle)


def _numbered_steps(ss) -> list:
    """(number, label, anchor, done, todo). Numbers match the section titles
    1-6; the Pay-2 step for earlier films lives inside section 6."""
    out, n = [], 0
    for label, anchor, done, todo in _step_status(ss):
        if label.startswith("Pay-2"):
            out.append((6, label, anchor, done, todo))
        else:
            n += 1
            out.append((n, label, anchor, done, todo))
    return out


def _step_bar(ss):
    """Compact, clickable step bar -- the one place a student sees where
    they are in this film's cycle and what's left before Simulate."""
    steps = _step_status(ss)
    chips = []
    for i, label, anchor, done, _ in _numbered_steps(ss):
        bg, border, mark = (("rgba(102,187,106,.15)", SUCCESS, "✓") if done
                            else ("#1a1d26", "#252836", str(i)))
        chips.append(f'<a href="#{anchor}" style="text-decoration:none;color:#ffffff;background:{bg};'
                     f'border:1px solid {border};border-radius:14px;padding:3px 10px;font-size:13px;'
                     f'white-space:nowrap;"><b>{mark}</b> {label}</a>')
    ready = all(s[2] for s in steps)
    chips.append(f'<a href="#simulate" style="text-decoration:none;color:{"#0b0c10" if ready else "#ffffff"};'
                 f'background:{SUCCESS if ready else "#1a1d26"};border:1px solid {SUCCESS if ready else "#252836"};'
                 f'border-radius:14px;padding:3px 10px;font-size:13px;white-space:nowrap;">'
                 f'<b>7</b> Simulate{" ▶" if ready else " 🔒"}</a>')
    st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;">{"".join(chips)}</div>',
                unsafe_allow_html=True)


def _section_your_slate(ss, title: str = "🎬 Your Slate"):
    """One clear row per film this team has made (2026-10-05, per explicit
    user request: "there should be a clear table"). Own films only --
    other teams' results live on the leaderboard."""
    log = sorted(ss.movie_log, key=lambda r: r["cycle"])
    if not log:
        return
    rows = []
    for r in log:
        kw = r["project_kwargs"]
        p = MovieProject(**kw)
        domestic = p.domestic_box_office(r["multiplier"])
        worldwide = domestic + p.international_box_office(domestic)
        lead = kw.get("lead_actor")
        ip = kw.get("library_ip")
        rows.append({
            "Film":            f"{r['cycle']} of {CYCLES_TOTAL}",
            "Years":           _cycle_years_label(r["cycle"]),
            "Title":           kw["title"],
            "Genre / Concept": f"{kw['genre']} ({kw.get('concept_type', 'New IP')})",
            "Source / IP":     UNIVERSAL_LIBRARY_IP[ip]["name"] if ip in UNIVERSAL_LIBRARY_IP
                               else kw.get("source_material", "Original Screenplay"),
            "Lead":            TALENT_PARTNERS[lead]["name"] if lead in TALENT_PARTNERS
                               else f"Unnamed (Star Power {kw['star_power']})",
            "Release":         RELEASE_LABELS.get(kw["release_strategy"], kw["release_strategy"]),
            "Run (days)":      p.window_days(),
            "Capital at Risk": f"${r['capital_at_risk']:.0f}M",
            "Opening Wknd":    f"${p.opening_weekend():.0f}M",
            "Worldwide B.O.":  f"${worldwide:.0f}M",
            "Critics":         f"{r['critical_score']:.0f}/100",
            "NPV":             _fmt_money(r["npv"]),
            "Result":          "✅ Made money" if r["npv"] >= 0 else "❌ Lost money",
        })
    total = sum(r["npv"] for r in log)
    st.markdown(f'<div class="section-title">{title} '
                f'<span class="text-xs text-muted">({len(log)} of {CYCLES_TOTAL} films · total NPV '
                f'{_fmt_money(total)})</span></div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _pending_pay2_films(ss) -> list:
    """Earlier films whose Pay-2 window opens now and hasn't been decided
    yet (2026-10-05). Day-and-Date films are excluded -- that strategy
    commits the title to Peacock, same as Pay-1."""
    return [r for r in sorted(ss.movie_log, key=lambda r: r["cycle"])
            if r["cycle"] < ss.movie_cycle and r.get("pay2_decided_cycle") is None
            and r["project_kwargs"].get("release_strategy") != "day_and_date"]


def _film_npv(entry: dict, kw: dict) -> float:
    """A logged film's NPV under (possibly changed) project kwargs, with the
    same resolved draws it was simulated with."""
    return MovieProject(**kw).npv(entry["multiplier"], entry["critical_score"],
                                  pvod_mult=entry.get("pvod_mult", 1.0),
                                  theme_park_mult=entry.get("theme_park_mult", 1.0),
                                  ewom_mult=entry.get("ewom_mult", 1.0))


def _contracted_talent(ss) -> list:
    """TALENT_PARTNERS keys this studio can cast THIS cycle: a Holding Deal
    that held together for this cycle, or an active Multi-Picture Deal."""
    keys = [k for k, h in ss.get("movie_talent_holds", {}).items()
            if h.get("status") == "succeeded" and h.get("available_cycle") == ss.movie_cycle]
    keys += [k for k, signed in ss.get("movie_multi_picture_deals", {}).items()
             if signed <= ss.movie_cycle < signed + MULTI_PICTURE_DEAL_CYCLES and k not in keys]
    return keys


def _current_project(ss) -> MovieProject:
    d = ss.movie_draft
    genre = d.get("genre", GENRES[0])
    bonus = _active_talent_bonus(ss, genre, d.get("source_material", SOURCE_MATERIALS[0]))
    star_power = d.get("star_power", 50) + bonus.get("star_power_bonus", 0)
    return MovieProject(
        title=d.get("title", f"Untitled {_cycle_years_label(ss.movie_cycle)} Release"),
        genre=genre,
        budget_m=d.get("budget_m", 60.0),
        pa_spend_m=d.get("pa_spend_m", 40.0),
        star_power=min(100, star_power),
        screens=d.get("screens", 3000),
        cycle=ss.movie_cycle,
        release_strategy=d.get("release_strategy", "wide_theatrical"),
        concept_type=d.get("concept_type", CONCEPT_TYPES[0]),
        financing_structure=d.get("financing_structure", "self_finance"),
        exhibitor_posture=d.get("exhibitor_posture", "standard"),
        pay1_licensing=d.get("pay1_licensing", "keep"),
        ai_production_tools=d.get("ai_production_tools", False),
        debut_season=d.get("debut_season", "Off-Peak"),
        source_material=d.get("source_material", SOURCE_MATERIALS[0]),
        imax_release=d.get("imax_release", False),
        pay1_platform=d.get("pay1_platform", DEFAULT_LICENSING_PLATFORM),
        pay1_auction_fee_m=d.get("pay1_auction_fee_m"),
        pay1_auction_winner=d.get("pay1_auction_winner"), pay1_auction_term_mo=d.get("pay1_auction_term_mo"),
        pay2_licensing=d.get("pay2_licensing", "keep"),
        pay2_platform=d.get("pay2_platform", DEFAULT_LICENSING_PLATFORM),
        theatrical_run_length=d.get("theatrical_run_length"),
        theatrical_run_days=d.get("theatrical_run_days"),
        pvod_dynamic_pricing=d.get("pvod_dynamic_pricing", False),
        pvod_chosen_price=d.get("pvod_chosen_price"),
        library_ip=d.get("library_ip"),
        lead_actor=d.get("lead_actor"),
    )


# ── Studio Partnerships (Overall/First-Look) & Holding Deals, rivals ────────
def _resolve_talent_cycle_transitions(ss):
    """Two deterministic, seeded resolutions run at the top of every
    Decisions render (safe to call repeatedly -- gated so each only fires
    once per real cycle transition, same posture as preview_show_variance's
    replay-safety on the TV side):
    1. Any Holding Deal placed last cycle (status 'pending', on an
       individual TALENT_PARTNERS actor) resolves to succeeded/failed.
    2. Any STUDIO_PARTNERS banner not yet under an Overall/First-Look Deal
       may have been poached by a rival studio -- the real cost of passing
       on a standing relationship. 2026-08-18: scoped to studios only (not
       individual talent) -- an Overall/First-Look Deal is the one genuinely
       standing, level-long relationship; a Holding Deal is already a
       one-cycle, project-specific booking with its own real risk (rival
       claim + hold forfeit), so a THIRD "permanently gone" risk on the same
       individual actor would be redundant, not a new lesson.
    Returns (resolved_hold_key_or_None, newly_poached: dict) for the caller
    to render as this-render notices."""
    resolved_hold_key = None
    for key, h in ss.movie_talent_holds.items():
        if h.get("status") == "pending" and h.get("cycle_placed") == ss.movie_cycle - 1:
            forfeit = draw_hold_forfeit(ss.team_name, h["cycle_placed"], key)
            if forfeit:
                h["status"] = "failed"
                h["forfeit_reason"] = forfeit
            else:
                h["status"] = "succeeded"
                h["available_cycle"] = ss.movie_cycle
            resolved_hold_key = key

    newly_poached = {}
    checked_through = ss.movie_rival_poach_checked_through
    if ss.movie_cycle > checked_through:
        for c in range(checked_through + 1, ss.movie_cycle + 1):
            for key in STUDIO_PARTNERS:
                if key == ss.movie_overall_deal or key in ss.movie_rival_exclusive:
                    continue
                rival = draw_rival_poach(ss.team_name, key, c)
                if rival:
                    ss.movie_rival_exclusive[key] = rival
                    newly_poached[key] = rival
        ss.movie_rival_poach_checked_through = ss.movie_cycle
    return resolved_hold_key, newly_poached


def _section_distribution_pipeline(ss):
    """Slate-wide scorecard, rendered before Studio Partnerships -- one row
    per movie in the studio's pipeline this level, showing where it
    actually sits in its distribution run right now (not a hypothetical),
    whether it earned theme-park/merch revenue, and a Sequel Potential
    signal. 2026-08-18, per explicit user request ("is there a scorecard...
    so we can see where each movie is from year to year in the distribution
    run... is there a way to tabulate this?").

    Three row sources, clearly distinguished by a Slate column:
    - "Yours": the student's own real greenlit-and-simulated movies
      (ss.movie_log) -- reuses each project's own real windowed_cashflows()
      boundaries via _current_distribution_window, never a parallel
      timeline, so it can't drift out of sync with the financial engine.
    - "Studio": a non-interactive background slate (generate_background_
      slate) for every year through the current cycle -- per the same
      conversation's follow-up request ("in year 1, there should be 5-10
      movies already slated to go out that year... students get to review
      another 5-10 the following year... begin to see some of them
      bloom"), scoped down from a full portfolio-rewrite to this
      lightweight flavor layer (explicit user choice over the larger
      option) -- these never affect compute_movie_score, purely context so
      the studio's slate looks and feels busy around the one real bet the
      student is actually making each cycle.
    - "Rival": Scouted Concepts the team passed on and a rival studio
      picked up (ss.movie_scouted_poached) -- the real, visible
      competitive consequence per explicit user request ("do we get
      updates... about rival studios buying movies we pass on?"). Shown
      with a fixed "🏆 Rival Release" window label since these resolve
      immediately on poaching, not on the team's own timeline.

    Renders from Cycle 1 onward regardless of whether the student has
    simulated anything yet -- the background slate alone is enough to show
    "movies already slated to go out this year". Header line shows the
    Studio Annual Budget (2026-08-18, see next_studio_budget) -- a real,
    performance-linked capital pool that also sizes the Background Slate
    below (a shrunk pool visibly produces a smaller/cheaper background
    slate)."""
    st.markdown('<div class="section-title">Distribution Pipeline — Slate Scorecard</div>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="text-xs text-ink2 mb-1">🏦 Studio Annual Budget: '
        f'<b class="text-ink">${ss.movie_studio_budget_m/1000:,.2f}B</b> '
        f'<span class="text-muted">— moves year to year based on how the slate actually performs. '
        f'A soft signal for your own Greenlight spend below, not a hard cap — your Production Budget '
        f'input can still go up to $300M regardless of how far this has shrunk.</span></p>',
        unsafe_allow_html=True)
    st.caption("Where every movie in the studio's pipeline actually sits in its distribution run right "
               "now, based on real elapsed time since each one's own release. \"Yours\" is your own "
               "greenlit slate; \"Studio\" is the rest of the studio's non-interactive background slate "
               "for context — it never affects your score.")

    def _platform_label(project_kwargs: dict, licensing_key: str, platform_key: str) -> str:
        if project_kwargs.get(licensing_key, "keep") != "license_out":
            return "Keep In-House"
        # 2026-08-18: an accepted competitive bid (Pay-1 only) carries its
        # own winner name, not a LICENSING_PLATFORMS key -- check it first
        # so it isn't silently mislabeled via LICENSING_PLATFORMS' fallback.
        auction_winner = project_kwargs.get("pay1_auction_winner")
        if licensing_key == "pay1_licensing" and auction_winner:
            return f"{auction_winner} (bid)"
        platform = project_kwargs.get(platform_key, DEFAULT_LICENSING_PLATFORM)
        return LICENSING_PLATFORMS.get(platform, LICENSING_PLATFORMS[DEFAULT_LICENSING_PLATFORM])["name"]

    rows = []   # list of (cycle, row_dict) so the final sort is numeric, not lexical on the year label
    seen_genres_with_sequel = {r["project_kwargs"]["genre"] for r in ss.movie_log
                                if r["project_kwargs"]["concept_type"] == "Sequel"}
    for entry in ss.movie_log:
        project = MovieProject(**entry["project_kwargs"])
        months_elapsed = (ss.movie_cycle - entry["cycle"]) * YEARS_PER_CYCLE * 12.0
        sequel_potential = (
            "🎬 Yes" if (project.concept_type != "Sequel"
                         and (entry["npv"] > 0 or entry.get("cut_buzz_sequel"))
                         and project.genre not in seen_genres_with_sequel)
            else "—"
        )
        rows.append((entry["cycle"], {
            "Slate":             "Yours",
            "Year":              _cycle_years_label(entry["cycle"]),
            "Title":             project.title,
            "Description":       describe_pipeline_movie(project.title, project.genre, project.concept_type,
                                                         entry.get("logline")),
            "Genre / Concept":   f"{project.genre} ({project.concept_type})",
            "Current Window":    _current_distribution_window(project.window_days(), months_elapsed,
                                                                project.is_licensing_out()),
            "NPV":               _fmt_money(entry["npv"]),
            "Theme Park / Merch": f"${entry['theme_park']:.1f}M" if entry.get("theme_park", 0) > 0 else "—",
            "Pay-1":             _platform_label(entry["project_kwargs"], "pay1_licensing", "pay1_platform"),
            "Pay-2":             _platform_label(entry["project_kwargs"], "pay2_licensing", "pay2_platform"),
            "Sequel Potential":  sequel_potential,
        }))

    for cyc in range(1, ss.movie_cycle + 1):
        for bg in generate_background_slate(ss.team_name, cyc, studio_budget_m=ss.movie_studio_budget_m):
            months_elapsed = (ss.movie_cycle - bg["cycle"]) * YEARS_PER_CYCLE * 12.0
            rows.append((cyc, {
                "Slate":             "Studio",
                "Year":              _cycle_years_label(bg["cycle"]),
                "Title":             bg["title"],
                "Description":       describe_pipeline_movie(bg["title"], bg["genre"], bg["concept_type"]),
                "Genre / Concept":   f"{bg['genre']} ({bg['concept_type']})",
                "Current Window":    _current_distribution_window(bg["window_days"], months_elapsed),
                "NPV":               _fmt_money(bg["npv"]),
                "Theme Park / Merch": f"${bg['theme_park']:.1f}M" if bg.get("theme_park", 0) > 0 else "—",
                "Pay-1":             "—",
                "Pay-2":             "—",
                "Sequel Potential":  "—",
            }))

    for outcome in ss.movie_scouted_poached.values():
        rows.append((outcome["cycle"], {
            "Slate":             "Rival",
            "Year":              _cycle_years_label(outcome["cycle"]),
            "Title":             f"{outcome['title']} ({outcome['rival']})",
            "Description":       describe_pipeline_movie(outcome["title"], outcome["genre"],
                                                         outcome["concept_type"], outcome.get("logline")),
            "Genre / Concept":   f"{outcome['genre']} ({outcome['concept_type']})",
            "Current Window":    "🏆 Rival Release",
            "NPV":               _fmt_money(outcome["npv"]),
            "Theme Park / Merch": f"${outcome['theme_park']:.1f}M" if outcome.get("theme_park", 0) > 0 else "—",
            "Pay-1":             "—",
            "Pay-2":             "—",
            "Sequel Potential":  "—",
        }))

    # Film Festival Acquisitions (2026-08-18) -- won films are a real
    # pipeline addition ("Festival" slate), shown with their own real
    # distribution window same as "Yours" rows. Deliberately excluded from
    # compute_movie_score (see the FESTIVALS module comment in
    # utils/movie_models.py) -- this scorecard is context, not the score.
    for outcome in ss.movie_festival_log.values():
        months_elapsed = (ss.movie_cycle - outcome["cycle"]) * YEARS_PER_CYCLE * 12.0
        rows.append((outcome["cycle"], {
            "Slate":             "Festival",
            "Year":              _cycle_years_label(outcome["cycle"]),
            "Title":             f"{outcome['title']} ({outcome['festival_name']})",
            "Description":       describe_pipeline_movie(outcome["title"], outcome["genre"],
                                                         outcome["concept_type"], outcome.get("logline")),
            "Genre / Concept":   f"{outcome['genre']} ({outcome['concept_type']})",
            "Current Window":    _current_distribution_window(outcome["window_days"], months_elapsed),
            "NPV":               _fmt_money(outcome["npv"]),
            "Theme Park / Merch": f"${outcome['theme_park']:.1f}M" if outcome.get("theme_park", 0) > 0 else "—",
            "Pay-1":             "—",
            "Pay-2":             "—",
            "Sequel Potential":  "—",
        }))
    for outcome in ss.movie_festival_rival_log.values():
        rows.append((outcome["cycle"], {
            "Slate":             "Festival Rival",
            "Year":              _cycle_years_label(outcome["cycle"]),
            "Title":             f"{outcome['title']} ({outcome['winner']}, {outcome['festival_name']})",
            "Description":       describe_pipeline_movie(outcome["title"], outcome["genre"],
                                                         outcome["concept_type"], outcome.get("logline")),
            "Genre / Concept":   f"{outcome['genre']} ({outcome['concept_type']})",
            "Current Window":    "🏆 Rival Release",
            "NPV":               _fmt_money(outcome["npv"]),
            "Theme Park / Merch": f"${outcome['theme_park']:.1f}M" if outcome.get("theme_park", 0) > 0 else "—",
            "Pay-1":             "—",
            "Pay-2":             "—",
            "Sequel Potential":  "—",
        }))

    rows.sort(key=lambda cr: (cr[0], cr[1]["Slate"]))
    # Taller rows so the few-sentence Description wraps instead of truncating;
    # hover any cell to see its full text.
    st.dataframe(pd.DataFrame([r for _, r in rows]), use_container_width=True, hide_index=True,
                 height=min(560, 40 + 80 * len(rows)), row_height=80,
                 column_config={"Description": st.column_config.TextColumn(
                     "Description", width=420,
                     help="What the movie is about and what its concept type means commercially.")})
    st.divider()


def _research_covers(bought, genre: str, concept_type: str) -> bool:
    """Research is bought for one Genre + Concept Type (2026-10-05 QA fix:
    a single purchase used to reveal the seeded draw for every combination
    as the dropdowns changed). Legacy sessions stored a bare True."""
    if bought is True:
        return True
    return bool(bought) and bought.get("genre") == genre and bought.get("concept_type") == concept_type


def _research_label(bought) -> str:
    return "this concept" if bought is True else f"{bought.get('genre')} · {bought.get('concept_type')}"


def _render_research_card(ss, project: MovieProject, logline: str):
    """Paid Research preview, 2026-10-05 rewrite per explicit user request
    ("clearer metrics... should consider the title, genre, concept type and
    source material along with the logline"). Same seeded draws Simulate
    uses, translated into dollars via the real engine for the full current
    draft, so source material, budget, P&A, stars and screens all show up."""
    genre, concept_type = project.genre, project.concept_type
    preview_mult = draw_actual_multiplier(ss.team_name, ss.movie_cycle, genre, concept_type)
    preview_cs = draw_critical_reception(ss.team_name, ss.movie_cycle, genre,
                                         ai_production_tools=project.ai_production_tools)
    stars = multiplier_to_stars(preview_mult, genre, concept_type)
    star_str = "⭐" * stars + "☆" * (5 - stars)
    bo_c = SUCCESS if stars >= 4 else (WARN if stars == 3 else DANGER)
    cs_c = SUCCESS if preview_cs >= 55 else (WARN if preview_cs >= 35 else DANGER)
    cs_tier = ("Acclaimed" if preview_cs >= 75 else "Well Reviewed" if preview_cs >= 55
               else "Mixed" if preview_cs >= 35 else "Panned")
    bo_word = {5: "Breakout", 4: "Strong", 3: "Solid", 2: "Soft", 1: "Weak"}.get(stars, "")

    opening = project.opening_weekend()
    domestic = project.domestic_box_office(preview_mult)
    worldwide = domestic + project.international_box_office(domestic)
    base_domestic = project.domestic_box_office("base")
    base_ww = base_domestic + project.international_box_office(base_domestic)
    vs_base = (worldwide / base_ww - 1) * 100 if base_ww else 0.0
    npv_here = project.npv(preview_mult, preview_cs)
    npv_c = SUCCESS if npv_here >= 0 else DANGER
    src_boost = (SOURCE_OPENING_BOOST.get(project.source_material, 1.0) - 1) * 100
    src_name = project.source_material
    if project.library_ip in UNIVERSAL_LIBRARY_IP:
        src_boost = (library_ip_opening_boost(project.library_ip, genre) - 1) * 100
        src_name = f"Revived Universal IP: {UNIVERSAL_LIBRARY_IP[project.library_ip]['name']}"

    implications = [
        f"{'✅ Clears' if preview_cs >= THEME_PARK_CRITICAL_GATE else '❌ Misses'} the "
        f"{THEME_PARK_CRITICAL_GATE}/100 bar for theme-park/merch revenue"]
    if genre in AWARDS_ELIGIBLE_GENRES:
        implications.append(
            f"{'✅ An' if preview_cs >= AWARDS_CONTENDER_THRESHOLD else '❌ Not an'} awards contender "
            f"(needs {AWARDS_CONTENDER_THRESHOLD}+)")
    src_line = (f"{src_name}: +{src_boost:.0f}% opening from a built-in fan base"
                if src_boost > 0 else f"{src_name}: no built-in fan base")
    pitch = escape(logline.strip()) if logline.strip() else "<i>No pitch written yet.</i>"

    st.markdown(f"""
    <div class="rounded-lg border border-line bg-surface2 p-3 mb-2" style="color:#ffffff;">
      <div style="font-size:13px;margin-bottom:8px;line-height:1.5;">
        <b>Researching:</b> "{escape(project.title)}" · {genre} · {concept_type} · {escape(src_name)}<br>
        <b>Pitch:</b> {pitch}
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:8px;">
        <div><div class="text-[10px] font-mono">AUDIENCE DEMAND</div>
          <div class="text-sm" style="color:{bo_c};">{star_str} {bo_word}</div>
          <div style="font-size:12px;">{vs_base:+.0f}% vs. a typical run</div></div>
        <div><div class="text-[10px] font-mono">OPENING WEEKEND</div>
          <div class="text-sm">${opening:,.1f}M</div>
          <div style="font-size:12px;">at your current screens, stars &amp; P&amp;A</div></div>
        <div><div class="text-[10px] font-mono">WORLDWIDE BOX OFFICE</div>
          <div class="text-sm">${worldwide:,.0f}M</div>
          <div style="font-size:12px;">${domestic:,.0f}M domestic + ${worldwide - domestic:,.0f}M intl</div></div>
        <div><div class="text-[10px] font-mono">CRITICS</div>
          <div class="text-sm" style="color:{cs_c};">{preview_cs:.0f}/100 · {cs_tier}</div></div>
        <div><div class="text-[10px] font-mono">NPV AT THESE SIGNALS</div>
          <div class="text-sm" style="color:{npv_c};">{_fmt_money(npv_here)}</div>
          <div style="font-size:12px;">wide release, before risk events</div></div>
      </div>
      <div style="font-size:12px;line-height:1.5;">
        📚 {src_line}<br>🎭 {' · '.join(implications)}
      </div>
      <div style="font-size:12px;line-height:1.5;margin-top:6px;">
        Demand and critics are for this Genre and Concept Type. The dollar figures follow Source Material,
        Production Budget, P&amp;A, Star Power and Screens, so change those and watch these move.
        Your title and pitch are how the movie is presented to the class; they don't change the numbers.
        Release Strategy, Production Trouble, the AI Tooling Setback, Ancillary Markets Surprise, and
        eWOM &amp; Piracy still apply on top of this at Simulate.
      </div>
    </div>
    """, unsafe_allow_html=True)


def _star_vs_critical_explainer():
    """What each partner bonus type actually buys, 2026-10-05 per explicit
    user request ("explain what star power vs critical reception offers
    students"). Numbers come straight from the engine constants so the
    explanation can't drift from the model."""
    st.markdown(f"""
    <div class="rounded-lg border border-line bg-surface2 p-3 mb-3" style="color:#ffffff;">
      <div class="text-sm font-semibold mb-2">⭐ Star Power vs 🎭 Critical Reception — what a partner bonus buys you</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;font-size:13px;line-height:1.5;">
        <div>
          <b>⭐ Star Power = a bigger opening.</b> Recognizable talent draws audiences on name alone,
          so Star Power (0-100) scales your opening weekend by up to +{STAR_POWER_BOOST_MAX * 100:.0f}% at 100.
          It's front-loaded theatrical money — predictable, and worth the most in NPV because it arrives first.
          You can also buy it directly with the Star Power slider (${STAR_POWER_COST_PER_POINT_M:.2f}M per point),
          so a +Star Power partner is effectively discounted casting. Best fit: wide-release, commercial
          genres where opening weekend is the business.
        </div>
        <div>
          <b>🎭 Critical Reception = longer legs.</b> Reviews (0-100) are a random draw after release, shaped by
          genre — you can't buy them, only shift the odds upward. The score drives the long tail: library and
          catalog value scale from 0.7x to 1.8x, movies under {THEME_PARK_CRITICAL_GATE} can't earn theme-park/merch
          revenue, and Drama/Awards titles at {AWARDS_CONTENDER_THRESHOLD}+ get an awards-season re-release
          bump ({AWARDS_WIN_THRESHOLD}+ wins the Oscar). Best fit: prestige and franchise-building plays.
        </div>
      </div>
      <div class="mt-2" style="font-size:13px;line-height:1.5;">
        <b>The trade-off:</b> Star Power is <i>marketability</i> — a known, near-term payoff.
        Critical Reception is <i>quality</i> — a riskier, back-loaded payoff that keeps paying for years.
        Match the bonus to how your movies actually make money.
      </div>
    </div>
    """, unsafe_allow_html=True)


def _section_studio_partnerships(ss, newly_poached: dict):
    """Standing Overall/First-Look Deal with a production STUDIO/banner --
    rendered before Greenlight, same placement rationale as TV/Streaming's
    Sports Rights section: a standing relationship should shape what gets
    built, not the other way around. 2026-08-18, real fix: this used to
    share one dict/mechanic with individual-actor Holding Deals, which
    conflated two genuinely different real-world relationships -- the
    teaching note is explicit that Overall/First-Look Deals are studio-level
    (Ryan Reynolds' Maximum Effort production house has a deal with
    Paramount), not a direct signing of one actor. Signed once, benefits
    every remaining cycle whose genre matches the banner's specialty.
    Banners nobody signs can be poached permanently by a rival studio each
    cycle -- passing on the relationship isn't a neutral no-op. Individual
    Holding Deals (booking a specific actor's window for a specific,
    already-greenlit movie) render separately, after Greenlight -- see
    _section_holding_deals. newly_poached comes from a single shared
    _resolve_talent_cycle_transitions(ss) call in _decisions() -- calling
    it separately per section would double-process the same cycle
    transition."""
    st.markdown('<a id="talent"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">1 · Studio Partnerships '
                '<span class="text-xs text-muted">(required · Overall/First-Look Deal: sign, then renew or replace each cycle)</span></div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-2">Sign a standing deal with a production banner for '
        'first-look access to whatever they\'re developing next: a bonus on every film in their '
        'specialty genre. From the next cycle on they ask for a renewal fee each cycle (more after a '
        'hit). A banner nobody signs can quietly get poached by a rival studio.</p>',
        unsafe_allow_html=True)
    _star_vs_critical_explainer()

    for key, rival in newly_poached.items():
        st.markdown(f"""
        <div class="rounded-lg p-3 mb-2" style="background:rgba(255,167,38,.08);border:1px solid rgba(255,167,38,.3);">
          <div class="text-sm font-semibold" style="color:{WARN};">🚨 {rival} signed {STUDIO_PARTNERS[key]['name']} to an exclusive deal</div>
          <div class="text-xs text-ink2 mt-1">No longer available to you for the rest of this level.</div>
        </div>
        """, unsafe_allow_html=True)

    released = ss.movie_partner_releases.get(ss.movie_cycle)
    if released:
        gone = (f"{released['rival']} signed them right away." if released.get("rival")
                else "No rival has signed them yet; you can sign a banner below.")
        st.markdown(f'<div style="font-size:13px;margin-bottom:8px;">👋 You let '
                    f'<b>{STUDIO_PARTNERS[released["partner"]]["name"]}</b> go. {gone}</div>',
                    unsafe_allow_html=True)

    renewal_due = _partner_renewal_due(ss)
    if renewal_due:
        partner = STUDIO_PARTNERS[ss.movie_overall_deal]
        prev = next((r for r in ss.movie_log if r["cycle"] == ss.movie_cycle - 1), None)
        fee, hit = partner_renewal_fee(ss.movie_overall_deal, prev["npv"] if prev else None)
        bonus_label = (f"+{partner['star_power_bonus']} Star Power" if "star_power_bonus" in partner
                       else f"+{partner['critical_score_bonus']:.0f} Critical Reception")
        why = ("Your last film made money, so they know their worth: the fee is up "
               f"{(PARTNER_RENEWAL_HIT_MULT - 1):.0%}." if hit else "Your last film didn't make money, so they're "
               "asking the standard renewal.")
        st.markdown(f"""
        <div class="rounded-lg border border-line bg-surface2 p-3 mb-2" style="color:#ffffff;">
          <div class="text-sm font-semibold">🤝 Renewal due: {partner['name']} wants ${fee:.1f}M to stay on</div>
          <div style="font-size:13px;line-height:1.5;margin-top:4px;">They give {bonus_label} on
          {partner['specialty']} films. {why} Let them go and the bonus ends; there's a
          ~{PARTNER_RELEASE_POACH_CHANCE:.0%} chance a rival signs them on the spot. You could then sign a
          different banner at its full price.</div>
        </div>
        """, unsafe_allow_html=True)
        rc1, rc2 = st.columns(2)
        if rc1.button(f"✅ Renew for ${fee:.1f}M", key=f"renew_partner_{ss.movie_cycle}", use_container_width=True):
            ss.movie_overall_renewed_through = ss.movie_cycle
            ss.movie_talent_total_spend += fee
            st.rerun()
        if rc2.button("👋 Let them go", key=f"release_partner_{ss.movie_cycle}", use_container_width=True):
            key = ss.movie_overall_deal
            rival = draw_partner_release_poach(ss.team_name, key, ss.movie_cycle)
            if rival:
                ss.movie_rival_exclusive[key] = rival
            ss.movie_partner_releases[ss.movie_cycle] = {"partner": key, "rival": rival}
            ss.movie_overall_deal = None
            ss.movie_overall_deal_signed_cycle = None
            st.rerun()
    elif ss.movie_overall_deal:
        partner = STUDIO_PARTNERS[ss.movie_overall_deal]
        bonus_label = (f"+{partner['star_power_bonus']} Star Power" if "star_power_bonus" in partner
                       else f"+{partner['critical_score_bonus']:.0f} Critical Reception")
        st.markdown(f"""
        <div class="rounded-lg border border-line bg-surface2 p-3 mb-3">
          <div class="text-sm" style="color:{ACCENT};">🤝 Overall Deal active: <b>{partner['name']}</b>
          ({partner['specialty']} specialty) — {bonus_label} on {partner['specialty']} projects. They'll ask for a
          renewal fee each cycle.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        cols = st.columns(len(STUDIO_PARTNERS))
        for col, key in zip(cols, STUDIO_PARTNERS):
            partner = STUDIO_PARTNERS[key]
            with col:
                poached_by = ss.movie_rival_exclusive.get(key)
                bonus_label = (f"+{partner['star_power_bonus']} Star Power" if "star_power_bonus" in partner
                               else f"+{partner['critical_score_bonus']:.0f} Critical Reception")
                opacity = "opacity:.45;" if poached_by else ""
                st.markdown(f"""
                <div class="rounded-lg border border-line bg-surface p-3" style="height:100%;{opacity}">
                  <div class="text-sm font-semibold text-ink">{partner['name']}</div>
                  <div class="text-[10px] text-muted font-mono mb-2">{partner['specialty']} specialty</div>
                  <div class="text-[10px] text-ink2 mb-2" style="line-height:1.4;">{partner.get('bio', '')}</div>
                  <div class="text-xs text-ink2">{bonus_label}</div>
                  <div class="text-xs text-warn mt-1">${partner['deal_cost_m']:.0f}M</div>
                  {f'<div class="text-[10px] mt-1" style="color:{DANGER};">Signed by {poached_by}</div>' if poached_by else ''}
                </div>
                """, unsafe_allow_html=True)
                if not poached_by and st.button("Sign", key=f"sign_overall_{key}", use_container_width=True):
                    ss.movie_overall_deal = key
                    ss.movie_overall_deal_signed_cycle = ss.movie_cycle
                    ss.movie_talent_total_spend += partner["deal_cost_m"]
                    st.rerun()

    if ss.movie_talent_total_spend > 0:
        st.caption(f"💸 Total spent on talent/studio relationships so far: ${ss.movie_talent_total_spend:.1f}M "
                   f"(a real cash cost, tracked separately from any single project's NPV — see the "
                   f"Slate Complete summary).")

    st.divider()


def _resolve_scouted_concept_transitions(ss) -> dict:
    """One-time poach roll for every PAST cycle's scouted concepts not yet
    optioned or already resolved -- 2026-08-18, real game theory for movie
    CONCEPTS (not just talent), per explicit user request. Deliberately
    excludes the CURRENT cycle's own freshly-shown concepts (range stops
    before ss.movie_cycle) -- they get a full cycle to be optioned before
    facing any risk. Idempotent via movie_scouted_resolved_through, same
    gating pattern as _resolve_talent_cycle_transitions. Returns
    {concept_id: resolve_scouted_outcome() dict} for concepts poached THIS
    render, for the caller to show as fresh notices."""
    newly_poached = {}
    checked_through = ss.movie_scouted_resolved_through
    if ss.movie_cycle > checked_through:
        for cyc in range(checked_through + 1, ss.movie_cycle):
            for concept in generate_scouted_concepts(ss.team_name, cyc):
                cid = concept["id"]
                if cid in ss.movie_scouted_optioned or cid in ss.movie_scouted_poached:
                    continue
                rival = draw_scouted_poach(ss.team_name, cid, hot=bool(concept.get("hot_rival")))
                if rival and concept.get("hot_rival"):
                    rival = concept["hot_rival"]   # the studio that was circling is the one that takes it
                if rival:
                    outcome = resolve_scouted_outcome(concept, rival)
                    ss.movie_scouted_poached[cid] = outcome
                    newly_poached[cid] = outcome
        ss.movie_scouted_resolved_through = ss.movie_cycle - 1
    return newly_poached


def _section_scouted_concepts(ss, newly_poached: dict):
    """This cycle's 2-3 studio-scouted candidate concepts -- Option one to
    pre-fill the Greenlight draft below, or build your own from scratch.
    2026-08-18, per explicit user request for real competitive consequence
    around movie concepts specifically ("is there game theory in here? do
    we get updates... about rival studios buying movies we pass on?"). A
    concept not optioned by next cycle faces a real, steep one-time chance
    of being picked up by a rival -- see _resolve_scouted_concept_
    transitions and resolve_scouted_outcome. Rendered between Studio
    Partnerships and Greenlight -- a scouted concept, once optioned, feeds
    directly into the Greenlight fields right below it."""
    st.markdown('<a id="scouted"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">2 · Scouted Concepts '
                '<span class="text-xs text-muted">(required · option at least one each cycle)</span></div>',
                unsafe_allow_html=True)
    st.markdown(
        f'<p class="text-xs text-ink2 mb-2">The studio\'s scouts surface {SCOUTED_CONCEPTS_PER_CYCLE} concepts '
        'every cycle. <b>Option at least one</b>: it fills in your Greenlight form below, and you can still '
        'change anything there. Each card has the <b>scout\'s read</b>: a demand estimate (it can be off by a '
        'star; paid Research gives the real signal), how volatile the genre is, and what the concept earns as '
        f'scouted. Each concept you skip has a ~{SCOUTED_POACH_CHANCE:.0%} chance a rival makes it instead, '
        f'~{SCOUTED_HOT_POACH_CHANCE:.0%} for one a rival is already circling.</p>', unsafe_allow_html=True)

    for cid, outcome in newly_poached.items():
        npv_ok = outcome["npv"] >= 0
        st.markdown(f"""
        <div class="rounded-lg p-3 mb-2" style="background:rgba(255,167,38,.08);border:1px solid rgba(255,167,38,.3);">
          <div class="text-sm font-semibold" style="color:{WARN};">🚨 {outcome['rival']} picked up
          "{outcome['title']}" — you passed on this {outcome['genre']} concept.</div>
          <div class="text-xs text-ink2 mt-1">It went on to post {'a' if npv_ok else 'a real'}
          {_fmt_money(outcome['npv'])} NPV for them{' — a real hit you left on the table.' if npv_ok else '.'}</div>
        </div>
        """, unsafe_allow_html=True)

    concepts = generate_scouted_concepts(ss.team_name, ss.movie_cycle)
    per_row = 3
    cols = [c for _ in range(0, len(concepts), per_row) for c in st.columns(per_row)]
    for col, concept in zip(cols, concepts):
        with col:
            optioned = concept["id"] in ss.movie_scouted_optioned
            # Scout's read + hot badge (2026-10-05, per explicit user request for more intensity).
            read = scout_read(ss.team_name, concept)
            hot_html = (f'<div style="font-size:12px;margin-bottom:4px;">🔥 <b>{concept["hot_rival"]} is circling</b>: '
                        f'~{SCOUTED_HOT_POACH_CHANCE:.0%} chance it\'s gone next cycle</div>'
                        if concept.get("hot_rival") and not optioned else "")
            stars_html = "⭐" * read["stars"] + "☆" * (5 - read["stars"])
            st.markdown(f"""
            <div class="rounded-lg border border-line bg-surface p-3" style="height:100%;">
              {hot_html}
              <div class="text-[10px] text-muted font-mono mb-1">{concept['genre']} · {concept['concept_type']} · {concept['source_material']}</div>
              <div class="text-xs text-ink2 mb-2" style="line-height:1.4;">{concept['logline']}</div>
              <div class="text-[10px] text-muted font-mono">Est. Budget: ${concept['budget_m']:.0f}M</div>
              <div style="font-size:12px;margin-top:6px;line-height:1.5;">🔭 <b>Scout's read</b>: {stars_html} demand (±1 star)
                · {read['risk']} risk<br>As scouted: {_fmt_money(read['npv_weak'])} (weak run) to
                {_fmt_money(read['npv_expected'])} (expected run)</div>
              {'<div class="text-[10px] mt-1" style="color:' + SUCCESS + ';">✅ Optioned</div>' if optioned else ''}
            </div>
            """, unsafe_allow_html=True)
            if not optioned and st.button("Option This Concept", key=f"option_{concept['id']}", use_container_width=True):
                ss.movie_scouted_optioned.add(concept["id"])
                ss.movie_draft = {
                    **ss.movie_draft,
                    "genre": concept["genre"], "concept_type": concept["concept_type"],
                    "source_material": concept["source_material"], "budget_m": concept["budget_m"],
                    "pa_spend_m": concept["pa_spend_m"], "star_power": concept["star_power"],
                    "screens": concept["screens"],
                }
                st.rerun()

    st.divider()


def _resolve_festival_transitions(ss) -> dict:
    """Auto-resolve every PAST cycle's un-bid festival films as a real
    'passed' outcome -- team_bid_m=0.0 fed straight into the SAME
    resolve_festival_acquisition auction rivals bid into, no separate
    poach-chance roll needed (unlike Scouted Concepts, this is already a
    live competitive auction every cycle, so 'passing' just means the
    highest rival bid wins on its own -- the real thing that happens at an
    actual festival if a studio never shows up to bid). Deliberately
    excludes the CURRENT cycle's own freshly-shown films (range stops
    before ss.movie_cycle) -- same one-full-cycle grace period Scouted
    Concepts gives. Idempotent via movie_festival_resolved_through.
    Returns {film_id: outcome dict} for films resolved THIS render, for
    the caller to show as fresh notices."""
    newly_resolved = {}
    checked_through = ss.movie_festival_resolved_through
    if ss.movie_cycle > checked_through:
        for cyc in range(checked_through + 1, ss.movie_cycle):
            for film in generate_festival_slate(ss.team_name, cyc):
                fid = film["id"]
                if fid in ss.movie_festival_log or fid in ss.movie_festival_rival_log:
                    continue
                bg = generate_background_slate(ss.team_name, cyc, studio_budget_m=ss.movie_studio_budget_m)
                appetite = draw_licensing_bidder_appetite(ss.team_name, cyc, bg, bidders=RIVAL_STUDIOS)
                appetite_mult = {b: v["mult"] for b, v in appetite.items()}
                rival_bids = draw_festival_acquisition_bids(ss.team_name, cyc, fid,
                                                              film["asking_anchor_m"], appetite_mult)
                auction = resolve_festival_acquisition(0.0, rival_bids)
                outcome = resolve_festival_acquisition_outcome(film, auction["winner"], auction["winning_bid_m"])
                if auction["team_won"]:
                    ss.movie_festival_log[fid] = outcome
                else:
                    ss.movie_festival_rival_log[fid] = outcome
                newly_resolved[fid] = outcome
        ss.movie_festival_resolved_through = ss.movie_cycle - 1
    return newly_resolved


def _section_festival_acquisitions(ss, newly_resolved: dict):
    """This cycle's 3 real festival acquisition targets (Sundance/TIFF/
    Cannes) -- 2026-08-18, per explicit user request ("is it possible to
    build in Sundance, TIFF and Cannes... as a way to find movies to
    buy?"). Unlike Scouted Concepts (a starting point to Greenlight
    yourself), these are ALREADY-PRODUCED films with critical reception
    ALREADY REVEALED -- real post-screening buzz -- and rival studios are
    real live bidders every cycle, not a deferred poach risk. A won film
    adds real NPV to the studio's pipeline (shown on the Distribution
    Pipeline scorecard as its own Festival row) but is deliberately kept
    out of ss.movie_log / compute_movie_score -- see the FESTIVALS module
    comment in utils/movie_models.py for why."""
    st.markdown('<a id="festivals"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">3 · Film Festival Acquisitions '
                '<span class="text-xs text-muted">(required · bid on at least one each cycle)</span></div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-2">Sundance, TIFF, and Cannes each offer one finished film with '
        'its reviews already known. <b>Bid on at least one</b>. Bids are sealed: rivals bid too, the '
        'highest bid wins and pays what it bid. Your analysts give each film a <b>break-even bid</b>: '
        'pay more than that and the film loses money unless it breaks out. Hot films draw more rival '
        'bidders, so winning one often means overpaying (the winner\'s curse). A film you win joins your '
        'pipeline as an extra release; it doesn\'t use your greenlight slot.</p>', unsafe_allow_html=True)

    for fid, outcome in newly_resolved.items():
        team_won = fid in ss.movie_festival_log
        if team_won:
            continue   # a team win from a past cycle's late auto-resolve is shown by the scorecard, not a notice
        npv_ok = outcome["npv"] >= 0
        st.markdown(f"""
        <div class="rounded-lg p-3 mb-2" style="background:rgba(255,167,38,.08);border:1px solid rgba(255,167,38,.3);">
          <div class="text-sm font-semibold" style="color:{WARN};">🚨 {outcome['winner']} acquired
          "{outcome['title']}" ({outcome['festival_name']}) — you didn't place a winning bid.</div>
          <div class="text-xs text-ink2 mt-1">It went on to post {'a' if npv_ok else 'a real'}
          {_fmt_money(outcome['npv'])} NPV for them{' — a real one that got away.' if npv_ok else '.'}</div>
        </div>
        """, unsafe_allow_html=True)

    films = generate_festival_slate(ss.team_name, ss.movie_cycle)
    bg = generate_background_slate(ss.team_name, ss.movie_cycle, studio_budget_m=ss.movie_studio_budget_m)
    appetite = draw_licensing_bidder_appetite(ss.team_name, ss.movie_cycle, bg, bidders=RIVAL_STUDIOS)
    appetite_mult = {b: v["mult"] for b, v in appetite.items()}

    cols = st.columns(len(films))
    for col, film in zip(cols, films):
        with col:
            fid = film["id"]
            resolved = ss.movie_festival_log.get(fid) or ss.movie_festival_rival_log.get(fid)
            cs = film["critical_score"]
            cs_tier = "Acclaimed" if cs >= 75 else ("Well Reviewed" if cs >= 55 else ("Mixed" if cs >= 35 else "Panned"))
            # 2026-10-05 (explicit user request for more intensity): a real
            # valuation and a read on rival interest, so a bid is a call, not a guess.
            be_bear, be_base = festival_breakeven_bids(film)
            rival_bids = draw_festival_acquisition_bids(ss.team_name, ss.movie_cycle, fid,
                                                        film["asking_anchor_m"], appetite_mult)
            interest, interested = festival_interest(rival_bids)
            interest_icon = {"Hot": "🔥", "Warm": "👀", "Quiet": "😴"}[interest]
            interest_txt = (f"{interest_icon} <b>{interest}</b>: " + (", ".join(interested) + " screened it"
                            if interested else "no rival studio screened it"))
            st.markdown(f"""
            <div class="rounded-lg border border-line bg-surface p-3" style="height:100%;">
              <div class="text-[10px] text-muted font-mono mb-1">{film['festival_name']} · {film['genre']} · {film['concept_type']}</div>
              <div class="text-xs text-ink2 mb-2" style="line-height:1.4;">{film['logline']}</div>
              <div class="text-[10px] text-muted font-mono">Critics: {cs:.0f}/100 ({cs_tier}), already screened</div>
              <div class="text-[10px] text-muted font-mono">Asking price: ${film['asking_anchor_m']:.1f}M</div>
              <div style="font-size:12px;margin-top:6px;line-height:1.45;">📈 Break-even bid: <b>${be_bear:.1f}M</b> (weak run)
                to <b>${be_base:.1f}M</b> (expected run)</div>
              <div style="font-size:12px;line-height:1.45;">{interest_txt}</div>
            </div>
            """, unsafe_allow_html=True)
            if resolved is not None:
                won = fid in ss.movie_festival_log
                if won:
                    st.success(f"✅ Acquired for \\${resolved['acquisition_cost_m']:.1f}M. Its NPV for you: "
                               f"{_fmt_money(resolved['npv']).replace('$', chr(92) + '$')}.")
                else:
                    st.error(f"❌ {resolved['winner']} won at \\${resolved['acquisition_cost_m']:.1f}M. Its NPV for "
                             f"them: {_fmt_money(resolved['npv']).replace('$', chr(92) + '$')}.")
            else:
                bid = st.number_input(f"Your bid ($M)", min_value=0.0, value=float(film["asking_anchor_m"]),
                                       step=0.5, key=f"festival_bid_{fid}",
                                       help="Sealed-bid — you can't see rival offers before submitting your own. "
                                            "Highest bid wins and pays exactly what it bid.")
                # Live market-anchor feedback (2026-08-24 add, found in a QA
                # pass, same fix as TV's Sports Rights bid input) -- the
                # default already equals the anchor, but the ratio should
                # keep updating as the student edits the bid.
                if bid > 0:
                    if bid <= be_bear:
                        verdict = "below the weak-run break-even: profitable even if it underperforms"
                    elif bid <= be_base:
                        verdict = "profitable on an expected run, a loss on a weak one"
                    else:
                        verdict = "above the expected-run break-even: you need a breakout to make money"
                    st.markdown(f'<div style="font-size:12px;margin:-6px 0 6px;">→ ${bid:.1f}M is {verdict}.</div>',
                                unsafe_allow_html=True)
                if st.button("Submit Bid", key=f"festival_submit_{fid}", use_container_width=True):
                    rival_bids = draw_festival_acquisition_bids(ss.team_name, ss.movie_cycle, fid,
                                                                  film["asking_anchor_m"], appetite_mult)
                    auction = resolve_festival_acquisition(bid, rival_bids)
                    outcome = resolve_festival_acquisition_outcome(film, auction["winner"], auction["winning_bid_m"])
                    if auction["team_won"]:
                        ss.movie_festival_log[fid] = outcome
                    else:
                        ss.movie_festival_rival_log[fid] = outcome
                    st.rerun()

    st.divider()


def _section_holding_deals(ss, resolved_hold_key):
    """One-off Holding Deals on an individual TALENT_PARTNERS actor's
    window -- 2026-08-18, moved here (was rendered alongside Studio
    Partnerships before Greenlight) per explicit user question ("a holding
    deal probably comes after the greenlighting of a movie right?"): booking
    a specific actor only makes sense once you know what you're making,
    same as a real production locks down its cast after the project is
    actually greenlit. Placed for NEXT cycle (production/casting lead time),
    resolved (succeeded/rival-claimed/forfeited) at the top of that next
    cycle's Decisions render -- see _resolve_talent_cycle_transitions. Not
    genre-filtered -- next cycle's concept isn't chosen yet, so any actor
    may end up being the right fit. resolved_hold_key comes from the same
    shared _resolve_talent_cycle_transitions(ss) call _section_studio_
    partnerships uses -- see that function's docstring."""
    st.markdown('<a id="holding"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">5 · Holding Deals '
                '<span class="text-xs text-muted">(required · hold or sign at least one actor for your '
                'next film; skipped on your final film)</span></div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-2"><b>Lock at least one actor for your next film.</b> An actor '
        'you hold or sign can be cast as the <b>Lead Actor</b> in Greenlight next cycle. A Hold is cheap '
        'but risky: a rival may already have their window, and even a successful hold can fall through. '
        'A Multi-Picture Deal costs more but is guaranteed.</p>', unsafe_allow_html=True)

    if resolved_hold_key:
        h = ss.movie_talent_holds[resolved_hold_key]
        ok = h["status"] == "succeeded"
        st.markdown(f"""
        <div class="rounded-lg p-3 mb-2" style="background:rgba({'102,187,106' if ok else '239,83,80'},.08);
             border:1px solid rgba({'102,187,106' if ok else '239,83,80'},.3);">
          <div class="text-sm font-semibold" style="color:{SUCCESS if ok else DANGER};">
            {'✅' if ok else '❌'} Holding Deal Update — {TALENT_PARTNERS[resolved_hold_key]['name']}</div>
          <div class="text-xs text-ink2 mt-1">{'The window held together. Cast them as 🎭 Lead Actor in Greenlight (step 4) this cycle; their bonus applies in one of their best genres.' if ok else h['forfeit_reason']}</div>
        </div>
        """, unsafe_allow_html=True)

    # This cycle's hold attempts -- rival-claim results are instant.
    for key, h in ss.movie_talent_holds.items():
        if h.get("cycle_placed") == ss.movie_cycle and h["status"] in ("pending", "rival_claimed"):
            if h["status"] == "rival_claimed":
                st.markdown(f"""
                <div class="rounded-lg p-3 mb-2" style="background:rgba(239,83,80,.08);border:1px solid rgba(239,83,80,.3);">
                  <div class="text-sm" style="color:{DANGER};">❌ {h['rival']} had already locked up
                  {TALENT_PARTNERS[key]['name']}'s window — the hold fee is gone either way.</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="rounded-lg p-3 mb-2" style="background:rgba(26,107,181,.08);border:1px solid rgba(26,107,181,.3);">
                  <div class="text-sm" style="color:{ACCENT2};">🤞 Hold placed on {TALENT_PARTNERS[key]['name']}
                  — you'll know whether it held together at the start of next cycle.</div>
                </div>
                """, unsafe_allow_html=True)

    def _multi_picture_active(key: str) -> bool:
        signed = ss.movie_multi_picture_deals.get(key)
        return signed is not None and signed <= ss.movie_cycle < signed + MULTI_PICTURE_DEAL_CYCLES

    st.markdown(
        '<p class="text-xs text-ink2 mt-3 mb-2">Or negotiate a Multi-Picture Deal — real negotiation '
        f'depth beyond a one-off Hold: pay more upfront (~4x the hold fee) to lock an actor\'s '
        f'availability for {MULTI_PICTURE_DEAL_CYCLES} full cycles outright, with no rival-claim roll '
        'and no forfeit risk. Expensive and safe, versus Holding\'s cheap and risky.</p>',
        unsafe_allow_html=True)

    holdable = [k for k in TALENT_PARTNERS
                if ss.movie_talent_holds.get(k, {}).get("status") != "pending"
                and not _multi_picture_active(k)]
    if holdable:
        # Wrapped 4-per-row grid, not one column per talent (2026-08-24, per
        # user request) -- the roster grew from 4 to 8, and cramming 8 cards
        # into one row made each one unreadably narrow. Same chunking pattern
        # already used for the New-this-year debut-month pickers in
        # app_pages/renewal.py.
        nc = 4
        holdable_chunks = [holdable[i:i+nc] for i in range(0, len(holdable), nc)]
        for chunk in holdable_chunks:
            hcols = st.columns(nc)
            for col, key in zip(hcols, chunk):
                partner = TALENT_PARTNERS[key]
                with col:
                    synergy_material = ORIGIN_MEDIUM_SOURCE_SYNERGY.get(partner.get("origin_medium"))
                    synergy_note = (f'<div class="text-[10px] mt-1" style="color:{ACCENT2};">🎯 {synergy_material} synergy '
                                    f'(×{TALENT_SOURCE_SYNERGY_MULT:.1f}) if paired with that Source Material</div>'
                                    if synergy_material else "")
                    bonus_label = (f"+{partner['star_power_bonus']} Star Power" if "star_power_bonus" in partner
                                   else f"+{partner['critical_score_bonus']:.0f} Critical Reception")
                    st.markdown(f"""
                    <div class="rounded-lg border border-line bg-surface p-3" style="height:100%;">
                      <div class="text-sm font-semibold text-ink">{partner['name']} <span class="text-[10px] text-muted">
                        ({partner.get('gender', '')}, {partner.get('age', '?')}, {partner.get('ethnicity', '—')})</span></div>
                      <div class="text-[10px] text-muted font-mono mb-1">Best genres: {', '.join(partner.get('best_genres', [partner['specialty']]))}</div>
                      <div class="text-[10px] text-muted font-mono mb-2">From: {partner.get('origin_medium', '—')}</div>
                      <div class="text-[10px] text-ink2 mb-2" style="line-height:1.4;">{partner.get('bio', '')}</div>
                      <div class="text-[10px] text-muted font-mono">Lifetime B.O.: ${partner.get('lifetime_box_office_m', 0):,.0f}M</div>
                      <div class="text-[10px] text-muted font-mono mb-2">Social: {partner.get('social_followers_m', 0):.1f}M followers</div>
                      <div class="text-xs text-ink2">{bonus_label}</div>
                      <div class="text-[10px] text-muted font-mono">${partner['hold_cost_m']:.1f}M hold fee · ${partner['multi_picture_cost_m']:.0f}M multi-picture</div>
                      {synergy_note}
                    </div>
                    """, unsafe_allow_html=True)
                    bcol1, bcol2 = st.columns(2)
                    with bcol1:
                        if st.button("Place Hold", key=f"hold_{key}", use_container_width=True):
                            ss.movie_talent_total_spend += partner["hold_cost_m"]
                            rival = draw_rival_claim(ss.team_name, ss.movie_cycle, key)
                            if rival:
                                ss.movie_talent_holds[key] = {"status": "rival_claimed",
                                                               "cycle_placed": ss.movie_cycle, "rival": rival}
                            else:
                                ss.movie_talent_holds[key] = {"status": "pending", "cycle_placed": ss.movie_cycle}
                            st.rerun()
                    with bcol2:
                        if st.button("Multi-Picture", key=f"multi_{key}", use_container_width=True):
                            ss.movie_talent_total_spend += partner["multi_picture_cost_m"]
                            ss.movie_multi_picture_deals[key] = ss.movie_cycle
                            st.rerun()

    for key, signed_cycle in ss.movie_multi_picture_deals.items():
        if _multi_picture_active(key):
            through = _cycle_years_label(signed_cycle + MULTI_PICTURE_DEAL_CYCLES - 1)
            st.caption(f"🤝 Multi-Picture Deal active: {TALENT_PARTNERS[key]['name']} — locked through {through}.")

    st.divider()


# ── Progress indicator ───────────────────────────────────────────────────────
def _progress_bar(ss):
    steps = ["Decisions", "Results"]
    phase_idx = {"decisions": 0, "results": 1, "complete": 1}[ss.movie_phase]
    dot_items = []
    for i, label in enumerate(steps):
        done = i < phase_idx or ss.movie_phase == "complete"
        current = i == phase_idx and ss.movie_phase != "complete"
        bg, txt, clr = ("#66bb6a", "✓", "#0b0c10") if done else \
                       ("#1a6bb5", str(i + 1), "#ffffff") if current else \
                       ("#252836", str(i + 1), "#ffffff")
        dot_items.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">'
            f'<div style="width:32px;height:32px;border-radius:50%;background:{bg};'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-family:DM Mono,monospace;font-size:15px;font-weight:700;color:{clr};">{txt}</div>'
            f'<div style="font-size:13px;color:#ffffff;font-family:DM Mono,monospace;">{label}</div></div>'
        )
    connector = '<div style="width:40px;height:2px;background:#252836;margin-bottom:16px;"></div>'
    if ss.movie_phase != "complete":
        y1, y2 = _cycle_year_range(ss.movie_cycle)
        # Year note (2026-10-01): ties the studio calendar to NPV's t=0 convention.
        cycle_label = (f"Film {ss.movie_cycle} of {CYCLES_TOTAL} · {_cycle_years_label(ss.movie_cycle)} of "
                       f"{CYCLES_TOTAL * YEARS_PER_CYCLE}<div style=\"font-size:13px;margin-top:4px;\">"
                       f"Year {y1} = greenlight &amp; produce (your t = 0 investment) · "
                       f"Year {y2} = release &amp; windows</div>")
    else:
        cycle_label = "Slate Complete"
    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;padding:14px 20px;margin-bottom:18px;">
      <div style="font-family:DM Mono,monospace;font-size:14px;color:#ffffff;margin-bottom:10px;">{cycle_label}</div>
      <div style="display:flex;align-items:center;justify-content:center;">{connector.join(dot_items)}</div>
    </div>
    """, unsafe_allow_html=True)


# ── Main render ────────────────────────────────────────────────────────────────
def render():
    ss = st.session_state
    _init(ss)


    _progress_bar(ss)

    if ss.movie_phase == "decisions":
        _decisions(ss)
    elif ss.movie_phase == "results":
        _results(ss)
    else:
        _complete(ss)


# ── Last Cycle recap ──────────────────────────────────────────────────────────
def _last_cycle_recap(prev: dict):
    """Pinned strip at the top of Decisions showing the previous cycle's
    actual outcome — the Movies-side parallel to pages/simulation.py's
    _last_year_recap, added 2026-08-03 per user request. Unlike TV/Streaming
    (which gets a synthetic "Starting Position" baseline for Year 1, built
    from the incoming show roster's own built-in economics), Cycle 1 has no
    equivalent to show — there's no inherited slate; every movie is a fresh,
    standalone bet — so this only ever fires for cycle > 1, when a real
    prior outcome actually exists in ss.movie_log."""
    npv_ok = prev["npv"] >= 0
    npv_c  = SUCCESS if npv_ok else DANGER
    title  = prev["project_kwargs"]["title"]
    strat  = prev["project_kwargs"]["release_strategy"]
    cs     = prev["critical_score"]
    cs_c   = SUCCESS if cs >= 55 else (WARN if cs >= 35 else DANGER)
    st.markdown(f"""
    <div class="rounded-lg border border-line bg-surface2 p-4 mb-4">
      <div class="font-mono text-[10px] text-muted uppercase tracking-widest mb-2">
        {_cycle_years_label(prev['cycle'])} — "{title}" — Last Period's Actuals
      </div>
      <div class="flex gap-8 flex-wrap items-end">
        <div><div class="text-[9px] text-muted font-mono">NPV</div>
          <div class="text-xl font-serif" style="color:{npv_c};">{_fmt_money(prev['npv'])}</div></div>
        <div><div class="text-[9px] text-muted font-mono">IRR</div>
          <div class="text-xl font-serif text-ink">{_irr_label(prev['irr'])}</div></div>
        <div><div class="text-[9px] text-muted font-mono">CRITICAL RECEPTION</div>
          <div class="text-xl font-serif" style="color:{cs_c};">{cs:.0f}/100</div></div>
        <div><div class="text-[9px] text-muted font-mono">RELEASE STRATEGY</div>
          <div class="text-sm text-ink mt-1">{RELEASE_LABELS[strat]}</div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def _progress_chart(ss):
    """Compact multi-cycle NPV trend, shown once 2+ cycles have real
    actuals in ss.movie_log -- the TV/Streaming parallel to
    pages/simulation.py's _progress_chart, added 2026-08-04 per the same
    user request. Reuses the same bar-of-NPV-per-cycle shape as the
    'Slate So Far' chart in _results() for visual consistency, but that
    one only shows after simulating the current cycle -- this compounds
    it into the Decisions screen too, before the student locks in the
    next cycle's greenlight/release calls."""
    log        = sorted(ss.movie_log, key=lambda r: r["cycle"])
    cyc_labels = [_cycle_years_label(r["cycle"]) for r in log]
    npvs       = [r["npv"] for r in log]
    fig = go.Figure(go.Bar(x=cyc_labels, y=npvs,
                            marker_color=[SUCCESS if v >= 0 else DANGER for v in npvs]))
    fig.add_hline(y=0, line_dash="dash", line_color=WARN, opacity=0.4)
    fig.update_layout(**base_layout("Your Progress So Far — NPV by Year", height=210))
    st.markdown('<div class="mb-4">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)


def _resolve_movie_outcome(ss, project) -> dict:
    """The single source of truth for resolving a movie's stochastic fate --
    used by BOTH the Theatrical Mini-Run button (resolves early, before
    PVOD/licensing decisions exist) and the final Simulate button (which
    reuses the mini-run's locked result when present, only resolving fresh
    itself as a defensive fallback). Every draw here is a pure function of
    (team, cycle, genre, concept_type, ai_production_tools, source_material)
    -- see draw_actual_multiplier/draw_critical_reception's own docstrings
    -- so calling it early and again later for the same locked Greenlight
    inputs is guaranteed to return identical numbers. That guarantee is
    what makes the two-stage Theatrical Mini-Run -> Simulate flow safe
    (2026-08-18) -- it isn't "probably the same," it's structurally the
    same function call. locked_inputs captures exactly the fields this
    resolution depends on, so the caller can detect if the student changed
    Greenlight after resolving and needs to re-run the mini-sim."""
    multiplier = draw_actual_multiplier(ss.team_name, ss.movie_cycle, project.genre, project.concept_type)
    critical_score = draw_critical_reception(ss.team_name, ss.movie_cycle, project.genre,
                                              ai_production_tools=project.ai_production_tools)
    talent_bonus = _active_talent_bonus(ss, project.genre, project.source_material)
    if "critical_score_bonus" in talent_bonus:
        critical_score = min(100.0, critical_score + talent_bonus["critical_score_bonus"])

    trouble = draw_production_trouble(ss.team_name, ss.movie_cycle)
    trouble_reason = None
    if trouble:
        trouble_reason, haircut = trouble
        multiplier *= haircut

    ai_setback_reason = None
    if project.ai_production_tools:
        ai_setback = draw_ai_tooling_setback(ss.team_name, ss.movie_cycle)
        if ai_setback:
            ai_setback_reason, ai_haircut = ai_setback
            multiplier *= ai_haircut

    ancillary = draw_ancillary_surprise(ss.team_name, ss.movie_cycle)
    ancillary_reason = None
    pvod_mult = theme_park_mult = 1.0
    if ancillary:
        ancillary_reason, ancillary_mult = ancillary
        pvod_mult = theme_park_mult = ancillary_mult

    ewom = draw_ewom_piracy_swing(ss.team_name, ss.movie_cycle)
    ewom_reason = None
    ewom_mult = 1.0
    if ewom:
        ewom_reason, ewom_mult = ewom

    return {
        "multiplier":          multiplier,
        "critical_score":      critical_score,
        "talent_bonus":        talent_bonus,
        "trouble_reason":      trouble_reason,
        "ai_setback_reason":   ai_setback_reason,
        "ancillary_reason":    ancillary_reason,
        "pvod_mult":           pvod_mult,
        "theme_park_mult":     theme_park_mult,
        "ewom_reason":         ewom_reason,
        "ewom_mult":           ewom_mult,
        "locked_inputs": {
            "genre":                project.genre,
            "concept_type":         project.concept_type,
            "ai_production_tools":  project.ai_production_tools,
            "source_material":      project.source_material,
        },
    }


# ── Phase 1: Decisions (Greenlight + Release Strategy) ───────────────────────
def _decisions(ss):
    """Single scrolling page (redesigned 2026-07-27, replacing the old
    Greenlight -> Release Strategy click-through per user request:
    "students should have prompts that force them to make decisions as
    they scroll down... then click simulate at the bottom"). Both
    decisions render unconditionally, top to bottom, ending in one
    button that does what the old "Lock Strategy -> See Results" button
    did."""
    prev = next((r for r in ss.movie_log if r["cycle"] == ss.movie_cycle - 1), None) \
           if ss.movie_cycle > 1 else None
    if prev:
        _last_cycle_recap(prev)

    # Your Slate table replaces the old NPV-by-year bar chart here
    # (2026-10-05): one row per film says far more than one bar per film.
    _section_your_slate(ss, title="🎬 Your Slate So Far")


    # Both resolutions run BEFORE the scorecard renders -- ss.movie_scouted_
    # poached/ss.movie_rival_exclusive must already reflect this render's
    # transitions by the time _section_distribution_pipeline reads them, or
    # the scorecard would show last render's stale state for one full
    # render (Streamlit isn't reactive -- an earlier st.dataframe() call
    # doesn't see state mutated later in the same script run).
    resolved_hold_key, newly_poached = _resolve_talent_cycle_transitions(ss)
    newly_poached_concepts = _resolve_scouted_concept_transitions(ss)
    newly_resolved_festivals = _resolve_festival_transitions(ss)

    # Step bar (2026-10-05) replaces the plain jump-link row: same anchors,
    # plus a ✓ per finished required step and a locked/unlocked Simulate.
    # Rendered after the transitions above so its statuses are current.
    _step_bar(ss)

    # Context, not a decision (2026-10-05 QA): collapsed so step 1 is the
    # first thing a team sees under the step bar. Your own films are in the
    # Your Slate table above.
    with st.expander("📊 Distribution Pipeline: every film in the studio's pipeline and where it sits in "
                     "its run (context, not scored)", expanded=False):
        _section_distribution_pipeline(ss)

    # A standing Studio Partnership should shape what gets greenlit, not the
    # other way around -- rendered before Greenlight, same placement
    # rationale as TV/Streaming's Sports Rights section. Holding Deals
    # (individual actors) render AFTER Greenlight instead -- see
    # _section_holding_deals's docstring for why.
    _section_studio_partnerships(ss, newly_poached)

    # Scouted Concepts render right before Greenlight -- optioning one
    # pre-fills the Greenlight fields directly below it.
    _section_scouted_concepts(ss, newly_poached_concepts)

    # Film Festival Acquisitions -- a real alternative source for the
    # studio's pipeline, distinct from Greenlight-from-scratch, so it
    # renders alongside Scouted Concepts rather than feeding into the
    # Greenlight draft below it.
    _section_festival_acquisitions(ss, newly_resolved_festivals)

    st.markdown('<a id="greenlight"></a>', unsafe_allow_html=True)
    _slots_left = CYCLES_TOTAL - ss.movie_cycle + 1
    st.markdown(f'<div class="section-title">4 · Greenlight a New Movie '
                f'<span class="text-xs text-muted">(Greenlight Slot {ss.movie_cycle} of {CYCLES_TOTAL})</span></div>',
                unsafe_allow_html=True)
    st.markdown(
        f'<p class="text-xs text-ink2 mb-2">🎟️ <b>One new movie per {YEARS_PER_CYCLE}-year cycle, {CYCLES_TOTAL} in all.</b> '
        f'This is slot {ss.movie_cycle} ({_slots_left} left including this one). Choose the concept, cast it, '
        f'write the pitch, and commit the money. Your pitch saves automatically and posts to the class Pitch '
        f'Board when you Simulate.</p>'
        '<p class="text-xs text-ink2 mb-2">💸 Production Budget and <b>P&A (Prints & Advertising: trailers, '
        'ad buys, publicity, delivering the film to theaters)</b> are paid in full, upfront, before you know '
        'whether the movie earns a cent. Unlike TV, where a show\'s cost is spread (amortized) over several '
        'years.</p>', unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    d = ss.movie_draft

    with left:
        st.markdown('<div class="section-title mt-2">🎬 Concept</div>', unsafe_allow_html=True)
        title = st.text_input("Working Title", d.get("title", f"Untitled {_cycle_years_label(ss.movie_cycle)} Release"))
        gc1, gc2 = st.columns(2)
        genre = gc1.selectbox("Genre", GENRES, index=GENRES.index(d.get("genre", GENRES[0])) if d.get("genre") in GENRES else 0,
                               help="Drives international box-office reach and Peacock streaming appeal.")
        active_bonus = _active_talent_bonus(ss, genre, d.get("source_material", SOURCE_MATERIALS[0]))
        if active_bonus:
            bonus_txt = (f"+{active_bonus['star_power_bonus']:.0f} Star Power" if "star_power_bonus" in active_bonus
                         else f"+{active_bonus['critical_score_bonus']:.0f} Critical Reception")
            synergy_txt = " 🎯 Source Material synergy active — bonus amplified." if active_bonus.get("synergy") else ""
            st.caption(f"🤝 {active_bonus['partner_name']} bonus active for {genre}: {bonus_txt}.{synergy_txt}")
        concept_type = gc2.selectbox(
            "Concept Type", CONCEPT_TYPES,
            index=CONCEPT_TYPES.index(d.get("concept_type", CONCEPT_TYPES[0])) if d.get("concept_type") in CONCEPT_TYPES else 0,
            help="Sequel: built-in opening awareness that fades each cycle (franchise fatigue). "
                 "New IP: no bonus — earns awareness through P&A instead. Family/Kids: softer "
                 "opening, much stronger long-tail library value. Indie-Horror: budget capped, "
                 "wider variance — huge outperformers on tiny budgets are the whole case for it.",
        )

        gc3, gc4 = st.columns(2)
        # Universal Library IP (2026-10-05): revive a title the studio already owns.
        # Each library title can be revived once per slate.
        used_ips = {r["project_kwargs"].get("library_ip") for r in ss.movie_log if r["cycle"] != ss.movie_cycle}
        ip_keys = [None] + [k for k in UNIVERSAL_LIBRARY_IP if k not in used_ips]
        library_ip = gc4.selectbox(
            "🏛️ Revive a Universal Library IP?", ip_keys,
            index=ip_keys.index(d.get("library_ip")) if d.get("library_ip") in ip_keys else 0,
            format_func=lambda k: "No — a new property" if k is None else UNIVERSAL_LIBRARY_IP[k]["name"],
            help="Each title can be revived once per slate. "
                 "Universal already owns these, so there's no rights fee, but reviving one carries a legacy "
                 "fee (original creators' and estates' participations, legacy cast). Its built-in audience "
                 "replaces Source Material's boost. Revived outside its home genre, only half that audience "
                 "shows up.",
        )
        source_material = gc3.selectbox(
            "Source Material", SOURCE_MATERIALS,
            index=SOURCE_MATERIALS.index(d.get("source_material", SOURCE_MATERIALS[0]))
                  if d.get("source_material") in SOURCE_MATERIALS else 0,
            help="Where the underlying story comes from — separate from Concept Type (a Sequel "
                 "can itself be an original-screenplay franchise OR a book-adaptation sequel).",
            disabled=library_ip is not None,
        )
        acq_cost = SOURCE_ACQUISITION_COST_M.get(source_material, 0.0)
        boost = SOURCE_OPENING_BOOST.get(source_material, 1.0)
        if library_ip:
            ip = UNIVERSAL_LIBRARY_IP[library_ip]
            acq_cost = ip["legacy_fee_m"]
            ip_lift = (library_ip_opening_boost(library_ip, genre) - 1) * 100
            fit = (f"a home genre ({', '.join(ip['genres'])}), so the full audience shows up"
                   if genre in ip["genres"] else
                   f"outside its home genre ({', '.join(ip['genres'])}), so only half the audience carries over")
            st.markdown(
                f'<div style="font-size:13px;color:#ffffff;line-height:1.5;margin-bottom:6px;">'
                f'🏛️ <b>{ip["name"]}</b>: {ip["note"]}<br>'
                f'<b>+{ip_lift:.0f}% opening weekend</b>: {genre} is {fit}. '
                f'<b>+${acq_cost:.0f}M legacy fee</b> added to Capital at Risk.</div>',
                unsafe_allow_html=True)
        elif acq_cost > 0:
            st.caption(f"📚 Rights acquisition: +${acq_cost:.0f}M added to Capital at Risk — but a "
                       f"built-in fan base lifts your opening weekend by {(boost - 1) * 100:.0f}% "
                       f"before you spend a dollar of P&A. Real-world example: game/book/show "
                       f"publishers command real premiums for adaptation rights precisely because "
                       f"that audience already exists.")
        else:
            st.caption("An original screenplay has no rights to acquire, but also no built-in "
                       "audience — every dollar of awareness has to be earned through P&A and Star Power.")

        # Logline (2026-10-01): always available and required to Simulate --
        # it's posted to the class Pitch Board when the film is simulated.
        logline = st.text_area(
            "Your Pitch / Logline (1-3 sentences): who it's about, what they want, and what's in the way",
            value=d.get("logline", ""), max_chars=500, key=f"movie_logline_{ss.movie_cycle}",
            placeholder="e.g. A stranded astronaut has to out-think a planet that's actively "
                        "trying to kill her, using only what she can scavenge...",
            help="A logline is the one- or two-sentence pitch a studio greenlights from. You don't need a "
                 "full synopsis. Required before you can Simulate.",
        )
        ss.movie_draft["logline"] = logline
        _logline_len = len(logline.strip())
        if _logline_len >= 20:
            st.markdown(f'<div style="font-size:13px;color:{SUCCESS};">✅ Pitch saved. It posts to the class '
                        f'Pitch Board when you Simulate at the bottom of the page.</div>', unsafe_allow_html=True)
        else:
            _short = 20 - _logline_len
            st.markdown(f'<div style="font-size:13px;color:{WARN};">✏️ Pitch needed before you can Simulate '
                        f'({_short} more character{"s" if _short != 1 else ""}). Type it in, then click '
                        f'outside the box (or press Ctrl+Enter) to save.</div>', unsafe_allow_html=True)

        # ── Peer Pitch Board (2026-10-01; replaced AI pitch feedback) ──────────
        with st.expander("👀 See the movies other teams in your class have pitched", expanded=False):
            from app_pages.pitch_board import render_pitch_board
            render_pitch_board(ss, sim="movies", key="movie_pitch_board")

        # ── Research / Social Listening ──────────────────────────────────────
        # Phase 4 item 9, 2026-08-05: Movies-side parallel to TV/Streaming's
        # paid Research feature (app_pages/renewal.py::preview_show_variance)
        # -- pay to preview the actual seeded signals this cycle's Simulate
        # button will draw, before committing budget/P&A. Unlike TV's
        # per-show sequential RNG consumption (order-dependent, needs replay
        # plumbing), draw_actual_multiplier/draw_critical_reception are pure
        # functions of (team, cycle, genre, concept_type) -- calling them
        # here to preview is exactly as safe as calling them for real at
        # Simulate, no extra machinery needed. Doesn't preview Production
        # Trouble, the AI Tooling Setback, Ancillary Markets Surprise, or
        # eWOM & Piracy -- those are separate, later risk axes, same as TV's
        # Research never previewing draw_production_risk_event.
        research_ip_note = (
            "for this Sequel: how much of the franchise's built-in awareness is still carrying through"
            if concept_type == "Sequel" else
            f"for this {genre} · {concept_type} concept, your only hard signal before you commit"
        )
        st.markdown('<div class="section-title mt-3">🔎 Research '
                    '<span class="text-xs text-muted">(optional — '
                    'this previews real seeded outcome signals, not qualitative advice)</span></div>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<p class="text-xs text-ink2 mt-1 mb-1">Pay ${RESEARCH_FEE_M:.0f}M (added to P&A spend) to '
            f'preview the actual audience-demand and critics signals {research_ip_note}. Research covers '
            f'the Genre and Concept Type you buy it for; switching either needs new research.</p>',
            unsafe_allow_html=True)
        # The paid card renders into this slot AFTER the Capital inputs below
        # are read, so its dollar metrics use the full current draft (title,
        # genre, concept type, source material, budget, P&A, stars, screens).
        research_slot = st.container()
        bought = ss.movie_research_paid.get(ss.movie_cycle)
        research_covers_this = _research_covers(bought, genre, concept_type)
        if bought and not research_covers_this:
            st.markdown(f'<div style="font-size:13px;margin-bottom:6px;">🔎 Your research covers '
                        f'<b>{escape(_research_label(bought))}</b>. You changed the concept, so buy new research '
                        f'to see this one.</div>', unsafe_allow_html=True)
        if not research_covers_this:
            if st.button(f"🔎 Pay for Research (${RESEARCH_FEE_M:.0f}M)", key=f"movie_research_{ss.movie_cycle}"):
                ss.movie_research_paid[ss.movie_cycle] = {"genre": genre, "concept_type": concept_type}
                ss.movie_draft["pa_spend_m"] = float(d.get("pa_spend_m", 40.0)) + RESEARCH_FEE_M
                st.rerun()

        st.markdown('<div class="section-title mt-3">💰 Capital</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        budget_cap = INDIE_HORROR_BUDGET_CAP_M if concept_type == "Indie-Horror" else 300.0
        budget_default = min(float(d.get("budget_m", 60.0)), budget_cap)
        with c1:
            budget = st.number_input("Production Budget ($M)", 10.0, budget_cap, budget_default, step=5.0,
                                      help=f"Capped at ${INDIE_HORROR_BUDGET_CAP_M:.0f}M for Indie-Horror — "
                                           f"that's what makes it \"indie.\"" if concept_type == "Indie-Horror" else None)
            st.caption("The negative cost — everything spent to actually make the film (cast/crew, sets, "
                       "VFX, post-production) before a single ticket sells. Not the same as Capital at "
                       "Risk below, which also folds in P&A and any financing discount you've chosen.")
            # Genre norm (2026-10-01 balance pass): budget now buys production value.
            _typ = GENRE_TYPICAL_BUDGET_M.get(genre, 60.0)
            st.markdown(
                f'<div style="font-size:13px;color:#e8c547;">🎯 Typical {genre} budget: ~${_typ:.0f}M. '
                f'Well below it, the film looks cheap and draws weaker audiences; above it, gains taper off.</div>',
                unsafe_allow_html=True)
        with c2:
            pa = st.number_input("P&A / Marketing Spend ($M)", 5.0, 200.0, float(d.get("pa_spend_m", 40.0)), step=5.0,
                                  help="Historically rivals or exceeds the production budget for a wide release.")
            st.caption("Prints & Advertising — trailers, media buys, publicity, the physical/digital "
                       "prints themselves. Real studios routinely spend as much on P&A as on production "
                       "itself for a wide release; it buys awareness (see Star Power below) but not "
                       "quality or word-of-mouth.")
        c3, c4 = st.columns(2)
        with c3:
            # Lead Actor (2026-10-05): any actor under a Holding Deal that held
            # together, or an active Multi-Picture Deal, can be cast by name.
            contracted = _contracted_talent(ss)
            lead_opts = [None] + contracted
            lead_actor = st.selectbox(
                "🎭 Lead Actor", lead_opts,
                index=lead_opts.index(d.get("lead_actor")) if d.get("lead_actor") in lead_opts else 0,
                format_func=lambda k: ("Unnamed cast (set Star Power below)" if k is None else
                                       f"{TALENT_PARTNERS[k]['name']} (Star Power {TALENT_BASE_STAR_POWER.get(k, 50)})"),
                help="Actors you hold (Holding Deals) or sign (Multi-Picture Deal) can be cast here. Casting "
                     "one sets this film's Star Power to theirs, and their relationship bonus applies if the "
                     "genre is one of their best.",
            )
            if not contracted:
                st.caption("No actors under contract this cycle. Place a Holding Deal or sign a "
                           "Multi-Picture Deal (step 5) to cast a named actor in a future film.")
            if lead_actor:
                talent = TALENT_PARTNERS[lead_actor]
                star = TALENT_BASE_STAR_POWER.get(lead_actor, 50)
                fits = genre in talent.get("best_genres", [talent["specialty"]])
                bonus_lbl = (f"+{talent['star_power_bonus']} Star Power" if "star_power_bonus" in talent
                             else f"+{talent['critical_score_bonus']:.0f} Critical Reception")
                st.markdown(
                    f'<div style="font-size:13px;color:#ffffff;line-height:1.5;">Star Power <b>{star}</b> '
                    f'(${star * STAR_POWER_COST_PER_POINT_M:.1f}M fee). '
                    + (f'✅ {genre} is one of their best genres, so their {bonus_lbl} bonus applies.'
                       if fits else
                       f'⚠ {genre} isn\'t one of their best genres '
                       f'({", ".join(talent.get("best_genres", []))}), so no relationship bonus.')
                    + '</div>', unsafe_allow_html=True)
            else:
                star = st.slider("Star Power", 0, 100, int(d.get("star_power", 50)),
                                  help="Lifts opening awareness, moderately — doesn't compound with P&A. "
                                       f"Costs ${STAR_POWER_COST_PER_POINT_M:.2f}M per point, added to "
                                       "Capital at Risk.")
            star_cost = star * STAR_POWER_COST_PER_POINT_M
            st.caption(f"A-list casting's built-in name recognition — lifts opening-weekend awareness "
                       f"on top of whatever P&A buys, but doesn't stack multiplicatively with it. Costs "
                       f"real money, added directly to Capital at Risk below: at this level, "
                       f"+${star_cost:.1f}M. Real A-list talent also commands gross participation once "
                       f"the movie is out (see the Deal-Participation Waterfall) — this is the upfront "
                       f"cost of getting them attached at all.")

        # Soft financial-health warning tied to the real Studio Annual
        # Budget (2026-08-24 fix, found in a QA pass) -- this greenlight
        # form previously never referenced ss.movie_studio_budget_m at all,
        # even though the header above claims it "moves year to year based
        # on how the slate actually performs." A single movie's spend
        # (max ~$520M: $300M budget + $200M P&A + $20M star power) is
        # never actually comparable in scale to the studio-wide pool
        # ($800M floor-$3.5B start, see STUDIO_BUDGET_MIN_M/
        # STUDIO_ANNUAL_BUDGET_START_M) -- a dollar-for-dollar comparison
        # would never fire. Instead this warns off the pool's own real
        # signal: how far it's shrunk from its starting point, i.e.
        # whether recent cycles have actually been performing.
        studio_budget_m = ss.get("movie_studio_budget_m", STUDIO_ANNUAL_BUDGET_START_M)
        if studio_budget_m < STUDIO_ANNUAL_BUDGET_START_M * 0.7:
            st.warning(
                f"⚠ The Studio Annual Budget has shrunk to \\${studio_budget_m/1000:.2f}B (started at "
                f"\\${STUDIO_ANNUAL_BUDGET_START_M/1000:.1f}B) — recent cycles have been running weak NPV. "
                f"Not a hard cap on this greenlight, but a real signal the studio is under real financial "
                f"pressure right now."
            )
        with c4:
            screens = st.number_input("Planned Opening Screens", 500, 4500, int(d.get("screens", 3000)), step=250)
            st.markdown(
                f'<div style="font-size:13px;color:#e8c547;">🎯 A {genre} audience fills about '
                f'{GENRE_SCREEN_DEMAND.get(genre, 3000):,} screens. Booking more mostly adds empty seats.</div>',
                unsafe_allow_html=True)
            st.caption(f"The U.S. has roughly 40,000 movie screens total (NATO estimate), of which only "
                       f"about 700-900 are true large-format IMAX screens — a genuine scarce resource "
                       f"exhibitors allocate to their highest-confidence openings. A wide theatrical "
                       f"release typically opens on 3,500-4,500 screens; a platform/awards-qualifying "
                       f"rollout deliberately starts on a few hundred and expands week over week if the "
                       f"film performs. More screens raises your opening (see Opening Weekend below) — "
                       f"but going wide is a real, unconditional cost too (~${SCREEN_COST_PER_SCREEN_M*1000:.0f}K/screen "
                       f"in print/booking fees, paid whether the movie hits or flops), not just a soft warning.")

            imax_eligible_here = genre in IMAX_ELIGIBLE_GENRES and d.get("release_strategy", "wide_theatrical") != "day_and_date"
            imax_release = st.checkbox(
                "🎇 IMAX / Premium Large Format", value=bool(d.get("imax_release", False)) and imax_eligible_here,
                disabled=not imax_eligible_here,
                help=f"+{IMAX_OPENING_BOOST_PCT:.0%} opening weekend from premium pricing and event "
                     f"appeal on the screens you already have (not additional screens) — costs a flat "
                     f"${IMAX_COST_M:.0f}M for large-format prints/mastering and marketing coordination.",
            )
            if not imax_eligible_here:
                st.caption("Not available — IMAX only makes sense for spectacle-scale genres "
                           f"({', '.join(sorted(IMAX_ELIGIBLE_GENRES))}) with a real theatrical run "
                           "(not Day-and-Date).")

        st.markdown('<div class="section-title mt-3">🌎 Distribution Strategy</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="text-xs text-ink2 mb-2">How this movie gets funded globally and how hard you '
            'push exhibitors on terms — separate from Research above, which is about '
            'the concept itself, not how it reaches audiences.</p>', unsafe_allow_html=True)
        fin_labels = {
            "self_finance": "Self-Finance — full capital at risk, full upside",
            "presale": "Global Distribution Deal (Territorial Pre-Sales) — lower capital at risk, caps international upside",
            "tax_incentive": "Tax-Incentive Location — cuts budget cost, no upside cap",
        }
        financing_structure = st.selectbox(
            "Financing Structure", FINANCING_STRUCTURES,
            index=FINANCING_STRUCTURES.index(d.get("financing_structure", "self_finance"))
                  if d.get("financing_structure") in FINANCING_STRUCTURES else 0,
            format_func=lambda k: fin_labels[k],
            help="How this movie gets funded before a single ticket sells.",
        )
        fin_notes = {
            "self_finance": "You fund 100% of budget + P&A yourself and keep every dollar of "
                             "revenue, domestic and international.",
            "presale": f"A sales agent pre-sells your international rights for a guaranteed advance "
                       f"(a minimum guarantee) roughly equal to the international rentals your movie is "
                       f"expected to earn, paid before you shoot. The agent keeps "
                       f"{PRESALE_SALES_AGENT_FEE_PCT:.0%} (real-world range: 10-30%). Distributors recoup "
                       f"their advance first; you get {PRESALE_OVERAGE_SHARE:.0%} of anything beyond it. "
                       f"Worth it for risky, high-variance films (horror, indie): the money is yours even "
                       f"if it flops. For a likely hit, you're selling your upside cheap.",
            "tax_incentive": f"Shooting in a tax-friendly location cuts your effective production "
                              f"budget by ~{TAX_CREDIT_PCT:.0%} (net of the discount most non-local "
                              f"studios take to monetize the credit) — no revenue trade-off.",
        }
        st.caption(fin_notes[financing_structure])

        ai_production_tools = st.checkbox(
            "🤖 Use AI Production Tools (previz / scheduling / VFX-assist)",
            value=bool(d.get("ai_production_tools", False)),
            help=f"Cuts the production-budget component of capital at risk ~{AI_TOOLS_BUDGET_SAVINGS_PCT:.0%} "
                 f"and pulls the whole revenue timeline forward {AI_TOOLS_TIMELINE_SHIFT_MO:.1f} months (faster "
                 f"post-production, less discounting) — but caps how high critical reception can land "
                 f"(a heavily AI-assisted production rarely produces a transcendent one, even if it reliably "
                 f"avoids a disaster) and carries its own independent setback risk. Not a free efficiency win.",
        )
        if ai_production_tools:
            st.caption(f"⚖️ Tradeoff active: cheaper & faster, but critical reception is capped at "
                       f"~{AI_TOOLS_CRITICAL_CEILING_MULT:.0%} of this genre's usual ceiling, and there's a "
                       f"real chance of its own AI-tooling setback at release.")

        posture_labels = {
            "standard": "Standard Split — 52% studio share, screens as requested",
            "aggressive": "Aggressive Split — 58% studio share, exhibitors cut ~8% of requested screens",
            "exhibitor_friendly": "Exhibitor-Friendly Split — 46% studio share, exhibitors add ~8% more screens",
        }
        exhibitor_posture = st.selectbox(
            "Exhibitor Negotiation Posture", EXHIBITOR_POSTURES,
            index=EXHIBITOR_POSTURES.index(d.get("exhibitor_posture", "standard"))
                  if d.get("exhibitor_posture") in EXHIBITOR_POSTURES else 0,
            format_func=lambda k: posture_labels[k],
            help="Push harder for a bigger box-office cut and exhibitors deprioritize your screens; "
                 "give them better terms and they promote you harder. Not a free lunch either way.",
        )

        capital = budget + pa
        realistic_max_screens = capital * 18   # rough real-world benchmark: a wide-release
                                                # distribution deal scales screen count with
                                                # studio confidence/spend, not the other way around
        if screens > realistic_max_screens:
            st.warning(
                f"⚠ {screens:,.0f} screens is a wide-release scale commitment for "
                f"${capital:.0f}M in total capital — real distribution deals don't hand a "
                f"small-budget film that many screens. The math will still run, but this "
                f"combination isn't realistic; consider more capital or fewer screens."
            )

    draft = dict(title=title, genre=genre, budget_m=budget, pa_spend_m=pa, star_power=star, screens=screens,
                 release_strategy=d.get("release_strategy", "wide_theatrical"), concept_type=concept_type,
                 financing_structure=financing_structure, exhibitor_posture=exhibitor_posture,
                 pay1_licensing=d.get("pay1_licensing", "keep"), ai_production_tools=ai_production_tools,
                 debut_season=d.get("debut_season", "Off-Peak"), source_material=source_material,
                 imax_release=imax_release,
                 pay1_platform=d.get("pay1_platform", DEFAULT_LICENSING_PLATFORM),
                 pay1_auction_fee_m=d.get("pay1_auction_fee_m"),
                 pay1_auction_winner=d.get("pay1_auction_winner"), pay1_auction_term_mo=d.get("pay1_auction_term_mo"),
                 pay2_licensing=d.get("pay2_licensing", "keep"),
                 pay2_platform=d.get("pay2_platform", DEFAULT_LICENSING_PLATFORM),
                 theatrical_run_length=d.get("theatrical_run_length"),
                 theatrical_run_days=d.get("theatrical_run_days"),
                 pvod_dynamic_pricing=d.get("pvod_dynamic_pricing", False),
                 pvod_chosen_price=d.get("pvod_chosen_price"),
                 library_ip=library_ip, lead_actor=lead_actor,
                 logline=d.get("logline", ""))   # display text, not a MovieProject field
    ss.movie_draft = draft
    project = _current_project(ss)

    if _research_covers(ss.movie_research_paid.get(ss.movie_cycle), genre, concept_type):
        with research_slot:
            _render_research_card(ss, project, logline)

    with right:
        st.markdown('<div class="section-title">Capital at Risk</div>', unsafe_allow_html=True)
        st.caption("Every dollar committed before a single ticket sells — production budget, P&A, "
                   "casting cost, and any rights acquisition, net of whatever your Financing "
                   "Structure and AI Production Tools choices discount. This is the number NPV is "
                   "measured against.")
        raw_capital = budget + pa
        financed_capital = project.capital_at_risk()
        savings_line = ""
        if financed_capital < raw_capital:
            savings_line = (f'<div class="flex justify-between text-sm py-1" style="color:{SUCCESS};">'
                             f'<span class="text-ink2">Financing Savings</span>'
                             f'<span class="font-mono">-${raw_capital - financed_capital:.1f}M</span></div>')
        star_cost_line = ""
        if star_cost > 0:
            star_cost_line = (f'<div class="flex justify-between text-sm py-1"><span class="text-ink2">'
                               f'{"Lead Actor Fee" if lead_actor else "Star Power Cost"}</span>'
                               f'<span class="font-mono text-warn">+${star_cost:.1f}M</span></div>')
        acq_line = ""
        if acq_cost > 0:
            acq_line = (f'<div class="flex justify-between text-sm py-1"><span class="text-ink2">'
                        f'{"Legacy IP Fee" if library_ip else "Rights Acquisition"}</span>'
                        f'<span class="font-mono text-warn">+${acq_cost:.1f}M</span></div>')
        imax_line = ""
        if project.is_imax_eligible():
            imax_line = (f'<div class="flex justify-between text-sm py-1"><span class="text-ink2">IMAX / Large Format</span>'
                         f'<span class="font-mono text-warn">+${IMAX_COST_M:.0f}M</span></div>')
        screen_cost = screens * SCREEN_COST_PER_SCREEN_M
        screen_cost_line = (
            f'<div class="flex justify-between text-sm py-1"><span class="text-ink2">Screen/Booking Fees</span>'
            f'<span class="font-mono text-warn">+${screen_cost:.1f}M</span></div>'
        )
        st.markdown(f"""
        <div class="rounded-lg border border-line bg-surface p-4">
          <div class="flex justify-between text-sm py-1"><span class="text-ink2">Production Budget</span>
            <span class="font-mono text-warn">${budget:.1f}M</span></div>
          <div class="flex justify-between text-sm py-1 border-b border-line pb-2"><span class="text-ink2">P&A Spend</span>
            <span class="font-mono text-warn">${pa:.1f}M</span></div>
          {star_cost_line}
          {acq_line}
          {imax_line}
          {screen_cost_line}
          {savings_line}
          <div class="flex justify-between text-base font-semibold pt-2">
            <span class="text-ink">Capital At Risk</span>
            <span class="font-mono text-danger">${financed_capital:.1f}M</span></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title mt-4">Projected Range (Wide Theatrical, before release-strategy choice)</div>',
                    unsafe_allow_html=True)
        bear_npv, base_npv, bull_npv = (project.npv(sc) for sc in ("bear", "base", "bull"))
        st.plotly_chart(
            _bear_base_bull_chart(bear_npv, base_npv, bull_npv,
                                   title="Bear → Base → Bull NPV ($M)"),
            use_container_width=True, config={"displayModeBar": False},
        )
        st.markdown(
            '<div style="font-size:13px;color:#ffffff;line-height:1.55;">'
            '<b>How to read this:</b> the chart shows <b>three possible outcomes</b> for this exact movie, '
            'one point each: <b>Bear</b> (a weak run), <b>Base</b> (the expected run), and <b>Bull</b> '
            '(a breakout hit). Each point is that outcome\'s NPV: all the revenue the movie would earn, '
            'converted to today\'s dollars, <b>minus the Capital at Risk above</b>. Above $0 the movie makes '
            'money in that outcome; below $0 it loses money. Every extra $10M of budget, P&A, or stars pushes '
            'all three down about $10M unless a bigger opening or longer run earns it back. This preview '
            'assumes a <b>wide release</b> (Release Strategy below shows each option\'s own range) and '
            '<b>no reviews yet</b>; critics are revealed when the movie comes out. The real result lands '
            'somewhere between Bear and Bull.</div>',
            unsafe_allow_html=True)

    st.divider()

    # Holding Deals render AFTER Greenlight -- booking a specific actor's
    # window only makes sense once the concept it's for actually exists.
    _section_holding_deals(ss, resolved_hold_key)

    # ── 6 · Release Plan — one row per film in the slate ─────────────────────
    # 2026-10-05, per explicit user request: "there should be a slate table
    # for release strategy on down through the theatrical simulate and the
    # simulate... that way, students can make decisions for entire slate
    # quickly and efficiently." One row per film, windows in the order they
    # open. Earlier films are locked (their real choices and result) except
    # Pay-2, which comes due the cycle after release; the current film's row
    # holds every release decision; later slots are placeholders. Follow-ups
    # that need a real interaction (Pay-1 competitive bids, PVOD market
    # rejections) render right under the table once they're triggered.
    st.markdown('<a id="release"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">6 · Release Plan — Your Slate</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-2">One row per film, windows in the order they open: <b>theaters</b> '
        '(release type and run length) → <b>PVOD</b> (premium rental at home; you set the price) → <b>Pay-1</b> '
        '(first streaming window: keep it on Peacock or license it) → <b>Pay-2</b> (second window, '
        f'~{PAY2_WINDOW_MONTH/12:.0f} years out, decided the cycle after release). Fill in this film\'s row, click '
        '<b>🎬 Theatrical Sim</b>, then set PVOD and Pay-1 with the real opening in hand.</p>',
        unsafe_allow_html=True)

    d = ss.movie_draft   # the live draft (Greenlight just rebuilt it), not the start-of-run copy
    windowing_unlocked = ss.movie_cycle >= WINDOWING_UNLOCK_CYCLE
    strategies_shown = RELEASE_STRATEGIES if windowing_unlocked else ["wide_theatrical"]
    final_film = ss.movie_cycle >= CYCLES_TOTAL
    platform_names = {k: v["name"] for k, v in LICENSING_PLATFORMS.items()}

    widths = [1.3, 1.85, 2.15, 0.85, 1.0, 1.55, 1.7, 1.35]
    headers = ["Film", "Season", "Release", "Run (days)", "PVOD price", "Pay-1", "Pay-2", "Status"]
    for c, h in zip(st.columns(widths), headers):
        c.markdown(f'<div class="font-mono" style="font-size:12px;border-bottom:1px solid #252836;'
                   f'padding-bottom:4px;">{h}</div>', unsafe_allow_html=True)

    def _cell(col, text):
        col.markdown(f'<div style="font-size:13px;padding-top:8px;line-height:1.35;">{text}</div>',
                     unsafe_allow_html=True)

    def _pay1_text(kw):
        if kw.get("release_strategy") == "day_and_date" or kw.get("pay1_licensing", "keep") == "keep":
            return "Peacock"
        if kw.get("pay1_auction_winner"):
            return f"{kw['pay1_auction_winner']} (bid)"
        return platform_names.get(kw.get("pay1_platform"), "Licensed")

    def _pay2_text(entry):
        kw = entry["project_kwargs"]
        if entry.get("pay2_outcome"):
            return entry["pay2_outcome"]
        if kw.get("pay2_licensing", "keep") == "keep":
            return "Peacock"
        return platform_names.get(kw.get("pay2_platform"), "Licensed")

    # Pay-2 (2026-10-05 rework, per explicit user request for more intensity):
    # Keep is a gamble on the film's catalog life (expected value rises with
    # reviews, realized value revealed on lock); licensing is a guaranteed fee
    # whose size depends on each streamer's appetite THIS cycle. Locking is
    # final, so a team can't peek at the draw and switch.
    pay2_offers = draw_pay2_offer_mults(ss.team_name, ss.movie_cycle)
    rev_lo, rev_hi = pay2_revival_quantiles()

    def _pay2_choices(entry) -> dict:
        """NPV effect of each Pay-2 option for a logged film, versus not
        having made the call: Keep's expected / p10 / p90, and each
        streamer's guaranteed offer this cycle."""
        kw = entry["project_kwargs"]
        base_kw = {**kw, "pay2_decided": False, "pay2_licensing": "keep",
                   "pay2_keep_mult": None, "pay2_fee_mult": None}
        undecided = _film_npv(entry, base_kw)
        keep = {q: _film_npv(entry, {**base_kw, "pay2_decided": True, "pay2_keep_mult": m}) - undecided
                for q, m in (("exp", None), ("p10", rev_lo), ("p90", rev_hi))}
        offers = {k: _film_npv(entry, {**base_kw, "pay2_decided": True, "pay2_licensing": "license_out",
                                       "pay2_platform": k, "pay2_fee_mult": pay2_offers[k]}) - undecided
                  for k in LICENSING_PLATFORMS}
        return {"keep": keep, "offers": offers}

    def _lock_pay2(cyc: int):
        """Lock an earlier film's Pay-2 call: realize Keep's catalog draw or
        the chosen streamer's offer, and re-price the film with the same
        resolved draws -- only the Pay-2 window changes. Final."""
        pick = ss.get(f"pay2_slate_{cyc}")
        entry = next((r for r in ss.movie_log if r["cycle"] == cyc), None)
        if entry is None or pick is None or entry.get("pay2_decided_cycle") is not None:
            return
        kw = entry["project_kwargs"]
        base_kw = {**kw, "pay2_decided": True, "pay2_keep_mult": None, "pay2_fee_mult": None}
        if pick == "keep":
            revival = draw_pay2_revival(ss.team_name, cyc)
            new_kw = {**base_kw, "pay2_licensing": "keep", "pay2_keep_mult": revival}
        else:
            new_kw = {**base_kw, "pay2_licensing": "license_out", "pay2_platform": pick,
                      "pay2_fee_mult": pay2_offers[pick]}
        delta = _film_npv(entry, new_kw) - _film_npv(entry, kw)
        mults = dict(pvod_mult=entry.get("pvod_mult", 1.0), theme_park_mult=entry.get("theme_park_mult", 1.0),
                     ewom_mult=entry.get("ewom_mult", 1.0))
        p_new = MovieProject(**new_kw)
        entry["project_kwargs"] = new_kw
        entry["npv"] += delta
        entry["irr"] = p_new.irr(entry["multiplier"], entry["critical_score"], **mults)
        entry["total_revenue"] = p_new.total_revenue(entry["multiplier"], entry["critical_score"], **mults)
        entry["pay2_decided_cycle"] = ss.movie_cycle
        entry["pay2_npv_delta"] = entry.get("pay2_npv_delta", 0.0) + delta
        if pick == "keep":
            read = "strong" if revival >= 1.25 else ("as expected" if revival >= 0.8 else "weak")
            entry["pay2_outcome"] = f"Kept: catalog {read} ({_fmt_money(delta)})"
        else:
            entry["pay2_outcome"] = f"{platform_names[pick]} ({_fmt_money(delta)})"

    log_by_cycle = {r["cycle"]: r for r in ss.movie_log}
    current_row = None
    pay2_notes = []
    for cyc in range(1, CYCLES_TOTAL + 1):
        row = st.columns(widths)
        if cyc == ss.movie_cycle:
            current_row = row     # filled in below, once the theatrical state is known
            continue
        entry = log_by_cycle.get(cyc)
        if entry is None:
            _cell(row[0], f"{cyc} · <i>greenlight in {_cycle_years_label(cyc)}</i>")
            for c in row[1:]:
                _cell(c, "—")
            continue
        kw = entry["project_kwargs"]
        is_dd = kw.get("release_strategy") == "day_and_date"
        _cell(row[0], f"{cyc} · {escape(kw['title'])}")
        _cell(row[1], kw.get("debut_season", "Off-Peak"))
        _cell(row[2], RELEASE_LABELS.get(kw.get("release_strategy"), kw.get("release_strategy")))
        _cell(row[3], f"{MovieProject(**kw).window_days()}")
        _cell(row[4], "—" if is_dd or not kw.get("pvod_chosen_price") else f"${kw['pvod_chosen_price']:.2f}")
        _cell(row[5], _pay1_text(kw))
        pay2_due = not is_dd and cyc < ss.movie_cycle and entry.get("pay2_decided_cycle") is None
        if pay2_due:
            ch = _pay2_choices(entry)
            opts = ["keep"] + list(LICENSING_PLATFORMS)
            pick = row[6].selectbox(
                f"Pay-2 for Film {cyc}", opts, index=None, placeholder="⚠ Choose…",
                key=f"pay2_slate_{cyc}", label_visibility="collapsed",
                format_func=lambda k: "🎲 Keep" if k == "keep" else f"✓ {platform_names[k].split()[0]}",
                help="🎲 Keep (gamble): the film stays in Peacock's catalog and earns whatever its catalog life turns out to be. "
                     "License: a guaranteed fee now. The expected values and ranges are listed under the table. "
                     "Lock it in the Status column; locking is final.")
            if pick is None:
                _cell(row[7], f"{'✅' if entry['npv'] >= 0 else '❌'} {_fmt_money(entry['npv'])}")
            else:
                row[7].button("💼 Lock Pay-2", key=f"lock_pay2_{cyc}", on_click=_lock_pay2, args=(cyc,),
                              use_container_width=True, help="Final: reveals Keep's catalog outcome, or signs the deal.")
            offers_txt = " · ".join(f"{platform_names[k]} {_fmt_money(v)} guaranteed"
                                    for k, v in ch["offers"].items())
            pay2_notes.append(
                f"💼 <b>Film {cyc} Pay-2</b> (critics {entry['critical_score']:.0f}/100): Keep ≈ "
                f"{_fmt_money(ch['keep']['exp'])} expected, likely range {_fmt_money(ch['keep']['p10'])} to "
                f"{_fmt_money(ch['keep']['p90'])} · or license: {offers_txt}. Better reviews make Keep worth more.")
        else:
            if is_dd:
                _cell(row[6], "Peacock (D&amp;D)")
            elif cyc > ss.movie_cycle:
                _cell(row[6], "—")
            else:
                _cell(row[6], escape(_pay2_text(entry)))
            _cell(row[7], f"{'✅' if entry['npv'] >= 0 else '❌'} {_fmt_money(entry['npv'])}")

    # ── The current film's row ────────────────────────────────────────────────
    _cell(current_row[0], f"<b>{ss.movie_cycle} · {escape(title)}</b><br><span style='font-size:11px;'>this film</span>")

    # Debut Season (Phase 5, 2026-08-05): release timing. Summer/Holiday open
    # bigger but crowd out awards recall; Fall/Awards opens softer but is the
    # awards on-ramp; Off-Peak is the neutral baseline.
    debut_season = current_row[1].selectbox(
        "Debut Season", DEBUT_SEASONS,
        index=DEBUT_SEASONS.index(d.get("debut_season", "Off-Peak")) if d.get("debut_season") in DEBUT_SEASONS else 0,
        label_visibility="collapsed",
        help="Summer Tentpole/Holiday open bigger (more audience, more competition) but a summer release "
             "rarely gets recalled by awards voters. Fall/Awards opens softer but is the industry on-ramp "
             "into awards season. Off-Peak is neutral.",
    )
    ss.movie_draft["debut_season"] = debut_season
    project_base = MovieProject(**{**project.__dict__, "debut_season": debut_season})
    ra_by_strategy = {s: risk_adjusted_npv(MovieProject(**{**project_base.__dict__, "release_strategy": s}))
                      for s in strategies_shown}
    cur_strat = d.get("release_strategy", "wide_theatrical")
    if cur_strat not in strategies_shown:
        cur_strat = strategies_shown[0]
    release_key = f"release_strategy_{ss.movie_cycle}"
    if ss.get(release_key) not in strategies_shown:
        ss[release_key] = cur_strat   # seed once; the key alone then carries the student's pick
    chosen = current_row[2].selectbox(
        "Release Strategy", strategies_shown,
        key=release_key,
        # Plain labels on purpose: on older Streamlit (the local 1.45 install)
        # a widget's identity includes its option labels, so live NPVs in
        # them would reset the pick whenever a number moved. The NPV of each
        # option is shown in the line under the table instead.
        format_func=lambda s: RELEASE_LABELS[s],
        disabled=not windowing_unlocked, label_visibility="collapsed",
        help="Each option's risk-adjusted NPV for this film is listed under the table. Wide Theatrical suits tentpoles; "
             "Platform opens small and expands (strongest for drama/awards); Day-and-Date premieres in theaters "
             "and on Peacock together, giving up box office for subscriber value."
             + ("" if windowing_unlocked else
                f" Only Wide Theatrical is available until {_cycle_years_label(WINDOWING_UNLOCK_CYCLE)}."),
    )
    ss.movie_draft["release_strategy"] = chosen

    default_days = d.get("theatrical_run_days") or THEATRICAL_RUN_LENGTHS["Standard"]
    theatrical_run_days = int(current_row[3].number_input(
        "Theatrical Run Length (days)", RUN_LENGTH_DAYS_MIN, RUN_LENGTH_DAYS_MAX, int(default_days), step=5,
        label_visibility="collapsed",
        help=f"Short≈{THEATRICAL_RUN_LENGTHS['Short']}d · Standard≈{THEATRICAL_RUN_LENGTHS['Standard']}d · "
             f"Extended≈{THEATRICAL_RUN_LENGTHS['Extended']}d. Longer runs capture more box office (diminishing "
             "returns) but delay every later window, which costs NPV through discounting. Universal's own "
             "benchmark: at least 30 days if a film opens above $50M.",
    ))
    ss.movie_draft["theatrical_run_days"] = theatrical_run_days
    ss.movie_draft["theatrical_run_length"] = None   # superseded by the exact day count

    current_lock_inputs = {"genre": genre, "concept_type": concept_type,
                           "ai_production_tools": ai_production_tools, "source_material": source_material}
    resolved_entry = ss.movie_theatrical_resolved.get(ss.movie_cycle)
    inputs_changed = resolved_entry is not None and resolved_entry["locked_inputs"] != current_lock_inputs
    if inputs_changed:
        resolved_entry = None
    live_project = MovieProject(**{**project.__dict__, "release_strategy": chosen, "debut_season": debut_season,
                                   "theatrical_run_days": theatrical_run_days, "theatrical_run_length": None})

    # PVOD price -- band sized off the REAL theatrical result, so it only
    # exists after the Theatrical Sim. The input defaults from the price the
    # student picked (pvod_selected_price), never from pvod_chosen_price,
    # which also carries the Market Checks' post-cut price (2026-08-18 fix).
    pvod_price = None
    lo = hi = None
    if chosen == "day_and_date":
        _cell(current_row[4], "—")
        ss.movie_draft["pvod_chosen_price"] = None
        ss.movie_draft["pvod_selected_price"] = None
    elif resolved_entry is None:
        _cell(current_row[4], "<i>after Theatrical Sim</i>")
        ss.movie_draft["pvod_chosen_price"] = None
        ss.movie_draft["pvod_selected_price"] = None
    else:
        lo, hi = pvod_price_band(resolved_entry["multiplier"], genre, concept_type)
        existing_price = d.get("pvod_selected_price")
        default_price = existing_price if existing_price is not None and lo <= existing_price <= hi \
            else round((lo + hi) / 2, 2)
        pvod_price = float(current_row[4].number_input(
            "PVOD Rental Price", float(lo), float(hi), float(default_price), step=0.50, format="%.2f",
            label_visibility="collapsed",
            help=f"Your band is \\${lo:.2f}–\\${hi:.2f}, sized off this film's real opening. Higher prices earn more "
                 "per rental but sell fewer, and the market may reject a price near the top (see checks below)."))
        ss.movie_draft["pvod_chosen_price"] = pvod_price
        ss.movie_draft["pvod_selected_price"] = pvod_price
    ss.movie_draft["pvod_dynamic_pricing"] = False

    # Pay-1 -- keep on Peacock, license at a flat fee, or (below) take a
    # competitive bid. An accepted bid shows up here as its own option.
    pay1_key = f"pay1_pick_{ss.movie_cycle}"
    if chosen == "day_and_date":
        _cell(current_row[5], "Peacock (D&amp;D)")
        ss.movie_draft["pay1_licensing"] = "keep"
    elif resolved_entry is None:
        _cell(current_row[5], "<i>after Theatrical Sim</i>")
    else:
        winner = d.get("pay1_auction_winner")
        pay1_opts = ["keep"] + list(LICENSING_PLATFORMS) + (["bid"] if winner else [])

        def _pay1_changed():
            if ss.get(pay1_key) != "bid":
                ss.movie_draft["pay1_auction_fee_m"] = None
                ss.movie_draft["pay1_auction_winner"] = None
                ss.movie_draft["pay1_auction_term_mo"] = None
        cur_pay1 = ("bid" if winner else "keep" if d.get("pay1_licensing", "keep") == "keep"
                    else d.get("pay1_platform", DEFAULT_LICENSING_PLATFORM))
        if ss.get(pay1_key) not in pay1_opts:
            ss[pay1_key] = cur_pay1   # seed once; the key alone then carries the student's pick
        pay1_pick = current_row[5].selectbox(
            "Pay-1 Window", pay1_opts, key=pay1_key,
            label_visibility="collapsed", on_change=_pay1_changed,
            format_func=lambda k: ("Keep on Peacock" if k == "keep" else
                                   f"{winner} bid ${d.get('pay1_auction_fee_m') or 0:.1f}M" if k == "bid" else
                                   f"{platform_names[k]} (~{LICENSING_PLATFORMS[k]['fee_pct']:.0%} fee)"),
            help="Keep on Peacock: full subscriber value, tied to how the film performs. License: a flat, "
                 "guaranteed fee (a % of base-case subscriber value), paid sooner. Or shop it to competitive "
                 "bidders below the table.")
        if pay1_pick == "keep":
            ss.movie_draft["pay1_licensing"] = "keep"
        elif pay1_pick == "bid":
            ss.movie_draft["pay1_licensing"] = "license_out"
        else:
            ss.movie_draft["pay1_licensing"] = "license_out"
            ss.movie_draft["pay1_platform"] = pay1_pick

    # Pay-2 -- opens years after release, so it's decided next cycle (as
    # this film's row up top), except on the final film.
    if chosen == "day_and_date":
        _cell(current_row[6], "Peacock (D&amp;D)")
        ss.movie_draft["pay2_licensing"] = "keep"
    elif not final_film:
        _cell(current_row[6], "<i>decide next cycle</i>")
        ss.movie_draft["pay2_licensing"] = "keep"
    else:
        pay2_opts = ["keep"] + list(LICENSING_PLATFORMS)
        cur_pay2 = ("keep" if d.get("pay2_licensing", "keep") == "keep"
                    else d.get("pay2_platform", DEFAULT_LICENSING_PLATFORM))
        pay2_pick = current_row[6].selectbox(
            "Pay-2 Window", pay2_opts, index=pay2_opts.index(cur_pay2) if cur_pay2 in pay2_opts else 0,
            label_visibility="collapsed",
            format_func=lambda k: "🎲 Keep" if k == "keep" else f"✓ {platform_names[k].split()[0]}",
            help=f"Your final film, so decide Pay-2 now. It opens ~{PAY2_WINDOW_MONTH/12:.0f} years after "
                 "release. Keep: the film stays in Peacock's catalog and earns whatever its catalog life turns "
                 "out to be (better reviews, more value). License: a guaranteed fee, sized by that streamer's "
                 "appetite this cycle. The outcome is revealed at Simulate.")
        ss.movie_draft["pay2_licensing"] = "keep" if pay2_pick == "keep" else "license_out"
        if pay2_pick != "keep":
            ss.movie_draft["pay2_platform"] = pay2_pick

    # Status -- the Theatrical Sim button lives in the row itself.
    if resolved_entry is None:
        if current_row[7].button("🎬 Theatrical Sim", key=f"run_theatrical_{ss.movie_cycle}",
                                 use_container_width=True,
                                 help="Locks in this film's real opening, reviews and any surprises, so you can "
                                      "set PVOD and Pay-1 with the result in hand."):
            ss.movie_theatrical_resolved[ss.movie_cycle] = _resolve_movie_outcome(ss, live_project)
            st.rerun()
    else:
        dom_bo = live_project.domestic_box_office(resolved_entry["multiplier"])
        _cell(current_row[7], f"✅ ${dom_bo:.0f}M domestic<br>critics {resolved_entry['critical_score']:.0f}/100")

    # ── Notes and follow-ups under the table ─────────────────────────────────
    season_open_mult = (SEASON_OPENING_MULT.get(debut_season, 1.0)
                        * SEASON_GENRE_SYNERGY.get(debut_season, {}).get(genre, 1.0))
    season_recall = SEASON_AWARDS_RECALL.get(debut_season, 1.0)
    notes = ["💡 Risk-adjusted NPV by release: " + " · ".join(
        f"{RELEASE_LABELS[s]} {_fmt_money(ra_by_strategy[s])}" for s in strategies_shown)]
    if season_open_mult != 1.0:
        notes.append(f"📅 {debut_season}: {'+' if season_open_mult > 1 else ''}{(season_open_mult - 1) * 100:.0f}% "
                     f"opening for {genre}")
    if genre in AWARDS_ELIGIBLE_GENRES and season_recall != 1.0:
        notes.append(f"{season_recall:.0%} awards recall")
    if not windowing_unlocked:
        notes.append(f"🔒 Platform and Day-and-Date unlock {_cycle_years_label(WINDOWING_UNLOCK_CYCLE)}")
    notes.append(f"🎞️ {theatrical_run_days} days in theaters = {run_days_box_office_mult(theatrical_run_days):.2f}x "
                 f"box office")
    st.caption(" · ".join(notes).replace("$", "\\$"))   # bare $ pairs render as LaTeX math
    if pay2_notes:
        st.markdown('<div style="font-size:13px;line-height:1.6;margin:2px 0 6px;">' + "<br>".join(pay2_notes)
                    + '</div>', unsafe_allow_html=True)
    if inputs_changed:
        st.info("⚠ Your Greenlight choices (Genre / Concept Type / Source Material / AI Production Tools) changed "
                "since you ran the Theatrical Sim. Click 🎬 Theatrical Sim again to lock in a fresh result.")

    if resolved_entry is not None:
        r = resolved_entry
        event_notes = [n for n in (r["trouble_reason"], r["ai_setback_reason"],
                                   r["ancillary_reason"], r["ewom_reason"]) if n]
        stars = multiplier_to_stars(r["multiplier"], genre, concept_type)
        st.markdown(
            f'<div style="font-size:13px;line-height:1.6;margin:4px 0 8px;">🎬 <b>Theatrical Sim locked in:</b> '
            f'{"⭐" * stars}{"☆" * (5 - stars)} audience demand · '
            f'${live_project.domestic_box_office(r["multiplier"]):.1f}M domestic · critics {r["critical_score"]:.0f}/100 · '
            f'{theatrical_run_days}-day run'
            + "".join(f"<br>⚡ {escape(e)}" for e in event_notes) + '</div>', unsafe_allow_html=True)

    # ── PVOD Market Acceptance Checks ────────────────────────────────────────
    # 2026-08-18, per explicit user request: "the market may or may not
    # accept it every 6 months, let's say." Accepted checkpoints resolve
    # silently in sequence (own independent seed, see draw_pvod_market_
    # rejection) -- the FIRST rejection pauses here and requires a real
    # choice (per explicit user decision: hold vs. cut, not a passive
    # automatic haircut) before Simulate unlocks again. No rejection at
    # all across both checkpoints leaves pvod_market_mult at its true
    # 1.0 zero-effect default.
    ss.movie_draft["pvod_market_mult"] = 1.0
    if chosen != "day_and_date" and resolved_entry is not None and pvod_price is not None:
        st.markdown('<div class="section-title mt-3">PVOD Market Acceptance Checks</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="text-xs text-ink2 mb-2">Every 6 months the market gets a real chance to reject '
            'your PVOD price — pricing near the top of your band is a real gamble, pricing near the '
            'floor is nearly always accepted. A rejection is a real choice: hold the price (an ongoing '
            'conversion cost) or cut it toward the floor (a one-time disruption cost, but the lower '
            'price sticks for the rest of the window).</p>', unsafe_allow_html=True)

        cps = ss.movie_pvod_checkpoints.get(ss.movie_cycle, [])
        # A changed price after checkpoints started invalidates the sequence --
        # same "changed the inputs, redo it" posture as the mini-run/Pay-1 locks.
        if cps and cps[0]["price_before"] != pvod_price:
            cps = []
            ss.movie_pvod_checkpoints[ss.movie_cycle] = []
            ss.movie_pvod_pending_rejection.pop(ss.movie_cycle, None)

        pending = ss.movie_pvod_pending_rejection.get(ss.movie_cycle)
        current_price = cps[-1]["price_after"] if cps else pvod_price

        # Silently auto-resolve every accepted checkpoint in order; stop at
        # the first rejection, which needs a real response before continuing.
        if pending is None:
            while len(cps) < len(PVOD_MARKET_CHECK_MONTHS):
                next_month = PVOD_MARKET_CHECK_MONTHS[len(cps)]
                price_frac = (current_price - lo) / (hi - lo) if hi > lo else 0.0
                if draw_pvod_market_rejection(ss.team_name, ss.movie_cycle, len(cps), price_frac):
                    pending = {"month": next_month, "price_before": current_price}
                    ss.movie_pvod_pending_rejection[ss.movie_cycle] = pending
                    break
                cps.append({"month": next_month, "price_before": current_price, "rejected": False,
                            "response": None, "price_after": current_price, "buzz": None})
                ss.movie_pvod_checkpoints[ss.movie_cycle] = cps
                current_price = cps[-1]["price_after"]

        for cp in cps:
            if not cp["rejected"]:
                st.caption(f"✅ Month {cp['month']:.0f}: market accepted your ${cp['price_before']:.2f} price.")
            else:
                # `\\$` throughout: this caption carries two dollar amounts, and two bare
                # `$` render as LaTeX math (the text between them comes out garbled).
                resp_txt = f"held at \\${cp['price_after']:.2f}" if cp["response"] == "hold" else f"cut to \\${cp['price_after']:.2f}"
                buzz_txt = ""
                if cp.get("buzz") == "awards":
                    buzz_txt = " — the wider audience sparked real buzz, a critical-reception boost."
                elif cp.get("buzz") == "sequel":
                    buzz_txt = " — the wider audience sparked real buzz, a Sequel Potential spark."
                st.caption(f"⚠ Month {cp['month']:.0f}: market rejected \\${cp['price_before']:.2f} — you {resp_txt}.{buzz_txt}")

        if pending is not None:
            st.warning(f"⚠ Month {pending['month']:.0f}: the market rejected your "
                       f"${pending['price_before']:.2f} PVOD price. How do you respond?")
            cut_price = round(pending["price_before"] - (pending["price_before"] - lo) * PVOD_CUT_STEP_FRAC, 2)
            hcol1, hcol2 = st.columns(2)
            checkpoint_key = f"{ss.movie_cycle}_{len(cps)}"
            with hcol1:
                if st.button(f"Hold at ${pending['price_before']:.2f}", key=f"pvod_hold_{checkpoint_key}", use_container_width=True):
                    cps.append({"month": pending["month"], "price_before": pending["price_before"],
                                "rejected": True, "response": "hold", "price_after": pending["price_before"],
                                "buzz": None})
                    ss.movie_pvod_checkpoints[ss.movie_cycle] = cps
                    ss.movie_pvod_pending_rejection.pop(ss.movie_cycle, None)
                    st.rerun()
            with hcol2:
                if st.button(f"Cut to ${cut_price:.2f}", key=f"pvod_cut_{checkpoint_key}", use_container_width=True):
                    # 2026-08-18, per explicit user request: a price cut carries a
                    # real, randomized chance of buzz feeding awards momentum or
                    # Sequel Potential -- see draw_pvod_cut_buzz's docstring.
                    buzz = draw_pvod_cut_buzz(ss.team_name, ss.movie_cycle, len(cps))
                    cps.append({"month": pending["month"], "price_before": pending["price_before"],
                                "rejected": True, "response": "cut", "price_after": cut_price,
                                "buzz": buzz})
                    ss.movie_pvod_checkpoints[ss.movie_cycle] = cps
                    ss.movie_pvod_pending_rejection.pop(ss.movie_cycle, None)
                    st.rerun()

        cps = ss.movie_pvod_checkpoints.get(ss.movie_cycle, [])
        if cps:
            ss.movie_draft["pvod_chosen_price"] = cps[-1]["price_after"]
            mult = 1.0
            for cp in cps:
                if cp["rejected"]:
                    mult *= PVOD_HOLD_THROUGH_REJECTION_MULT if cp["response"] == "hold" else PVOD_CUT_RESPONSE_MULT
            ss.movie_draft["pvod_market_mult"] = mult

    # ── Pay-1 Competitive Bidding (follow-up under the table) ─────────────────
    # 2026-08-18, per explicit user request: rival platforms bid for the
    # Pay-1 window, sized off this film's ACTUAL theatrical result. An
    # accepted bid becomes the Pay-1 cell's own option in the table above.
    if chosen != "day_and_date" and resolved_entry is not None:
        st.markdown('<div class="section-title mt-3" style="font-size:13px;">🏷️ Pay-1: Shop It to Competitive Bidders '
                    '<span class="text-xs text-muted">(optional)</span></div>', unsafe_allow_html=True)

        def _run_bid_round(round_num: int) -> dict:
            anchor_value = live_project.subscriber_value(resolved_entry["multiplier"])
            # Game theory (2026-08-18): each bidder's appetite ties into the
            # real background slate -- see draw_licensing_bidder_appetite.
            bg_slate = generate_background_slate(ss.team_name, ss.movie_cycle,
                                                 studio_budget_m=ss.movie_studio_budget_m)
            appetite = draw_licensing_bidder_appetite(ss.team_name, ss.movie_cycle, bg_slate)
            appetite_mult = {b: v["mult"] for b, v in appetite.items()}
            bids = draw_licensing_bids(ss.team_name, ss.movie_cycle, anchor_value,
                                       appetite_mult=appetite_mult, round_num=round_num)
            return {"bids": bids, "result": resolve_licensing_auction(bids), "appetite": appetite,
                    "round": round_num}

        def _accept_bid(bidder: str, fee: float, term):
            # on_click, so it runs before the Pay-1 cell is drawn on the rerun.
            ss.movie_draft["pay1_licensing"] = "license_out"
            ss.movie_draft["pay1_auction_fee_m"] = fee
            ss.movie_draft["pay1_auction_winner"] = bidder
            ss.movie_draft["pay1_auction_term_mo"] = term
            ss[pay1_key] = "bid"

        auction = ss.movie_licensing_auction.get(ss.movie_cycle)
        if auction is None:
            st.markdown('<p class="text-xs text-ink2 mb-1">Instead of a flat fee, rival platforms bid on the Pay-1 '
                        'window based on how this film actually opened. Not every platform bids. (Real '
                        'streamers, simulated bids.)</p>',
                        unsafe_allow_html=True)
            if st.button("🏷️ Shop This Window to Competitive Bid", key=f"shop_bids_{ss.movie_cycle}",
                         use_container_width=True):
                ss.movie_licensing_auction[ss.movie_cycle] = _run_bid_round(1)
                st.rerun()
        else:
            result = auction["result"]
            round_num = auction.get("round", 1)
            if round_num > 1:
                st.markdown('<p class="text-xs text-ink2 mb-1">🔁 <b>Round 2</b>: you took the window back to '
                            'market. The first round\'s offers are gone.</p>', unsafe_allow_html=True)
            if not result["all_bids"]:
                st.caption("No platforms made an offer this round. Keep it on Peacock or take a flat fee in the "
                           "Pay-1 cell above.")
            else:
                st.markdown(
                    '<p class="text-xs text-ink2 mb-2">Accept <b>any</b> offer, not just the highest. When a bid\'s '
                    'term ends, the film returns to Peacock and you keep part of its subscriber value '
                    f'({PAY1_REVERSION_SHARE[12]:.0%} after 12 months, {PAY1_REVERSION_SHARE[18]:.0%} after 18), '
                    'so a lower bid on a shorter term can be worth more.</p>', unsafe_allow_html=True)
                appetite = auction.get("appetite", {})
                sub_val = live_project.subscriber_value(resolved_entry["multiplier"])
                accepted = ss.movie_draft.get("pay1_auction_winner")
                for b in result["all_bids"]:
                    state = appetite.get(b["bidder"], {}).get("state")
                    flavor = licensing_appetite_flavor(b["bidder"], state)
                    icon = "🔥" if state == "hot" else ("⚠" if state == "hungry" else "")
                    term = b.get("term_mo")
                    kept = sub_val * PAY1_REVERSION_SHARE.get(term, 0.0) if term else 0.0
                    term_html = f' · {term}-month term, ~${kept:.1f}M back to Peacock after' if term else ""
                    flavor_html = f'<div style="font-size:11px;">{icon} {flavor}</div>' if flavor else ""
                    bc1, bc2 = st.columns([3, 1])
                    bc1.markdown(f'<div style="font-size:13px;padding:4px 0;"><b>{b["bidder"]}</b>: '
                                 f'${b["bid_m"]:.1f}M{term_html}{flavor_html}</div>', unsafe_allow_html=True)
                    if accepted == b["bidder"]:
                        bc2.markdown('<div style="font-size:13px;padding:4px 0;">✅ Accepted</div>',
                                     unsafe_allow_html=True)
                    else:
                        bc2.button("Accept", key=f"accept_bid_{ss.movie_cycle}_{round_num}_{b['bidder']}",
                                   use_container_width=True, on_click=_accept_bid,
                                   args=(b["bidder"], b["bid_m"], term))

            # Take it back to market: once per cycle, only before accepting anything.
            if round_num < LICENSING_MAX_ROUNDS and not ss.movie_draft.get("pay1_auction_winner"):
                lo_r, hi_r = LICENSING_RESHOP_MULT_RANGE
                st.markdown(
                    '<p class="text-xs text-ink2 mt-2 mb-1">Not happy with these offers? Reject all of them and take '
                    'the window back to market <b>once</b>. Buyers know the title was passed over, so new bids '
                    f'typically land {1 - hi_r:.0%}–{1 - lo_r:.0%} lower, and some platforms may not bid at all.</p>',
                    unsafe_allow_html=True)
                if st.button("🔁 Reject All & Take It Back to Market", key=f"reshop_bids_{ss.movie_cycle}",
                             use_container_width=True):
                    ss.movie_licensing_auction[ss.movie_cycle] = _run_bid_round(round_num + 1)
                    st.rerun()

    st.divider()

    # ── Simulate ───────────────────────────────────────────────────────────────
    # 2026-08-18: Simulate no longer rolls the theatrical outcome itself --
    # it reuses the Theatrical Mini-Run's locked result (see
    # _resolve_movie_outcome), so the button is disabled until that step is
    # done. The fresh-resolve fallback below only fires if that invariant
    # is ever violated (e.g. a legacy/malformed session) -- normal play
    # never exercises it.
    st.markdown('<a id="simulate"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">7 · Simulate</div>', unsafe_allow_html=True)
    pending_pvod_response = ss.movie_pvod_pending_rejection.get(ss.movie_cycle) is not None
    has_logline = len(ss.movie_draft.get("logline", "").strip()) >= 20
    # Required steps (2026-10-05): Partnerships / Scouted / Festivals /
    # Holding Deals gate Simulate alongside the pitch and theatrical run.
    missing = [(i, label, todo) for i, label, _, done, todo in _numbered_steps(ss)
               if not done and label not in ("Greenlight", "Release")]
    if not has_logline:
        missing.append((4, "Greenlight", "write your Pitch / Logline (at least a sentence)"))
    if resolved_entry is None:
        missing.append((6, "Release", "click 🎬 Theatrical Sim in the Release Plan table"))
    can_simulate = not missing and not pending_pvod_response
    for i, label, todo in sorted(missing, key=lambda m: (m[0], m[1] != "Pay-2 (earlier films)")):
        st.caption(f"⚠ Step {i} · {label}: {todo} before you can Simulate.")
    if resolved_entry is not None and pending_pvod_response:
        st.caption("⚠ Respond to the PVOD Market Acceptance rejection above before you can Simulate the full year.")
    if st.button("▶  Simulate  →  See Results", type="primary", use_container_width=True, disabled=not can_simulate):
        project = _current_project(ss)
        if ss.movie_cycle >= CYCLES_TOTAL and project.release_strategy != "day_and_date":
            # Final film: its Pay-2 call was made in its Release Plan row, so
            # realize it now -- Keep's catalog draw, or the streamer's offer.
            if project.pay2_licensing == "keep":
                project = replace(project, pay2_decided=True,
                                  pay2_keep_mult=draw_pay2_revival(ss.team_name, ss.movie_cycle))
            else:
                project = replace(project, pay2_decided=True, pay2_fee_mult=draw_pay2_offer_mults(
                    ss.team_name, ss.movie_cycle).get(project.pay2_platform, 1.0))
        current_inputs = {"genre": project.genre, "concept_type": project.concept_type,
                           "ai_production_tools": project.ai_production_tools,
                           "source_material": project.source_material}
        resolved = ss.movie_theatrical_resolved.get(ss.movie_cycle)
        if resolved is None or resolved["locked_inputs"] != current_inputs:
            resolved = _resolve_movie_outcome(ss, project)
        multiplier          = resolved["multiplier"]
        critical_score       = resolved["critical_score"]
        talent_bonus         = resolved["talent_bonus"]
        trouble_reason        = resolved["trouble_reason"]
        ai_setback_reason     = resolved["ai_setback_reason"]
        ancillary_reason      = resolved["ancillary_reason"]
        theme_park_mult       = resolved["theme_park_mult"]
        ewom_reason           = resolved["ewom_reason"]
        ewom_mult             = resolved["ewom_mult"]
        # PVOD Market Acceptance Checks (2026-08-18): folds the resolved
        # hold/cut journey's multiplier into the SAME pvod_mult slot
        # Ancillary Surprise already uses -- no movie_models.py signature
        # changes needed. 1.0 (true no-op) if the student never hit a
        # rejection, or never opened the PVOD section at all (day_and_date).
        pvod_mult = resolved["pvod_mult"] * ss.movie_draft.get("pvod_market_mult", 1.0)

        # PVOD Cut-Response Buzz (2026-08-18): aggregate any buzz drawn when
        # the student chose to cut price in response to a market rejection
        # (see draw_pvod_cut_buzz). 1.0-no-op-equivalent (empty/None) for a
        # student who never triggered a rejection or never cut.
        this_cycle_checkpoints = ss.movie_pvod_checkpoints.get(ss.movie_cycle, [])
        cut_buzz_awards_hits = sum(1 for cp in this_cycle_checkpoints if cp.get("buzz") == "awards")
        cut_buzz_sequel = any(cp.get("buzz") == "sequel" for cp in this_cycle_checkpoints)
        if cut_buzz_awards_hits:
            critical_score = min(100.0, critical_score + PVOD_CUT_BUZZ_AWARDS_BONUS * cut_buzz_awards_hits)

        awards_eligible = project.genre in AWARDS_ELIGIBLE_GENRES
        waterfall = participation_waterfall(project, multiplier, critical_score,
                                             pvod_mult=pvod_mult, theme_park_mult=theme_park_mult,
                                             ewom_mult=ewom_mult)
        outcome = {
            "cycle":            ss.movie_cycle,
            "project_kwargs":   dict(project.__dict__),
            "logline":          ss.movie_draft.get("logline", ""),
            "multiplier":       multiplier,
            "scenario_label":   nearest_scenario_label(multiplier, project.genre, project.concept_type),
            "critical_score":   critical_score,
            "awards_contender": awards_eligible and critical_score >= AWARDS_CONTENDER_THRESHOLD,
            "oscar_win":        awards_eligible and critical_score >= AWARDS_WIN_THRESHOLD,
            "production_trouble": trouble_reason,
            "ancillary_surprise": ancillary_reason,
            "ai_tooling_setback": ai_setback_reason,
            "ewom_piracy_swing": ewom_reason,
            "ewom_mult":         ewom_mult,
            "pvod_mult":         pvod_mult,
            "theme_park_mult":   theme_park_mult,
            "cut_buzz_awards":   cut_buzz_awards_hits > 0,
            "cut_buzz_sequel":   cut_buzz_sequel,
            "npv":              project.npv(multiplier, critical_score, pvod_mult=pvod_mult, theme_park_mult=theme_park_mult, ewom_mult=ewom_mult),
            "irr":              project.irr(multiplier, critical_score, pvod_mult=pvod_mult, theme_park_mult=theme_park_mult, ewom_mult=ewom_mult),
            "total_revenue":    project.total_revenue(multiplier, critical_score, pvod_mult=pvod_mult, theme_park_mult=theme_park_mult, ewom_mult=ewom_mult),
            "domestic_bo":      project.domestic_box_office(multiplier),
            "theatrical_net":   project.theatrical_studio_net(multiplier),
            "pvod":             project.pvod_revenue(multiplier) * pvod_mult * ewom_mult,
            "sub_value":        (project.pay1_license_fee() + project.pay1_reversion_value(multiplier, ewom_mult)
                                  if project.is_licensing_out()
                                  else project.subscriber_value(multiplier) * ewom_mult),
            "longtail":         project.library_longtail(multiplier, critical_score),
            "awards_bump":      project.awards_season_bump(multiplier, critical_score),
            "theme_park":       project.theme_park_value(multiplier, critical_score) * theme_park_mult,
            "capital_at_risk":  project.capital_at_risk(),
            "talent_take":      waterfall["talent_take"],
            "producer_take":    waterfall["producer_take"],
            "studio_residual":  waterfall["residual"],
            "talent_partner_bonus": talent_bonus.get("partner_name"),
        }
        ss.movie_log = [r for r in ss.movie_log if r["cycle"] != ss.movie_cycle] + [outcome]
        # Share the film and how it did on the class Pitch Board (2026-10-01).
        # Re-simulating the same cycle replaces its post.
        from utils.game_state import post_pitch
        post_pitch(ss.get("team_name", ""), ss.get("school", ""), ss.get("class_section", ""), "movies",
                   key=f"cycle-{ss.movie_cycle}", title=project.title, genre=project.genre,
                   pitch=ss.movie_draft.get("logline", ""),
                   details={"cycle_label": f"Film {ss.movie_cycle}", "concept_type": project.concept_type,
                            "budget_m": project.budget_m, "pa_spend_m": project.pa_spend_m,
                            "release_label": RELEASE_LABELS.get(project.release_strategy, project.release_strategy),
                            "npv": outcome["npv"], "critical_score": outcome["critical_score"]})
        ss.movie_phase = "results"
        st.rerun()


# ── Phase 2: Results ──────────────────────────────────────────────────────────
def _decision_result_card(result: dict):
    """What you decided → what happened → why, side by side (2026-10-05,
    per explicit user request for "clear decisions with clear results").
    Every 'why' line is computed from the same engine the result came from,
    and every random event that moved the number is named."""
    kw = result["project_kwargs"]
    p = MovieProject(**kw)
    opening = p.opening_weekend()
    domestic = p.domestic_box_office(result["multiplier"])
    worldwide = domestic + p.international_box_office(domestic)
    lead = kw.get("lead_actor")
    ip = kw.get("library_ip")
    source = (UNIVERSAL_LIBRARY_IP[ip]["name"] + " (revived)") if ip in UNIVERSAL_LIBRARY_IP \
        else kw.get("source_material", "Original Screenplay")
    lead_txt = (f"{TALENT_PARTNERS[lead]['name']} (Star Power {kw['star_power']})" if lead in TALENT_PARTNERS
                else f"Unnamed cast (Star Power {kw['star_power']})")
    decisions = [
        ("Concept", f"{kw['genre']} · {kw.get('concept_type', 'New IP')} · {source}"),
        ("Lead", lead_txt),
        ("Money", f"${kw['budget_m']:.0f}M budget + ${kw['pa_spend_m']:.0f}M P&A "
                  f"→ ${result['capital_at_risk']:.0f}M at risk"),
        ("Release", f"{RELEASE_LABELS.get(kw['release_strategy'], kw['release_strategy'])}, "
                    f"{kw.get('debut_season', 'Off-Peak')}, {kw['screens']:,} screens"),
    ]
    cs = result["critical_score"]
    outcomes = [
        ("Opening weekend", f"${opening:,.0f}M"),
        ("Worldwide box office", f"${worldwide:,.0f}M"),
        ("Critics", f"{cs:.0f}/100"),
        ("Total revenue", f"${result['total_revenue']:,.0f}M"),
        ("NPV", _fmt_money(result["npv"])),
    ]

    why = []
    star_boost = 1 + (kw["star_power"] / 100) * STAR_POWER_BOOST_MAX
    why.append(f"⭐ Star Power {kw['star_power']} added about ${opening - opening / star_boost:,.1f}M "
               f"to the opening weekend.")
    src_boost = (library_ip_opening_boost(ip, kw["genre"]) if ip in UNIVERSAL_LIBRARY_IP
                 else SOURCE_OPENING_BOOST.get(kw.get("source_material"), 1.0))
    if src_boost > 1:
        why.append(f"📚 {source}'s built-in audience added about ${opening - opening / src_boost:,.1f}M "
                   f"to the opening.")
    label = result.get("scenario_label", "base")
    why.append({"bear": "📉 Audience demand came in weak (Bear): the film had short legs after opening.",
                "base": "📊 Audience demand came in as expected (Base).",
                "bull": "📈 Audience demand broke out (Bull): strong legs well past opening."}
               .get(label, f"Audience demand landed near {label}."))
    if result.get("talent_partner_bonus"):
        why.append(f"🤝 {result['talent_partner_bonus']} relationship bonus applied.")
    if result.get("theme_park", 0) > 0:
        park = f"🎢 earned ${result['theme_park']:.1f}M in theme-park/merch"
    elif kw["genre"] not in THEME_PARK_ELIGIBLE_GENRES and kw.get("concept_type") != "Family/Kids":
        park = "no theme-park/merch (not a park genre)"
    elif cs < THEME_PARK_CRITICAL_GATE:
        park = f"no theme-park/merch (critics under {THEME_PARK_CRITICAL_GATE})"
    else:
        park = "no theme-park/merch (box office below the expected run)"
    why.append(f"🎭 Critics at {cs:.0f}: catalog value {0.7 + cs / 100 * 1.1:.1f}x; {park}"
               + ("; 🏆 awards bump" if result.get("awards_contender") else "") + ".")
    for key, icon in (("production_trouble", "⚠"), ("ai_tooling_setback", "🤖"),
                      ("ancillary_surprise", "🎢"), ("ewom_piracy_swing", "📱")):
        if result.get(key):
            why.append(f"{icon} Random event: {result[key]}.")

    def _rows(items):
        return "".join(f'<div style="display:flex;justify-content:space-between;gap:10px;padding:2px 0;">'
                       f'<span>{k}</span><b style="text-align:right;">{escape(str(v))}</b></div>'
                       for k, v in items)
    st.markdown(f"""
    <div class="rounded-lg border border-line bg-surface2 p-4 mb-4" style="color:#ffffff;font-size:13px;">
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;">
        <div><div class="font-mono text-[11px] mb-1">WHAT YOU DECIDED</div>{_rows(decisions)}</div>
        <div><div class="font-mono text-[11px] mb-1">WHAT HAPPENED</div>{_rows(outcomes)}</div>
      </div>
      <div class="font-mono text-[11px] mt-3 mb-1">WHY</div>
      <div style="line-height:1.6;">{'<br>'.join(why)}</div>
    </div>
    """, unsafe_allow_html=True)


def _results(ss):
    result = next((r for r in ss.movie_log if r["cycle"] == ss.movie_cycle), None)
    if not result:
        ss.movie_phase = "decisions"
        st.rerun()
        return

    npv_ok = result["npv"] >= 0
    npv_c = SUCCESS if npv_ok else DANGER
    title = result["project_kwargs"]["title"]
    strat = result["project_kwargs"]["release_strategy"]
    concept_type = result["project_kwargs"].get("concept_type", "New IP")
    trouble_reason    = result.get("production_trouble")
    ancillary_reason  = result.get("ancillary_surprise")
    ai_setback_reason = result.get("ai_tooling_setback")
    ewom_reason       = result.get("ewom_piracy_swing")
    ewom_up           = (result.get("ewom_mult") or 1.0) >= 1.0
    scenario_framing = (
        "landed below plan — Production Trouble hit" if trouble_reason
        else f"landed near your {result['scenario_label'].title()} Case"
    )

    st.markdown(f"""
    <div class="rounded-lg p-5 mb-4" style="background:rgba({'102,187,106' if npv_ok else '239,83,80'},.07);
         border:1px solid rgba({'102,187,106' if npv_ok else '239,83,80'},.3);">
      <div class="font-mono text-[10px] text-muted uppercase tracking-widest mb-3">
        "{title}" ({concept_type}) — {RELEASE_LABELS[strat]} — Actual Results ({scenario_framing})
      </div>
      <div class="flex gap-8 flex-wrap">
        <div><div class="text-[9px] text-muted font-mono">TOTAL REVENUE</div>
          <div class="text-2xl font-serif text-ink">${result['total_revenue']:.1f}M</div>
          <div class="text-[10px] text-muted mt-1" style="max-width:140px;">Every window summed — theatrical through library longtail.</div></div>
        <div><div class="text-[9px] text-muted font-mono">CAPITAL AT RISK</div>
          <div class="text-2xl font-serif" style="color:{WARN};">${result['capital_at_risk']:.1f}M</div>
          <div class="text-[10px] text-muted mt-1" style="max-width:140px;">What you committed before revenue arrived — the number NPV is measured against.</div></div>
        <div><div class="text-[9px] text-muted font-mono">NPV</div>
          <div class="text-2xl font-serif" style="color:{npv_c};">{_fmt_money(result['npv'])}</div>
          <div class="text-[10px] text-muted mt-1" style="max-width:140px;">Total Revenue's present value minus Capital at Risk — positive means real value created.</div></div>
        <div><div class="text-[9px] text-muted font-mono">IRR</div>
          <div class="text-2xl font-serif text-ink">{_irr_label(result['irr'])}</div>
          <div class="text-[10px] text-muted mt-1" style="max-width:140px;">Annualized rate of return — &gt;500% means capital came back too fast for the rate to be meaningful.</div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    _decision_result_card(result)

    # ── Bear/Base/Bull range with the real outcome marked on it ───────────────
    # 2026-08-24, per a QA-pass finding: previously this was narrated in
    # text only ("landed near your Bull Case"), with no visual showing
    # WHERE on the range it actually landed. Reuses _bear_base_bull_chart
    # from Greenlight -- same range this project was originally drawn
    # against, reconstructed from the frozen project_kwargs.
    _outcome_project = MovieProject(**result["project_kwargs"])
    _bear_npv, _base_npv, _bull_npv = (_outcome_project.npv(sc) for sc in ("bear", "base", "bull"))
    st.plotly_chart(
        _bear_base_bull_chart(_bear_npv, _base_npv, _bull_npv, actual_npv=result["npv"],
                               title="Where This Landed: Bear → Base → Bull, Actual NPV Marked"),
        use_container_width=True, config={"displayModeBar": False},
    )

    # ── Production Trouble — a real, involuntary setback, not a choice ────────
    if trouble_reason:
        st.markdown(f"""
        <div class="rounded-lg p-4 mb-3" style="background:rgba(239,83,80,.08);border:1px solid rgba(239,83,80,.3);">
          <div class="text-sm" style="color:{DANGER};font-weight:600;">🎬 Production Trouble</div>
          <div class="text-xs text-ink2 mt-1">{trouble_reason} — this dragged down the resolved
          box-office outcome before you ever saw a number.</div>
        </div>
        """, unsafe_allow_html=True)

    # ── AI Tooling Setback — a real edge of the AI Production Tools tradeoff ──
    if ai_setback_reason:
        st.markdown(f"""
        <div class="rounded-lg p-4 mb-3" style="background:rgba(255,167,38,.08);border:1px solid rgba(255,167,38,.3);">
          <div class="text-sm" style="color:{WARN};font-weight:600;">🤖 AI Tooling Setback</div>
          <div class="text-xs text-ink2 mt-1">{ai_setback_reason} — the cost/timeline savings from AI
          Production Tools aren't a free efficiency win.</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Ancillary Markets Surprise — PVOD rentals / theme park / merchandise ──
    if ancillary_reason:
        surprise_c = ACCENT2
        st.markdown(f"""
        <div class="rounded-lg p-4 mb-3" style="background:rgba(26,107,181,.08);border:1px solid rgba(26,107,181,.3);">
          <div class="text-sm" style="color:{surprise_c};font-weight:600;">🎢 Ancillary Markets Surprise</div>
          <div class="text-xs text-ink2 mt-1">{ancillary_reason} — this moved PVOD rental and
          theme-park/merchandise revenue independently of box office and reviews.</div>
        </div>
        """, unsafe_allow_html=True)

    # ── eWOM & Piracy — a separate, more-common digital-revenue swing ────────
    if ewom_reason:
        ewom_c = SUCCESS if ewom_up else DANGER
        st.markdown(f"""
        <div class="rounded-lg p-4 mb-3" style="background:rgba({'102,187,106' if ewom_up else '239,83,80'},.08);
             border:1px solid rgba({'102,187,106' if ewom_up else '239,83,80'},.3);">
          <div class="text-sm" style="color:{ewom_c};font-weight:600;">📱 eWOM &amp; Piracy</div>
          <div class="text-xs text-ink2 mt-1">{ewom_reason} — this moved PVOD and Peacock subscriber value
          together, independently of box office, reviews, and Ancillary Markets.</div>
        </div>
        """, unsafe_allow_html=True)

    # ── PVOD Cut-Response Buzz — a real upside from choosing to cut price ─────
    if result.get("cut_buzz_awards") or result.get("cut_buzz_sequel"):
        buzz_bits = []
        if result.get("cut_buzz_awards"):
            buzz_bits.append("a critical-reception boost")
        if result.get("cut_buzz_sequel"):
            buzz_bits.append("a Sequel Potential spark")
        st.markdown(f"""
        <div class="rounded-lg p-4 mb-3" style="background:rgba(102,187,106,.08);border:1px solid rgba(102,187,106,.3);">
          <div class="text-sm" style="color:{SUCCESS};font-weight:600;">📣 Price-Cut Buzz</div>
          <div class="text-xs text-ink2 mt-1">Cutting your PVOD price reached a wider audience — the
          real, randomized payoff landed: {' and '.join(buzz_bits)}.</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Critical reception — a genuinely separate outcome from box office ──────
    cs = result["critical_score"]
    cs_tier = "Widely Acclaimed" if cs >= 75 else ("Well Reviewed" if cs >= 55 else
              ("Mixed" if cs >= 35 else "Panned"))
    cs_c = SUCCESS if cs >= 55 else (WARN if cs >= 35 else DANGER)
    genre = result["project_kwargs"]["genre"]
    st.markdown('<div class="section-title">Critical Reception</div>', unsafe_allow_html=True)
    awards_note = ""
    if genre in AWARDS_ELIGIBLE_GENRES:
        if result.get("oscar_win"):
            awards_note = (f'<div class="text-xs mt-2" style="color:{ACCENT};">'
                            f'🏆 Oscar Win — cleared the {AWARDS_WIN_THRESHOLD:.0f} threshold, on top of '
                            f'the nomination-level rerelease bump: +${result["awards_bump"]:.2f}M.</div>')
        elif result["awards_contender"]:
            awards_note = (f'<div class="text-xs mt-2" style="color:{SUCCESS};">'
                            f'🎬 Oscar Nomination — cleared the {AWARDS_CONTENDER_THRESHOLD:.0f} threshold '
                            f'(win needs {AWARDS_WIN_THRESHOLD:.0f}+), triggering a For-Your-Consideration '
                            f'rerelease bump: +${result["awards_bump"]:.2f}M.</div>')
        else:
            awards_note = (f'<div class="text-xs text-muted mt-2">Didn\'t clear the '
                            f'{AWARDS_CONTENDER_THRESHOLD:.0f} awards-contender threshold — no rerelease bump.</div>')
    else:
        awards_note = '<div class="text-xs text-muted mt-2">Not an awards-eligible genre — reception still affects library/EST value, but no rerelease window.</div>'
    st.markdown(f"""
    <div class="rounded-lg border border-line bg-surface2 p-4">
      <div class="flex items-center gap-4">
        <div class="text-3xl font-serif" style="color:{cs_c};">{cs:.0f}</div>
        <div>
          <div class="text-sm font-semibold" style="color:{cs_c};">{cs_tier}</div>
          <div class="text-[10px] text-muted font-mono">Critical Reception Score / 100 — independent of box office</div>
        </div>
      </div>
      {awards_note}
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title mt-4">Revenue Waterfall</div>', unsafe_allow_html=True)
    labels = ["Theatrical Net", "PVOD", "Peacock Sub Value", "Library/EST"]
    vals = [result["theatrical_net"], result["pvod"], result["sub_value"], result["longtail"]]
    if result["awards_bump"] > 0:
        labels.append("Awards Rerelease")
        vals.append(result["awards_bump"])
    if result.get("theme_park", 0) > 0:
        labels.append("Theme Park/Merch")
        vals.append(result["theme_park"])
    labels.append("Total Revenue")
    vals.append(result["total_revenue"])
    fig = waterfall_chart(labels, vals, title="Revenue by Window ($M)", height=300)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Deal Waterfall — where revenue goes, not where it comes from ─────────
    # 2026-08-04: the chart above answers "where did the money come from";
    # this answers "who gets paid, and in what order" -- see
    # utils/movie_models.py::participation_waterfall. `.get()`-guarded since
    # movie_log entries recorded before this feature existed won't carry
    # these keys.
    if all(k in result for k in ("talent_take", "producer_take", "studio_residual")):
        st.markdown('<div class="section-title mt-4">Deal Waterfall — Who Gets Paid</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="text-xs text-ink2 mb-2">Revenue doesn\'t all stay with the studio. Talent gross '
            'participation is paid off top-line revenue regardless of profitability, before capital is '
            'even recouped; the producer\'s net participation only comes out of whatever\'s left after '
            'that. Studio Residual can go negative even on a nominal box-office win.</p>',
            unsafe_allow_html=True)
        wf_labels = ["Total Revenue", "Talent Gross Participation", "Capital Recoupment",
                     "Producer Net Participation", "Studio Residual"]
        wf_vals = [result["total_revenue"], -result["talent_take"], -result["capital_at_risk"],
                   -result["producer_take"], result["studio_residual"]]
        fig_wf = waterfall_chart(wf_labels, wf_vals, title="Distribution & Participation ($M)", height=300)
        st.plotly_chart(fig_wf, use_container_width=True, config={"displayModeBar": False})

    # Chart cut 2026-08-24 (found in a QA pass): this NPV-by-cycle bar chart
    # was a near-exact duplicate of _progress_chart (shown in Decisions,
    # right before this cycle) and 'Slate — NPV by Cycle' (shown at the
    # Final Slate screen) -- same chart, same data, shown 2-3 times across
    # one cycle's play-through. Kept a one-line text recap in its place.
    # The one-line recap became the full Your Slate table (2026-10-05).
    _section_your_slate(ss, title="🎬 Your Slate So Far")

    st.divider()
    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button(f"← Redo {_cycle_years_label(ss.movie_cycle)}", use_container_width=True):
            ss.movie_log = [r for r in ss.movie_log if r["cycle"] != ss.movie_cycle]
            ss.movie_theatrical_resolved.pop(ss.movie_cycle, None)   # redo re-opens the theatrical mini-run too
            ss.movie_pvod_checkpoints.pop(ss.movie_cycle, None)
            ss.movie_pvod_pending_rejection.pop(ss.movie_cycle, None)
            ss.movie_licensing_auction.pop(ss.movie_cycle, None)
            ss.movie_phase = "decisions"
            st.rerun()
    with nav2:
        if ss.movie_cycle < CYCLES_TOTAL:
            if st.button(f"→ Start {_cycle_years_label(ss.movie_cycle + 1)}", type="primary", use_container_width=True):
                # Studio Annual Budget (2026-08-18): a performance-linked
                # pool, adjusted once per real cycle transition off this
                # just-completed cycle's own resolved NPV -- "year to year
                # performance should also explain budget slate," per
                # explicit user request.
                if ss.movie_studio_budget_updated_through < ss.movie_cycle:
                    just_completed = next((r for r in ss.movie_log if r["cycle"] == ss.movie_cycle), None)
                    ss.movie_studio_budget_m = next_studio_budget(
                        ss.movie_studio_budget_m, just_completed["npv"] if just_completed else None
                    )
                    ss.movie_studio_budget_updated_through = ss.movie_cycle
                ss.movie_cycle += 1
                ss.movie_draft = {}
                ss.movie_phase = "decisions"
                st.rerun()
        else:
            if st.button("→ View Final Slate & Submit Score", type="primary", use_container_width=True):
                ss.movie_phase = "complete"
                st.rerun()


# ── Phase 3: Complete ──────────────────────────────────────────────────────────
def _complete(ss):
    if not ss.movie_log:
        ss.movie_phase = "decisions"
        ss.movie_cycle = 1
        st.rerun()
        return

    sorted_log = sorted(ss.movie_log, key=lambda r: r["cycle"])
    projects = [MovieProject(**r["project_kwargs"]) for r in sorted_log]
    critical_scores = [r["critical_score"] for r in sorted_log]
    # 25% of each film's graded NPV is what it actually earned (MOVIE_LUCK_WEIGHT).
    actual_npvs = [r.get("npv") for r in sorted_log]
    score = compute_movie_score(projects, critical_scores,
                                actual_npvs=actual_npvs if all(v is not None for v in actual_npvs) else None)

    total_c = SUCCESS if score["total"] >= 70 else (WARN if score["total"] >= 50 else DANGER)
    npv_c = SUCCESS if score["avg_ra_npv_m"] >= 0 else DANGER
    dec_npv = score.get("avg_decision_npv_m", score["avg_ra_npv_m"])
    pass_c = SUCCESS if score["passed"] else DANGER

    st.markdown(f"""
    <div class="rounded-lg bg-surface2 p-5 mb-5" style="border-left:4px solid #1a6bb5;">
      <div class="font-mono text-[10px] text-muted uppercase tracking-widest mb-3">
        Full Slate Results — Universal Pictures · {CYCLES_TOTAL * YEARS_PER_CYCLE} Years
      </div>
      <div class="flex gap-8 flex-wrap">
        <div><div class="text-[9px] text-muted font-mono">PASS / FAIL (DECISIONS ONLY)</div>
          <div class="text-3xl font-serif" style="color:{pass_c};">{'PASS' if score['passed'] else 'FAIL'}</div>
          <div class="text-[9px] text-muted font-mono">decisions avg {_fmt_money(dec_npv)} — must be above $0</div></div>
        <div><div class="text-[9px] text-muted font-mono">AVG GRADED NPV (75% DECISIONS + 25% LUCK)</div>
          <div class="text-3xl font-serif" style="color:{npv_c};">{_fmt_money(score['avg_ra_npv_m'])}</div></div>
        <div><div class="text-[9px] text-muted font-mono">SCORE</div>
          <div class="text-3xl font-serif" style="color:{total_c};">{score['total']:.0f}</div>
          <div class="text-[9px] text-muted font-mono">/ 100 pts</div></div>
        <div><div class="text-[9px] text-muted font-mono">TALENT DEAL SPEND</div>
          <div class="text-3xl font-serif" style="color:{WARN};">${ss.get('movie_talent_total_spend', 0.0):.1f}M</div>
          <div class="text-[9px] text-muted font-mono">tracked separately, not folded into Score above</div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    _section_your_slate(ss, title="🎬 Your Final Slate")

    chart_col, score_col = st.columns([3, 2])
    with chart_col:
        st.markdown('<div class="section-title">Slate — NPV by Cycle</div>', unsafe_allow_html=True)
        rows = sorted(ss.movie_log, key=lambda r: r["cycle"])
        cyc_labels = [f"C{r['cycle']}: {r['project_kwargs']['title'][:18]}" for r in rows]
        npvs = [r["npv"] for r in rows]
        fig = go.Figure(go.Bar(x=cyc_labels, y=npvs, marker_color=[SUCCESS if v >= 0 else DANGER for v in npvs]))
        fig.add_hline(y=0, line_dash="dash", line_color=WARN, opacity=0.4)
        fig.update_layout(**base_layout("NPV per Cycle ($M)", height=280))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Genre/Concept-Type mix (2026-08-24 add, found in a QA pass) --
        # Portfolio Diversification is a real, 15%-weighted score component
        # right below (see score_col) but had zero visualization anywhere
        # -- same capital-at-risk weighting portfolio_diversification_score
        # itself uses, so this is literally what that score is graded on.
        genre_capital, concept_capital = {}, {}
        for r in ss.movie_log:
            k_g = r["project_kwargs"]["genre"]
            k_c = r["project_kwargs"].get("concept_type", "New IP")
            genre_capital[k_g]     = genre_capital.get(k_g, 0.0) + r["capital_at_risk"]
            concept_capital[k_c]   = concept_capital.get(k_c, 0.0) + r["capital_at_risk"]
        dcol1, dcol2 = st.columns(2)
        with dcol1:
            fig_g = donut_chart(list(genre_capital.keys()), [round(v, 1) for v in genre_capital.values()],
                                 "Capital by Genre", height=210)
            st.plotly_chart(fig_g, use_container_width=True, config={"displayModeBar": False})
        with dcol2:
            fig_c = donut_chart(list(concept_capital.keys()), [round(v, 1) for v in concept_capital.values()],
                                 "Capital by Concept Type", height=210)
            st.plotly_chart(fig_c, use_container_width=True, config={"displayModeBar": False})
        st.caption("Both feed Portfolio Diversification below — three Sequels in a row scores low here "
                   "even if each one individually did well.")

    with score_col:
        st.markdown('<div class="section-title">Score Breakdown</div>', unsafe_allow_html=True)
        components = [
            ("Risk-Adj. NPV",           score["risk_adjusted_npv"],       "45%",
             f"{1 - MOVIE_LUCK_WEIGHT:.0%} your decisions, {MOVIE_LUCK_WEIGHT:.0%} luck. The decision part "
             "weights your bear case at 50% rather than the rosy base case, rewarding risk-aware greenlighting. "
             "The luck part is what each film actually earned: a breakout helps, a flop hurts. It's the "
             "movie business."),
            ("Capital Efficiency",      score["capital_efficiency"],      "20%",
             "Total lifetime revenue per P&A dollar spent, averaged across your slate — a real-world "
             "3-6x is healthy; 6x total revenue / P&A scores 100."),
            ("Strategic Fit",           score["strategic_fit"],           "20%",
             "Did your release-strategy choice (wide/platform/day-and-date) actually beat a naive "
             "'always go wide theatrical' default, net of cannibalization?"),
            ("Portfolio Diversification", score["portfolio_diversification"], "15%",
             "How spread your slate is across Genre AND Concept Type, weighted by capital committed — "
             "three Sequels in a row scores low even if each one individually did well."),
        ]
        for label, val, weight, defn in components:
            c = SUCCESS if val >= 70 else (WARN if val >= 40 else DANGER)
            st.markdown(f"""
            <div class="mb-3">
              <div class="flex justify-between text-xs mb-1">
                <span class="text-ink2">{label} <span class="text-muted">({weight})</span></span>
                <span class="font-mono" style="color:{c};">{val:.0f}/100</span></div>
              <div class="h-[5px] rounded bg-line overflow-hidden">
                <div class="h-full rounded" style="width:{val}%;background:{c};"></div></div>
              <div class="text-[10px] text-muted mt-1">{defn}</div>
            </div>
            """, unsafe_allow_html=True)

        passed_badge = (f'<span style="background:{SUCCESS};color:#0b0c10;" class="px-3 py-1 rounded text-xs font-mono">PASSED ✓</span>'
                        if score["passed"] else
                        f'<span style="background:{DANGER};color:#fff;" class="px-3 py-1 rounded text-xs font-mono">NOT PASSED</span>')
        st.markdown(f"""
        <div class="rounded-lg bg-surface2 p-3 text-center mt-2">
          <div class="text-4xl font-serif" style="color:{total_c};">{score['total']:.0f}</div>
          <div class="text-[10px] text-muted font-mono mb-2">/ 100 points</div>
          {passed_badge}
        </div>
        """, unsafe_allow_html=True)

    # ── Slate-level Deal-Participation Waterfall ────────────────────────────
    # 2026-08-24 add, found in a QA pass: the per-cycle version of this
    # waterfall already existed at Results (see _results() above) but
    # disappeared once you moved to the next cycle -- nothing ever
    # aggregated "who got paid" across the whole slate. Same fields, summed
    # across every cycle that carries them (older movie_log entries from
    # before this feature existed won't, same guard the per-cycle version
    # already uses).
    waterfall_entries = [r for r in sorted_log
                          if all(k in r for k in ("talent_take", "producer_take", "studio_residual"))]
    if waterfall_entries:
        st.markdown('<div class="section-title">Slate Deal Waterfall — Who Got Paid, In Total</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="text-xs text-ink2 mb-2">Same per-movie waterfall from Results, summed across your '
            'whole slate. Talent gross participation comes off top-line revenue regardless of '
            'profitability; Studio Residual can be negative even on a slate with real box-office wins.</p>',
            unsafe_allow_html=True)
        total_revenue_all = sum(r["total_revenue"] for r in waterfall_entries)
        talent_take_all   = sum(r["talent_take"] for r in waterfall_entries)
        capital_all       = sum(r["capital_at_risk"] for r in waterfall_entries)
        producer_take_all = sum(r["producer_take"] for r in waterfall_entries)
        residual_all      = sum(r["studio_residual"] for r in waterfall_entries)
        wf_labels = ["Total Revenue", "Talent Gross Participation", "Capital Recoupment",
                     "Producer Net Participation", "Studio Residual"]
        wf_vals = [total_revenue_all, -talent_take_all, -capital_all, -producer_take_all, residual_all]
        fig_slate_wf = waterfall_chart(wf_labels, wf_vals, title="Slate-Wide Distribution & Participation ($M)", height=300)
        st.plotly_chart(fig_slate_wf, use_container_width=True, config={"displayModeBar": False})

    # ── Slate Notables ────────────────────────────────────────────────────────
    # Movies-track equivalent of the TV side's Level Notables, shown to the
    # student regardless of submission -- always reflects the live
    # movie_log, so it stays current through Redo This Cycle.
    notables = compute_movie_notables(sorted_log)
    st.markdown('<div class="section-title">🌟 Your Slate Notables</div>', unsafe_allow_html=True)

    bc = notables["best_cycle"]
    mi = notables["most_improved"]
    cs = notables["consistency_score"]
    gv = notables["genre_variety"]

    bc_val = bc["label"] if bc else "—"
    bc_sub = f"{_fmt_money(bc['npv'])} NPV" if bc else "not enough data"
    mi_c   = SUCCESS if (mi or 0) > 0 else (DANGER if (mi or 0) < 0 else TEXT2)
    mi_val = f"{_fmt_money(mi)}" if mi is not None else "—"
    cs_c     = SUCCESS if (cs or 0) >= 85 else (WARN if (cs or 0) >= 65 else DANGER)
    cs_val   = f"{cs:.0f}/100" if cs is not None else "—"
    cs_label = ("Rock-solid" if cs >= 85 else "Steady" if cs >= 65 else "Volatile") if cs is not None else "not enough data"
    ow = notables.get("oscar_wins") or 0
    on = notables.get("oscar_nominations") or 0
    oscar_val = f"{ow} win{'s' if ow != 1 else ''}" if ow else (f"{on} nom{'s' if on != 1 else ''}" if on else "—")
    oscar_c   = ACCENT if ow else (SUCCESS if on else TEXT2)
    oscar_sub = f"{on} total nomination{'s' if on != 1 else ''}" if ow and on > ow else "across the slate"

    n_cols = st.columns(5)
    cards = [
        ("BEST CYCLE",     bc_val, SUCCESS, bc_sub),
        ("MOST IMPROVED",  mi_val, mi_c,    "NPV, first → last cycle"),
        ("CONSISTENCY",    cs_val, cs_c,    cs_label),
        ("GENRE VARIETY",  str(gv), ACCENT, "distinct genres attempted"),
        ("OSCAR RECOGNITION", oscar_val, oscar_c, oscar_sub),
    ]
    for col, (title, val, color, sub) in zip(n_cols, cards):
        with col:
            st.markdown(f"""
            <div class="rounded-lg bg-surface2 p-3" style="height:100%;">
              <div class="text-[9px] text-muted font-mono mb-1">{title}</div>
              <div class="text-lg font-serif" style="color:{color};">{val}</div>
              <div class="text-xs" style="color:#ffffff;">{sub}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    attempts = get_attempt_count(ss.team_name, MOVIE_NETWORK_KEY, ss.school, ss.class_section)
    prev_official = get_official_score(ss.team_name, MOVIE_NETWORK_KEY, ss.school, ss.class_section)
    already_passed = bool(prev_official and prev_official.get("passed", False))
    can_sub = attempts < MAX_ATTEMPTS and not already_passed

    act_col, restart_col = st.columns([2, 1])
    with act_col:
        if already_passed:
            st.success("✅ Universal Pictures already passed! Check the Leaderboard tab.")
        elif not can_sub:
            st.warning(f"All {MAX_ATTEMPTS} attempts used.")
        else:
            if attempts > 0:
                st.markdown(
                    f'<p class="text-xs text-ink2 mb-2">⚠ Attempt {attempts + 1} of {MAX_ATTEMPTS}. '
                    f'Your <b>first submission</b> is the official score — retries are practice only.</p>',
                    unsafe_allow_html=True)
            st.markdown('<div class="submit-btn">', unsafe_allow_html=True)
            btn_lbl = "🎯 Submit Official Score" if attempts == 0 else f"🔄 Retry  ({score['total']:.0f} pts)"
            if st.button(btn_lbl, use_container_width=True):
                slate_summary = [
                    {"name": r["project_kwargs"]["title"], "genre": r["project_kwargs"]["genre"],
                     "concept_type": r["project_kwargs"].get("concept_type", "New IP"),
                     "release_strategy": RELEASE_LABELS[r["project_kwargs"]["release_strategy"]],
                     "npv": round(r["npv"], 1)}
                    for r in sorted_log
                ]
                entry = record_attempt(
                    team_name=ss.team_name, network=MOVIE_NETWORK_KEY,
                    attempt_num=attempts + 1, score=score["total"], passed=score["passed"], details=score,
                    school=ss.school, class_section=ss.class_section,
                    class_abbrev=ss.get("class_abbrev", ""),
                    slate_summary=slate_summary,
                    notables=compute_movie_notables(sorted_log),
                )
                ss.movie_last_score = entry
                ss.movie_submitted = True
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        if ss.get("movie_submitted") and ss.get("movie_last_score"):
            e = ss.movie_last_score
            ec = SUCCESS if e["passed"] else DANGER
            st.markdown(f"""
            <div class="rounded-lg p-3 mt-3 text-center" style="background:rgba({'102,187,106' if e['passed'] else '239,83,80'},.1);
                 border:1px solid rgba({'102,187,106' if e['passed'] else '239,83,80'},.3);">
              <div class="text-xl font-serif" style="color:{ec};">{'✅ PASSED' if e['passed'] else '❌ DID NOT PASS'}</div>
              <div class="font-mono text-2xl my-1" style="color:{ec};">{e['score']:.0f} pts</div>
            </div>
            """, unsafe_allow_html=True)

    with restart_col:
        if st.button("↺ Restart Slate", use_container_width=True):
            ss.movie_cycle = 1
            ss.movie_phase = "decisions"
            ss.movie_log = []
            ss.movie_draft = {}
            ss.movie_research_paid = {}
            ss.movie_theatrical_resolved = {}
            ss.movie_pvod_checkpoints = {}
            ss.movie_pvod_pending_rejection = {}
            ss.movie_licensing_auction = {}
            ss.movie_submitted = False
            ss.movie_last_score = None
            st.rerun()

    # ── How You Compare ───────────────────────────────────────────────────────
    # 2026-08-24, per user request: show competitors right here at the end
    # of the slate instead of only on the separate Leaderboard tab.
    st.divider()
    render_vs_competitors_board(MOVIE_NETWORK_KEY, ss.team_name, ss.school, ss.class_section)
