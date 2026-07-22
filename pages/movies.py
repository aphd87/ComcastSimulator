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
    SCENARIO_MULTIPLIERS, CYCLES_TOTAL, risk_adjusted_npv, capital_efficiency,
    strategic_fit_score, compute_movie_score, draw_actual_multiplier, nearest_scenario_label,
    draw_critical_reception, AWARDS_ELIGIBLE_GENRES, AWARDS_CONTENDER_THRESHOLD,
)
from utils.game_state import record_attempt, get_attempt_count, get_official_score, MAX_ATTEMPTS
from utils.charts import base_layout, waterfall_chart, SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2

MOVIE_NETWORK_KEY = "movies"   # leaderboard/attempt-tracking key — same FERPA-safe infra as Day 1
RELEASE_LABELS = {
    "wide_theatrical": "Wide Theatrical",
    "platform":         "Platform / Limited",
    "day_and_date":     "Day-and-Date (Peacock)",
}


# ── Session state init ─────────────────────────────────────────────────────────
def _init(ss):
    if ss.get("movie_cycle") is None:
        ss.movie_cycle = 1
    if ss.get("movie_phase") not in ("greenlight", "release", "results", "complete"):
        ss.movie_phase = "greenlight"
    if not isinstance(ss.get("movie_log"), list):
        ss.movie_log = []          # finished cycles: [{project_kwargs, multiplier, npv, irr, ...}, ...]
    if not isinstance(ss.get("movie_draft"), dict):
        ss.movie_draft = {}        # in-progress project kwargs for the current cycle


# ── Small helpers ────────────────────────────────────────────────────────────
def _fmt_money(v: float) -> str:
    return f"${v:+.1f}M" if v < 0 else f"${v:.1f}M"


def _irr_label(irr) -> str:
    if irr is None:
        return "never recovers capital"
    if irr == float("inf"):
        return "> 500%"
    return f"{irr * 100:.0f}%"


def _current_project(ss) -> MovieProject:
    d = ss.movie_draft
    return MovieProject(
        title=d.get("title", f"Untitled Cycle {ss.movie_cycle} Release"),
        genre=d.get("genre", GENRES[0]),
        budget_m=d.get("budget_m", 60.0),
        pa_spend_m=d.get("pa_spend_m", 40.0),
        star_power=d.get("star_power", 50),
        screens=d.get("screens", 3000),
        cycle=ss.movie_cycle,
        release_strategy=d.get("release_strategy", "wide_theatrical"),
    )


# ── Progress indicator ───────────────────────────────────────────────────────
def _progress_bar(ss):
    steps = ["Greenlight", "Release Strategy", "Results"]
    phase_idx = {"greenlight": 0, "release": 1, "results": 2, "complete": 2}[ss.movie_phase]
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
            f'font-family:DM Mono,monospace;font-size:12px;font-weight:700;color:{clr};">{txt}</div>'
            f'<div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">{label}</div></div>'
        )
    connector = '<div style="width:40px;height:2px;background:#252836;margin-bottom:16px;"></div>'
    cycle_label = f"Cycle {ss.movie_cycle} of {CYCLES_TOTAL}" if ss.movie_phase != "complete" else "Slate Complete"
    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;padding:14px 20px;margin-bottom:18px;">
      <div style="font-family:DM Mono,monospace;font-size:11px;color:#e0e2ea;margin-bottom:10px;">{cycle_label}</div>
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

    if ss.movie_phase == "greenlight":
        _greenlight(ss)
    elif ss.movie_phase == "release":
        _release(ss)
    elif ss.movie_phase == "results":
        _results(ss)
    else:
        _complete(ss)


