"""
Simulation tab — quarterly turn engine.
Decisions → Results → repeat for 4 quarters, then submit final score.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from utils.models import distribution_revenue, annual_budget
from utils.game_state import (
    NETWORK_INFO, NETWORK_ORDER, compute_score_for_network,
    record_attempt, get_attempt_count, can_advance,
    get_official_score, MAX_ATTEMPTS, hhi_from_genres, SCORE_WEIGHTS,
)
from utils.charts import base_layout, SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2

QUARTER_LABELS  = ["Q1", "Q2", "Q3", "Q4"]
QUARTER_MONTHS  = ["Jan – Mar", "Apr – Jun", "Jul – Sep", "Oct – Dec"]
QUARTERS_PER_LEVEL = 4


# ── Helpers ───────────────────────────────────────────────────────────────────

def _qlabel(q: int, year: int) -> str:
    idx = (q - 1) % 4
    return f"{QUARTER_LABELS[idx]} · {QUARTER_MONTHS[idx]} · {2011 + year}"


def _active_shows(shows, cancelled: set):
    return [s for s in shows if s.id not in cancelled]


def _quarterly_cost(shows, year: int, prev_cancelled: set, new_cancel: set) -> float:
    """Quarterly amort cost. New cancellations pay 50% penalty; prior cancellations cost nothing."""
    total = 0.0
    for s in shows:
        if s.id in prev_cancelled:
            continue
        if s.id in new_cancel:
            total += s.monthly_amort(year) * 3 * 0.5   # one-quarter penalty
        else:
            total += s.monthly_amort(year) * 3          # normal quarterly amort
    return total


def _preview_pnl(shows, year: int, quarterly_mkt: float,
                 prev_cancelled: set, new_cancel: set) -> dict:
    """Expected (no-variance) P&L for the live preview card."""
    cancelled = prev_cancelled | new_cancel
    active    = _active_shows(shows, cancelled)
    ann_mkt   = quarterly_mkt * 4
    per       = ann_mkt / max(len(active), 1)

    ad_rev   = sum(s.ad_revenue(year, per) / 4 for s in active)
    dist_rev = distribution_revenue(year) / 4
    rev      = ad_rev + dist_rev
    cost     = _quarterly_cost(shows, year, prev_cancelled, new_cancel)
    ga       = rev * 0.06
    ocf      = rev - cost - quarterly_mkt - ga
    margin   = (ocf / rev * 100) if rev > 0 else 0.0
    return {"rev": rev, "ad_rev": ad_rev, "dist_rev": dist_rev,
            "cost": cost, "ga": ga, "ocf": ocf, "margin": margin}


def _compute_quarter(ss, shows, year: int, quarterly_mkt: float,
                     q: int, new_cancel: set) -> dict:
    """Apply seeded ±7% rating variance and compute the quarter's actual P&L."""
    seed = (abs(hash(ss.team_name)) + q * 1337 + year * 100) % (2 ** 31)
    rng  = np.random.default_rng(seed)

    prev_cancelled = ss.cancelled_shows
    cancelled_all  = prev_cancelled | new_cancel
    active         = _active_shows(shows, cancelled_all)
    ann_mkt        = quarterly_mkt * 4
    per            = ann_mkt / max(len(active), 1)

    show_rows  = []
    adj_ad_rev = 0.0

    for s in shows:
        v = float(rng.uniform(0.93, 1.08))   # always consume an RNG value for reproducibility
        if s.id in prev_cancelled:
            show_rows.append({"id": s.id, "name": s.name, "network": s.network,
                               "status": "prev_cancelled",
                               "rating_base": s.rating, "rating_adj": 0.0,
                               "variance": round(v, 3), "revenue": 0.0, "cost": 0.0})
        elif s.id in new_cancel:
            show_rows.append({"id": s.id, "name": s.name, "network": s.network,
                               "status": "cancelled",
                               "rating_base": s.rating, "rating_adj": 0.0,
                               "variance": round(v, 3), "revenue": 0.0,
                               "cost": round(s.monthly_amort(year) * 3 * 0.5, 2)})
        else:
            rev = (s.ad_revenue(year, per) / 4) * v
            adj_ad_rev += rev
            show_rows.append({"id": s.id, "name": s.name, "network": s.network,
                               "status": "active",
                               "rating_base": s.rating,
                               "rating_adj": round(s.rating * v, 2),
                               "variance": round(v, 3),
                               "revenue": round(rev, 2),
                               "cost": round(s.monthly_amort(year) * 3, 2)})

    dist_rev   = distribution_revenue(year) / 4
    total_rev  = adj_ad_rev + dist_rev
    total_cost = sum(r["cost"] for r in show_rows)
    ga         = total_rev * 0.06
    ocf        = total_rev - total_cost - quarterly_mkt - ga
    margin     = (ocf / total_rev * 100) if total_rev > 0 else 0.0

    return {
        "quarter": q,
        "label":   _qlabel(q, year),
        "revenue": round(total_rev, 2),
        "ad_rev":  round(adj_ad_rev, 2),
        "dist_rev":round(dist_rev, 2),
        "cost":    round(total_cost, 2),
        "mkt":     round(quarterly_mkt, 2),
        "ga":      round(ga, 2),
        "ocf":     round(ocf, 2),
        "margin":  round(margin, 1),
        "new_cancellations": list(new_cancel),
        "shows":   show_rows,
    }


