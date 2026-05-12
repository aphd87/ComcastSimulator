"""
Tab 6 — 10-Year Forecast
Full portfolio simulation: Oxygen → Bravo → Peacock SVOD+
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utils.models import ten_year_sim, annual_budget, cable_subs, phase_label
from utils.charts import (
    base_layout, SUCCESS, DANGER, WARN, ACCENT, ACCENT2,
    TEXT2, BRAVO_C, OXY_C, SVOD_C
)

PHASE_COLORS = {
    "Phase 1 — Oxygen":           "#8e44ad",
    "Phase 2 — Oxygen + Bravo":   "#c0392b",
    "Phase 3 — Full Portfolio":   "#1a6bb5",
}


def render():
    ss   = st.session_state
    mkt  = ss.get("mkt_budget", 5.0)

    st.markdown("""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #4fc3f7;
         border-radius:6px;padding:12px 16px;margin-bottom:16px;font-size:12px;color:#8b90a0;">
    💡 <b style="color:#e8eaf0;">10-Year Strategy:</b> Prove OCF on Oxygen (Years 1–3) →
    earn the right to add Bravo (Years 4–7) → launch Peacock SVOD+ (Years 8–10).
    Each phase is a performance threshold. Cord-cutting accelerates after Year 4.
    Peacock becomes the hedge against linear erosion.
    </div>
    """, unsafe_allow_html=True)

    # ── Scenario Controls ──────────────────────────────────────────────────────
    with st.expander("🎛️ Scenario Parameters", expanded=True):
        c1,c2,c3,c4 = st.columns(4)
        cord_cut_override = c1.slider("Cord-cut Rate (%/yr)", 1.0, 8.0, 3.0, 0.5,
                                       help="Base = 3%. Accelerate to stress-test.")
        budget_growth     = c2.slider("Budget Growth (%/yr)", 0.0, 6.0, 3.0, 0.5,
                                       help="Base = 3% per year.")
        bravo_year        = c3.selectbox("Bravo Launch Year", [3,4,5,6], index=1,
                                          help="When does the team earn Bravo?")
        svod_year         = c4.selectbox("Peacock Launch Year", [7,8,9,10], index=1,
                                          help="When does Peacock SVOD+ launch?")

    # Re-run simulation with custom params
    from utils.models import (portfolio_ad_rev, portfolio_cost,
                               REV_PER_RATING_POINT, SUB_RATE_PER_MONTH)
    import numpy as np

    sim_rows = []
    for y in range(1, 11):
        shows = ss.oxygen_shows[:]
        if y >= bravo_year:
            shows += ss.bravo_shows

        cord   = (1 - cord_cut_override/100)**(y-1)
        ad     = (sum(s.rating * REV_PER_RATING_POINT * cord for s in shows)
                  + mkt * 0.015 * sum(s.rating for s in shows) / max(len(shows), 1))
        subs_m = 45 * cord
        esc    = min(1 + (0.05*(y-1)), 1.25)
        dist   = subs_m * SUB_RATE_PER_MONTH * 12 / 1000 * esc
        cost   = sum(s.annual_amort_expense(y) for s in shows)
        budget = 220 * (1 + budget_growth/100)**(y-1)
        ga     = (ad + dist) * 0.06
        ocf    = ad + dist - cost - mkt - ga

        svod_rev = 0
        if y >= svod_year:
            svod_rev = 0.3 * ad * (1 + (y - svod_year) * 0.15)

        sim_rows.append({
            "Year":           y,
            "Calendar Year":  2011 + y,
            "Phase":          phase_label(y),
            "Ad Revenue":     round(ad, 2),
            "SVOD Revenue":   round(svod_rev, 2),
            "Distribution":   round(dist, 2),
            "Total Revenue":  round(ad + dist + svod_rev, 2),
            "Content Cost":   round(cost, 2),
            "OCF":            round(ocf + svod_rev * 0.3, 2),
            "Budget":         round(budget, 2),
            "Cable Subs (M)": round(subs_m, 2),
            "Active Shows":   len(shows),
        })

    df = pd.DataFrame(sim_rows)

    # ── KPI Summary ────────────────────────────────────────────────────────────
    total_ocf = df["OCF"].sum()
    peak_ocf  = df["OCF"].max()
    peak_year = df.loc[df["OCF"].idxmax(), "Calendar Year"]
    avg_margin= (df["OCF"] / df["Total Revenue"] * 100).mean()
    sub_loss  = 45 - df.iloc[-1]["Cable Subs (M)"]

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("10-Year Cumulative OCF", f"${total_ocf:.0f}M")
    c2.metric("Peak Annual OCF",        f"${peak_ocf:.1f}M", f"Year {peak_year-2011} ({peak_year})")
    c3.metric("Avg OCF Margin",         f"{avg_margin:.1f}%", "across 10 years")
    c4.metric("Subscribers Lost",       f"{sub_loss:.1f}M",  "to cord-cutting")

    st.divider()

    # ── Main 10-Year Chart ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">10-Year Revenue, Cost & OCF</div>', unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["Year"], y=df["Ad Revenue"], name="Ad Revenue",
                          marker_color=SUCCESS, opacity=0.7))
    fig.add_trace(go.Bar(x=df["Year"], y=df["SVOD Revenue"], name="SVOD Revenue",
                          marker_color=SVOD_C, opacity=0.7))
    fig.add_trace(go.Bar(x=df["Year"], y=df["Distribution"], name="Distribution",
                          marker_color=ACCENT2, opacity=0.7))
    fig.add_trace(go.Scatter(x=df["Year"], y=df["Content Cost"], name="Content Cost",
                              mode="lines+markers", line=dict(color=DANGER,width=2,dash="dot"),
                              marker=dict(size=6)))
    fig.add_trace(go.Scatter(x=df["Year"], y=df["OCF"], name="OCF",
                              mode="lines+markers", line=dict(color=ACCENT,width=3),
                              marker=dict(size=8, color=ACCENT)))

    for ph_y, ph_label_txt, ph_color in [
        (bravo_year-0.5, f"← Bravo Y{bravo_year}",   BRAVO_C),
        (svod_year-0.5,  f"← Peacock Y{svod_year}", SVOD_C),
    ]:
        fig.add_vline(x=ph_y, line_dash="dash", line_color=ph_color, opacity=0.5,
                      annotation_text=ph_label_txt, annotation_font_color=ph_color,
                      annotation_font_size=10)

    fig.update_layout(**base_layout("10-Year Simulation — $M", height=380), barmode="stack")
    fig.update_xaxes(tickvals=list(range(1,11)),
                     ticktext=[f"Y{y}\n({2011+y})" for y in range(1,11)])
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})

    # ── Phase breakdown ───────────────────────────────────────────────────────
    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="section-title">OCF by Phase</div>', unsafe_allow_html=True)
        phase_agg = df.groupby("Phase")["OCF"].sum().reset_index()
        phase_agg.columns = ["Phase","Cumulative OCF ($M)"]
        phase_agg["Color"] = phase_agg["Phase"].map(PHASE_COLORS)

        fig_ph = go.Figure(go.Bar(
            x=phase_agg["Phase"], y=phase_agg["Cumulative OCF ($M)"],
            marker_color=phase_agg["Color"], opacity=0.8,
            text=phase_agg["Cumulative OCF ($M)"].apply(lambda v: f"${v:.0f}M"),
            textposition="outside", textfont=dict(size=11, color="#e8eaf0"),
        ))
        fig_ph.update_layout(**base_layout("Cumulative OCF by Phase ($M)", height=280))
        fig_ph.update_xaxes(tickfont=dict(size=9))
        st.plotly_chart(fig_ph, use_container_width=True, config={"displayModeBar":False})

    with c2:
        st.markdown('<div class="section-title">Subscriber Erosion vs. SVOD Growth</div>', unsafe_allow_html=True)

        fig_subs = go.Figure()
        fig_subs.add_trace(go.Scatter(
            x=df["Year"], y=df["Cable Subs (M)"], name="Cable Subs (M)",
            mode="lines+markers", line=dict(color=DANGER,width=2),
            fill="tozeroy", fillcolor="rgba(239,83,80,0.08)"))
        svod_subs = [max(0, (y-svod_year+1)*1.5) if y >= svod_year else 0 for y in range(1,11)]
        fig_subs.add_trace(go.Scatter(
            x=df["Year"], y=svod_subs, name="Peacock Subs (M)",
            mode="lines+markers", line=dict(color=SVOD_C,width=2),
            fill="tozeroy", fillcolor="rgba(26,107,181,0.08)"))
        fig_subs.update_layout(**base_layout("Subscriber Base (M)", height=280))
        fig_subs.update_xaxes(tickvals=list(range(1,11)),
                               ticktext=[f"Y{y}" for y in range(1,11)])
        st.plotly_chart(fig_subs, use_container_width=True, config={"displayModeBar":False})

    st.divider()

    # ── Full Data Table ───────────────────────────────────────────────────────
    st.markdown('<div class="section-title">10-Year Model — Full Data Table</div>', unsafe_allow_html=True)

    def color_ocf(val):
        try:
            return "color:#66bb6a;font-weight:600;" if float(val) >= 0 else "color:#ef5350;font-weight:600;"
        except: return ""

    styled_df = (
        df.style
        .applymap(color_ocf, subset=["OCF"])
        .format({
            "Ad Revenue":"${:.1f}M","SVOD Revenue":"${:.1f}M",
            "Distribution":"${:.1f}M","Total Revenue":"${:.1f}M",
            "Content Cost":"${:.1f}M","OCF":"${:.1f}M",
            "Budget":"${:.1f}M","Cable Subs (M)":"{:.1f}M"
        })
        .set_properties(**{"font-family":"DM Mono,monospace","font-size":"11px"})
    )
    st.dataframe(styled_df, use_container_width=True)

    st.download_button(
        "⬇️ Download 10-Year Model CSV",
        df.to_csv(index=False),
        file_name="cableos_10yr_forecast.csv", mime="text/csv"
    )

    # ── Strategic Decision Log ────────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">Strategic Decision Log</div>', unsafe_allow_html=True)
    cur_year = ss.get("year", 1)

    events = [
        (1,              "🔮", "Oxygen slate launched — 20 shows, $95M budget, 45M cable subs"),
        (2,              "🔄", "Year 2 renewals — cancel bottom-quartile ROI shows, redeploy budget"),
        (3,              "✅", f"OCF threshold met — board reviews expansion case for Bravo (Yr {bravo_year})"),
        (bravo_year,     "📺", f"Bravo acquired — reality slate, avg $750K/ep, 12-mo amortization"),
        (bravo_year+1,   "📊", "Cross-network portfolio management begins — dual P&L (Oxygen + Bravo)"),
        (svod_year-1,    "📱", f"Peacock business case built — green light model shows streaming wins (Yr {svod_year})"),
        (svod_year,      "🦚", f"Peacock launched — first original greenlit for streaming-first release"),
        (svod_year+1,    "🔗", "Content windowing strategy: Peacock first → linear later"),
        (10,             "🚀", "Full portfolio: Oxygen + Bravo + Peacock — three P&Ls, one strategy"),
    ]

    for ev_year, icon, text in events:
        cal        = 2011 + ev_year
        is_past    = ev_year <= cur_year
        is_current = ev_year == cur_year
        opacity    = "1.0" if is_past else "0.4"
        border     = "border-left:3px solid #e8c547;" if is_current else "border-left:3px solid #252836;"
        st.markdown(f"""
        <div style="display:flex;gap:12px;padding:8px 12px;margin-bottom:4px;
             background:#1a1d26;border-radius:6px;{border}opacity:{opacity};">
          <span style="font-size:16px;min-width:24px;">{icon}</span>
          <span style="font-family:'DM Mono',monospace;font-size:10px;color:#555a6e;
                min-width:60px;padding-top:2px;">Y{ev_year} · {cal}</span>
          <span style="font-size:12px;color:{'#e8eaf0' if is_past else '#555a6e'};">{text}</span>
        </div>
        """, unsafe_allow_html=True)
