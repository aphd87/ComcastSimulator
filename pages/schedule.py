"""
Tab 2 — Schedule & Amortization
Premiere-day cash trough, monthly amortization grid, scheduling optimizer.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from utils.models import (
    distribution_revenue, portfolio_ad_rev, AMORT_MONTHS_LINEAR,
    MONTHS, HOUR_LABELS, HOURLY_INDEX
)
from utils.charts import (
    base_layout, bar_chart, line_chart,
    ACCENT, ACCENT2, SUCCESS, DANGER, WARN, TEXT2, BORDER, SURFACE, SURFACE2
)


def render():
    ss   = st.session_state
    year = ss.get("year", 1)
    mkt  = ss.get("mkt_budget", 5.0)

    shows = ss.bravo_shows[:]
    if year >= 5:
        shows += ss.oxygen_shows

    # ── Section 1: Premiere Day Risk ─────────────────────────────────────────
    st.markdown('<div class="section-title">Premiere Day Cash Trough — The March Problem</div>', unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #e8c547;
         border-radius:6px;padding:12px 16px;margin-bottom:12px;font-size:12px;color:#8b90a0;">
    💡 <b style="color:#e8eaf0;">Key insight:</b> You pay 1/12 of a show's total annual cost on the 1st of each month the show is on air — 
    regardless of when in the month it premieres. A March 30 launch means you absorb a full monthly 
    amortization payment with only 2 days of ad revenue. Your cash cows must fund this gap.
    </div>
    """, unsafe_allow_html=True)

    # Student inputs
    with st.expander("🎛️ Configure Premiere Day Scenario", expanded=True):
        c1,c2,c3,c4 = st.columns(4)
        pd_show_name = c1.selectbox("Show", [s.name for s in shows[:10]])
        pd_launch    = c2.radio("Launch Day", [1, 15, 30], horizontal=True,
                                help="Day of month the show premieres")
        pd_eps       = c3.number_input("Episode Count", 6, 24, 10)
        pd_cost_k    = c4.number_input("Cost/Episode ($K)", 100, 3000, 750, step=50)

    total_season_cost = pd_eps * pd_cost_k / 1000     # $M
    monthly_amort     = total_season_cost / 12         # $M per month
    days_in_month     = 31
    revenue_days      = days_in_month - pd_launch + 1
    daily_ad_rev      = (portfolio_ad_rev(shows, year, mkt) / len(shows)) / 365
    month_rev         = daily_ad_rev * revenue_days
    net_position      = month_rev - monthly_amort

    # Three-column comparison
    c1,c2,c3 = st.columns(3)

    with c1:
        st.markdown(f"""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;padding:16px;">
          <div style="font-family:'DM Mono',monospace;font-size:10px;color:#555a6e;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;">Day {pd_launch} Launch</div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px;">
            <span style="color:#8b90a0;">Monthly amort bill</span>
            <span style="font-family:'DM Mono',monospace;color:#ffa726;">${monthly_amort:.3f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px;">
            <span style="color:#8b90a0;">Revenue days in month</span>
            <span style="font-family:'DM Mono',monospace;{'color:#66bb6a' if revenue_days > 15 else 'color:#ef5350'};">{revenue_days}</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px;">
            <span style="color:#8b90a0;">Ad revenue earned</span>
            <span style="font-family:'DM Mono',monospace;color:#66bb6a;">${month_rev:.3f}M</span>
          </div>
          <div style="border-top:1px solid #252836;margin-top:10px;padding-top:10px;display:flex;justify-content:space-between;font-size:14px;font-weight:600;">
            <span>Net Position</span>
            <span style="font-family:'DM Mono',monospace;color:{'#66bb6a' if net_position >= 0 else '#ef5350'};">{'+'if net_position>=0 else ''}{net_position:.3f}M</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        # Day 1 baseline for comparison
        mar1_rev = daily_ad_rev * 31
        mar1_net = mar1_rev - monthly_amort
        st.markdown(f"""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;padding:16px;">
          <div style="font-family:'DM Mono',monospace;font-size:10px;color:#555a6e;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;">Day 1 Baseline</div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px;">
            <span style="color:#8b90a0;">Monthly amort bill</span>
            <span style="font-family:'DM Mono',monospace;color:#ffa726;">${monthly_amort:.3f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px;">
            <span style="color:#8b90a0;">Revenue days in month</span>
            <span style="font-family:'DM Mono',monospace;color:#66bb6a;">31</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px;">
            <span style="color:#8b90a0;">Ad revenue earned</span>
            <span style="font-family:'DM Mono',monospace;color:#66bb6a;">${mar1_rev:.3f}M</span>
          </div>
          <div style="border-top:1px solid #252836;margin-top:10px;padding-top:10px;display:flex;justify-content:space-between;font-size:14px;font-weight:600;">
            <span>Net Position</span>
            <span style="font-family:'DM Mono',monospace;color:{'#66bb6a' if mar1_net >= 0 else '#ef5350'};">{'+'if mar1_net>=0 else ''}{mar1_net:.3f}M</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        gap = net_position - mar1_net
        cow_coverage = sum(s.ad_revenue(year, mkt/len(shows)) / 12
                           for s in shows if s.rating >= 1.5)
        funded = "✅ Cash cows cover" if cow_coverage >= abs(net_position) else "❌ Cash gap — raise reserve"
        st.markdown(f"""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;padding:16px;">
          <div style="font-family:'DM Mono',monospace;font-size:10px;color:#555a6e;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;">Cash Gap Analysis</div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px;">
            <span style="color:#8b90a0;">Revenue shortfall vs. Day 1</span>
            <span style="font-family:'DM Mono',monospace;color:#ef5350;">${abs(gap):.3f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px;">
            <span style="color:#8b90a0;">Cash cow monthly rev</span>
            <span style="font-family:'DM Mono',monospace;color:#66bb6a;">${cow_coverage:.3f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px;">
            <span style="color:#8b90a0;">Reserve needed</span>
            <span style="font-family:'DM Mono',monospace;color:#ffa726;">${max(0,-net_position):.3f}M</span>
          </div>
          <div style="border-top:1px solid #252836;margin-top:10px;padding-top:10px;font-size:12px;">
            <span style="color:{'#66bb6a' if '✅' in funded else '#ef5350'};">{funded}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Section 2: Monthly Amortization Grid ─────────────────────────────────
    st.markdown('<div class="section-title">Monthly Amortization Grid — All Active Shows</div>', unsafe_allow_html=True)

    grid_shows = sorted(shows, key=lambda s: -s.total_cost(year))[:12]
    amort_rows = []
    for s in grid_shows:
        row = {"Show": s.name[:22]}
        active_months = set(s.cash_months(s.air_month, s.episodes))
        for i, m in enumerate(MONTHS):
            row[m] = round(s.monthly_amort(year) * 1000, 1) if i in active_months else 0
        amort_rows.append(row)

    amort_df = pd.DataFrame(amort_rows).set_index("Show")

    # Plotly heatmap
    fig_h = go.Figure(go.Heatmap(
        z=amort_df.values,
        x=MONTHS,
        y=amort_df.index.tolist(),
        colorscale=[[0,"rgba(37,40,54,0.4)"],[0.3,"rgba(239,83,80,0.3)"],
                    [0.7,"rgba(239,83,80,0.6)"],[1,"rgba(239,83,80,0.9)"]],
        hovertemplate="<b>%{y}</b><br>%{x}: $%{z:.0f}K<extra></extra>",
        showscale=True,
        colorbar=dict(title="$K/mo", tickfont=dict(size=10, color=TEXT2)),
        xgap=2, ygap=2,
    ))
    fig_h.update_layout(**base_layout("Monthly Cash Outflows ($K) — Active Shows", height=380))
    fig_h.update_yaxes(tickfont=dict(size=10))
    st.plotly_chart(fig_h, use_container_width=True, config={"displayModeBar":False})

    # ── Monthly Cash Bridge ───────────────────────────────────────────────────
    st.markdown('<div class="section-title">Monthly Cash Flow Bridge</div>', unsafe_allow_html=True)

    monthly_rev  = [portfolio_ad_rev(shows,year,mkt)/12 * (0.8+0.4*np.sin(i*0.5)) for i in range(12)]
    monthly_dist = [distribution_revenue(year)/12] * 12
    monthly_cost = [sum(s.total_cost(year)/12 * (1 if i in s.cash_months(s.air_month,s.episodes) else 0)
                        for s in shows) for i in range(12)]
    monthly_net  = [monthly_rev[i]+monthly_dist[i]-monthly_cost[i] for i in range(12)]

    bridge_df = pd.DataFrame({
        "Month": MONTHS,
        "Ad Revenue":     [round(v,2) for v in monthly_rev],
        "Distribution":   [round(v,2) for v in monthly_dist],
        "Content Cost":   [round(v,2) for v in monthly_cost],
        "Net Cash Flow":  [round(v,2) for v in monthly_net],
    })

    fig_b = go.Figure()
    fig_b.add_trace(go.Bar(name="Ad Revenue",   x=MONTHS, y=bridge_df["Ad Revenue"],
                            marker_color=SUCCESS, opacity=0.75))
    fig_b.add_trace(go.Bar(name="Distribution", x=MONTHS, y=bridge_df["Distribution"],
                            marker_color=ACCENT2, opacity=0.75))
    fig_b.add_trace(go.Bar(name="Content Cost", x=MONTHS, y=[-v for v in bridge_df["Content Cost"]],
                            marker_color=DANGER,  opacity=0.7))
    fig_b.add_trace(go.Scatter(name="Net Monthly", x=MONTHS, y=bridge_df["Net Cash Flow"],
                                mode="lines+markers", line=dict(color=ACCENT, width=2.5),
                                marker=dict(size=7, color=ACCENT)))
    fig_b.update_layout(**base_layout("Monthly P&L Bridge ($M)", height=320), barmode="relative")
    st.plotly_chart(fig_b, use_container_width=True, config={"displayModeBar":False})

    with st.expander("📋 Monthly Detail Table"):
        st.dataframe(bridge_df.style.format({
            "Ad Revenue":"${:.2f}M","Distribution":"${:.2f}M",
            "Content Cost":"${:.2f}M","Net Cash Flow":"${:.2f}M"
        }).applymap(lambda v: "color:#66bb6a;" if v >= 0 else "color:#ef5350;",
                    subset=["Net Cash Flow"]), use_container_width=True)

    st.divider()

    # ── Scheduling Grid ───────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Primetime Scheduling Optimizer</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:12px;color:#8b90a0;margin-bottom:12px;">
    Assign high-rating shows to Tue/Wed/Thu primetime to maximize short-term ratings. 
    Emerging IP can anchor weekend slots to build audience without cannibalizing cash cows.
    </div>
    """, unsafe_allow_html=True)

    days_of_week = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    time_slots   = ["7PM","8PM","9PM","10PM"]

    # Auto-assign by rating (highest → best slots)
    sorted_shows = sorted(shows, key=lambda s: -s.rating)
    slot_map = {}
    for idx, slot in enumerate([(t,d) for t in time_slots for d in days_of_week]):
        if idx < len(sorted_shows):
            slot_map[slot] = sorted_shows[idx]

    sched_data = []
    for t in time_slots:
        row = {"Time": t}
        for d in days_of_week:
            sh = slot_map.get((t,d))
            row[d] = f"{sh.name[:12]} ({sh.rating:.1f})" if sh else "—"
        sched_data.append(row)

    sched_df = pd.DataFrame(sched_data).set_index("Time")
    st.dataframe(sched_df, use_container_width=True)
    st.caption("Auto-assigned by rating. Primetime = Tue–Thu 8–10PM. Adjust via Show Editor.")

    # ── Hourly Revenue Index ──────────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">Hourly Ad Revenue Index — Premiere Week</div>', unsafe_allow_html=True)

    total_daily = portfolio_ad_rev(shows, year, mkt) / 365
    hourly_rev  = [total_daily * idx for idx in HOURLY_INDEX]

    fig_hr = go.Figure(go.Bar(
        x=HOUR_LABELS, y=hourly_rev,
        marker_color=[f"rgba(232,197,71,{0.15+v*0.75})" for v in HOURLY_INDEX],
        hovertemplate="%{x}: $%{y:.3f}M<extra></extra>",
    ))
    fig_hr.update_layout(**base_layout(
        "Daily Ad Revenue Distribution ($M) — Primetime peaks 8–10PM", height=220))
    st.plotly_chart(fig_hr, use_container_width=True, config={"displayModeBar":False})
    st.caption("Revenue ratio applied per hour. Premiere episodes earn a 1.5–2× premium above daily average.")