# ── Session state init ─────────────────────────────────────────────────────────

def _init(ss):
    if not isinstance(ss.get("monthly_log"), list):
        ss.monthly_log = []
    if not isinstance(ss.get("cancelled_shows"), set):
        ss.cancelled_shows = set(ss.get("cancelled_shows") or [])
    if ss.get("sim_month") is None:
        ss.sim_month = 1
    if ss.get("sim_phase") not in ("decisions", "results", "complete"):
        ss.sim_phase = "decisions"


# ── Progress bar ───────────────────────────────────────────────────────────────

def _progress_bar(ss, net_info, q, phase, year):
    dot_items = []
    for i in range(1, QUARTERS_PER_LEVEL + 1):
        done    = any(r["quarter"] == i for r in ss.monthly_log)
        current = (i == q) and phase != "complete"
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
            f'font-family:DM Mono,monospace;font-size:12px;font-weight:700;color:{clr};">{txt}</div>'
            f'<div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;margin-top:2px;">'
            f'{QUARTER_LABELS[i-1]}</div>'
            f'</div>'
        )
    connector   = '<div style="width:44px;height:2px;background:#252836;margin-bottom:16px;"></div>'
    phase_label = {"decisions": "▶ Decision Phase",
                   "results":   "📊 Quarter Results",
                   "complete":  "✅ Season Complete"}[phase]
    q_label = _qlabel(q, year) if phase != "complete" else f"Year {year} — Season Complete"

    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;
         padding:14px 20px;margin-bottom:18px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <div style="font-family:DM Mono,monospace;font-size:11px;color:#e0e2ea;">{q_label}</div>
        <div style="font-family:DM Mono,monospace;font-size:10px;color:{net_info['color']};
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
    _init(ss)

    net      = ss.active_network
    net_info = NETWORK_INFO[net]
    team     = ss.team_name
    year     = ss.get("year", 1)

    shows = ss.oxygen_shows[:]
    if net in ("bravo", "peacock"):
        shows += ss.bravo_shows
    if net == "peacock":
        shows += ss.get("peacock_shows", [])

    q     = ss.sim_month
    phase = ss.sim_phase

    _progress_bar(ss, net_info, q, phase, year)

    if phase == "decisions":
        _decisions(ss, shows, net_info, year, q)
    elif phase == "results":
        _results(ss, shows, net_info, year, q, team, net)
    else:
        _complete(ss, shows, net_info, year, team, net)


