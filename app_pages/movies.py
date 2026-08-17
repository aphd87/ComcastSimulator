"""
Day 2 — Movies tab ("Universal Pictures")
Turn engine mirroring pages/simulation.py's Decisions -> Results pattern,
scaled to 3 greenlight-to-release cycles (see DESIGN_NOTES.md "Day 2").
Each cycle: Greenlight (production concept + P&A commit, cash out, no
revenue visibility yet) -> Release Strategy (the linear-vs-SVOD tension
from Day 1's Green Light tab, extended to theatrical/day-and-date/platform)
-> Results (actual outcome resolves against a hidden bull/base/bear draw).
"""
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
    draw_production_trouble, draw_ancillary_surprise,
    FINANCING_STRUCTURES, PRESALE_ADVANCE_PCT, PRESALE_SALES_AGENT_FEE_PCT, TAX_CREDIT_PCT, participation_waterfall,
    TALENT_PARTNERS, STUDIO_PARTNERS, RIVAL_STUDIOS, draw_rival_claim, draw_hold_forfeit, draw_rival_poach,
    ORIGIN_MEDIUM_SOURCE_SYNERGY, TALENT_SOURCE_SYNERGY_MULT,
    EXHIBITOR_POSTURES, PAY1_LICENSING_OPTIONS, PAY1_LICENSE_DISCOUNT,
    AI_TOOLS_BUDGET_SAVINGS_PCT, AI_TOOLS_TIMELINE_SHIFT_MO, AI_TOOLS_CRITICAL_CEILING_MULT,
    draw_ai_tooling_setback, multiplier_to_stars, draw_ewom_piracy_swing,
    DEBUT_SEASONS, SEASON_OPENING_MULT, SEASON_GENRE_SYNERGY, SEASON_AWARDS_RECALL,
)
from utils.game_state import (
    record_attempt, get_attempt_count, get_official_score, MAX_ATTEMPTS,
    compute_movie_notables,
)
from utils.charts import base_layout, waterfall_chart, SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2

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


# ── Small helpers ────────────────────────────────────────────────────────────
def _fmt_money(v: float) -> str:
    return f"${v:+.1f}M" if v < 0 else f"${v:.1f}M"


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