# ── Phase 1: Greenlight ──────────────────────────────────────────────────────
def _greenlight(ss):
    st.markdown('<div class="section-title">Decision 1 — Greenlight the Concept</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-2">Both budget and P&A spend are cash out today, before any '
        'revenue visibility — unlike Day 1\'s amortized TV cost.</p>', unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    d = ss.movie_draft

    with left:
        title = st.text_input("Working Title", d.get("title", f"Untitled Cycle {ss.movie_cycle} Release"))
        genre = st.selectbox("Genre", GENRES, index=GENRES.index(d.get("genre", GENRES[0])) if d.get("genre") in GENRES else 0,
                              help="Drives international box-office reach and Peacock streaming appeal.")
        c1, c2 = st.columns(2)
        budget = c1.number_input("Production Budget ($M)", 10.0, 300.0, float(d.get("budget_m", 60.0)), step=5.0)
        pa = c2.number_input("P&A / Marketing Spend ($M)", 5.0, 200.0, float(d.get("pa_spend_m", 40.0)), step=5.0,
                              help="Historically rivals or exceeds the production budget for a wide release.")
        c3, c4 = st.columns(2)
        star = c3.slider("Star Power", 0, 100, int(d.get("star_power", 50)),
                          help="Lifts opening awareness, moderately — doesn't compound with P&A.")
        screens = c4.number_input("Planned Opening Screens", 500, 4500, int(d.get("screens", 3000)), step=250)

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
                 release_strategy=d.get("release_strategy", "wide_theatrical"))
    ss.movie_draft = draft
    project = _current_project(ss)

    with right:
        st.markdown('<div class="section-title">Capital at Risk</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="rounded-lg border border-line bg-surface p-4">
          <div class="flex justify-between text-sm py-1"><span class="text-ink2">Production Budget</span>
            <span class="font-mono text-warn">${budget:.1f}M</span></div>
          <div class="flex justify-between text-sm py-1 border-b border-line pb-2"><span class="text-ink2">P&A Spend</span>
            <span class="font-mono text-warn">${pa:.1f}M</span></div>
          <div class="flex justify-between text-base font-semibold pt-2">
            <span class="text-ink">Total Committed</span>
            <span class="font-mono text-danger">${project.capital_at_risk():.1f}M</span></div>
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
    if st.button("▶  Commit Capital  →  Choose Release Strategy", type="primary", use_container_width=True):
        ss.movie_phase = "release"
        st.rerun()


# ── Phase 2: Release Strategy ────────────────────────────────────────────────
def _release(ss):
    project_base = _current_project(ss)

    st.markdown('<div class="section-title">Decision 2 — Release Strategy</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-3">The direct extension of Day 1\'s linear-vs-SVOD Green Light call — '
        'day-and-date trades theatrical box office for immediate, dollarized Peacock subscriber value. '
        'Ground truth: 2021\'s WarnerMedia/HBO Max day-and-date experiment, and Universal\'s post-2020 '
        'shortened theatrical window with AMC.</p>', unsafe_allow_html=True)

    cols = st.columns(3)
    previews = {}
    for i, strat in enumerate(RELEASE_STRATEGIES):
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
            if st.button(f"Choose {RELEASE_LABELS[strat]}", key=f"pick_{strat}", use_container_width=True):
                ss.movie_draft["release_strategy"] = strat
                st.rerun()

    st.divider()
    chosen = ss.movie_draft.get("release_strategy", "wide_theatrical")
    st.markdown(f'<p class="text-sm text-ink2">Currently selected: <b class="text-ink">{RELEASE_LABELS[chosen]}</b></p>',
                unsafe_allow_html=True)

    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button("← Back to Greenlight", use_container_width=True):
            ss.movie_phase = "greenlight"
            st.rerun()
    with nav2:
        if st.button("▶  Lock Strategy  →  See Results", type="primary", use_container_width=True):
            project = _current_project(ss)
            multiplier = draw_actual_multiplier(ss.team_name, ss.movie_cycle, project.genre)
            # Critical reception is drawn independently of box-office
            # performance — a movie can open huge and get panned, or open
            # modestly and find acclaim. Neither draw is known to the
            # student until this exact moment.
            critical_score = draw_critical_reception(ss.team_name, ss.movie_cycle, project.genre)
            awards_eligible = project.genre in AWARDS_ELIGIBLE_GENRES
            outcome = {
                "cycle":            ss.movie_cycle,
                "project_kwargs":   dict(project.__dict__),
                "multiplier":       multiplier,
                "scenario_label":   nearest_scenario_label(multiplier, project.genre),
                "critical_score":   critical_score,
                "awards_contender": awards_eligible and critical_score >= AWARDS_CONTENDER_THRESHOLD,
                "npv":              project.npv(multiplier, critical_score),
                "irr":              project.irr(multiplier, critical_score),
                "total_revenue":    project.total_revenue(multiplier, critical_score),
                "domestic_bo":      project.domestic_box_office(multiplier),
                "theatrical_net":   project.theatrical_studio_net(multiplier),
                "pvod":             project.pvod_revenue(multiplier),
                "sub_value":        project.subscriber_value(multiplier),
                "longtail":         project.library_longtail(multiplier, critical_score),
                "awards_bump":      project.awards_season_bump(multiplier, critical_score),
                "capital_at_risk":  project.capital_at_risk(),
            }
            ss.movie_log = [r for r in ss.movie_log if r["cycle"] != ss.movie_cycle] + [outcome]
            ss.movie_phase = "results"
            st.rerun()


# ── Phase 3: Results ──────────────────────────────────────────────────────────
def _results(ss):
    result = next((r for r in ss.movie_log if r["cycle"] == ss.movie_cycle), None)
    if not result:
        ss.movie_phase = "greenlight"
        st.rerun()
        return

    npv_ok = result["npv"] >= 0
    npv_c = SUCCESS if npv_ok else DANGER
    title = result["project_kwargs"]["title"]
    strat = result["project_kwargs"]["release_strategy"]

    st.markdown(f"""
    <div class="rounded-lg p-5 mb-4" style="background:rgba({'102,187,106' if npv_ok else '239,83,80'},.07);
         border:1px solid rgba({'102,187,106' if npv_ok else '239,83,80'},.3);">
      <div class="font-mono text-[10px] text-muted uppercase tracking-widest mb-3">
        "{title}" — {RELEASE_LABELS[strat]} — Actual Results (landed near your {result['scenario_label'].title()} Case)
      </div>
      <div class="flex gap-8 flex-wrap">
        <div><div class="text-[9px] text-muted font-mono">TOTAL REVENUE</div>
          <div class="text-2xl font-serif text-ink">${result['total_revenue']:.1f}M</div></div>
        <div><div class="text-[9px] text-muted font-mono">CAPITAL AT RISK</div>
          <div class="text-2xl font-serif" style="color:{WARN};">${result['capital_at_risk']:.1f}M</div></div>
        <div><div class="text-[9px] text-muted font-mono">NPV</div>
          <div class="text-2xl font-serif" style="color:{npv_c};">{_fmt_money(result['npv'])}</div></div>
        <div><div class="text-[9px] text-muted font-mono">IRR</div>
          <div class="text-2xl font-serif text-ink">{_irr_label(result['irr'])}</div></div>
      </div>
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
        if result["awards_contender"]:
            awards_note = (f'<div class="text-xs mt-2" style="color:{SUCCESS};">'
                            f'🏆 Awards contender — cleared the {AWARDS_CONTENDER_THRESHOLD:.0f} threshold, '
                            f'triggering a For-Your-Consideration rerelease bump: '
                            f'+${result["awards_bump"]:.2f}M.</div>')
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
    labels.append("Total Revenue")
    vals.append(result["total_revenue"])
    fig = waterfall_chart(labels, vals, title="Revenue by Window ($M)", height=300)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    if ss.movie_log:
        st.markdown('<div class="section-title mt-2">Slate So Far — NPV by Cycle</div>', unsafe_allow_html=True)
        cyc_labels = [f"Cycle {r['cycle']}" for r in sorted(ss.movie_log, key=lambda r: r["cycle"])]
        npvs = [r["npv"] for r in sorted(ss.movie_log, key=lambda r: r["cycle"])]
        fig2 = go.Figure(go.Bar(x=cyc_labels, y=npvs,
                                 marker_color=[SUCCESS if v >= 0 else DANGER for v in npvs]))
        fig2.add_hline(y=0, line_dash="dash", line_color=WARN, opacity=0.4)
        fig2.update_layout(**base_layout("NPV per Cycle ($M)", height=240))
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    st.divider()
    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button("← Redo This Cycle", use_container_width=True):
            ss.movie_log = [r for r in ss.movie_log if r["cycle"] != ss.movie_cycle]
            ss.movie_phase = "greenlight"
            st.rerun()
    with nav2:
        if ss.movie_cycle < CYCLES_TOTAL:
            if st.button(f"→ Start Cycle {ss.movie_cycle + 1}", type="primary", use_container_width=True):
                ss.movie_cycle += 1
                ss.movie_draft = {}
                ss.movie_phase = "greenlight"
                st.rerun()
        else:
            if st.button("→ View Final Slate & Submit Score", type="primary", use_container_width=True):
                ss.movie_phase = "complete"
                st.rerun()


# ── Phase 4: Complete ──────────────────────────────────────────────────────────
def _complete(ss):
    if not ss.movie_log:
        ss.movie_phase = "greenlight"
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
        Full Slate Results — Universal Pictures · {CYCLES_TOTAL} Cycles
      </div>
      <div class="flex gap-8 flex-wrap">
        <div><div class="text-[9px] text-muted font-mono">AVG RISK-ADJ. NPV</div>
          <div class="text-3xl font-serif" style="color:{npv_c};">{_fmt_money(score['avg_ra_npv_m'])}</div></div>
        <div><div class="text-[9px] text-muted font-mono">SCORE</div>
          <div class="text-3xl font-serif" style="color:{total_c};">{score['total']:.0f}</div>
          <div class="text-[9px] text-muted font-mono">/ 100 pts</div></div>
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
            ("Risk-Adj. NPV",     score["risk_adjusted_npv"],  "55%"),
            ("Capital Efficiency", score["capital_efficiency"], "20%"),
            ("Strategic Fit",      score["strategic_fit"],      "25%"),
        ]
        for label, val, weight in components:
            c = SUCCESS if val >= 70 else (WARN if val >= 40 else DANGER)
            st.markdown(f"""
            <div class="mb-3">
              <div class="flex justify-between text-xs mb-1">
                <span class="text-ink2">{label} <span class="text-muted">({weight})</span></span>
                <span class="font-mono" style="color:{c};">{val:.0f}/100</span></div>
              <div class="h-[5px] rounded bg-line overflow-hidden">
                <div class="h-full rounded" style="width:{val}%;background:{c};"></div></div>
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

    st.divider()
    attempts = get_attempt_count(ss.team_name, MOVIE_NETWORK_KEY)
    prev_official = get_official_score(ss.team_name, MOVIE_NETWORK_KEY)
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
                entry = record_attempt(
                    team_name=ss.team_name, network=MOVIE_NETWORK_KEY,
                    attempt_num=attempts + 1, score=score["total"], passed=score["passed"], details=score,
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
            ss.movie_phase = "greenlight"
            ss.movie_log = []
            ss.movie_draft = {}
            ss.movie_submitted = False
            ss.movie_last_score = None
            st.rerun()
