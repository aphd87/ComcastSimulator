"""
Simulation tab — annual turn engine.
Decisions → Results → repeat for YEARS_PER_LEVEL years, then submit final score.

Restructured 2026-07-24 from a quarterly engine (4 quarters within a single
frozen "year 1") to a genuine annual engine per Zach Schlessel's (NBCUniversal)
feedback — see DESIGN_NOTES.md. ss.year is the actual turn counter driving
all financial math, not a fixed value.

Reshaped 2026-07-27 to real calendar eras per network, each starting
exactly YEARS_PER_LEVEL after the last (clean handoff, no overlap) —
YEARS_PER_LEVEL and LEVEL_START_YEAR now live in utils/game_state.py as the
single source of truth (app.py's LEVEL_BRIEFS mission text reads the same
constants), not duplicated here. YEARS_PER_LEVEL defaults to 4 but is
instructor-tailorable per deployment (2026-08-03) — see README.md.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from utils.models import (
    distribution_revenue, portfolio_ad_rev,
    greenlight_linear, greenlight_svod, performance_linked_growth,
    MIN_MARKETING_PER_SHOW_M, draw_production_risk_event,
    draw_emergency_budget_shock,
    draw_emmy_reception, EMMY_ELIGIBLE_GENRES, EMMY_NOMINATION_THRESHOLD, EMMY_WIN_THRESHOLD,
)
from utils.game_state import (
    NETWORK_INFO, NETWORK_ORDER, compute_score_for_network,
    record_attempt, get_attempt_count, can_advance,
    get_official_score, MAX_ATTEMPTS, hhi_from_genres, SCORE_WEIGHTS,
    YEARS_PER_LEVEL, LEVEL_START_YEAR, compute_level_notables,
)
from utils.sports_models import (
    SPORTS_LEAGUES, leagues_up_for_bid, cycle_for_year, draw_rival_bids,
    resolve_auction, SportsContract, held_this_year, sports_year_pnl,
)
from utils.charts import base_layout, SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2


# ── Helpers ───────────────────────────────────────────────────────────────────

def _year_label(year: int, net: str) -> str:
    return f"Year {year} · {LEVEL_START_YEAR[net] + (year - 1)}"


def _active_shows(shows, cancelled: set):
    return [s for s in shows if s.id not in cancelled]


def _remove_greenlit_shows(ss, ids_to_remove: set):
    """Strips the given show IDs out of whichever roster list(s) they're
    in — used to undo shows added via pages/greenlight.py's "Greenlight
    This Show" action on Redo Year / Restart Level. IDs are globally
    unique (see ss.next_show_id, initialized in pages/greenlight.py), so
    filtering all three lists uniformly is safe and simple. Note: unlike
    cancellations, this does NOT refund the production cost already
    deducted from ss.level_budget — same posture as Research fees, which
    also aren't refunded on redo. Only the phantom show itself is removed
    so it doesn't linger with no record of how it was paid for."""
    if not ids_to_remove:
        return
    for key in ("oxygen_shows", "bravo_shows", "peacock_shows"):
        ss[key] = [s for s in ss.get(key, []) if s.id not in ids_to_remove]


def _annual_cost(shows, year: int, prev_cancelled: set, new_cancel: set) -> float:
    """Full annual amort cost. New cancellations pay a 25% sunk-cost penalty
    (production already committed before the decision); prior cancellations
    cost nothing."""
    total = 0.0
    for s in shows:
        if s.id in prev_cancelled:
            continue
        if s.id in new_cancel:
            total += s.annual_amort_expense(year) * 0.25
        else:
            total += s.annual_amort_expense(year)
    return total


def _preview_pnl(shows, year: int, mkt: float,
                 prev_cancelled: set, new_cancel: set,
                 sports_rev_m: float = 0.0, sports_cost_m: float = 0.0) -> dict:
    """Expected (no-variance) P&L for the live preview card. sports_rev_m/
    sports_cost_m (Peacock only — see utils/sports_models.py) are added as
    real revenue/cost lines, same treatment as ad/distribution revenue and
    content cost, so a held sports contract's structural loss shows up in
    OCF margin exactly like any other business decision."""
    cancelled = prev_cancelled | new_cancel
    active    = _active_shows(shows, cancelled)
    per       = mkt / max(len(active), 1)

    ad_rev   = sum(s.ad_revenue(year, per) for s in active)
    dist_rev = distribution_revenue(year)
    rev      = ad_rev + dist_rev + sports_rev_m
    cost     = _annual_cost(shows, year, prev_cancelled, new_cancel) + sports_cost_m
    ga       = rev * 0.06
    ocf      = rev - cost - mkt - ga
    margin   = (ocf / rev * 100) if rev > 0 else 0.0
    return {"rev": rev, "ad_rev": ad_rev, "dist_rev": dist_rev,
            "sports_rev": sports_rev_m, "sports_cost": sports_cost_m,
            "cost": cost, "ga": ga, "ocf": ocf, "margin": margin}


def _compute_year(ss, shows, year: int, mkt: float, new_cancel: set, net: str,
                  sports_rev_m: float = 0.0, sports_cost_m: float = 0.0) -> dict:
    """Apply seeded ±7% rating variance and compute the year's actual P&L.
    sports_rev_m/sports_cost_m (Peacock only) fold straight into total
    revenue/cost, same as _preview_pnl above — everything downstream
    (Results banner, Complete-phase totals, score) reads result["revenue"]/
    ["cost"] and so already reflects the sports P&L without further changes."""
    seed = (abs(hash(ss.team_name)) + year * 1337) % (2 ** 31)
    rng  = np.random.default_rng(seed)

    prev_cancelled = ss.cancelled_shows
    cancelled_all  = prev_cancelled | new_cancel
    active         = _active_shows(shows, cancelled_all)
    per            = mkt / max(len(active), 1)

    show_rows  = []
    adj_ad_rev = 0.0

    for s in shows:
        v = float(rng.uniform(0.93, 1.08))   # always consume an RNG value for reproducibility
        # Production-risk event — an independent risk axis from rating
        # variance (own seed, drawn regardless of branch below so it never
        # perturbs the `rng` sequence preview_show_variance() replicates).
        # Only rolled for shows the student didn't already choose to drop.
        risk_reason = None
        if s.id not in prev_cancelled and s.id not in new_cancel:
            risk_reason = draw_production_risk_event(ss.team_name, year, s.id)

        if s.id in prev_cancelled:
            show_rows.append({"id": s.id, "name": s.name, "network": s.network, "genre": s.genre,
                               "status": "prev_cancelled",
                               "rating_base": s.rating, "rating_adj": 0.0,
                               "variance": round(v, 3), "revenue": 0.0, "cost": 0.0})
        elif s.id in new_cancel:
            show_rows.append({"id": s.id, "name": s.name, "network": s.network, "genre": s.genre,
                               "status": "cancelled",
                               "rating_base": s.rating, "rating_adj": 0.0,
                               "variance": round(v, 3), "revenue": 0.0,
                               "cost": round(s.annual_amort_expense(year) * 0.25, 2)})
        elif risk_reason:
            # A real, involuntary setback — not a student decision. Same
            # sunk-cost treatment as a mid-year cancellation (production
            # already committed), but the show stays in the roster for
            # next year's Renewal decision rather than being permanently
            # dropped — one bad year, not a career-ending one.
            show_rows.append({"id": s.id, "name": s.name, "network": s.network, "genre": s.genre,
                               "status": "risk_event", "reason": risk_reason,
                               "rating_base": s.rating, "rating_adj": 0.0,
                               "variance": round(v, 3), "revenue": 0.0,
                               "cost": round(s.annual_amort_expense(year) * 0.25, 2)})
        else:
            rev = s.ad_revenue(year, per) * v
            adj_ad_rev += rev
            # Emmy Tracking (Phase 6, 2026-08-05) -- only rolled for shows
            # that actually aired at full value this year, own independent
            # seed (never perturbs `rng`'s sequence or draw_production_risk_
            # event's). None for non-eligible genres -- see EMMY_ELIGIBLE_
            # GENRES in utils/models.py.
            emmy_score = draw_emmy_reception(ss.team_name, year, s.id, s.genre)
            show_rows.append({"id": s.id, "name": s.name, "network": s.network, "genre": s.genre,
                               "status": "active",
                               "rating_base": s.rating,
                               "rating_adj": round(s.rating * v, 2),
                               "variance": round(v, 3),
                               "revenue": round(rev, 2),
                               "cost": round(s.annual_amort_expense(year), 2),
                               "emmy_score": emmy_score,
                               "emmy_nomination": emmy_score is not None and emmy_score >= EMMY_NOMINATION_THRESHOLD,
                               "emmy_win": emmy_score is not None and emmy_score >= EMMY_WIN_THRESHOLD})

    dist_rev   = distribution_revenue(year)
    total_rev  = adj_ad_rev + dist_rev + sports_rev_m
    total_cost = sum(r["cost"] for r in show_rows) + sports_cost_m
    ga         = total_rev * 0.06
    ocf        = total_rev - total_cost - mkt - ga
    margin     = (ocf / total_rev * 100) if total_rev > 0 else 0.0
    emmy_nominations = sum(1 for r in show_rows if r.get("emmy_nomination"))
    emmy_wins         = sum(1 for r in show_rows if r.get("emmy_win"))

    return {
        "year":    year,
        "label":   _year_label(year, net),
        "revenue": round(total_rev, 2),
        "ad_rev":  round(adj_ad_rev, 2),
        "dist_rev":round(dist_rev, 2),
        "sports_rev":  round(sports_rev_m, 2),
        "sports_cost": round(sports_cost_m, 2),
        "cost":    round(total_cost, 2),
        "mkt":     round(mkt, 2),
        "ga":      round(ga, 2),
        "ocf":     round(ocf, 2),
        "margin":  round(margin, 1),
        "emmy_nominations": emmy_nominations,
        "emmy_wins":        emmy_wins,
        "new_cancellations": list(new_cancel),
        "shows":   show_rows,
    }