# ── Decisions phase ────────────────────────────────────────────────────────────

def _decisions(ss, shows, net_info, year, q):
    threshold = net_info["pass_threshold"]

    left, right = st.columns([3, 2])

    with left:
        # ── Marketing spend ───────────────────────────────────────────────────
        st.markdown('<div class="section-title">Decision 1 — Quarterly Marketing Spend</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11px;color:#e0e2ea;margin-bottom:10px;">'
            'Higher spend lifts ratings and ad revenue. Each $1M quarterly ≈ +1.5% ad rev lift. '
            'Diminishing returns above $4M.</div>', unsafe_allow_html=True)

        default_mkt = ss.get("mkt_budget", 5.0) / 4
        mkt = st.slider("Marketing ($M this quarter)", 0.0, 6.0,
                         float(round(default_mkt, 2)), step=0.25, key=f"dec_mkt_{q}")

        st.divider()

        # ── Cancel shows ──────────────────────────────────────────────────────
        st.markdown('<div class="section-title">Decision 2 — Cancel Shows (optional)</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11px;color:#e0e2ea;margin-bottom:10px;">'
            'Cancelling stops all future amort cost but incurs a 50% one-quarter penalty now. '
            'Target shows with negative OCF — they are destroying value every quarter.</div>',
            unsafe_allow_html=True)

        active = _active_shows(shows, ss.cancelled_shows)
        ann_mkt = mkt * 4
        per_preview = ann_mkt / max(len(active), 1)

        rows_sorted = sorted(
            [(s.name, round(s.ocf(year, per_preview), 2), s.id) for s in active],
            key=lambda x: x[1]   # lowest OCF first
        )
        options     = [f"{n}  (OCF ${o:+.2f}M/yr)" for n, o, _ in rows_sorted]
        id_by_label = {f"{n}  (OCF ${o:+.2f}M/yr)": sid for n, o, sid in rows_sorted}

        selected = st.multiselect(
            "Shows to cancel this quarter",
            options=options,
            default=[],
            key=f"cancel_{q}",
            help="Sorted lowest OCF first. Cancellations are permanent.",
        )
        new_cancel = {id_by_label[l] for l in selected}

        if ss.cancelled_shows:
            already = [s.name for s in shows if s.id in ss.cancelled_shows]
            st.markdown(
                f'<div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;margin-top:6px;">'
                f'Already cancelled: {", ".join(already)}</div>', unsafe_allow_html=True)

    with right:
        # ── Live P&L preview ──────────────────────────────────────────────────
        st.markdown('<div class="section-title">Expected This Quarter</div>', unsafe_allow_html=True)
        p = _preview_pnl(shows, year, mkt, ss.cancelled_shows, new_cancel)

        ocf_c    = SUCCESS if p["ocf"] >= 0 else DANGER
        margin_c = SUCCESS if p["margin"] >= threshold else (WARN if p["margin"] >= 0 else DANGER)
        bar_pct  = min(abs(p["margin"]) / max(threshold * 1.5, 1), 1.0) * 100

        items = [
            ("Ad Revenue",    f"${p['ad_rev']:.2f}M",  SUCCESS),
            ("Distribution",  f"${p['dist_rev']:.2f}M", ACCENT2),
            ("Content Cost",  f"-${p['cost']:.2f}M",   WARN),
            ("Marketing",     f"-${mkt:.2f}M",           WARN),
            ("G&A (6%)",      f"-${p['ga']:.2f}M",      TEXT2),
        ]
        rows_html = "".join([
            f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
            f'border-bottom:1px solid rgba(37,40,54,.5);font-size:11px;">'
            f'<span style="color:#e0e2ea;">{lbl}</span>'
            f'<span style="font-family:DM Mono,monospace;color:{clr};">{val}</span></div>'
            for lbl, val, clr in items
        ])

        if new_cancel:
            penalty = sum(s.monthly_amort(year) * 3 * 0.5
                          for s in shows if s.id in new_cancel)
            penalty_note = (f'<div style="font-size:10px;color:{WARN};margin-top:6px;'
                            f'font-family:DM Mono,monospace;">⚠ Cancel penalty this quarter: '
                            f'${penalty:.2f}M</div>')
        else:
            penalty_note = ""

        st.markdown(f"""
        <div style="background:#12141a;border:1px solid #252836;border-radius:8px;padding:14px;">
          {rows_html}
          <div style="margin-top:10px;padding-top:8px;border-top:1px solid #252836;">
            <div style="display:flex;justify-content:space-between;font-size:14px;font-weight:600;">
              <span style="color:#e8eaf0;">Quarterly OCF</span>
              <span style="font-family:DM Mono,monospace;color:{ocf_c};">${p['ocf']:+.2f}M</span>
            </div>
            <div style="margin-top:8px;">
              <div style="display:flex;justify-content:space-between;font-size:10px;margin-bottom:3px;">
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
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Active slate summary ──────────────────────────────────────────────────
    with st.expander("📋 View Active Show Slate", expanded=False):
        ann_mkt = mkt * 4
        per = ann_mkt / max(len(_active_shows(shows, ss.cancelled_shows | new_cancel)), 1)
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
                "Qtr Rev $M": round(s.ad_revenue(year, per) / 4, 2) if status == "✅ Active" else 0.0,
                "Qtr Cost $M": round(s.monthly_amort(year) * 3, 2) if status not in ("Cancelled",) else 0.0,
                "Status": status,
            })
        df = pd.DataFrame(slate_rows)
        st.dataframe(
            df.style
            .map(lambda v: "color:#66bb6a;" if v == "✅ Active"
                 else ("color:#ef5350;" if "Cancel" in str(v) else "color:#b0b5c4;"),
                 subset=["Status"])
            .format({"Rating": "{:.2f}", "Qtr Rev $M": "${:.2f}M", "Qtr Cost $M": "${:.2f}M"})
            .set_properties(**{"font-family": "DM Mono,monospace", "font-size": "11px"}),
            use_container_width=True, height=280,
        )

    st.divider()

    # ── End quarter button ────────────────────────────────────────────────────
    btn_col, _ = st.columns([1, 2])
    with btn_col:
        if st.button(f"▶  End {QUARTER_LABELS[(q-1)%4]}  →  See Results",
                     type="primary", use_container_width=True):
            result = _compute_quarter(ss, shows, year, mkt, q, new_cancel)
            ss.monthly_log.append(result)
            ss.cancelled_shows = ss.cancelled_shows | new_cancel
            ss.mkt_budget      = mkt * 4     # sync annual equivalent to sidebar
            ss.sim_phase       = "results"
            st.rerun()


# ── Results phase ──────────────────────────────────────────────────────────────

def _results(ss, shows, net_info, year, q, team, net):
    log    = ss.monthly_log
    result = next((r for r in log if r["quarter"] == q), None)
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
      <div style="font-family:DM Mono,monospace;font-size:10px;color:#b0b5c4;
           text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;">
        {result['label']} — Actual Results
      </div>
      <div style="display:flex;gap:32px;flex-wrap:wrap;">
        <div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">REVENUE</div>
          <div style="font-size:26px;font-family:DM Serif Display,serif;color:#e8eaf0;">${result['revenue']:.1f}M</div>
        </div>
        <div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">CONTENT COST</div>
          <div style="font-size:26px;font-family:DM Serif Display,serif;color:{WARN};">${result['cost']:.1f}M</div>
        </div>
        <div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">OCF</div>
          <div style="font-size:26px;font-family:DM Serif Display,serif;color:{ocf_c};">${result['ocf']:+.1f}M</div>
        </div>
        <div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">MARGIN</div>
          <div style="font-size:26px;font-family:DM Serif Display,serif;color:{margin_c};">{result['margin']:.1f}%</div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">target {threshold:.0f}%</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Rating movers ─────────────────────────────────────────────────────────
    active_rows = [r for r in result["shows"] if r["status"] == "active"]
    if active_rows:
        movers = sorted(active_rows, key=lambda x: abs(x["variance"] - 1.0), reverse=True)[:5]
        st.markdown('<div class="section-title">Rating Movers This Quarter</div>',
                    unsafe_allow_html=True)
        cols = st.columns(5)
        for i, m in enumerate(movers):
            delta = m["rating_adj"] - m["rating_base"]
            c     = SUCCESS if delta >= 0 else DANGER
            arrow = "▲" if delta >= 0 else "▼"
            cols[i].markdown(f"""
            <div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;
                 padding:10px;text-align:center;">
              <div style="font-size:10px;color:#e0e2ea;font-family:DM Mono,monospace;
                   margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                {m['name'][:15]}
              </div>
              <div style="font-size:18px;font-family:DM Serif Display,serif;color:{c};">
                {arrow} {abs(delta):.2f}
              </div>
              <div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;margin-top:2px;">
                {m['rating_base']:.1f} → {m['rating_adj']:.1f}
              </div>
              <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">
                {'+' if delta>=0 else ''}{(m['variance']-1)*100:.1f}%
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Cumulative P&L chart ──────────────────────────────────────────────────
    if log:
        st.markdown('<div class="section-title" style="margin-top:18px;">Season P&L — Quarter by Quarter</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11px;color:#e0e2ea;margin-bottom:8px;">'
            'Green bars = revenue. Red bars = total spend (cost + marketing + G&A). '
            'Gold line = net OCF. A line above zero means you\'re profitable that quarter.</div>',
            unsafe_allow_html=True)

        qlabels = [r["label"].split(" · ")[0] for r in log]
        cum_ocf = np.cumsum([r["ocf"] for r in log]).tolist()

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Revenue", x=qlabels, y=[r["revenue"] for r in log],
            marker_color=SUCCESS, opacity=0.75,
            text=[f"${r['revenue']:.1f}M" for r in log], textposition="outside",
            textfont=dict(size=10, color="#e0e2ea"),
        ))
        fig.add_trace(go.Bar(
            name="Spend (cost+mkt+G&A)", x=qlabels,
            y=[-(r["cost"] + r["mkt"] + r["ga"]) for r in log],
            marker_color=DANGER, opacity=0.6,
        ))
        fig.add_trace(go.Scatter(
            name="Quarterly OCF", x=qlabels, y=[r["ocf"] for r in log],
            mode="lines+markers", line=dict(color=ACCENT, width=2.5),
            marker=dict(size=9, color=[SUCCESS if r["ocf"] >= 0 else DANGER for r in log]),
        ))
        fig.add_trace(go.Scatter(
            name="Cumulative OCF", x=qlabels, y=cum_ocf,
            mode="lines+markers", line=dict(color=ACCENT2, width=1.5, dash="dot"),
            marker=dict(size=6), opacity=0.7,
        ))
        fig.add_hline(y=0, line_dash="dash", line_color=WARN, opacity=0.3)
        fig.update_layout(**base_layout("Quarterly P&L ($M)", height=300), barmode="relative")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Cancelled shows this quarter ──────────────────────────────────────────
    newly = [r for r in result["shows"] if r["status"] == "cancelled"]
    if newly:
        names = ", ".join(r["name"] for r in newly)
        st.markdown(
            f'<div style="font-size:11px;color:{WARN};font-family:DM Mono,monospace;margin-top:6px;">'
            f'✂ Cancelled this quarter: {names}</div>', unsafe_allow_html=True)

    st.divider()

    # ── Navigation ────────────────────────────────────────────────────────────
    nav1, nav2 = st.columns([1, 1])
    with nav1:
        if st.button("← Redo This Quarter", use_container_width=True):
            new_cancel_ids = set(result.get("new_cancellations", []))
            ss.monthly_log   = [r for r in ss.monthly_log if r["quarter"] != q]
            ss.cancelled_shows = ss.cancelled_shows - new_cancel_ids
            ss.sim_phase     = "decisions"
            st.rerun()
    with nav2:
        if q < QUARTERS_PER_LEVEL:
            next_qlabel = QUARTER_LABELS[q % 4]
            if st.button(f"→ Start {next_qlabel}", type="primary", use_container_width=True):
                ss.sim_month = q + 1
                ss.sim_phase = "decisions"
                st.rerun()
        else:
            if st.button("→ View Final Results & Submit Score",
                         type="primary", use_container_width=True):
                ss.sim_phase = "complete"
                st.rerun()