def _current_distribution_window(project: "MovieProject", months_elapsed: float) -> str:
    """Which real distribution window a resolved movie is sitting in RIGHT
    NOW, given how many months have elapsed since its own release -- reuses
    the exact window boundaries MovieProject.windowed_cashflows() already
    computes for that project (window_days()-derived theatrical exclusivity,
    then PVOD, then Pay-1 streaming/library), so this never drifts out of
    sync with the real financial engine. 2026-08-18, per explicit user
    request for a slate-wide scorecard showing where each movie actually is
    in its distribution run."""
    window_mo = project.window_days() / 30.0
    if months_elapsed < 1.5:
        return "🎬 Theatrical (Opening)"
    if months_elapsed < window_mo + 1.0:
        return "🎬 Theatrical"
    if months_elapsed < window_mo + 3.0:
        return "📀 PVOD / Premium Rental"
    if months_elapsed < 24.0:
        return "📡 Licensed Out (Pay-1)" if project.is_licensing_out() else "📡 Pay-1 Streaming (Peacock)"
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

    talent_key = None
    for k, h in ss.get("movie_talent_holds", {}).items():
        if h.get("status") == "succeeded" and h.get("available_cycle") == ss.movie_cycle:
            talent_key = k
            break
    if talent_key:
        talent = TALENT_PARTNERS[talent_key]
        if talent["specialty"] == genre:
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
    per movie greenlit so far this level, showing where it actually sits in
    its distribution run right now (not a hypothetical), whether it earned
    theme-park/merch revenue, and a Sequel Potential signal. 2026-08-18, per
    explicit user request ("is there a scorecard... so we can see where each
    movie is from year to year in the distribution run... is there a way to
    tabulate this?"). Reuses each project's own real windowed_cashflows()
    boundaries (see _current_distribution_window) rather than inventing a
    parallel timeline, so it can never drift out of sync with the actual
    financial engine. Only renders once at least one movie has real results
    -- nothing to tabulate before the first Simulate."""
    if not ss.movie_log:
        return

    st.markdown('<div class="section-title">Distribution Pipeline — Slate Scorecard</div>', unsafe_allow_html=True)
    st.caption("Where every movie you've released so far actually sits in its distribution run right "
               "now, based on real elapsed time since each one's own release — not a hypothetical.")

    rows = []
    seen_genres_with_sequel = {r["project_kwargs"]["genre"] for r in ss.movie_log
                                if r["project_kwargs"]["concept_type"] == "Sequel"}
    for entry in sorted(ss.movie_log, key=lambda r: r["cycle"]):
        project = MovieProject(**entry["project_kwargs"])
        months_elapsed = (ss.movie_cycle - entry["cycle"]) * YEARS_PER_CYCLE * 12.0
        sequel_potential = (
            "🎬 Yes" if (project.concept_type != "Sequel" and entry["npv"] > 0
                         and project.genre not in seen_genres_with_sequel)
            else "—"
        )
        rows.append({
            "Year":              _cycle_years_label(entry["cycle"]),
            "Title":             project.title,
            "Genre / Concept":   f"{project.genre} ({project.concept_type})",
            "Current Window":    _current_distribution_window(project, months_elapsed),
            "NPV":               _fmt_money(entry["npv"]),
            "Theme Park / Merch": f"${entry['theme_park']:.1f}M" if entry.get("theme_park", 0) > 0 else "—",
            "Sequel Potential":  sequel_potential,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                 height=min(300, 40 + 35 * len(rows)))
    st.divider()


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
                '<span class="text-xs text-muted">(optional, Overall/First-Look Deal)</span></div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-2">Sign a standing deal with a production banner for '
        'first-look access to whatever they\'re developing next -- benefits every remaining cycle '
        'whose genre matches their specialty. A banner nobody signs can quietly get poached by a '
        'rival studio.</p>',
        unsafe_allow_html=True)

    for key, rival in newly_poached.items():
        st.markdown(f"""
        <div class="rounded-lg p-3 mb-2" style="background:rgba(255,167,38,.08);border:1px solid rgba(255,167,38,.3);">
          <div class="text-sm font-semibold" style="color:{WARN};">🚨 {rival} signed {STUDIO_PARTNERS[key]['name']} to an exclusive deal</div>
          <div class="text-xs text-ink2 mt-1">No longer available to you for the rest of this level.</div>
        </div>
        """, unsafe_allow_html=True)

    if ss.movie_overall_deal:
        partner = STUDIO_PARTNERS[ss.movie_overall_deal]
        bonus_label = (f"+{partner['star_power_bonus']} Star Power" if "star_power_bonus" in partner
                       else f"+{partner['critical_score_bonus']:.0f} Critical Reception")
        st.markdown(f"""
        <div class="rounded-lg border border-line bg-surface2 p-3 mb-3">
          <div class="text-sm" style="color:{ACCENT};">🤝 Overall Deal active: <b>{partner['name']}</b>
          ({partner['specialty']} specialty) — {bonus_label} on {partner['specialty']} projects for the
          rest of your slate.</div>
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
                    ss.movie_talent_total_spend += partner["deal_cost_m"]
                    st.rerun()

    if ss.movie_talent_total_spend > 0:
        st.caption(f"💸 Total spent on talent/studio relationships so far: ${ss.movie_talent_total_spend:.1f}M "
                   f"(a real cash cost, tracked separately from any single project's NPV — see the "
                   f"Slate Complete summary).")

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
    st.markdown('<div class="section-title">Holding Deals '
                '<span class="text-xs text-muted">(optional, individual talent)</span></div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-2">Now that this cycle\'s concept is set, consider locking a '
        'specific actor\'s window for <b>next</b> cycle\'s production -- a cheaper, one-off booking '
        'versus a standing Studio Partnership. A rival studio may have already locked the same window '
        '(resolved instantly), and even a successful hold can still fall through by the time it '
        'converts.</p>', unsafe_allow_html=True)

    if resolved_hold_key:
        h = ss.movie_talent_holds[resolved_hold_key]
        ok = h["status"] == "succeeded"
        st.markdown(f"""
        <div class="rounded-lg p-3 mb-2" style="background:rgba({'102,187,106' if ok else '239,83,80'},.08);
             border:1px solid rgba({'102,187,106' if ok else '239,83,80'},.3);">
          <div class="text-sm font-semibold" style="color:{SUCCESS if ok else DANGER};">
            {'✅' if ok else '❌'} Holding Deal Update — {TALENT_PARTNERS[resolved_hold_key]['name']}</div>
          <div class="text-xs text-ink2 mt-1">{'The window held together — available this cycle if it fits your genre.' if ok else h['forfeit_reason']}</div>
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

    holdable = [k for k in TALENT_PARTNERS
                if ss.movie_talent_holds.get(k, {}).get("status") != "pending"]
    if holdable:
        hcols = st.columns(len(holdable))
        for col, key in zip(hcols, holdable):
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
                    ({partner.get('gender', '')}, {partner.get('age', '?')})</span></div>
                  <div class="text-[10px] text-muted font-mono mb-1">Best genres: {', '.join(partner.get('best_genres', [partner['specialty']]))}</div>
                  <div class="text-[10px] text-muted font-mono mb-2">From: {partner.get('origin_medium', '—')}</div>
                  <div class="text-[10px] text-ink2 mb-2" style="line-height:1.4;">{partner.get('bio', '')}</div>
                  <div class="text-[10px] text-muted font-mono">Lifetime B.O.: ${partner.get('lifetime_box_office_m', 0):,.0f}M</div>
                  <div class="text-[10px] text-muted font-mono mb-2">Social: {partner.get('social_followers_m', 0):.1f}M followers</div>
                  <div class="text-xs text-ink2">{bonus_label}</div>
                  <div class="text-[10px] text-muted font-mono">${partner['hold_cost_m']:.1f}M hold fee</div>
                  {synergy_note}
                </div>
                """, unsafe_allow_html=True)
                if st.button("Place Hold", key=f"hold_{key}", use_container_width=True):
                    ss.movie_talent_total_spend += partner["hold_cost_m"]
                    rival = draw_rival_claim(ss.team_name, ss.movie_cycle, key)
                    if rival:
                        ss.movie_talent_holds[key] = {"status": "rival_claimed",
                                                       "cycle_placed": ss.movie_cycle, "rival": rival}
                    else:
                        ss.movie_talent_holds[key] = {"status": "pending", "cycle_placed": ss.movie_cycle}
                    st.rerun()

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
                       ("#252836", str(i + 1), "#b0b5c4")
        dot_items.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">'
            f'<div style="width:32px;height:32px;border-radius:50%;background:{bg};'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-family:DM Mono,monospace;font-size:15px;font-weight:700;color:{clr};">{txt}</div>'
            f'<div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">{label}</div></div>'
        )
    connector = '<div style="width:40px;height:2px;background:#252836;margin-bottom:16px;"></div>'
    cycle_label = (f"{_cycle_years_label(ss.movie_cycle)} of {CYCLES_TOTAL * YEARS_PER_CYCLE}"
                   if ss.movie_phase != "complete" else "Slate Complete")
    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;padding:14px 20px;margin-bottom:18px;">
      <div style="font-family:DM Mono,monospace;font-size:14px;color:#e0e2ea;margin-bottom:10px;">{cycle_label}</div>
      <div style="display:flex;align-items:center;justify-content:center;">{connector.join(dot_items)}</div>
    </div>
    """, unsafe_allow_html=True)


# ── Main render ────────────────────────────────────────────────────────────────
def render():
    ss = st.session_state
    _init(ss)

    st.markdown("""
    <div class="rounded-lg border border-line bg-surface2 px-4 py-3 mb-4 text-sm text-ink2" style="border-left:3px solid #1a6bb5;">
    💡 <b class="text-ink">Day 2 — Universal Pictures.</b> A movie isn't a portfolio of amortized shows — it's
    one concentrated bet. Cost is paid entirely upfront; revenue arrives as a windowed waterfall
    (theatrical → PVOD → Peacock → library) that you can't fully see coming. You're graded on
    <b class="text-ink">risk-adjusted NPV</b>, not a margin percentage.
    </div>
    """, unsafe_allow_html=True)

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

    if len(ss.movie_log) >= 2:
        _progress_chart(ss)

    st.markdown(
        '<div style="font-size:14px;color:#8a8f9e;margin-bottom:10px;">'
        '<a href="#talent" style="color:#1a6bb5;">Studio Partnerships</a> · '
        '<a href="#greenlight" style="color:#1a6bb5;">Greenlight</a> · '
        '<a href="#holding" style="color:#1a6bb5;">Holding Deals</a> · '
        '<a href="#release" style="color:#1a6bb5;">Release Strategy</a> · '
        '<a href="#simulate" style="color:#1a6bb5;">Simulate</a>'
        '</div>', unsafe_allow_html=True)

    _section_distribution_pipeline(ss)

    # A standing Studio Partnership should shape what gets greenlit, not the
    # other way around -- rendered before Greenlight, same placement
    # rationale as TV/Streaming's Sports Rights section. Holding Deals
    # (individual actors) render AFTER Greenlight instead -- see
    # _section_holding_deals's docstring for why.
    resolved_hold_key, newly_poached = _resolve_talent_cycle_transitions(ss)
    _section_studio_partnerships(ss, newly_poached)

    st.markdown('<a id="greenlight"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">2 · Greenlight the Concept</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-2">Both budget and P&A spend are cash out today, before any '
        'revenue visibility — unlike Day 1\'s amortized TV cost.</p>', unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    d = ss.movie_draft

    with left:
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

        gc3, _ = st.columns(2)
        source_material = gc3.selectbox(
            "Source Material", SOURCE_MATERIALS,
            index=SOURCE_MATERIALS.index(d.get("source_material", SOURCE_MATERIALS[0]))
                  if d.get("source_material") in SOURCE_MATERIALS else 0,
            help="Where the underlying story comes from — separate from Concept Type (a Sequel "
                 "can itself be an original-screenplay franchise OR a book-adaptation sequel).",
        )
        acq_cost = SOURCE_ACQUISITION_COST_M.get(source_material, 0.0)
        boost = SOURCE_OPENING_BOOST.get(source_material, 1.0)
        if acq_cost > 0:
            st.caption(f"📚 Rights acquisition: +${acq_cost:.0f}M added to Capital at Risk — but a "
                       f"built-in fan base lifts your opening weekend by {(boost - 1) * 100:.0f}% "
                       f"before you spend a dollar of P&A. Real-world example: game/book/show "
                       f"publishers command real premiums for adaptation rights precisely because "
                       f"that audience already exists.")
        else:
            st.caption("An original screenplay has no rights to acquire, but also no built-in "
                       "audience — every dollar of awareness has to be earned through P&A and Star Power.")

        # ── AI Pitch Feedback (optional, BYOK — see README.md) ─────────────────
        # 2026-08-17: Movies-side parallel to app_pages/greenlight.py's AI
        # Pitch Feedback panel -- TV had this fully built and Movies never
        # got the equivalent, even though the same BYOK infrastructure
        # (utils/ai_grading.py) already existed. Uses grade_movie_concept, a
        # genuinely separate model/prompt from TV's grade_show_concept (see
        # MovieConceptGrade's docstring) -- theatrical feasibility/market-fit
        # criteria don't map onto a TV budget/network framing.
        from utils.ai_grading import api_key_configured, grade_movie_concept

        st.markdown(
            '<div class="section-title mt-3">AI Pitch Feedback '
            '<span style="font-size:14px;color:#8a8f9e;">(optional)</span></div>',
            unsafe_allow_html=True,
        )
        if not api_key_configured():
            st.caption("Ask your instructor to enable AI feedback for this class.")
        else:
            pitch = st.text_area(
                "Describe your movie concept in your own words (2-4 sentences)",
                placeholder="e.g. A stranded astronaut has to out-think a planet that's actively "
                            "trying to kill her, using only what she can scavenge...",
                key="movie_pitch_text",
            )
            if st.button("🤖 Get AI Feedback", key="movie_grade_button"):
                if not pitch.strip():
                    st.warning("Write a short pitch first.")
                else:
                    with st.spinner("Grading your pitch..."):
                        grade = grade_movie_concept(title, genre, concept_type, source_material, pitch)
                    if grade is None:
                        st.error("AI feedback is temporarily unavailable. Try again later.")
                    else:
                        total = (grade.originality_score + grade.market_fit_score
                                  + grade.feasibility_score + grade.presentation_score)
                        st.markdown(f"**Score: {total}/100**")
                        st.write(grade.feedback)
                        pgc1, pgc2 = st.columns(2)
                        with pgc1:
                            st.markdown("**Strengths**")
                            for s in grade.strengths:
                                st.markdown(f"- {s}")
                        with pgc2:
                            st.markdown("**Risks**")
                            for r in grade.risks:
                                st.markdown(f"- {r}")
                        if grade.research_recommended:
                            st.info(f"🔬 **Worth paying for Research on this one** before you "
                                    f"commit budget — {grade.research_rationale}")
                        else:
                            st.caption(f"🔬 Probably not worth paying for Research on this one — "
                                       f"{grade.research_rationale}")

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
            "for this Sequel — how much of the franchise's built-in awareness is actually "
            "carrying through this cycle, not just this one entry's fresh reception"
            if concept_type == "Sequel" else "for this New IP concept — you have no franchise "
            "track record to lean on, so this is your only signal before you commit"
        )
        st.markdown('<div class="section-title mt-3">🔎 Research '
                    '<span class="text-xs text-muted">(optional, distinct from AI Pitch Feedback above — '
                    'this previews real seeded outcome signals, not qualitative advice)</span></div>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<p class="text-xs text-ink2 mt-1 mb-1">Pay ${RESEARCH_FEE_M:.0f}M (added to P&A spend) to '
            f'preview the actual box-office and critical-reception signals {research_ip_note}, before '
            f'committing your budget. Works the same way whether the concept is brand-new or an '
            f'established franchise entry.</p>',
            unsafe_allow_html=True)
        if ss.movie_research_paid.get(ss.movie_cycle):
            preview_mult = draw_actual_multiplier(ss.team_name, ss.movie_cycle, genre, concept_type)
            preview_cs = draw_critical_reception(ss.team_name, ss.movie_cycle, genre,
                                                  ai_production_tools=bool(d.get("ai_production_tools", False)))
            stars = multiplier_to_stars(preview_mult, genre, concept_type)
            star_str = "⭐" * stars + "☆" * (5 - stars)
            bo_c = SUCCESS if stars >= 4 else (WARN if stars == 3 else DANGER)
            cs_c = SUCCESS if preview_cs >= 55 else (WARN if preview_cs >= 35 else DANGER)
            st.markdown(f"""
            <div class="rounded-lg border border-line bg-surface2 p-3 mb-2">
              <div class="flex gap-6 flex-wrap">
                <div><div class="text-[9px] text-muted font-mono">BOX-OFFICE SIGNAL</div>
                  <div class="text-sm" style="color:{bo_c};">{star_str}</div></div>
                <div><div class="text-[9px] text-muted font-mono">SOCIAL / CRITICAL BUZZ</div>
                  <div class="text-sm" style="color:{cs_c};">{preview_cs:.0f}/100</div></div>
              </div>
              <div class="text-[10px] text-muted mt-1">Live for the currently selected Genre/Concept Type —
              updates if you change either. Production Trouble, the AI Tooling Setback, Ancillary Markets
              Surprise, and eWOM &amp; Piracy still apply on top of this at Simulate.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            if st.button(f"🔎 Pay for Research (${RESEARCH_FEE_M:.0f}M)", key=f"movie_research_{ss.movie_cycle}"):
                ss.movie_research_paid[ss.movie_cycle] = True
                ss.movie_draft["pa_spend_m"] = float(d.get("pa_spend_m", 40.0)) + RESEARCH_FEE_M
                st.rerun()

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
        with c2:
            pa = st.number_input("P&A / Marketing Spend ($M)", 5.0, 200.0, float(d.get("pa_spend_m", 40.0)), step=5.0,
                                  help="Historically rivals or exceeds the production budget for a wide release.")
            st.caption("Prints & Advertising — trailers, media buys, publicity, the physical/digital "
                       "prints themselves. Real studios routinely spend as much on P&A as on production "
                       "itself for a wide release; it buys awareness (see Star Power below) but not "
                       "quality or word-of-mouth.")
        c3, c4 = st.columns(2)
        with c3:
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
        with c4:
            screens = st.number_input("Planned Opening Screens", 500, 4500, int(d.get("screens", 3000)), step=250)
            st.caption("The U.S. has roughly 40,000 movie screens total (NATO estimate), of which only "
                       "about 700-900 are true large-format IMAX screens — a genuine scarce resource "
                       "exhibitors allocate to their highest-confidence openings. A wide theatrical "
                       "release typically opens on 3,500-4,500 screens; a platform/awards-qualifying "
                       "rollout deliberately starts on a few hundred and expands week over week if the "
                       "film performs. More screens raises your opening (see Opening Weekend below) but "
                       "doesn't guarantee people show up.")

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
            'push exhibitors on terms — separate from Research/AI Pitch Feedback above, which are about '
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
        net_advance_pct = PRESALE_ADVANCE_PCT * (1 - PRESALE_SALES_AGENT_FEE_PCT)
        fin_notes = {
            "self_finance": "You fund 100% of budget + P&A yourself and keep every dollar of "
                             "revenue, domestic and international.",
            "presale": f"A sales agent brokers advances from international distributors, territory "
                       f"by territory, worth ~{PRESALE_ADVANCE_PCT:.0%} of your production budget "
                       f"before you shoot — but the agent takes a real {PRESALE_SALES_AGENT_FEE_PCT:.0%} "
                       f"fee off that advance (real-world range: 10-30%), so only ~{net_advance_pct:.0%} "
                       f"of budget actually reaches you. In exchange, those distributors own most of "
                       f"the international box office outright — real cash relief now, a capped "
                       f"upside later.",
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
                 imax_release=imax_release)
    ss.movie_draft = draft
    project = _current_project(ss)

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
            star_cost_line = (f'<div class="flex justify-between text-sm py-1"><span class="text-ink2">Star Power Cost</span>'
                               f'<span class="font-mono text-warn">+${star_cost:.1f}M</span></div>')
        acq_line = ""
        if acq_cost > 0:
            acq_line = (f'<div class="flex justify-between text-sm py-1"><span class="text-ink2">Rights Acquisition</span>'
                        f'<span class="font-mono text-warn">+${acq_cost:.1f}M</span></div>')
        imax_line = ""
        if project.is_imax_eligible():
            imax_line = (f'<div class="flex justify-between text-sm py-1"><span class="text-ink2">IMAX / Large Format</span>'
                         f'<span class="font-mono text-warn">+${IMAX_COST_M:.0f}M</span></div>')
        st.markdown(f"""
        <div class="rounded-lg border border-line bg-surface p-4">
          <div class="flex justify-between text-sm py-1"><span class="text-ink2">Production Budget</span>
            <span class="font-mono text-warn">${budget:.1f}M</span></div>
          <div class="flex justify-between text-sm py-1 border-b border-line pb-2"><span class="text-ink2">P&A Spend</span>
            <span class="font-mono text-warn">${pa:.1f}M</span></div>
          {star_cost_line}
          {acq_line}
          {imax_line}
          {savings_line}
          <div class="flex justify-between text-base font-semibold pt-2">
            <span class="text-ink">Capital At Risk</span>
            <span class="font-mono text-danger">${financed_capital:.1f}M</span></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title mt-4">Projected Range (Wide Theatrical, before release-strategy choice)</div>',
                    unsafe_allow_html=True)
        rows = ""
        for sc in ("bear", "base", "bull"):
            npv = project.npv(sc)
            c = SUCCESS if npv >= 0 else DANGER
            rows += (f'<div class="flex justify-between text-xs py-1 border-b border-line/50">'
                     f'<span class="text-ink2 capitalize">{sc} case</span>'
                     f'<span class="font-mono" style="color:{c};">{_fmt_money(npv)}</span></div>')
        st.markdown(f'<div class="rounded-lg border border-line bg-surface2 p-3">{rows}</div>', unsafe_allow_html=True)
        st.caption("Actual outcome is drawn continuously between these at Results — not one of exactly three buckets.")

    st.divider()

    # Holding Deals render AFTER Greenlight -- booking a specific actor's
    # window only makes sense once the concept it's for actually exists.
    _section_holding_deals(ss, resolved_hold_key)

    # ── Decision 2: Release Strategy ─────────────────────────────────────────
    st.markdown('<a id="release"></a>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">3 · Release Strategy</div>', unsafe_allow_html=True)

    # ── Seasonality / Debut Timing ───────────────────────────────────────────
    # Phase 5, 2026-08-05: the release-*timing* decision Movies never had
    # before (release_strategy below is wide/platform/day-and-date -- a
    # different axis entirely, decided second so a season's crowding/genre-
    # fit effect is visible on every release-strategy preview card below).
    # Summer/Holiday open bigger but crowd out awards recall; Fall/Awards
    # opens softer but is the deliberate on-ramp into the real awards
    # calendar. "Off-Peak" is a real strategy too, not a placeholder -- many
    # mid-budget films release in an unremarkable week specifically to dodge
    # summer/holiday crowding.
    debut_season = st.selectbox(
        "Debut Season", DEBUT_SEASONS,
        index=DEBUT_SEASONS.index(d.get("debut_season", "Off-Peak")) if d.get("debut_season") in DEBUT_SEASONS else 0,
        help="Summer Tentpole/Holiday open bigger (more audience, more competition) but a summer release "
             "rarely gets recalled by awards voters even with great reviews. Fall/Awards opens softer but "
             "is the real industry on-ramp into awards season. Off-Peak is neutral either way -- a genuine "
             "strategy for dodging crowded weeks, not a placeholder.",
    )
    ss.movie_draft["debut_season"] = debut_season
    project_base = MovieProject(**{**project.__dict__, "debut_season": debut_season})
    season_open_mult = (SEASON_OPENING_MULT.get(debut_season, 1.0)
                         * SEASON_GENRE_SYNERGY.get(debut_season, {}).get(genre, 1.0))
    season_recall = SEASON_AWARDS_RECALL.get(debut_season, 1.0)
    season_notes = []
    if season_open_mult != 1.0:
        season_notes.append(f"{'+' if season_open_mult > 1 else ''}{(season_open_mult - 1) * 100:.0f}% opening intensity")
    if genre in AWARDS_ELIGIBLE_GENRES and season_recall != 1.0:
        season_notes.append(f"{season_recall:.0%} awards-bump recall (vs. full recall for a well-timed release)")
    if season_notes:
        st.caption(f"📅 {' · '.join(season_notes)} for {genre} released {debut_season}.")

    # Progressive windowing — Zach Schlessel's brief: the theatrical vs.
    # streaming vs. PVOD tradeoff is a "Year 3 Introduction," not available
    # from the start. Cycles before WINDOWING_UNLOCK_CYCLE are wide-
    # theatrical only; the strategy choice itself doesn't exist yet.
    windowing_unlocked = ss.movie_cycle >= WINDOWING_UNLOCK_CYCLE
    if not windowing_unlocked:
        ss.movie_draft["release_strategy"] = "wide_theatrical"   # defensive — no other choice is reachable
        st.markdown(f"""
        <div class="rounded-lg border border-line bg-surface2 p-4 mb-3" style="border-left:3px solid #ffa726;">
          <div class="text-xs" style="color:#ffb74d;font-weight:600;margin-bottom:4px;">
            🔒 Windowing strategy unlocks {_cycle_years_label(WINDOWING_UNLOCK_CYCLE)}
          </div>
          <div class="text-xs text-ink2">This early, every release is Wide Theatrical — the platform/
          day-and-date tradeoff (and the streaming infrastructure that makes it viable) isn't part of
          the studio's playbook yet. You'll get the full choice starting {_cycle_years_label(WINDOWING_UNLOCK_CYCLE)}.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(
            '<p class="text-xs text-ink2 mb-3">The direct extension of Day 1\'s linear-vs-SVOD Green Light call — '
            'day-and-date trades theatrical box office for immediate, dollarized Peacock subscriber value. '
            'Ground truth: 2021\'s WarnerMedia/HBO Max day-and-date experiment, and Universal\'s post-2020 '
            'shortened theatrical window with AMC.</p>', unsafe_allow_html=True)

    strategies_shown = RELEASE_STRATEGIES if windowing_unlocked else ["wide_theatrical"]
    cols = st.columns(len(strategies_shown))
    previews = {}
    for i, strat in enumerate(strategies_shown):
        p = MovieProject(**{**project_base.__dict__, "release_strategy": strat})
        ra_npv = risk_adjusted_npv(p)
        previews[strat] = (p, ra_npv)
        with cols[i]:
            c = SUCCESS if ra_npv >= 0 else DANGER
            selected = ss.movie_draft.get("release_strategy", "wide_theatrical") == strat
            border = "border:2px solid #1a6bb5;" if selected else "border:1px solid #252836;"
            st.markdown(f"""
            <div class="rounded-lg bg-surface2 p-4 h-full" style="{border}">
              <div class="font-mono text-xs uppercase tracking-wider text-ink mb-2">{RELEASE_LABELS[strat]}</div>
              <div class="text-2xl font-serif" style="color:{c};">{_fmt_money(ra_npv)}</div>
              <div class="text-[10px] text-muted font-mono mt-1">risk-adjusted NPV</div>
              <div class="text-xs text-ink2 mt-3">Window: {p.window_days()}d theatrical
                {'(skipped — straight to Peacock)' if strat == 'day_and_date' else ''}</div>
            </div>
            """, unsafe_allow_html=True)
            if windowing_unlocked:
                if st.button(f"Choose {RELEASE_LABELS[strat]}", key=f"pick_{strat}", use_container_width=True):
                    ss.movie_draft["release_strategy"] = strat
                    st.rerun()

    st.divider()
    chosen = ss.movie_draft.get("release_strategy", "wide_theatrical")
    st.markdown(f'<p class="text-sm text-ink2">Currently selected: <b class="text-ink">{RELEASE_LABELS[chosen]}</b></p>',
                unsafe_allow_html=True)

    # ── Pay-1 Window Licensing ────────────────────────────────────────────────
    # Doesn't apply to Day-and-Date -- that strategy already commits the
    # title to Peacock exclusivity as its core premise, so licensing the
    # same window away would contradict the choice just made (enforced
    # defensively in MovieProject.is_licensing_out() too, not just here).
    if chosen != "day_and_date":
        st.markdown('<div class="section-title mt-3">Pay-1 Window Licensing</div>', unsafe_allow_html=True)
        pay1_labels = {
            "keep": "Keep on Peacock — full subscriber value, tied to how the movie actually performs",
            "license_out": f"License to a Rival Platform — flat, guaranteed fee "
                            f"(~{PAY1_LICENSE_DISCOUNT:.0%} of base-case subscriber value), paid sooner",
        }
        pay1_choice = st.selectbox(
            "Pay-1 SVOD Window", PAY1_LICENSING_OPTIONS,
            index=PAY1_LICENSING_OPTIONS.index(ss.movie_draft.get("pay1_licensing", "keep")),
            format_func=lambda k: pay1_labels[k],
            help="A real Pay-1 licensing deal, negotiated before release — cash now and sooner, but "
                 "you give up the subscriber-value upside and the strategic value of owning the "
                 "streaming relationship.",
        )
        ss.movie_draft["pay1_licensing"] = pay1_choice
    else:
        ss.movie_draft["pay1_licensing"] = "keep"
        st.caption("Pay-1 licensing isn't available for Day-and-Date releases — that strategy already "
                   "commits this title to Peacock exclusivity.")

    st.divider()

    # ── Simulate ───────────────────────────────────────────────────────────────
    st.markdown('<a id="simulate"></a>', unsafe_allow_html=True)
    if st.button("▶  Simulate  →  See Results", type="primary", use_container_width=True):
        project = _current_project(ss)
        multiplier = draw_actual_multiplier(ss.team_name, ss.movie_cycle, project.genre, project.concept_type)
        # Critical reception is drawn independently of box-office
        # performance — a movie can open huge and get panned, or open
        # modestly and find acclaim. Neither draw is known to the
        # student until this exact moment. ai_production_tools caps the
        # ceiling of this draw (see utils/movie_models.py).
        critical_score = draw_critical_reception(ss.team_name, ss.movie_cycle, project.genre,
                                                  ai_production_tools=project.ai_production_tools)
        talent_bonus = _active_talent_bonus(ss, project.genre, project.source_material)
        if "critical_score_bonus" in talent_bonus:
            critical_score = min(100.0, critical_score + talent_bonus["critical_score_bonus"])

        # Production Trouble — a real, independent creative/talent risk axis
        # (director/actor/VFX/producer setbacks), rare (~5%), applied as a
        # haircut on the resolved box-office multiplier rather than zeroing
        # the cycle outright — a movie IS the whole bet, unlike a TV show
        # inside a 20-show portfolio. See utils/movie_models.py.
        trouble = draw_production_trouble(ss.team_name, ss.movie_cycle)
        trouble_reason = None
        if trouble:
            trouble_reason, haircut = trouble
            multiplier *= haircut

        # AI Tooling Setback — own independent risk axis, only ever rolled
        # for projects that opted into AI Production Tools (see
        # utils/movie_models.py::draw_ai_tooling_setback). Stacks
        # multiplicatively with Production Trouble's haircut if both fire
        # in the same cycle — two unrelated real-world setbacks can both
        # happen to the same movie.
        ai_setback_reason = None
        if project.ai_production_tools:
            ai_setback = draw_ai_tooling_setback(ss.team_name, ss.movie_cycle)
            if ai_setback:
                ai_setback_reason, ai_haircut = ai_setback
                multiplier *= ai_haircut

        # Ancillary Markets Surprise — PVOD rentals and theme-park/merchandise
        # licensing, genuinely movie-specific (TV has neither window at all),
        # independent of both box office and critical reception.
        ancillary = draw_ancillary_surprise(ss.team_name, ss.movie_cycle)
        ancillary_reason = None
        pvod_mult = theme_park_mult = 1.0
        if ancillary:
            ancillary_reason, ancillary_mult = ancillary
            pvod_mult = theme_park_mult = ancillary_mult

        # eWOM & Piracy — a separate, more-common independent swing on
        # digital revenue (PVOD + owned Peacock subscriber value together),
        # own seed, distinct from Ancillary Surprise's theme-park/rental
        # licensing story. See utils/movie_models.py.
        ewom = draw_ewom_piracy_swing(ss.team_name, ss.movie_cycle)
        ewom_reason = None
        ewom_mult = 1.0
        if ewom:
            ewom_reason, ewom_mult = ewom

        awards_eligible = project.genre in AWARDS_ELIGIBLE_GENRES
        waterfall = participation_waterfall(project, multiplier, critical_score,
                                             pvod_mult=pvod_mult, theme_park_mult=theme_park_mult,
                                             ewom_mult=ewom_mult)
        outcome = {
            "cycle":            ss.movie_cycle,
            "project_kwargs":   dict(project.__dict__),
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
            "npv":              project.npv(multiplier, critical_score, pvod_mult=pvod_mult, theme_park_mult=theme_park_mult, ewom_mult=ewom_mult),
            "irr":              project.irr(multiplier, critical_score, pvod_mult=pvod_mult, theme_park_mult=theme_park_mult, ewom_mult=ewom_mult),
            "total_revenue":    project.total_revenue(multiplier, critical_score, pvod_mult=pvod_mult, theme_park_mult=theme_park_mult, ewom_mult=ewom_mult),
            "domestic_bo":      project.domestic_box_office(multiplier),
            "theatrical_net":   project.theatrical_studio_net(multiplier),
            "pvod":             project.pvod_revenue(multiplier) * pvod_mult * ewom_mult,
            "sub_value":        (project.pay1_license_fee() if project.is_licensing_out()
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
        ss.movie_phase = "results"
        st.rerun()


# ── Phase 2: Results ──────────────────────────────────────────────────────────
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

    if ss.movie_log:
        st.markdown('<div class="section-title mt-2">Slate So Far — NPV by Year</div>', unsafe_allow_html=True)
        cyc_labels = [_cycle_years_label(r["cycle"]) for r in sorted(ss.movie_log, key=lambda r: r["cycle"])]
        npvs = [r["npv"] for r in sorted(ss.movie_log, key=lambda r: r["cycle"])]
        fig2 = go.Figure(go.Bar(x=cyc_labels, y=npvs,
                                 marker_color=[SUCCESS if v >= 0 else DANGER for v in npvs]))
        fig2.add_hline(y=0, line_dash="dash", line_color=WARN, opacity=0.4)
        fig2.update_layout(**base_layout("NPV by Year ($M)", height=240))
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    st.divider()
    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button(f"← Redo {_cycle_years_label(ss.movie_cycle)}", use_container_width=True):
            ss.movie_log = [r for r in ss.movie_log if r["cycle"] != ss.movie_cycle]
            ss.movie_phase = "decisions"
            st.rerun()
    with nav2:
        if ss.movie_cycle < CYCLES_TOTAL:
            if st.button(f"→ Start {_cycle_years_label(ss.movie_cycle + 1)}", type="primary", use_container_width=True):
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
    score = compute_movie_score(projects, critical_scores)

    total_c = SUCCESS if score["total"] >= 70 else (WARN if score["total"] >= 50 else DANGER)
    npv_c = SUCCESS if score["avg_ra_npv_m"] >= 0 else DANGER

    st.markdown(f"""
    <div class="rounded-lg bg-surface2 p-5 mb-5" style="border-left:4px solid #1a6bb5;">
      <div class="font-mono text-[10px] text-muted uppercase tracking-widest mb-3">
        Full Slate Results — Universal Pictures · {CYCLES_TOTAL * YEARS_PER_CYCLE} Years
      </div>
      <div class="flex gap-8 flex-wrap">
        <div><div class="text-[9px] text-muted font-mono">AVG RISK-ADJ. NPV</div>
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

    with score_col:
        st.markdown('<div class="section-title">Score Breakdown</div>', unsafe_allow_html=True)
        components = [
            ("Risk-Adj. NPV",           score["risk_adjusted_npv"],       "45%",
             "Weights your bear-case outcome at 50% rather than scoring on the rosy base case alone — "
             "rewards risk-aware greenlighting, not blind optimism."),
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
              <div class="text-xs" style="color:#e0e2ea;">{sub}</div>
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
            ss.movie_submitted = False
            ss.movie_last_score = None
            st.rerun()