# ── Session state init ─────────────────────────────────────────────────────────

def _init(ss, net_info):
    if not isinstance(ss.get("yearly_log"), list):
        ss.yearly_log = []
    if not isinstance(ss.get("cancelled_shows"), set):
        ss.cancelled_shows = set(ss.get("cancelled_shows") or [])
    if not isinstance(ss.get("renewal_decisions"), dict):
        ss.renewal_decisions = {}
    if not ss.get("year"):
        ss.year = 1
    if ss.get("sim_phase") not in ("decisions", "results", "complete"):
        ss.sim_phase = "decisions"
    if not ss.get("level_budget"):
        ss.level_budget = float(net_info["budget_base"])
    if not isinstance(ss.get("sports_contracts"), list):
        ss.sports_contracts = []
    if not isinstance(ss.get("sports_bid_log"), dict):
        ss.sports_bid_log = {}


# ── Progress bar ───────────────────────────────────────────────────────────────

def _progress_bar(ss, net_info, year, phase, net):
    dot_items = []
    for i in range(1, YEARS_PER_LEVEL + 1):
        done    = any(r["year"] == i for r in ss.yearly_log)
        current = (i == year) and phase != "complete"
        if done or phase == "complete":
            bg, txt, clr = "#66bb6a", "✓", "#0b0c10"
        elif current:
            bg, txt, clr = net_info["color"], str(i), "#ffffff"
        else:
            bg, txt, clr = "#252836", str(i), "#b0b5c4"
        dot_items.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">'
            f'<div style="width:34px;height:34px;border-radius:50%;background:{bg};'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-family:DM Mono,monospace;font-size:15px;font-weight:700;color:{clr};">{txt}</div>'
            f'<div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;margin-top:2px;">'
            f'Yr {i}</div>'
            f'</div>'
        )
    connector   = '<div style="width:44px;height:2px;background:#252836;margin-bottom:16px;"></div>'
    phase_label = {"decisions": "▶ Decision Phase",
                   "results":   "📊 Year Results",
                   "complete":  "✅ Level Complete"}[phase]
    y_label = _year_label(year, net) if phase != "complete" else f"{net_info['display_name']} — Level Complete"

    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;
         padding:14px 20px;margin-bottom:18px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <div style="font-family:DM Mono,monospace;font-size:14px;color:#e0e2ea;">{y_label}</div>
        <div style="font-family:DM Mono,monospace;font-size:14px;color:{net_info['color']};
             text-transform:uppercase;letter-spacing:.08em;">{phase_label}</div>
      </div>
      <div style="display:flex;align-items:center;justify-content:center;">
        {connector.join(dot_items)}
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Main render ────────────────────────────────────────────────────────────────

def render():
    ss       = st.session_state
    net      = ss.active_network
    net_info = NETWORK_INFO[net]
    _init(ss, net_info)

    team     = ss.team_name
    year     = ss.year

    shows = ss.oxygen_shows[:]
    if net in ("bravo", "peacock"):
        shows += ss.bravo_shows
    if net == "peacock":
        shows += ss.get("peacock_shows", [])

    phase = ss.sim_phase

    _progress_bar(ss, net_info, year, phase, net)

    if phase == "decisions":
        _decisions(ss, shows, net_info, year, net)
    elif phase == "results":
        _results(ss, shows, net_info, year, team, net)
    else:
        _complete(ss, shows, net_info, team, net)


# ── Decisions phase ────────────────────────────────────────────────────────────

def _year_recap_narrative(prev: dict) -> str:
    """Auto-generated 1-2 sentence strengths/opportunities read on last
    year's actuals (2026-08-07, per user request) -- the metrics row above
    shows WHAT happened, this says what it means for this year's calls.
    Strength = the single top-revenue active show (+ Emmy recognition if
    any); Opportunity = the single worst active show where cost exceeded
    revenue, plus any involuntary production-risk setbacks. Deliberately
    picks one show each, not a full breakdown -- the point is a fast read,
    not a re-derivation of the Renewal table below."""
    # .get()-guarded throughout -- a yearly_log entry recorded before this
    # narrative existed (or before some other field was added) may carry a
    # "shows" list whose rows are missing "revenue"/"cost"/"name" entirely,
    # same legacy-entry posture as the Emmy badge above; must render
    # cleanly, not KeyError (see test_last_year_recap_omits_emmy_badge_for_
    # legacy_entries_without_the_field).
    active = [s for s in prev.get("shows", []) if s.get("status") == "active"]

    strengths = []
    if active:
        top = max(active, key=lambda s: s.get("revenue", 0))
        strengths.append(
            f"<b>{top.get('name', 'A show')}</b> was your strongest earner "
            f"(${top.get('revenue', 0):.1f}M revenue)"
        )
    if prev.get("emmy_wins"):
        n = prev["emmy_wins"]
        strengths.append(f"{n} Emmy win{'s' if n != 1 else ''}")
    elif prev.get("emmy_nominations"):
        n = prev["emmy_nominations"]
        strengths.append(f"{n} Emmy nomination{'s' if n != 1 else ''}")
    strength_line = " and ".join(strengths) if strengths else "no standout performer this year"

    opportunities = []
    losers = [s for s in active if s.get("cost", 0) > s.get("revenue", 0)]
    if losers:
        worst = max(losers, key=lambda s: s.get("cost", 0) - s.get("revenue", 0))
        opportunities.append(
            f"<b>{worst.get('name', 'A show')}</b> cost more (${worst.get('cost', 0):.1f}M) than it earned "
            f"(${worst.get('revenue', 0):.1f}M) — a renewal candidate to reconsider"
        )
    risk_events = [s for s in prev.get("shows", []) if s.get("status") == "risk_event"]
    if risk_events:
        n = len(risk_events)
        opportunities.append(f"{n} show{'s' if n != 1 else ''} hit an unplanned production setback")
    if not opportunities:
        opportunities.append("no major drags on the portfolio this year")
    opportunity_line = "; ".join(opportunities)

    return (f'💪 <b style="color:{SUCCESS};">Strength:</b> {strength_line}. '
            f'🎯 <b style="color:{WARN};">Opportunity:</b> {opportunity_line}.')


def _last_year_recap(prev: dict, threshold: float):
    """Pinned strip at the top of Decisions showing last year's actuals —
    otherwise invisible the moment a student advances past Results. Added
    2026-07-24 per user feedback: students need this as reference while
    making this year's calls, not just a one-time glance in Results."""
    ocf_c    = SUCCESS if prev["ocf"] >= 0 else DANGER
    margin_c = SUCCESS if prev["margin"] >= threshold else (WARN if prev["ocf"] >= 0 else DANGER)
    # .get()-guarded -- entries recorded before Emmy Tracking existed won't
    # carry these keys. Wins over nominations, same posture as Movies'
    # Oscar badge (a win is a strict superset of a nomination).
    emmy_wins = prev.get("emmy_wins") or 0
    emmy_noms = prev.get("emmy_nominations") or 0
    emmy_span = ""
    if emmy_wins:
        emmy_span = (f'<span style="font-size:14px;color:{ACCENT};">🏆 '
                     f'<b style="font-family:DM Mono,monospace;">{emmy_wins} Emmy win{"s" if emmy_wins != 1 else ""}</b></span>')
    elif emmy_noms:
        emmy_span = (f'<span style="font-size:14px;color:{SUCCESS};">🎬 '
                     f'<b style="font-family:DM Mono,monospace;">{emmy_noms} Emmy nom{"s" if emmy_noms != 1 else ""}</b></span>')
    st.markdown(f"""
    <div style="background:#12141a;border:1px solid #252836;border-radius:8px;
         padding:10px 18px;margin-bottom:16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px;">
        <div style="font-family:DM Mono,monospace;font-size:14px;color:#b0b5c4;
             text-transform:uppercase;letter-spacing:.08em;">{prev['label']} — Last Year's Actuals</div>
        <div style="display:flex;gap:22px;flex-wrap:wrap;">
          <span style="font-size:14px;color:#e0e2ea;">Revenue <b style="font-family:DM Mono,monospace;color:#e8eaf0;">${prev['revenue']:.1f}M</b></span>
          <span style="font-size:14px;color:#e0e2ea;">Cost <b style="font-family:DM Mono,monospace;color:{WARN};">${prev['cost']:.1f}M</b></span>
          <span style="font-size:14px;color:#e0e2ea;">OCF <b style="font-family:DM Mono,monospace;color:{ocf_c};">${prev['ocf']:+.1f}M</b></span>
          <span style="font-size:14px;color:#e0e2ea;">Margin <b style="font-family:DM Mono,monospace;color:{margin_c};">{prev['margin']:.1f}%</b></span>
          {emmy_span}
        </div>
      </div>
      <div style="font-size:14px;color:#e0e2ea;margin-top:8px;padding-top:8px;border-top:1px solid #252836;">
        {_year_recap_narrative(prev)}
      </div>
    </div>
    """, unsafe_allow_html=True)


