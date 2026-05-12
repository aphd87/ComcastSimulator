"""
Tab 3 — P&L / OCF
Full income statement, revenue decomposition, distribution model.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from utils.models import (
    annual_budget, cable_subs, distribution_revenue,
    portfolio_ad_rev, portfolio_cost, MONTHS,
    REV_PER_RATING_POINT, SUB_RATE_PER_MONTH
)
from utils.charts import (
    base_layout, bar_chart, line_chart, donut_chart,
    SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2, BORDER
)


def render():
    ss   = st.session_state
    year = ss.get("year", 1)
    mkt  = ss.get("mkt_budget", 5.0)

    net = ss.get("active_network", "oxygen")
    shows = ss.oxygen_shows[:]
    if net in ("bravo", "peacock"):
        shows += ss.bravo_shows
    if net == "peacock":
        shows += ss.get("peacock_shows", [])

    ad_rev   = portfolio_ad_rev(shows, year, mkt)
    dist_rev = distribution_revenue(year)
    total_rev= ad_rev + dist_rev
    cost     = portfolio_cost(shows, year)
    ga       = total_rev * 0.06
    ebitda   = total_rev - cost - mkt - ga
    net_ocf  = ebitda
    margin   = (net_ocf / total_rev * 100) if total_rev else 0
    subs     = cable_subs(year)
    budget   = annual_budget(year)

    # ── KPI Row ───────────────────────────────────────────────────────────────
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Ad Revenue",     f"${ad_rev:.1f}M",   f"Rating × ${REV_PER_RATING_POINT}M/pt")
    c2.metric("Distribution",   f"${dist_rev:.1f}M", f"{subs:.1f}M subs × ${SUB_RATE_PER_MONTH}/mo")
    c3.metric("Total Revenue",  f"${total_rev:.1f}M","Ad + Distribution")
    c4.metric("Content Spend",  f"${cost:.1f}M",     "Amortized")
    c5.metric("Marketing",      f"${mkt:.1f}M",      "Allocated")
    c6.metric("Net OCF",        f"${net_ocf:.1f}M",  f"Margin: {margin:.1f}%",
              delta_color="inverse" if net_ocf < 0 else "normal")

    st.divider()

    # ── Full P&L Statement ────────────────────────────────────────────────────
    left, right = st.columns([1, 1])

    with left:
        st.markdown('<div class="section-title">Income Statement — Year {}</div>'.format(year), unsafe_allow_html=True)

        pl_data = [
            ("Ad Revenue",           ad_rev,    True),
            ("Distribution Revenue", dist_rev,  True),
            ("──────────────────",   None,      None),
            ("Gross Revenue",        total_rev, True),
            ("Content Cost",        -cost,      False),
            ("Marketing Spend",     -mkt,       False),
            ("G&A (6%)",            -ga,        False),
            ("──────────────────",   None,       None),
            ("EBITDA / OCF",         net_ocf,   None),
        ]

        for label, val, is_rev in pl_data:
            if val is None:
                st.markdown('<hr style="border-color:#252836;margin:4px 0;">', unsafe_allow_html=True)
                continue
            pct   = (abs(val)/total_rev*100) if total_rev else 0
            sign  = "+" if val >= 0 else ""
            color = "#66bb6a" if val >= 0 else "#ef5350"
            bold  = "font-weight:600;" if label in ("Gross Revenue","EBITDA / OCF") else ""
            size  = "14px" if label in ("Gross Revenue","EBITDA / OCF") else "12px"
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;
                 padding:5px 0;border-bottom:1px solid rgba(37,40,54,.5);">
              <span style="font-size:{size};{bold}color:#e8eaf0;">{label}</span>
              <div style="display:flex;gap:20px;align-items:center;">
                <span style="font-size:10px;color:#555a6e;font-family:'DM Mono',monospace;">{pct:.1f}%</span>
                <span style="font-family:'DM Mono',monospace;{bold}font-size:{size};color:{color};">{sign}${abs(val):.1f}M</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Download P&L
        pl_df = pd.DataFrame([
            {"Line Item": l, "Amount ($M)": round(v,2), "% of Revenue": round(abs(v)/total_rev*100,1)}
            for l,v,_ in pl_data if v is not None
        ])
        st.download_button("⬇️ Download P&L as CSV", pl_df.to_csv(index=False),
                           file_name=f"cableos_pl_year{year}.csv", mime="text/csv")

    with right:
        # Revenue donut
        fig_rev = donut_chart(
            ["Ad Revenue","Distribution Revenue"],
            [round(ad_rev,2), round(dist_rev,2)],
            "Revenue Mix", height=240)
        st.plotly_chart(fig_rev, use_container_width=True, config={"displayModeBar":False})

        # Cost donut
        network_costs = {}
        for s in shows:
            network_costs[s.network] = network_costs.get(s.network,0) + s.total_cost(year)
        fig_cost = donut_chart(
            list(network_costs.keys()),
            [round(v,2) for v in network_costs.values()],
            "Content Cost by Network", height=220)
        fig_cost.update_traces(marker_colors=["#c0392b","#8e44ad","#1a6bb5"][:len(network_costs)])
        st.plotly_chart(fig_cost, use_container_width=True, config={"displayModeBar":False})

    st.divider()

    # ── Monthly P&L ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Monthly Revenue & Cost Trend</div>', unsafe_allow_html=True)

    monthly_ad   = [ad_rev/12*(0.8+0.4*np.sin(i*0.5)) for i in range(12)]
    monthly_dist = [dist_rev/12]*12
    monthly_cost = [cost/12]*12
    monthly_ocf  = [monthly_ad[i]+monthly_dist[i]-monthly_cost[i]-mkt/12 for i in range(12)]

    mo_df = pd.DataFrame({
        "Month":        MONTHS,
        "Ad Revenue":   [round(v,2) for v in monthly_ad],
        "Distribution": [round(v,2) for v in monthly_dist],
        "Content Cost": [round(v,2) for v in monthly_cost],
        "Monthly OCF":  [round(v,2) for v in monthly_ocf],
    })

    fig_mo = go.Figure()
    fig_mo.add_trace(go.Scatter(x=MONTHS, y=mo_df["Ad Revenue"],
                                 name="Ad Revenue", mode="lines+markers",
                                 line=dict(color=SUCCESS,width=2), marker=dict(size=5),
                                 fill="tozeroy", fillcolor="rgba(102,187,106,0.08)"))
    fig_mo.add_trace(go.Scatter(x=MONTHS, y=mo_df["Distribution"],
                                 name="Distribution", mode="lines+markers",
                                 line=dict(color=ACCENT2,width=2), marker=dict(size=5)))
    fig_mo.add_trace(go.Scatter(x=MONTHS, y=mo_df["Content Cost"],
                                 name="Content Cost", mode="lines+markers",
                                 line=dict(color=DANGER,width=2,dash="dot"), marker=dict(size=5)))
    fig_mo.add_trace(go.Bar(x=MONTHS, y=mo_df["Monthly OCF"], name="Monthly OCF",
                             marker_color=[SUCCESS if v>=0 else DANGER for v in monthly_ocf],
                             opacity=0.5, yaxis="y2"))
    fig_mo.update_layout(
        **base_layout("Monthly P&L ($M)", height=320),
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    tickfont=dict(size=10, color=TEXT2), title="OCF ($M)"),
    )
    st.plotly_chart(fig_mo, use_container_width=True, config={"displayModeBar":False})

    st.divider()

    # ── Distribution Revenue Model ────────────────────────────────────────────
    st.markdown('<div class="section-title">Distribution Revenue Calculator</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:12px;color:#8b90a0;margin-bottom:12px;">
    Distribution (affiliate) revenue = subscribers × monthly fee × 12 months. 
    Bravo commands a premium affiliate fee; this compounds with a 5% annual escalation clause 
    (capped at Year 5) even as cable subscribers erode at 3%/year.
    </div>
    """, unsafe_allow_html=True)

    user_subs, user_rate, user_esc = BASE_SUBS_M, SUB_RATE_PER_MONTH, 5.0
    with st.expander("🎛️ Adjust Distribution Model", expanded=False):
        c1,c2,c3 = st.columns(3)
        user_subs = c1.number_input("Base Subscribers (M)", 10.0, 100.0, float(BASE_SUBS_M), step=1.0)
        user_rate = c2.number_input("Rate $/sub/month", 0.05, 2.0, float(SUB_RATE_PER_MONTH), step=0.05)
        user_esc  = c3.number_input("Escalation % (annual)", 0.0, 10.0, 5.0, step=0.5)

    dist_rows = []
    for y in range(1, 11):
        s = user_subs * (1 - 0.03)**(y-1)
        e = min(1 + (user_esc/100)*(y-1), 1.25)
        d = s * user_rate * 12 / 1000 * e
        dist_rows.append({"Year": y, "Calendar": 2011+y, "Subs (M)": round(s,2),
                           "Esc Factor": round(e,3), "Distrib Rev ($M)": round(d,2)})
    dist_df = pd.DataFrame(dist_rows)

    c1, c2 = st.columns([1,1])
    with c1:
        st.dataframe(dist_df.style.format({
            "Subs (M)":"{:.2f}","Esc Factor":"{:.3f}","Distrib Rev ($M)":"${:.2f}M"
        }), use_container_width=True, height=280)
    with c2:
        fig_dist = go.Figure()
        fig_dist.add_trace(go.Scatter(x=dist_df["Year"], y=dist_df["Subs (M)"],
                                       name="Subscribers (M)", mode="lines+markers",
                                       line=dict(color=DANGER,width=2), yaxis="y2"))
        fig_dist.add_trace(go.Bar(x=dist_df["Year"], y=dist_df["Distrib Rev ($M)"],
                                   name="Distribution Rev ($M)", marker_color=ACCENT2, opacity=0.7))
        fig_dist.update_layout(
            **base_layout("Distribution Revenue vs. Subscriber Erosion", height=280),
            yaxis2=dict(overlaying="y", side="right", showgrid=False,
                        title="Subs (M)", tickfont=dict(size=10,color=DANGER)),
        )
        st.plotly_chart(fig_dist, use_container_width=True, config={"displayModeBar":False})

    # ── Revenue per Rating Point ──────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">Revenue per Rating Point — Show Benchmarks</div>', unsafe_allow_html=True)
    rpp_rows = []
    per = mkt / max(len(shows),1)
    for s in sorted(shows, key=lambda x: -x.rating)[:10]:
        rev = s.ad_revenue(year, per)
        rpp_rows.append({
            "Show": s.name[:22],
            "Rating (18-49)": s.rating,
            "Ad Revenue ($M)": round(rev,2),
            "Rev/Point ($M)": round(rev/s.rating,2) if s.rating else 0,
            "Cost/Point ($M)": round(s.total_cost(year)/s.rating,2) if s.rating else 0,
        })
    rpp_df = pd.DataFrame(rpp_rows)
    st.dataframe(rpp_df.style.format({
        "Rating (18-49)":"{:.2f}","Ad Revenue ($M)":"${:.2f}M",
        "Rev/Point ($M)":"${:.2f}M","Cost/Point ($M)":"${:.2f}M"
    }), use_container_width=True)


# Allow direct access to BASE_SUBS_M inside the expander fallback
from utils.models import BASE_SUBS_M, SUB_RATE_PER_MONTH