# ── Complete phase ─────────────────────────────────────────────────────────────

def _complete(ss, shows, net_info, year, team, net):
    log = ss.monthly_log
    if not log:
        ss.sim_phase = "decisions"
        ss.sim_month = 1
        st.rerun()
        return

    threshold  = net_info["pass_threshold"]
    total_rev  = sum(r["revenue"] for r in log)
    total_cost = sum(r["cost"]    for r in log)
    total_mkt  = sum(r["mkt"]     for r in log)
    total_ocf  = sum(r["ocf"]     for r in log)
    avg_margin = (total_ocf / total_rev * 100) if total_rev > 0 else 0.0

    # Compute score
    active = _active_shows(shows, ss.cancelled_shows)
    ann_mkt = total_mkt   # total mkt over the year ~ annual
    per = ann_mkt / max(len(active), 1)
    rois = [s.roi(year, per) for s in active]
    avg_roi = sum(rois) / len(rois) if rois else 0.0
    genre_costs = {}
    for s in active:
        genre_costs[s.genre] = genre_costs.get(s.genre, 0) + s.total_cost(year)
    hhi         = hhi_from_genres(genre_costs)
    renewal_pct = (sum(1 for r in rois if r > 0) / len(rois) * 100) if rois else 0.0
    mkt_eff     = (total_rev / total_mkt) if total_mkt > 0 else 0.0
    score_d     = compute_score_for_network(net, avg_margin, avg_roi, hhi, renewal_pct, mkt_eff)

    attempts      = get_attempt_count(team, net)
    prev_official = get_official_score(team, net)
    already_passed = prev_official and prev_official.get("passed", False)
    can_sub        = attempts < MAX_ATTEMPTS and not already_passed

    ocf_c    = SUCCESS if total_ocf >= 0 else DANGER
    margin_c = SUCCESS if avg_margin >= threshold else (WARN if avg_margin >= 0 else DANGER)
    total_c  = SUCCESS if score_d["total"] >= 70 else (WARN if score_d["total"] >= 50 else DANGER)

    # ── Season summary banner ─────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;
         border-left:4px solid {net_info['color']};
         border-radius:8px;padding:18px 22px;margin-bottom:20px;">
      <div style="font-family:DM Mono,monospace;font-size:10px;color:#b0b5c4;
           text-transform:uppercase;letter-spacing:.1em;margin-bottom:14px;">
        Full Season Results — {net_info['display_name']} · Year {year}
      </div>
      <div style="display:flex;gap:32px;flex-wrap:wrap;">
        <div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">TOTAL REVENUE</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:#e8eaf0;">${total_rev:.1f}M</div>
        </div>
        <div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">TOTAL COST</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:{WARN};">${total_cost:.1f}M</div>
        </div>
        <div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">TOTAL OCF</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:{ocf_c};">${total_ocf:+.1f}M</div>
        </div>
        <div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">AVG MARGIN</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:{margin_c};">{avg_margin:.1f}%</div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">target {threshold:.0f}%</div>
        </div>
        <div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">SCORE</div>
          <div style="font-size:28px;font-family:DM Serif Display,serif;color:{total_c};">{score_d['total']:.0f}</div>
          <div style="font-size:9px;color:#b0b5c4;font-family:DM Mono,monospace;">/ 100 pts</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Full season chart ─────────────────────────────────────────────────────
    chart_col, score_col = st.columns([3, 2])

    with chart_col:
        st.markdown('<div class="section-title">Season P&L — All Quarters</div>', unsafe_allow_html=True)
        qlabels = [r["label"].split(" · ")[0] for r in log]
        cum_ocf = np.cumsum([r["ocf"] for r in log]).tolist()
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Revenue", x=qlabels, y=[r["revenue"] for r in log],
                             marker_color=SUCCESS, opacity=0.75))
        fig.add_trace(go.Bar(name="Spend", x=qlabels,
                             y=[-(r["cost"] + r["mkt"] + r["ga"]) for r in log],
                             marker_color=DANGER, opacity=0.6))
        fig.add_trace(go.Scatter(name="Quarterly OCF", x=qlabels, y=[r["ocf"] for r in log],
                                 mode="lines+markers", line=dict(color=ACCENT, width=2.5),
                                 marker=dict(size=9)))
        fig.add_trace(go.Scatter(name="Cumulative OCF", x=qlabels, y=cum_ocf,
                                 mode="lines+markers", line=dict(color=ACCENT2, width=1.5, dash="dot"),
                                 marker=dict(size=6)))
        fig.add_hline(y=0, line_dash="dash", line_color=WARN, opacity=0.3)
        fig.update_layout(**base_layout("Quarterly P&L ($M)", height=280), barmode="relative")
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
              <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">
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
                        f'border-radius:3px;font-size:11px;font-family:DM Mono,monospace;">PASSED ✓</span>'
                        if score_d["passed"] else
                        f'<span style="background:{DANGER};color:#fff;padding:3px 10px;'
                        f'border-radius:3px;font-size:11px;font-family:DM Mono,monospace;">NOT PASSED</span>')
        st.markdown(f"""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;
             padding:12px;text-align:center;margin-top:8px;">
          <div style="font-family:DM Serif Display,serif;font-size:34px;color:{total_c};">
            {score_d['total']:.0f}
          </div>
          <div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;margin-bottom:8px;">/ 100 points</div>
          {passed_badge}
        </div>
        """, unsafe_allow_html=True)

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
                    f'<div style="font-size:11px;color:#e0e2ea;margin-bottom:8px;">'
                    f'⚠ Attempt {attempts + 1} of {MAX_ATTEMPTS}. '
                    f'Your <b>first submission</b> is the official score — retries are practice only.</div>',
                    unsafe_allow_html=True)
            st.markdown('<div class="submit-btn">', unsafe_allow_html=True)
            btn_lbl = "🎯 Submit Official Score" if attempts == 0 else f"🔄 Retry  ({score_d['total']:.0f} pts)"
            if st.button(f"{btn_lbl}", use_container_width=True):
                entry = record_attempt(
                    team_name=team, network=net,
                    attempt_num=attempts + 1,
                    score=score_d["total"],
                    passed=score_d["passed"],
                    details=score_d,
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
                if e["passed"] or can_advance(team, net):
                    if st.button(f"→ Advance to {next_info['display_name']}",
                                 use_container_width=True):
                        ss.active_network  = next_net
                        ss.submitted       = False
                        ss.sim_month       = 1
                        ss.sim_phase       = "decisions"
                        ss.monthly_log     = []
                        ss.cancelled_shows = set()
                        ss.year            = 1
                        st.rerun()

    with restart_col:
        if st.button("↺ Restart This Level", use_container_width=True):
            ss.sim_month       = 1
            ss.sim_phase       = "decisions"
            ss.monthly_log     = []
            ss.cancelled_shows = set()
            ss.submitted       = False
            ss.last_score      = None
            st.rerun()