def _progress_chart(ss, threshold: float):
    """Compact multi-year trend, shown once 2+ years have real actuals in
    ss.yearly_log -- added 2026-08-04 per user request: _last_year_recap
    above is a single-year snapshot, but students asked to see how they're
    trending across the level before making this year's calls, not just
    last year's number. Deliberately smaller/lighter than the full
    'Level P&L — All Years' chart in _complete() (same OCF-bar +
    cumulative-OCF-line shape for visual consistency) -- that one only
    ever renders once the whole level is over; this one compounds year
    by year as the level is played."""
    log     = sorted(ss.yearly_log, key=lambda r: r["year"])
    ylabels = [r["label"].split(" · ")[0] for r in log]
    cum_ocf = np.cumsum([r["ocf"] for r in log]).tolist()
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Annual OCF", x=ylabels, y=[r["ocf"] for r in log],
                         marker_color=[SUCCESS if r["ocf"] >= 0 else DANGER for r in log],
                         opacity=0.75))
    fig.add_trace(go.Scatter(name="Cumulative OCF", x=ylabels, y=cum_ocf,
                             mode="lines+markers", line=dict(color=ACCENT2, width=2, dash="dot"),
                             marker=dict(size=7)))
    fig.add_hline(y=0, line_dash="dash", line_color=WARN, opacity=0.3)
    fig.update_layout(**base_layout("Your Progress So Far — OCF by Year ($M)", height=210))
    st.markdown('<div style="margin-bottom:16px;">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)


def _starting_position(net_info, shows, net):
    """Year-1-only card, shown once before Financing: unlike _last_year_recap
    (which reads real yearly_log actuals from year > 1), there is no played
    year to recap yet — so this instead shows the incoming roster's baseline
    economics (its built-in ratings/costs, default $5M marketing, no
    cancellations/decisions applied) as a stand-in for "how the network was
    doing the year before you took over." Explicitly labeled as a baseline,
    not an official actual, so students don't mistake it for a real played year."""
    start_year = LEVEL_START_YEAR[net]
    baseline   = _preview_pnl(shows, 1, 5.0, set(), set())
    margin_c   = SUCCESS if baseline["margin"] >= net_info["pass_threshold"] else (
                 WARN if baseline["ocf"] >= 0 else DANGER)
    st.markdown(f"""
    <div style="background:#12141a;border:1px solid #252836;border-radius:8px;
         padding:10px 18px;margin-bottom:16px;">
      <div style="font-family:DM Mono,monospace;font-size:14px;color:#b0b5c4;
           text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;">
        {net_info['display_name']} — Starting Position ({start_year - 1})
      </div>
      <div style="font-size:14px;color:#e0e2ea;margin-bottom:10px;line-height:1.5;">
        This is where {net_info['display_name']} stood the year before you took over —
        its current show slate's built-in ratings and costs, run at a default $5M
        marketing spend with no cancellations. It's a baseline for comparison, not an
        official played year (that starts once you simulate Year 1 below).
        <b style="color:#e8eaf0;">Pass threshold</b> is the minimum OCF margin
        (OCF ÷ Revenue) {net_info['display_name']} needs to hit by the end of the level
        to pass — {net_info['pass_threshold']:.0f}% here — so this baseline's own margin
        tells you how far off the starting slate already is before you make a single decision.
      </div>
      <div style="display:flex;gap:22px;flex-wrap:wrap;">
        <span style="font-size:14px;color:#e0e2ea;">Revenue <b style="font-family:DM Mono,monospace;color:#e8eaf0;">${baseline['rev']:.1f}M</b></span>
        <span style="font-size:14px;color:#e0e2ea;">Cost <b style="font-family:DM Mono,monospace;color:{WARN};">${baseline['cost']:.1f}M</b></span>
        <span style="font-size:14px;color:#e0e2ea;">OCF <b style="font-family:DM Mono,monospace;color:{SUCCESS if baseline['ocf'] >= 0 else DANGER};">${baseline['ocf']:+.1f}M</b></span>
        <span style="font-size:14px;color:#e0e2ea;">Margin <b style="font-family:DM Mono,monospace;color:{margin_c};">{baseline['margin']:.1f}%</b></span>
        <span style="font-size:14px;color:#e0e2ea;">Pass threshold <b style="font-family:DM Mono,monospace;color:#e0e2ea;">{net_info['pass_threshold']:.0f}%</b></span>
      </div>
    </div>
    """, unsafe_allow_html=True)


def _section_financing(ss, shows, year, net_info, level_budget):
    st.markdown('<div class="section-title">1 · 💰 Financing</div>', unsafe_allow_html=True)

    # ── Mid-year emergency budget shock ─────────────────────────────────────
    # Rare, automated, seeded per team+year (see draw_emergency_budget_shock)
    # — answers one of Zach Schlessel's brief's own never-resolved "Open
    # Simulation Decisions" questions. Applied at most once per year:
    # ss.emergency_shock_years tracks which years have already had the cut
    # deducted, so re-rendering this step (every Streamlit rerun) doesn't
    # re-subtract it repeatedly.
    if "emergency_shock_years" not in ss:
        ss.emergency_shock_years = set()
    shock = draw_emergency_budget_shock(ss.team_name, year)
    if shock is not None:
        if year not in ss.emergency_shock_years:
            ss.level_budget -= level_budget * shock
            level_budget = ss.level_budget
            ss.emergency_shock_years.add(year)
        st.markdown(f"""
        <div style="background:rgba(239,83,80,.08);border:1px solid rgba(239,83,80,.35);
             border-left:3px solid {DANGER};border-radius:6px;padding:12px 16px;margin-bottom:14px;">
          <div style="font-size:15px;color:{DANGER};font-weight:600;margin-bottom:4px;">
            ⚠️ Mid-Year Emergency Budget Cut — {shock*100:.0f}%
          </div>
          <div style="font-size:14px;color:#e0e2ea;">
            Corporate pulled back this year's budget mid-cycle — real and permanent, not a
            preview. Adjust marketing and Renewal decisions to fit the new number below.
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Budget is performance-linked as of 2026-07-24 (Zach Schlessel
    # feedback: good year = more budget, poor year = a cut), not a flat
    # 3%/yr — see performance_linked_growth() in utils/models.py.
    if year > 1:
        st.markdown(
            f'<div style="font-size:14px;color:#e0e2ea;margin-bottom:6px;">'
            f'This year\'s budget (<b style="color:#e8eaf0;">${level_budget:.1f}M</b>) reflects how '
            f'Year {year-1} went — clear the {net_info["pass_threshold"]:.0f}% margin target and next '
            f'year\'s budget grows faster; miss it and it shrinks.</div>',
            unsafe_allow_html=True)

    # Revenue streams — where the money actually comes from, shown before
    # the marketing-spend decision so students see ad vs. distribution
    # (subscriber) revenue rather than just a budget number.
    ann_ad_rev   = portfolio_ad_rev(shows, year, ss.get("mkt_budget", 5.0))
    ann_dist_rev = distribution_revenue(year)
    ann_total    = ann_ad_rev + ann_dist_rev
    ad_pct   = (ann_ad_rev / ann_total * 100) if ann_total else 0
    dist_pct = 100 - ad_pct if ann_total else 0

    st.markdown(
        '<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;">'
        'Two revenue streams fund everything below: <b style="color:#e8eaf0;">ad revenue</b> '
        '(rating × marketing lift, eroding as cord-cutting continues) and '
        '<b style="color:#e8eaf0;">distribution revenue</b> (affiliate fees × subscriber count, '
        'also eroding but with an escalation clause). At current ratings/marketing:</div>',
        unsafe_allow_html=True)

    rcol1, rcol2, rcol3 = st.columns(3)
    rcol1.metric("📺 Ad Revenue", f"${ann_ad_rev:.1f}M", f"{ad_pct:.0f}% of revenue")
    rcol2.metric("📡 Distribution", f"${ann_dist_rev:.1f}M", f"{dist_pct:.0f}% of revenue")
    rcol3.metric("Total Revenue", f"${ann_total:.1f}M")

    # ── Linear vs. Streaming economics ──────────────────────────────────────
    active_for_cmp = _active_shows(shows, ss.cancelled_shows)
    if active_for_cmp:
        avg_rating   = sum(s.rating for s in active_for_cmp) / len(active_for_cmp)
        avg_eps      = round(sum(s.episodes for s in active_for_cmp) / len(active_for_cmp))
        avg_ep_cost  = sum(s.ep_cost_k for s in active_for_cmp) / len(active_for_cmp)
        per_show_mkt = ss.get("mkt_budget", 5.0) / len(active_for_cmp)

        st.markdown('<div class="section-title" style="margin-top:14px;">Linear vs. Streaming — Your Average Show</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;">'
            'Same math as the Greenlighting tab\'s linear-vs-SVOD builder, run on your own '
            'portfolio\'s average show instead of a new pitch. Linear wins on immediate cash '
            'early on; SVOD subscriber LTV catches up over time.</div>',
            unsafe_allow_html=True)

        checkpoints = sorted(set(y for y in (year, year + 3, year + 6) if y >= 1))
        lin_vals, svod_vals = [], []
        for yr in checkpoints:
            lin  = greenlight_linear(avg_eps, avg_ep_cost, avg_rating, per_show_mkt, yr)
            svod = greenlight_svod(avg_eps, avg_ep_cost, avg_rating, 65, per_show_mkt, yr)
            lin_vals.append(round(lin["ocf"], 2))
            svod_vals.append(round(svod["ocf"], 2))

        fig_ls = go.Figure()
        fig_ls.add_trace(go.Bar(name="📺 Linear OCF", x=[f"Year {y}" for y in checkpoints],
                                 y=lin_vals, marker_color=ACCENT, opacity=0.85))
        fig_ls.add_trace(go.Bar(name="📱 SVOD OCF", x=[f"Year {y}" for y in checkpoints],
                                 y=svod_vals, marker_color=ACCENT2, opacity=0.85))
        fig_ls.update_layout(**base_layout("Average Show OCF: Linear vs. SVOD ($M)", height=240), barmode="group")
        st.plotly_chart(fig_ls, use_container_width=True, config={"displayModeBar": False})
        st.caption("Genre appeal fixed at 65/100 (moderate streaming conversion) for this comparison — the Greenlighting tab lets you tune it per concept.")

    st.divider()

    # ── Marketing spend ───────────────────────────────────────────────────
    st.markdown('<div class="section-title">Decision — Marketing Spend</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:14px;color:#e0e2ea;margin-bottom:10px;">'
        'Higher spend lifts ratings and ad revenue. Each $1M ≈ +1.5% ad rev lift. '
        'Diminishing returns above $16M.</div>', unsafe_allow_html=True)

    # key="mkt_budget" binds this widget directly to ss.mkt_budget — reads
    # its current value as the default and writes back on every change, so
    # every other step (and the pinned P&L preview) always sees the live
    # figure instead of a value only synced at End Year (a real staleness
    # bug the old per-year-keyed slider had, fixed incidentally here).
    st.slider("Marketing ($M this year)", 0.0, 24.0, step=0.5, key="mkt_budget")

    # Zach Schlessel's feedback: shows below a per-show marketing floor
    # aren't realistically viable. Soft warning, not a hard block — the
    # math still runs either way, same posture as the screens-realism
    # warning in Greenlighting.
    active_count = len(_active_shows(shows, ss.cancelled_shows))
    per_show_mkt = ss.get("mkt_budget", 5.0) / max(active_count, 1)
    if active_count and per_show_mkt < MIN_MARKETING_PER_SHOW_M:
        st.warning(
            f"⚠ ${per_show_mkt:.1f}M/show is below the ${MIN_MARKETING_PER_SHOW_M:.0f}M/show "
            f"realistic minimum for a show to be marketed viably ({active_count} active shows "
            f"splitting ${ss.get('mkt_budget', 5.0):.1f}M). The math will still run, but consider "
            f"raising marketing or cancelling more shows in Renewal to concentrate spend."
        )

    if ss.cancelled_shows:
        already = [s.name for s in shows if s.id in ss.cancelled_shows]
        st.markdown(
            f'<div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;margin-top:6px;">'
            f'Already cancelled (prior years): {", ".join(already)}</div>', unsafe_allow_html=True)


def _section_sports_rights_bidding(ss, year, net, sec_num):
    """Peacock-only (2026-08-04, see utils/sports_models.py): real 5-7yr
    rights auctions against seeded rival tech/media bidders.

    Rendered BEFORE Greenlighting (2026-08-04, per explicit user feedback
    after using the feature: "is this right before entertainment show
    selection stuff?") — sports rights is a big, multi-year commitment
    students should weigh before building their originals slate around it,
    not an afterthought once the slate is already locked. The bid/auction
    decision itself doesn't need to know this year's originals spend, only
    the retention math does (see _sports_pnl_recap below, which runs after
    Greenlighting once that spend is final)."""
    st.markdown(f'<div class="section-title">{sec_num} · 🏈 Sports Rights</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:14px;color:#e0e2ea;margin-bottom:10px;">'
        'Real multi-year rights deals (5-7 years), auctioned sealed-bid against seeded '
        'tech/media rivals — highest bid wins and pays <i>its own</i> bid, so overpaying is a '
        'real risk. Sports rights are a deliberate <b>loss leader</b>: the rights fee usually '
        'exceeds the direct revenue a package generates on its own. The subscriber spike a '
        'season creates only becomes lasting value if your Peacock originals slate is strong '
        'enough to retain it — otherwise it churns back out once the season ends.</div>',
        unsafe_allow_html=True)

    anchor = LEVEL_START_YEAR["peacock"]
    held   = held_this_year(ss.sports_contracts, year)

    if held:
        st.markdown('<div style="font-size:14px;color:#b0b5c4;margin-bottom:6px;">Currently held:</div>',
                    unsafe_allow_html=True)
        for c in held:
            info       = SPORTS_LEAGUES[c.league]
            years_left = c.end_year - year
            st.markdown(f"""
            <div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;
                 padding:10px 14px;margin-bottom:6px;display:flex;justify-content:space-between;
                 flex-wrap:wrap;gap:10px;">
              <div><b style="color:#e8eaf0;">{c.league}</b>
                <span style="color:#b0b5c4;font-size:13px;"> · {info['tier']} · held through {c.end_year}
                ({years_left} yr{'s' if years_left != 1 else ''} left)</span></div>
              <div style="font-family:DM Mono,monospace;font-size:14px;color:{WARN};">-${c.annual_cost_m:.1f}M/yr</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<div style="font-size:14px;color:#b0b5c4;margin-bottom:10px;">No sports rights currently held.</div>',
                    unsafe_allow_html=True)

    # ── This year's auctions ────────────────────────────────────────────────
    up      = leagues_up_for_bid(year, anchor)
    already = ss.sports_bid_log.get(year, {})
    pending = [lg for lg in up if lg not in already]

    if pending:
        st.markdown(
            f'<div style="font-size:14px;color:#e0e2ea;margin:6px 0 8px;"><b>'
            f'{len(pending)} rights package{"s" if len(pending) != 1 else ""} up for auction this year:'
            f'</b></div>', unsafe_allow_html=True)
        for lg in pending:
            info = SPORTS_LEAGUES[lg]
            _, start, end = cycle_for_year(lg, year, anchor)
            term = end - start + 1
            st.markdown(
                f'<div style="font-size:14px;color:#e0e2ea;margin-bottom:2px;"><b>{lg}</b> '
                f'<span style="color:#b0b5c4;">({info["tier"]} · {term}-yr term, {start}-{end} · '
                f'~${info["base_rights_cost_m"]:.0f}M/yr market range)</span></div>',
                unsafe_allow_html=True)
            st.number_input(f"Your annual bid for {lg} ($M/yr — 0 = don't bid)",
                             min_value=0.0, max_value=300.0, step=1.0, value=0.0,
                             key=f"sports_bid_{year}_{lg}")

        if st.button("📡 Submit Sports Bids", use_container_width=True, key=f"sports_submit_{year}"):
            ss.sports_bid_log.setdefault(year, {})
            for lg in pending:
                bid = float(ss.get(f"sports_bid_{year}_{lg}", 0.0))
                idx, start, end = cycle_for_year(lg, year, anchor)
                rivals = draw_rival_bids(lg, idx)
                result = resolve_auction(bid, rivals)
                ss.sports_bid_log[year][lg] = result
                if result["won_by_team"]:
                    ss.sports_contracts.append(SportsContract(
                        league=lg, start_year=start, end_year=end,
                        annual_cost_m=result["winning_bid_m"],
                    ))
            st.rerun()

    if already:
        st.markdown('<div style="font-size:14px;color:#b0b5c4;margin-top:8px;">Auction results this year:</div>',
                    unsafe_allow_html=True)
        for lg, result in already.items():
            rival_bids = [b for b in result["all_bids"] if b["bidder"] != "You"]
            best_rival = max((b["bid_m"] for b in rival_bids), default=None)
            if result["won_by_team"]:
                rival_note = f" ({len(rival_bids)} rivals bid, best was ${best_rival:.1f}M)" if best_rival else " (no rivals bid)"
                st.markdown(f'<div style="color:{SUCCESS};font-size:14px;">✅ Won <b>{lg}</b> at '
                             f'${result["winning_bid_m"]:.1f}M/yr{rival_note}</div>', unsafe_allow_html=True)
            elif result["winner"]:
                st.markdown(f'<div style="color:{WARN};font-size:14px;">❌ Lost <b>{lg}</b> — '
                             f'{result["winner"]} won at ${result["winning_bid_m"]:.1f}M/yr</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="color:{TEXT2};font-size:14px;">No bidders for <b>{lg}</b> this '
                             f'cycle — it went unclaimed.</div>', unsafe_allow_html=True)

    if not pending and not up:
        st.markdown('<div style="font-size:14px;color:#b0b5c4;">No rights packages up for auction this '
                     'year — check back as existing contracts approach expiration.</div>', unsafe_allow_html=True)


def _sports_pnl_recap(ss, shows, year, net, new_cancel) -> dict:
    """Peacock-only: this year's actual sports-rights P&L, computed AFTER
    Greenlighting (2026-08-04) so retained_fraction() sees this year's
    finalized Peacock originals spend — the bidding decision itself
    (_section_sports_rights_bidding above) happens earlier in the page and
    doesn't need this number, only the retention math does. Renders a
    small recap card when a contract is held, and always returns the P&L
    dict so _decisions() can fold it into the Simulate preview/actual
    computation regardless of whether anything is displayed."""
    if net != "peacock":
        return {"revenue_m": 0.0, "cost_m": 0.0, "net_m": 0.0, "rows": []}

    held = held_this_year(ss.sports_contracts, year)
    peacock_shows_now = [s for s in shows if s.network == "Peacock"]
    originals_spend_m = _annual_cost(peacock_shows_now, year, ss.cancelled_shows, new_cancel)
    year_pnl = sports_year_pnl(held, year, originals_spend_m)

    if held:
        net_c = SUCCESS if year_pnl["net_m"] >= 0 else DANGER
        st.markdown(f"""
        <div style="background:#12141a;border:1px solid #252836;border-radius:6px;
             padding:10px 14px;margin-bottom:14px;font-size:14px;color:#e0e2ea;">
          🏈 This year's sports rights P&L (now that your originals slate is set):
          <b style="font-family:DM Mono,monospace;color:{SUCCESS};">+${year_pnl['revenue_m']:.1f}M</b> revenue
          &minus; <b style="font-family:DM Mono,monospace;color:{WARN};">${year_pnl['cost_m']:.1f}M</b> rights cost
          = <b style="font-family:DM Mono,monospace;color:{net_c};">${year_pnl['net_m']:+.1f}M</b> net
          &mdash; your Peacock originals slate (${originals_spend_m:.1f}M this year) {'covered' if year_pnl['net_m'] >= 0 else 'didn' + chr(39) + 't fully cover'} that gap.
        </div>
        """, unsafe_allow_html=True)

    return year_pnl


def _decisions(ss, shows, net_info, year, net):
    """Single scrolling page (redesigned 2026-07-27, replacing the old
    Back/Next 4-step wizard per user request: "students should have
    prompts that force them to make decisions as they scroll down...
    then click simulate at the bottom"). All four decision sections
    render unconditionally, top to bottom; each is a self-contained
    module (app_pages.renewal/greenlight/schedule) already written to read
    and write st.session_state directly with no cross-module widget key
    collisions, so nothing in those three files needed to change."""
    threshold    = net_info["pass_threshold"]
    level_budget = ss.level_budget

    prev = next((r for r in ss.yearly_log if r["year"] == year - 1), None) if year > 1 else None
    if prev:
        _last_year_recap(prev, threshold)
    elif year == 1:
        _starting_position(net_info, shows, net)

    if len(ss.yearly_log) >= 2:
        _progress_chart(ss, threshold)

    nav_links = [
        '<a href="#financing" style="color:#e8c547;">Financing</a>',
        '<a href="#renewal" style="color:#e8c547;">Renewal</a>',
    ]
    if net == "peacock":
        nav_links.append('<a href="#sports-rights" style="color:#e8c547;">Sports Rights</a>')
    nav_links += [
        '<a href="#greenlighting" style="color:#e8c547;">Greenlighting</a>',
        '<a href="#scheduling" style="color:#e8c547;">Scheduling</a>',
        '<a href="#simulate" style="color:#e8c547;">Simulate</a>',
    ]
    st.markdown(
        '<div style="font-size:14px;color:#b0b5c4;margin-bottom:14px;">'
        'Work through each decision as you scroll, then simulate the year at the bottom. '
        + ' · '.join(nav_links) + '</div>', unsafe_allow_html=True)

    st.markdown('<a id="financing"></a>', unsafe_allow_html=True)
    _section_financing(ss, shows, year, net_info, level_budget)
    # Re-read: an emergency budget shock (see draw_emergency_budget_shock)
    # may have just mutated ss.level_budget inside _section_financing.
    level_budget = ss.level_budget

    st.divider()
    st.markdown('<a id="renewal"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">2 · 🔄 Renewal</div>', unsafe_allow_html=True)
    from app_pages.renewal import render as render_renewal
    render_renewal()

    # Sports Rights (Peacock only) sits BEFORE Greenlighting, per explicit
    # user feedback after using the feature: a multi-year rights commitment
    # is the kind of decision that should shape the entertainment slate
    # built around it, not the other way around. Dynamically numbered so
    # Oxygen/Bravo (which never render this section) don't skip a number.
    next_sec = 3
    if net == "peacock":
        st.divider()
        st.markdown('<a id="sports-rights"></a>', unsafe_allow_html=True)
        _section_sports_rights_bidding(ss, year, net, next_sec)
        next_sec += 1

    st.divider()
    st.markdown('<a id="greenlighting"></a>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="section-title">{next_sec} · 🎬 Greenlighting '
        '<span style="font-size:14px;color:#b0b5c4;">(optional)</span></div>',
        unsafe_allow_html=True)
    next_sec += 1
    from app_pages.greenlight import render as render_greenlight
    render_greenlight()
    # Re-read again: Greenlighting's "Greenlight This Show" button also
    # deducts real production cost from ss.level_budget immediately.
    level_budget = ss.level_budget

    # Read once, now that Renewal/Greenlighting have both rendered and
    # written their widgets to session state.
    mkt = ss.get("mkt_budget", 5.0)
    active_now = _active_shows(shows, ss.cancelled_shows)
    new_cancel = {s.id for s in active_now if ss.renewal_decisions.get(s.id) == "Cancel"}

    # This year's actual sports P&L (Peacock only) — computed now that the
    # originals slate above is final, feeding retained_fraction() the real
    # number rather than a mid-page guess. See _sports_pnl_recap's docstring.
    sports_pnl = _sports_pnl_recap(ss, shows, year, net, new_cancel)

    st.divider()
    st.markdown('<a id="scheduling"></a>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="section-title">{next_sec} · 📅 Scheduling & Cash-Flow Reference '
        '<span style="font-size:14px;color:#b0b5c4;">(reference — the premiere-month and '
        'primetime-slot calls above in Renewal already drive the real math)</span></div>',
        unsafe_allow_html=True)
    from app_pages.schedule import render as render_schedule
    render_schedule()

    st.divider()

    st.markdown('<a id="simulate"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Expected This Year</div>', unsafe_allow_html=True)
    p = _preview_pnl(shows, year, mkt, ss.cancelled_shows, new_cancel,
                     sports_rev_m=sports_pnl["revenue_m"], sports_cost_m=sports_pnl["cost_m"])

    ocf_c    = SUCCESS if p["ocf"] >= 0 else DANGER
    margin_c = SUCCESS if p["margin"] >= threshold else (WARN if p["margin"] >= 0 else DANGER)
    bar_pct  = min(abs(p["margin"]) / max(threshold * 1.5, 1), 1.0) * 100

    items = [
        ("Ad Revenue",    f"${p['ad_rev']:.2f}M",  SUCCESS),
        ("Distribution",  f"${p['dist_rev']:.2f}M", ACCENT2),
        ("Content Cost",  f"-${p['cost'] - p['sports_cost']:.2f}M", WARN),
    ]
    if p["sports_rev"] or p["sports_cost"]:
        items += [
            ("Sports Rights Revenue", f"${p['sports_rev']:.2f}M", ACCENT2),
            ("Sports Rights Cost",    f"-${p['sports_cost']:.2f}M", WARN),
        ]
    items += [
        ("Marketing",     f"-${mkt:.2f}M",           WARN),
        ("G&A (6%)",      f"-${p['ga']:.2f}M",      TEXT2),
    ]
    rows_html = "".join([
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
        f'border-bottom:1px solid rgba(37,40,54,.5);font-size:14px;">'
        f'<span style="color:#e0e2ea;">{lbl}</span>'
        f'<span style="font-family:DM Mono,monospace;color:{clr};">{val}</span></div>'
        for lbl, val, clr in items
    ])

    if new_cancel:
        cancel_names = [s.name for s in shows if s.id in new_cancel]
        penalty = sum(s.annual_amort_expense(year) * 0.25
                      for s in shows if s.id in new_cancel)
        penalty_note = (f'<div style="font-size:14px;color:{WARN};margin-top:6px;'
                        f'font-family:DM Mono,monospace;">⚠ Cancelling this year '
                        f'({", ".join(cancel_names)}): ${penalty:.2f}M sunk-cost penalty</div>')
    else:
        penalty_note = ""

    spend_this_year = p["cost"] + mkt
    if spend_this_year > level_budget:
        over = spend_this_year - level_budget
        budget_note = (f'<div style="font-size:14px;color:{DANGER};margin-top:6px;'
                       f'font-family:DM Mono,monospace;">⚠ ${over:.1f}M over this year\'s '
                       f'${level_budget:.1f}M budget (content + marketing) — cut marketing or '
                       f'cancel more in Renewal.</div>')
    else:
        budget_note = (f'<div style="font-size:14px;color:{TEXT2};margin-top:6px;'
                       f'font-family:DM Mono,monospace;">Budget: ${level_budget:.1f}M · '
                       f'committed ${spend_this_year:.1f}M</div>')

    st.markdown(f"""
    <div style="background:#12141a;border:1px solid #252836;border-radius:8px;padding:14px;">
      {rows_html}
      <div style="margin-top:10px;padding-top:8px;border-top:1px solid #252836;">
        <div style="display:flex;justify-content:space-between;font-size:16px;font-weight:600;">
          <span style="color:#e8eaf0;">Annual OCF</span>
          <span style="font-family:DM Mono,monospace;color:{ocf_c};">${p['ocf']:+.2f}M</span>
        </div>
        <div style="margin-top:8px;">
          <div style="display:flex;justify-content:space-between;font-size:14px;margin-bottom:3px;">
            <span style="color:#b0b5c4;font-family:DM Mono,monospace;">OCF Margin</span>
            <span style="color:{margin_c};font-family:DM Mono,monospace;">
              {p['margin']:.1f}% / {threshold:.0f}% target
            </span>
          </div>
          <div style="height:5px;background:#252836;border-radius:3px;overflow:hidden;">
            <div style="width:{bar_pct}%;height:100%;background:{margin_c};border-radius:3px;"></div>
          </div>
        </div>
      </div>
      {penalty_note}
      {budget_note}
    </div>
    """, unsafe_allow_html=True)

    # ── Active slate summary ──────────────────────────────────────────────────
    with st.expander("📋 View Active Show Slate", expanded=False):
        per = mkt / max(len(_active_shows(shows, ss.cancelled_shows | new_cancel)), 1)
        slate_rows = []
        for s in shows:
            if s.id in ss.cancelled_shows:
                status = "Cancelled"
            elif s.id in new_cancel:
                status = "Cancelling"
            else:
                status = "✅ Active"
            slate_rows.append({
                "Show": s.name, "Network": s.network, "Genre": s.genre,
                "Rating": round(s.rating, 2),
                "Annual Rev $M": round(s.ad_revenue(year, per), 2) if status == "✅ Active" else 0.0,
                "Annual Cost $M": round(s.annual_amort_expense(year), 2) if status not in ("Cancelled",) else 0.0,
                "Status": status,
            })
        df = pd.DataFrame(slate_rows)
        st.dataframe(
            df.style
            .map(lambda v: "color:#66bb6a;" if v == "✅ Active"
                 else ("color:#ef5350;" if "Cancel" in str(v) else "color:#b0b5c4;"),
                 subset=["Status"])
            .format({"Rating": "{:.2f}", "Annual Rev $M": "${:.2f}M", "Annual Cost $M": "${:.2f}M"})
            .set_properties(**{"font-family": "DM Mono,monospace", "font-size": "11px"}),
            use_container_width=True, height=280,
        )

    st.divider()

    # ── Simulate the year ──────────────────────────────────────────────────────
    if st.button(f"▶  Simulate Year {year}  →  See Results",
                 type="primary", use_container_width=True, key="sim_end_year"):
        result           = _compute_year(ss, shows, year, mkt, new_cancel, net,
                                         sports_rev_m=sports_pnl["revenue_m"],
                                         sports_cost_m=sports_pnl["cost_m"])
        result["budget"] = round(level_budget, 2)   # what was available this year, for the Complete-phase chart
        ss.yearly_log.append(result)
        ss.cancelled_shows = ss.cancelled_shows | new_cancel
        # No manual ss.mkt_budget sync needed here (unlike the old per-step
        # wizard): Financing always renders on this page now, so its
        # key="mkt_budget" slider already keeps session state current —
        # reassigning it here would raise StreamlitAPIException ("cannot be
        # modified after the widget... is instantiated").
        # Next year's budget is performance-linked, not a flat 3%/yr —
        # computed from THIS year's actual result, so it's only known
        # once results are in, same as a real budget review would be.
        ss.level_budget    = level_budget * performance_linked_growth(result["margin"], threshold)
        ss.sim_phase       = "results"
        st.rerun()


# ── Results phase ──────────────────────────────────────────────────────────────

def _results(ss, shows, net_info, year, team, net):
    log    = ss.yearly_log
    result = next((r for r in log if r["year"] == year), None)
    if not result:
        ss.sim_phase = "decisions"
        st.rerun()
        return

    threshold = net_info["pass_threshold"]
    ocf_ok    = result["ocf"] >= 0
    ocf_c     = SUCCESS if ocf_ok else DANGER
    margin_c  = SUCCESS if result["margin"] >= threshold else (WARN if ocf_ok else DANGER)

    # ── Result banner ─────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:rgba({'102,187,106' if ocf_ok else '239,83,80'},.07);
         border:1px solid rgba({'102,187,106' if ocf_ok else '239,83,80'},.3);
         border-radius:8px;padding:16px 22px;margin-bottom:18px;">
      <div style="font-family:DM Mono,monospace;font-size:14px;color:#b0b5c4;
           text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;">
        {result['label']} — Actual Results
      </div>
      <div style="display:flex;gap:32px;flex-wrap:wrap;">
        <div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">REVENUE</div>
          <div style="font-size:26px;font-family:DM Serif Display,serif;color:#e8eaf0;">${result['revenue']:.1f}M</div>
        </div>
        <div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">CONTENT COST</div>
          <div style="font-size:26px;font-family:DM Serif Display,serif;color:{WARN};">${result['cost']:.1f}M</div>
        </div>
        <div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">OCF</div>
          <div style="font-size:26px;font-family:DM Serif Display,serif;color:{ocf_c};">${result['ocf']:+.1f}M</div>
        </div>
        <div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">MARGIN</div>
          <div style="font-size:26px;font-family:DM Serif Display,serif;color:{margin_c};">{result['margin']:.1f}%</div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">target {threshold:.0f}%</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Sports rights contribution (Peacock only, held contracts only) ────────
    if result.get("sports_rev") or result.get("sports_cost"):
        sp_net_c = SUCCESS if (result["sports_rev"] - result["sports_cost"]) >= 0 else DANGER
        st.markdown(f"""
        <div style="font-size:14px;color:#b0b5c4;margin:-8px 0 16px;">
          Includes sports rights: <span style="font-family:DM Mono,monospace;color:{SUCCESS};">
          +${result['sports_rev']:.1f}M</span> revenue &minus;
          <span style="font-family:DM Mono,monospace;color:{WARN};">${result['sports_cost']:.1f}M</span> rights cost
          = <span style="font-family:DM Mono,monospace;color:{sp_net_c};">
          ${result['sports_rev'] - result['sports_cost']:+.1f}M</span> net — the rest of this year's
          OCF is what your Peacock originals slate actually earned.
        </div>
        """, unsafe_allow_html=True)

    # ── Rating movers ─────────────────────────────────────────────────────────
    active_rows = [r for r in result["shows"] if r["status"] == "active"]
    if active_rows:
        movers = sorted(active_rows, key=lambda x: abs(x["variance"] - 1.0), reverse=True)[:5]
        st.markdown('<div class="section-title">Rating Movers This Year</div>',
                    unsafe_allow_html=True)
        cols = st.columns(5)
        for i, m in enumerate(movers):
            delta = m["rating_adj"] - m["rating_base"]
            c     = SUCCESS if delta >= 0 else DANGER
            arrow = "▲" if delta >= 0 else "▼"
            cols[i].markdown(f"""
            <div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;
                 padding:10px;text-align:center;">
              <div style="font-size:14px;color:#e0e2ea;font-family:DM Mono,monospace;
                   margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                {m['name'][:15]}
              </div>
              <div style="font-size:18px;font-family:DM Serif Display,serif;color:{c};">
                {arrow} {abs(delta):.2f}
              </div>
              <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;margin-top:2px;">
                {m['rating_base']:.1f} → {m['rating_adj']:.1f}
              </div>
              <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">
                {'+' if delta>=0 else ''}{(m['variance']-1)*100:.1f}%
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Emmy Tracking — a genuinely separate outcome from ratings ────────────
    # Phase 6, 2026-08-05: TV-side parallel to Movies' Oscar-win/nomination
    # banner. Only shows Drama/Scripted/Comedy shows that actually aired
    # this year (see EMMY_ELIGIBLE_GENRES) -- a Reality/Competition/Talk/
    # True Crime show, or one that was cancelled/hit a risk event, never
    # shows up here at all, same real-eligibility-gate posture as the
    # Movies side.
    emmy_rows = [r for r in active_rows if r.get("emmy_score") is not None]
    if emmy_rows:
        st.markdown('<div class="section-title" style="margin-top:14px;">🏆 Emmy Buzz</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;">'
            'Critical reception for this year\'s Drama/Scripted/Comedy shows — independent of ratings, '
            'same as the Movies side\'s critical reception being independent of box office.</div>',
            unsafe_allow_html=True)
        emmy_cols = st.columns(min(len(emmy_rows), 5))
        for i, r in enumerate(sorted(emmy_rows, key=lambda x: x["emmy_score"], reverse=True)[:5]):
            badge = "🏆 WIN" if r["emmy_win"] else ("🎬 NOMINATED" if r["emmy_nomination"] else "—")
            badge_c = ACCENT if r["emmy_win"] else (SUCCESS if r["emmy_nomination"] else TEXT2)
            emmy_cols[i].markdown(f"""
            <div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;
                 padding:10px;text-align:center;">
              <div style="font-size:14px;color:#e0e2ea;font-family:DM Mono,monospace;
                   margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                {r['name'][:15]}
              </div>
              <div style="font-size:18px;font-family:DM Serif Display,serif;color:{badge_c};">
                {r['emmy_score']:.0f}
              </div>
              <div style="font-size:13px;color:{badge_c};font-family:DM Mono,monospace;">
                {badge}
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Cumulative P&L chart ──────────────────────────────────────────────────
    if log:
        st.markdown('<div class="section-title" style="margin-top:18px;">Level P&L — Year by Year</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;">'
            'Green bars = revenue. Red bars = total spend (cost + marketing + G&A). '
            'Gold line = net OCF. A line above zero means you\'re profitable that year.</div>',
            unsafe_allow_html=True)

        ylabels = [r["label"].split(" · ")[0] for r in log]
        cum_ocf = np.cumsum([r["ocf"] for r in log]).tolist()

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Revenue", x=ylabels, y=[r["revenue"] for r in log],
            marker_color=SUCCESS, opacity=0.75,
            text=[f"${r['revenue']:.1f}M" for r in log], textposition="outside",
            textfont=dict(size=10, color="#e0e2ea"),
        ))
        fig.add_trace(go.Bar(
            name="Spend (cost+mkt+G&A)", x=ylabels,
            y=[-(r["cost"] + r["mkt"] + r["ga"]) for r in log],
            marker_color=DANGER, opacity=0.6,
        ))
        fig.add_trace(go.Scatter(
            name="Annual OCF", x=ylabels, y=[r["ocf"] for r in log],
            mode="lines+markers", line=dict(color=ACCENT, width=2.5),
            marker=dict(size=9, color=[SUCCESS if r["ocf"] >= 0 else DANGER for r in log]),
        ))
        fig.add_trace(go.Scatter(
            name="Cumulative OCF", x=ylabels, y=cum_ocf,
            mode="lines+markers", line=dict(color=ACCENT2, width=1.5, dash="dot"),
            marker=dict(size=6), opacity=0.7,
        ))
        fig.add_hline(y=0, line_dash="dash", line_color=WARN, opacity=0.3)
        fig.update_layout(**base_layout("Annual P&L ($M)", height=300), barmode="relative")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Cancelled shows this year ──────────────────────────────────────────
    newly = [r for r in result["shows"] if r["status"] == "cancelled"]
    if newly:
        names = ", ".join(r["name"] for r in newly)
        st.markdown(
            f'<div style="font-size:14px;color:{WARN};font-family:DM Mono,monospace;margin-top:6px;">'
            f'✂ Cancelled this year: {names}</div>', unsafe_allow_html=True)

    # ── Production-risk events — a real, involuntary setback, not a choice ────
    risk_events = [r for r in result["shows"] if r["status"] == "risk_event"]
    if risk_events:
        st.markdown('<div class="section-title" style="margin-top:14px;">🎲 Production Risk</div>',
                    unsafe_allow_html=True)
        for r in risk_events:
            st.markdown(
                f'<div style="background:rgba(239,83,80,.08);border:1px solid rgba(239,83,80,.3);'
                f'border-radius:6px;padding:10px 14px;margin-bottom:6px;font-size:15px;color:#e0e2ea;">'
                f'<b style="color:{DANGER};">{r["name"]}</b> — {r["reason"]}. No revenue this year, '
                f'25% sunk-cost still owed — but it stays on your slate for next year\'s Renewal call.'
                f'</div>', unsafe_allow_html=True)

    st.divider()

    # ── Navigation ────────────────────────────────────────────────────────────
    nav1, nav2 = st.columns([1, 1])
    with nav1:
        if st.button("← Redo This Year", use_container_width=True):
            new_cancel_ids = set(result.get("new_cancellations", []))
            ss.yearly_log      = [r for r in ss.yearly_log if r["year"] != year]
            ss.cancelled_shows = ss.cancelled_shows - new_cancel_ids
            # Undo the performance-linked budget update End Year applied —
            # result["budget"] is what was actually available *this* year,
            # before that update projected next year's figure.
            ss.level_budget    = result["budget"]
            # Undo any shows greenlit during the year being redone — a full
            # retry of the year's decisions, not a partial one. Production
            # cost already spent isn't refunded (see _remove_greenlit_shows'
            # docstring), matching how Research fees already behave.
            this_year_ids = ss.get("greenlit_ids_this_year", set())
            _remove_greenlit_shows(ss, this_year_ids)
            ss.greenlit_ids_this_level = ss.get("greenlit_ids_this_level", set()) - this_year_ids
            ss.total_shows_greenlit    = max(0, ss.get("total_shows_greenlit", 0) - len(this_year_ids))
            ss.greenlit_ids_this_year  = set()
            # Undo any sports rights bids placed during the year being
            # redone — a won contract's start_year always equals the
            # auction year (see utils/sports_models.py::cycle_for_year),
            # so filtering on that is exact, same posture as greenlit-show
            # undo above (bid amounts committed aren't refunded, only the
            # resulting contract/log entry is removed).
            ss.sports_bid_log.pop(year, None)
            ss.sports_contracts = [c for c in ss.sports_contracts if c.start_year != year]
            ss.sim_phase       = "decisions"
            st.rerun()
    with nav2:
        if year < YEARS_PER_LEVEL:
            if st.button(f"→ Start Year {year + 1}", type="primary", use_container_width=True):
                ss.year          = year + 1
                ss.sim_phase     = "decisions"
                ss.greenlit_ids_this_year = set()   # fresh greenlight cap for the new year
                st.rerun()
        else:
            if st.button("→ View Final Results & Submit Score",
                         type="primary", use_container_width=True):
                ss.sim_phase = "complete"
                st.rerun()


# ── Complete phase ─────────────────────────────────────────────────────────────

def _complete(ss, shows, net_info, team, net):
    log = ss.yearly_log
    if not log:
        ss.sim_phase = "decisions"
        ss.year      = 1
        st.rerun()
        return

    year       = ss.year   # final year of the level, used for the closing snapshot
    threshold  = net_info["pass_threshold"]
    total_rev  = sum(r["revenue"] for r in log)
    total_cost = sum(r["cost"]    for r in log)
    total_mkt  = sum(r["mkt"]     for r in log)
    total_ocf  = sum(r["ocf"]     for r in log)
    avg_margin = (total_ocf / total_rev * 100) if total_rev > 0 else 0.0

    # Compute score
    active = _active_shows(shows, ss.cancelled_shows)
    per = (total_mkt / YEARS_PER_LEVEL) / max(len(active), 1)   # avg annual mkt per show
    rois = [s.roi(year, per) for s in active]
    avg_roi = sum(rois) / len(rois) if rois else 0.0
    genre_costs = {}
    for s in active:
        genre_costs[s.genre] = genre_costs.get(s.genre, 0) + s.total_cost(year)
    hhi         = hhi_from_genres(genre_costs)
    renewal_pct = (sum(1 for r in rois if r > 0) / len(rois) * 100) if rois else 0.0
    mkt_eff     = (total_rev / total_mkt) if total_mkt > 0 else 0.0
    score_d     = compute_score_for_network(net, avg_margin, avg_roi, hhi, renewal_pct, mkt_eff)

    attempts      = get_attempt_count(team, net, ss.school, ss.class_section)
    prev_official = get_official_score(team, net, ss.school, ss.class_section)
    already_passed = prev_official and prev_official.get("passed", False)
    can_sub        = attempts < MAX_ATTEMPTS and not already_passed

    ocf_c    = SUCCESS if total_ocf >= 0 else DANGER
    margin_c = SUCCESS if avg_margin >= threshold else (WARN if avg_margin >= 0 else DANGER)
    total_c  = SUCCESS if score_d["total"] >= 70 else (WARN if score_d["total"] >= 50 else DANGER)

    # ── Level summary banner ──────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;
         border-left:4px solid {net_info['color']};
         border-radius:8px;padding:18px 22px;margin-bottom:20px;">
      <div style="font-family:DM Mono,monospace;font-size:14px;color:#b0b5c4;
           text-transform:uppercase;letter-spacing:.1em;margin-bottom:14px;">
        Full Level Results — {net_info['display_name']} · {YEARS_PER_LEVEL} Years
      </div>
      <div style="display:flex;gap:32px;flex-wrap:wrap;">
        <div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">TOTAL REVENUE</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:#e8eaf0;">${total_rev:.1f}M</div>
        </div>
        <div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">TOTAL COST</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:{WARN};">${total_cost:.1f}M</div>
        </div>
        <div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">TOTAL OCF</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:{ocf_c};">${total_ocf:+.1f}M</div>
        </div>
        <div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">AVG MARGIN</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:{margin_c};">{avg_margin:.1f}%</div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">target {threshold:.0f}%</div>
        </div>
        <div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">SCORE</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:{total_c};">{score_d['total']:.0f}</div>
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">/ 100 pts</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Full level chart ───────────────────────────────────────────────────────
    chart_col, score_col = st.columns([3, 2])

    with chart_col:
        st.markdown('<div class="section-title">Level P&L — All Years</div>', unsafe_allow_html=True)
        ylabels = [r["label"].split(" · ")[0] for r in log]
        cum_ocf = np.cumsum([r["ocf"] for r in log]).tolist()
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Revenue", x=ylabels, y=[r["revenue"] for r in log],
                             marker_color=SUCCESS, opacity=0.75))
        fig.add_trace(go.Bar(name="Spend", x=ylabels,
                             y=[-(r["cost"] + r["mkt"] + r["ga"]) for r in log],
                             marker_color=DANGER, opacity=0.6))
        fig.add_trace(go.Scatter(name="Annual OCF", x=ylabels, y=[r["ocf"] for r in log],
                                 mode="lines+markers", line=dict(color=ACCENT, width=2.5),
                                 marker=dict(size=9)))
        fig.add_trace(go.Scatter(name="Cumulative OCF", x=ylabels, y=cum_ocf,
                                 mode="lines+markers", line=dict(color=ACCENT2, width=1.5, dash="dot"),
                                 marker=dict(size=6)))
        fig.add_hline(y=0, line_dash="dash", line_color=WARN, opacity=0.3)
        fig.update_layout(**base_layout("Annual P&L ($M)", height=280), barmode="relative")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with score_col:
        st.markdown('<div class="section-title">Score Breakdown</div>', unsafe_allow_html=True)
        components = [
            ("OCF Margin",      score_d["ocf_margin"],  "35%"),
            ("Portfolio ROI",   score_d["roi"],          "25%"),
            ("Genre Diversity", score_d["diversity"],    "15%"),
            ("Renewal Quality", score_d["renewal"],      "10%"),
            ("Mkt Efficiency",  score_d["marketing"],    "15%"),
        ]
        for label, val, weight in components:
            bar_c = SUCCESS if val >= 70 else (WARN if val >= 40 else DANGER)
            st.markdown(f"""
            <div style="margin-bottom:10px;">
              <div style="display:flex;justify-content:space-between;font-size:14px;margin-bottom:3px;">
                <span style="color:#e0e2ea;">{label} <span style="color:#b0b5c4;">({weight})</span></span>
                <span style="font-family:DM Mono,monospace;color:{bar_c};">{val:.0f}/100</span>
              </div>
              <div style="height:5px;background:#252836;border-radius:3px;overflow:hidden;">
                <div style="width:{val}%;height:100%;background:{bar_c};border-radius:3px;"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        total_c = SUCCESS if score_d["total"] >= 70 else (WARN if score_d["total"] >= 50 else DANGER)
        passed_badge = (f'<span style="background:{SUCCESS};color:#0b0c10;padding:3px 10px;'
                        f'border-radius:3px;font-size:14px;font-family:DM Mono,monospace;">PASSED ✓</span>'
                        if score_d["passed"] else
                        f'<span style="background:{DANGER};color:#fff;padding:3px 10px;'
                        f'border-radius:3px;font-size:14px;font-family:DM Mono,monospace;">NOT PASSED</span>')
        st.markdown(f"""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;
             padding:12px;text-align:center;margin-top:8px;">
          <div style="font-family:DM Serif Display,serif;font-size:34px;color:{total_c};">
            {score_d['total']:.0f}
          </div>
          <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;margin-bottom:8px;">/ 100 points</div>
          {passed_badge}
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Year-over-year performance vs. budget ─────────────────────────────────
    # Budget is performance-linked as of 2026-07-24 (Zach Schlessel feedback:
    # good year = more budget, poor year = a cut) — real mechanic now, not
    # illustrative. r["budget"] on each yearly_log entry is what was actually
    # available that year (utils/models.py::performance_linked_growth()).
    # Plotted against a fixed-3%/yr baseline so the effect of performance is
    # visible, not because the fixed line is real anymore.
    if len(log) > 1:
        st.markdown('<div class="section-title">Year-over-Year: Actual Margin vs. Budget</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;">'
            'Gold bars = your actual OCF margin each year against the pass threshold. '
            'The solid line is the real budget you actually played with — performance-linked, '
            'not a flat raise. The dashed line shows what a flat 3%/yr would have given you instead, '
            'for comparison only.</div>',
            unsafe_allow_html=True)

        base_budget    = net_info["budget_base"]
        real_budget    = [r.get("budget", base_budget) for r in log]
        flat_baseline  = [base_budget * (1.03 ** i) for i in range(len(log))]

        ylabels = [r["label"].split(" · ")[0] for r in log]
        fig_perf = go.Figure()
        fig_perf.add_trace(go.Bar(
            name="OCF Margin", x=ylabels, y=[r["margin"] for r in log],
            marker_color=[SUCCESS if r["margin"] >= threshold else (WARN if r["margin"] >= 0 else DANGER) for r in log],
            opacity=0.7, yaxis="y2",
        ))
        fig_perf.add_trace(go.Scatter(
            name="Actual budget (performance-linked)", x=ylabels, y=[round(v, 1) for v in real_budget],
            mode="lines+markers", line=dict(color=ACCENT, width=2.5), marker=dict(size=8),
        ))
        fig_perf.add_trace(go.Scatter(
            name="Flat 3%/yr baseline (for comparison)", x=ylabels, y=[round(v, 1) for v in flat_baseline],
            mode="lines+markers", line=dict(color=ACCENT2, width=2, dash="dash"), marker=dict(size=8),
        ))
        fig_perf.add_hline(y=threshold, yref="y2", line_dash="dot", line_color=TEXT2, opacity=0.4)
        fig_perf.update_layout(
            **base_layout("Budget ($M) vs. OCF Margin (%)", height=300),
            yaxis2=dict(overlaying="y", side="right", showgrid=False,
                        title="OCF Margin (%)", tickfont=dict(size=10, color=TEXT2)),
        )
        st.plotly_chart(fig_perf, use_container_width=True, config={"displayModeBar": False})
        st.caption("Rule: margin ≥ threshold → +8%/yr, 0–threshold → +3%/yr, negative → −6%/yr. Real mechanic — this is what you actually played with.")

        st.divider()

    # ── Level Notables ──────────────────────────────────────────────────────────
    # Plain-language playthrough summary, shown to the student regardless of
    # submission -- always reflects the live yearly_log, so it stays current
    # through Redo/Restart. Distinct from record_attempt's stored `notables`,
    # which freezes a copy of this at Submit time for the Leaderboard.
    notables = compute_level_notables(log, ss.get("total_shows_greenlit", 0))
    st.markdown('<div class="section-title">🌟 Your Level Notables</div>', unsafe_allow_html=True)

    by = notables["best_year"]
    mi = notables["most_improved"]
    cs = notables["consistency_score"]
    sg = notables["shows_greenlit"]

    by_val = by["label"] if by else "—"
    by_sub = f"{by['margin']:.1f}% margin" if by else "not enough data"
    mi_c   = SUCCESS if (mi or 0) > 0 else (DANGER if (mi or 0) < 0 else TEXT2)
    mi_val = f"{mi:+.1f} pts" if mi is not None else "—"
    cs_c     = SUCCESS if (cs or 0) >= 85 else (WARN if (cs or 0) >= 65 else DANGER)
    cs_val   = f"{cs:.0f}/100" if cs is not None else "—"
    cs_label = ("Rock-solid" if cs >= 85 else "Steady" if cs >= 65 else "Volatile") if cs is not None else "not enough data"
    ew = notables.get("emmy_wins") or 0
    en = notables.get("emmy_nominations") or 0
    emmy_val = f"{ew} win{'s' if ew != 1 else ''}" if ew else (f"{en} nom{'s' if en != 1 else ''}" if en else "—")
    emmy_c   = ACCENT if ew else (SUCCESS if en else TEXT2)
    emmy_sub = f"{en} total nomination{'s' if en != 1 else ''}" if ew and en > ew else "across the level"
    tr       = notables.get("total_revenue")
    tr_val   = f"${tr:,.0f}M" if tr is not None else "—"

    n_cols = st.columns(6)
    cards = [
        ("BEST YEAR",       by_val, SUCCESS, by_sub),
        ("MOST IMPROVED",   mi_val, mi_c,    "margin, first → last year"),
        ("CONSISTENCY",     cs_val, cs_c,    cs_label),
        ("SHOWS GREENLIT",  str(sg), ACCENT, "new titles added this level"),
        ("EMMY RECOGNITION", emmy_val, emmy_c, emmy_sub),
        ("TOTAL REVENUE",   tr_val, ACCENT2, "summed across every year played"),
    ]
    for col, (title, val, color, sub) in zip(n_cols, cards):
        with col:
            st.markdown(f"""
            <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;padding:12px;height:100%;">
              <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;margin-bottom:4px;">{title}</div>
              <div style="font-size:17px;font-family:DM Serif Display,serif;color:{color};">{val}</div>
              <div style="font-size:14px;color:#e0e2ea;">{sub}</div>
            </div>
            """, unsafe_allow_html=True)

    dt = notables["diversity_trend"]
    if dt is not None:
        if dt > 0.02:
            dt_msg = f"Your portfolio concentrated over the level (genre HHI rose {dt:.2f}) — fewer genres carrying the slate by the end."
        elif dt < -0.02:
            dt_msg = f"Your portfolio diversified over the level (genre HHI fell {abs(dt):.2f}) — a broader genre mix by the end."
        else:
            dt_msg = "Your genre mix held roughly steady across the level."
        st.caption(f"📊 {dt_msg}")

    st.divider()

    # ── Submit & navigation ───────────────────────────────────────────────────
    act_col, restart_col = st.columns([2, 1])

    with act_col:
        if already_passed:
            st.success(f"✅ {net_info['display_name']} already passed! Check the Leaderboard tab.")
        elif not can_sub:
            st.warning(f"All {MAX_ATTEMPTS} attempts used for this network.")
        else:
            if attempts > 0:
                st.markdown(
                    f'<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;">'
                    f'⚠ Attempt {attempts + 1} of {MAX_ATTEMPTS}. '
                    f'Your <b>first submission</b> is the official score — retries are practice only.</div>',
                    unsafe_allow_html=True)
            st.markdown('<div class="submit-btn">', unsafe_allow_html=True)
            btn_lbl = "🎯 Submit Official Score" if attempts == 0 else f"🔄 Retry  ({score_d['total']:.0f} pts)"
            if st.button(f"{btn_lbl}", use_container_width=True):
                slate_summary = [
                    {"name": s.name, "genre": s.genre, "network": s.network,
                     "rating": round(s.rating, 2)}
                    for s in active
                ]
                entry = record_attempt(
                    team_name=team, network=net,
                    attempt_num=attempts + 1,
                    score=score_d["total"],
                    passed=score_d["passed"],
                    details=score_d,
                    school=ss.school, class_section=ss.class_section,
                    class_abbrev=ss.get("class_abbrev", ""),
                    slate_summary=slate_summary,
                    notables=compute_level_notables(log, ss.get("total_shows_greenlit", 0)),
                )
                ss.last_score = entry
                ss.submitted  = True
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # Post-submit result
        if ss.get("submitted") and ss.get("last_score"):
            e  = ss.last_score
            ec = SUCCESS if e["passed"] else DANGER
            st.markdown(f"""
            <div style="background:rgba({'102,187,106' if e['passed'] else '239,83,80'},.1);
                 border:1px solid rgba({'102,187,106' if e['passed'] else '239,83,80'},.3);
                 border-radius:8px;padding:12px;margin-top:10px;text-align:center;">
              <div style="font-family:DM Serif Display,serif;font-size:20px;color:{ec};">
                {'✅ PASSED' if e['passed'] else '❌ DID NOT PASS'}
              </div>
              <div style="font-family:DM Mono,monospace;font-size:22px;color:{ec};margin:6px 0;">
                {e['score']:.0f} pts
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Advance to next level
            if net != "peacock":
                next_net = NETWORK_ORDER[NETWORK_ORDER.index(net) + 1]
                next_info = NETWORK_INFO[next_net]
                if e["passed"] or can_advance(team, net, ss.school, ss.class_section):
                    if st.button(f"→ Advance to {next_info['display_name']}",
                                 use_container_width=True):
                        ss.active_network       = next_net
                        ss.submitted            = False
                        ss.sim_phase            = "decisions"
                        ss.yearly_log           = []
                        ss.cancelled_shows      = set()
                        ss.renewal_decisions    = {}
                        ss.research_revealed    = {}
                        ss.emergency_shock_years = set()
                        # Shows greenlit during the level just passed STAY in the
                        # roster (same as any other pre-existing show) — only the
                        # per-level trackers reset fresh for the new level.
                        ss.greenlit_ids_this_year  = set()
                        ss.greenlit_ids_this_level = set()
                        ss.total_shows_greenlit    = 0
                        ss.year                 = 1
                        ss.level_budget         = None   # re-derived from next_net's budget_base
                        st.rerun()

    with restart_col:
        if st.button("↺ Restart This Level", use_container_width=True):
            # Unlike Advance, a full restart also undoes any shows greenlit
            # during this level attempt — they were part of this attempt's
            # decisions, not a permanent fact of the roster yet.
            _remove_greenlit_shows(ss, ss.get("greenlit_ids_this_level", set()))
            ss.sim_phase            = "decisions"
            ss.yearly_log           = []
            ss.cancelled_shows      = set()
            ss.renewal_decisions    = {}
            ss.research_revealed    = {}
            ss.emergency_shock_years = set()
            ss.greenlit_ids_this_year  = set()
            ss.greenlit_ids_this_level = set()
            ss.total_shows_greenlit    = 0
            ss.submitted            = False
            ss.last_score           = None
            ss.year                 = 1
            ss.level_budget         = None   # re-derived from net_info's budget_base
            st.rerun()
