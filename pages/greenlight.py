"""
Tab 4 — Green Light Model
Student builds a show concept and compares Linear vs. SVOD P&L.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.models import greenlight_linear, greenlight_svod, ltv_curve, HOURLY_INDEX, HOUR_LABELS
from utils.charts import base_layout, ACCENT, ACCENT2, SUCCESS, DANGER, WARN, TEXT2


def render():
    ss   = st.session_state
    year = ss.get("year", 1)

    st.markdown("""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #4fc3f7;
         border-radius:6px;padding:12px 16px;margin-bottom:16px;font-size:12px;color:#8b90a0;">
    💡 <b style="color:#e8eaf0;">The Core Decision:</b> Do you put this show on Bravo (linear) or SVOD+?  
    In 2012, linear wins on immediate cash — faster ad revenue, no subscriber acquisition cost.  
    By Year 7+, SVOD subscription LTV starts to outpace a declining ad market. Build the P&L for both.
    </div>
    """, unsafe_allow_html=True)

    # ── Show Concept Builder ───────────────────────────────────────────────────
    st.markdown('<div class="section-title">Show Concept Inputs</div>', unsafe_allow_html=True)

    with st.container():
        c1,c2,c3 = st.columns(3)
        with c1:
            show_name = st.text_input("Show Name / Concept", "My New Show")
            genre     = st.selectbox("Genre", ["Reality","Competition","Talk","Scripted","True Crime","Drama"])
            eps       = st.number_input("Episode Count", 4, 24, 10, step=1)
        with c2:
            ep_cost   = st.number_input("Cost per Episode ($K)", 100, 5000, 750, step=50,
                                         help="Bravo reality ~$650-900K. Scripted ~$1-2M.")
            rating    = st.slider("Projected Rating (18-49)", 0.3, 4.0, 1.2, step=0.1,
                                   help="Bravo avg: 1.0–1.5. Hit show: 2.0+. Mega-hit: 3.0+")
            mkt_spend = st.slider("Marketing Budget ($M)", 0.0, 10.0, 2.0, step=0.5,
                                   help="Each $1M adds ~1.5% rating lift on linear; also lifts SVOD sub acquisition.")
        with c3:
            appeal    = st.slider("Genre Appeal Score (SVOD)", 20, 100, 72, step=1,
                                   help="How well does this genre convert to streaming subscriptions? "
                                        "True Crime: 85. Scripted drama: 90. Reality: 60.")
            air_month = st.slider("Premiere Month", 1, 12, 3, step=1,
                                   format="%d", help="Affects amortization cash trough (see Schedule tab).")
            svod_prem = st.number_input("SVOD Monthly Premium ($/sub)", 5.0, 20.0, 8.0, step=0.5,
                                         help="Price premium vs. baseline. Higher = more LTV per acquired sub.")

    # ── Calculate ─────────────────────────────────────────────────────────────
    linear = greenlight_linear(eps, ep_cost, rating, mkt_spend, year)
    svod   = greenlight_svod(eps, ep_cost, rating, appeal, mkt_spend, year)
    # Override SVOD LTV with student's premium
    svod["ltv_3yr"] = svod["sub_lift"] * svod_prem * 12 * 0.15 * 3
    svod["revenue"] = svod["ltv_3yr"] / 3
    svod["ocf"]     = svod["revenue"] - linear["cost"] - mkt_spend
    svod["roi"]     = (svod["ocf"] / linear["cost"] * 100) if linear["cost"] else 0

    st.divider()

    # ── Side-by-side P&L ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Platform P&L Comparison</div>', unsafe_allow_html=True)

    def pl_card(title, color, data, winner=False):
        border = f"border:2px solid {color};" if winner else f"border:1px solid #252836;"
        rows = "".join([
            f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
            f'border-bottom:1px solid rgba(37,40,54,.5);font-size:12px;">'
            f'<span style="color:#8b90a0;">{k}</span>'
            f'<span style="font-family:DM Mono,monospace;color:{vc};">{v}</span></div>'
            for k,v,vc in data
        ])
        w_badge = f'<span style="background:{color};color:#0b0c10;font-size:10px;padding:2px 8px;border-radius:3px;font-family:DM Mono,monospace;">WINNER</span>' if winner else ''
        return f"""
        <div style="background:#1a1d26;{border}border-radius:8px;padding:16px;height:100%;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <span style="font-family:DM Mono,monospace;font-size:11px;text-transform:uppercase;
                  letter-spacing:.1em;color:{color};">{title}</span>
            {w_badge}
          </div>
          {rows}
        </div>
        """

    lin_winner  = linear["ocf"] > svod["ocf"] and year < 7
    svod_winner = not lin_winner

    lin_rows = [
        ("Total Season Cost",   f"${linear['cost']:.2f}M",    WARN),
        ("Ad Revenue (Y1)",     f"${linear['revenue']:.2f}M", SUCCESS),
        ("Marketing",           f"-${mkt_spend:.1f}M",         DANGER),
        ("Net OCF",             f"${linear['ocf']:+.2f}M",    SUCCESS if linear["ocf"]>=0 else DANGER),
        ("ROI",                 f"{linear['roi']:+.1f}%",      SUCCESS if linear["roi"]>=0 else DANGER),
        ("Amortization",        "12 months",                  TEXT2),
        ("Cash Payback",        linear["payback"],             TEXT2),
        ("Revenue ceiling",     "Ad market (eroding)",        TEXT2),
    ]
    svod_rows = [
        ("Total Season Cost",   f"${svod['cost']:.2f}M",      WARN),
        ("Sub Lift Est.",       f"+{svod['sub_lift']:.2f}M subs", SUCCESS),
        ("LTV (3-year)",        f"${svod['ltv_3yr']:.2f}M",   SUCCESS),
        ("Y1 Revenue Share",    f"${svod['revenue']:.2f}M",   ACCENT2),
        ("Net OCF (Y1)",        f"${svod['ocf']:+.2f}M",      SUCCESS if svod["ocf"]>=0 else DANGER),
        ("ROI (3yr basis)",     f"{svod['roi']:+.1f}%",        SUCCESS if svod["roi"]>=0 else DANGER),
        ("Amortization",        "36 months",                  TEXT2),
        ("Engagement Score",    f"{svod['engagement']:.2f}",  TEXT2),
    ]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(pl_card("📺 Linear — Bravo", ACCENT, lin_rows, lin_winner), unsafe_allow_html=True)
    with c2:
        st.markdown(pl_card("📱 SVOD+", ACCENT2, svod_rows, svod_winner), unsafe_allow_html=True)

    # Winner banner
    if lin_winner:
        st.success(f"📺 **Linear wins in Year {year}** — Faster cash recovery. Ad revenue beats SVOD LTV at current cord-cut levels.")
    else:
        st.info(f"📱 **SVOD+ wins in Year {year}** — Subscription LTV outpaces declining linear ad market. Long-term play.")

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="section-title">3-Year P&L Comparison</div>', unsafe_allow_html=True)
        categories = ["Total Cost","Y1 Revenue","Y1 OCF","3yr Revenue","3yr OCF"]
        lin_vals   = [linear["cost"], linear["revenue"], linear["ocf"],
                      linear["revenue"]*3, linear["ocf"]*3]
        svod_vals  = [svod["cost"],   svod["revenue"],   svod["ocf"],
                      svod["ltv_3yr"], svod["ocf"]*3]

        fig_cmp = go.Figure()
        fig_cmp.add_trace(go.Bar(name="📺 Linear", x=categories,
                                  y=[round(v,2) for v in lin_vals],
                                  marker_color=ACCENT, opacity=0.8))
        fig_cmp.add_trace(go.Bar(name="📱 SVOD+",  x=categories,
                                  y=[round(v,2) for v in svod_vals],
                                  marker_color=ACCENT2, opacity=0.7))
        fig_cmp.update_layout(**base_layout("Linear vs. SVOD — Revenue, Cost, OCF ($M)", height=300))
        st.plotly_chart(fig_cmp, use_container_width=True, config={"displayModeBar":False})

    with c2:
        st.markdown('<div class="section-title">Cumulative LTV Curve (36 months)</div>', unsafe_allow_html=True)
        ltv_df = ltv_curve(linear, svod, months=36)
        fig_ltv = go.Figure()
        fig_ltv.add_trace(go.Scatter(
            x=ltv_df["Month"], y=ltv_df["Linear (cumul.)"],
            name="Linear (cumul.)", mode="lines",
            line=dict(color=ACCENT, width=2),
            fill="tozeroy", fillcolor="rgba(232,197,71,0.08)"))
        fig_ltv.add_trace(go.Scatter(
            x=ltv_df["Month"], y=ltv_df["SVOD LTV (cumul.)"],
            name="SVOD LTV (cumul.)", mode="lines",
            line=dict(color=ACCENT2, width=2),
            fill="tozeroy", fillcolor="rgba(79,195,247,0.08)"))
        crossover = ltv_df[ltv_df["SVOD LTV (cumul.)"] >= ltv_df["Linear (cumul.)"]]["Month"].min()
        if crossover and not pd.isna(crossover):
            fig_ltv.add_vline(x=crossover, line_dash="dash", line_color=WARN,
                               annotation_text=f"Crossover: M{crossover}", annotation_font_color=WARN)
        fig_ltv.update_layout(**base_layout("Cumulative Revenue: Linear vs. SVOD ($M)", height=300))
        st.plotly_chart(fig_ltv, use_container_width=True, config={"displayModeBar":False})

    st.divider()

    # ── Sensitivity Table ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Sensitivity Analysis — Rating vs. Episode Cost</div>', unsafe_allow_html=True)
    st.markdown('<span style="font-size:11px;color:#8b90a0;">Linear OCF ($M) at different rating × cost combinations. Green = profitable, Red = cancel.</span>', unsafe_allow_html=True)

    rating_range = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
    cost_range   = [300, 500, 750, 1000, 1500, 2000]

    sens_rows = []
    for ep_c in cost_range:
        row = {f"${ep_c}K/ep": f"${ep_c}K"}
        for r in rating_range:
            lin = greenlight_linear(eps, ep_c, r, mkt_spend, year)
            row[f"{r:.1f}"] = round(lin["ocf"], 2)
        sens_rows.append(row)

    sens_df = pd.DataFrame(sens_rows).set_index(f"${cost_range[0]}K/ep")
    sens_df.index.name = "Cost/Ep → Rating ↓"

    def color_cells(val):
        try:
            v = float(val)
            if v > 5:   return "background-color:rgba(102,187,106,.25);color:#81c784;"
            if v > 0:   return "background-color:rgba(255,167,38,.15);color:#ffb74d;"
            return "background-color:rgba(239,83,80,.2);color:#ef9a9a;"
        except: return ""

    st.dataframe(
        sens_df.style.applymap(color_cells).format("{:.2f}"),
        use_container_width=True
    )
    st.caption("Rows = episode cost. Columns = projected 18-49 rating. Cell = Linear OCF in $M.")

    st.divider()

    # ── Marketing ROI ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Marketing ROI: Linear vs. SVOD</div>', unsafe_allow_html=True)
    mkt_levels = [0, 1, 2, 3, 5, 7, 10]
    mkt_rows = []
    for m in mkt_levels:
        l = greenlight_linear(eps, ep_cost, rating, m, year)
        s = greenlight_svod(eps, ep_cost, rating, appeal, m, year)
        mkt_rows.append({
            "Marketing ($M)": m,
            "Linear OCF":     round(l["ocf"],2),
            "Linear ROI %":   round(l["roi"],1),
            "SVOD OCF":       round(s["ocf"],2),
            "SVOD ROI %":     round(s["roi"],1),
        })
    mkt_df = pd.DataFrame(mkt_rows)

    c1, c2 = st.columns(2)
    with c1:
        fig_mkt = go.Figure()
        fig_mkt.add_trace(go.Scatter(x=mkt_df["Marketing ($M)"], y=mkt_df["Linear OCF"],
                                      name="Linear OCF", mode="lines+markers",
                                      line=dict(color=ACCENT,width=2),marker=dict(size=7)))
        fig_mkt.add_trace(go.Scatter(x=mkt_df["Marketing ($M)"], y=mkt_df["SVOD OCF"],
                                      name="SVOD OCF",   mode="lines+markers",
                                      line=dict(color=ACCENT2,width=2),marker=dict(size=7)))
        fig_mkt.add_hline(y=0, line_dash="dash", line_color=DANGER, opacity=0.5)
        fig_mkt.update_layout(**base_layout("OCF vs. Marketing Spend ($M)", height=280))
        st.plotly_chart(fig_mkt, use_container_width=True, config={"displayModeBar":False})
    with c2:
        st.dataframe(mkt_df.style.format({
            "Linear OCF":"${:.2f}M","Linear ROI %":"{:.1f}%",
            "SVOD OCF":"${:.2f}M","SVOD ROI %":"{:.1f}%"
        }), use_container_width=True, height=280)
