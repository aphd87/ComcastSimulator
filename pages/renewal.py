"""
Tab 5 — Renewal Engine
Student decides which shows to renew/cancel, models cost escalation, budget impact.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.models import (
    annual_budget, portfolio_ad_rev, portfolio_cost,
    distribution_revenue, renewal_decision, CONTENT_COST_ESC
)
from utils.charts import base_layout, SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2


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

    next_year    = year + 1
    budget_now   = annual_budget(year)
    budget_next  = annual_budget(next_year)
    budget_delta = budget_next - budget_now

    st.markdown("""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #ffa726;
         border-radius:6px;padding:12px 16px;margin-bottom:16px;font-size:12px;color:#e0e2ea;">
    💡 <b style="color:#e8eaf0;">Renewal Economics:</b> Each renewed show costs 5% more next year. 
    Your budget grows only 3%. Cancel low-ROI shows to free capacity for new IP or marketing.
    The IP Value score captures long-term franchise potential — sometimes a show worth renewing 
    at a loss because it's building a franchise (e.g., Below Deck → 4 spinoffs).
    </div>
    """, unsafe_allow_html=True)

    # ── Budget Bridge ─────────────────────────────────────────────────────────
    c1,c2,c3,c4 = st.columns(4)
    c1.metric(f"Budget Year {year}",    f"${budget_now:.1f}M")
    c2.metric(f"Budget Year {next_year}", f"${budget_next:.1f}M", f"+${budget_delta:.1f}M (+3%)")
    renewal_delta = sum(s.total_cost(next_year)-s.total_cost(year) for s in shows)
    c3.metric("Renewal Cost Increase",  f"+${renewal_delta:.1f}M", f"+{CONTENT_COST_ESC*100:.0f}% per show")
    slots = max(0, int((budget_next - portfolio_cost(shows, next_year)) / 8))
    c4.metric("New Show Capacity",       f"~{slots} shows",        "after renewals")

    st.divider()

    # ── Renewal Decision Table ────────────────────────────────────────────────
    st.markdown('<div class="section-title">Renewal Decision Matrix — Year {} → {}</div>'.format(year, next_year), unsafe_allow_html=True)

    # Initialize student decisions in session state
    if "renewal_decisions" not in ss:
        ss.renewal_decisions = {}

    per = mkt / max(len(shows), 1)
    rows = []
    for s in shows:
        curr_cost  = s.total_cost(year)
        renew_cost = s.total_cost(next_year)
        proj_rate  = s.projected_rating(next_year)
        proj_rev   = s.ad_revenue(next_year, per)
        proj_ocf   = proj_rev - renew_cost
        roi_now    = s.roi(year, per)
        roi_next   = (proj_ocf / renew_cost * 100) if renew_cost else 0
        trend      = "↑" if roi_next > roi_now else ("→" if abs(roi_next-roi_now)<5 else "↓")
        auto_dec   = renewal_decision(s, next_year, per)

        # Student override
        student_dec = ss.renewal_decisions.get(s.id, auto_dec.split()[1])

        rows.append({
            "_id":       s.id,
            "Show":      s.name,
            "Network":   s.network,
            "Genre":     s.genre,
            "Curr Cost": round(curr_cost, 2),
            "Renew Cost":round(renew_cost, 2),
            "Δ Cost":    round(renew_cost-curr_cost, 2),
            "Proj Rating":round(proj_rate, 2),
            "Proj Rev":  round(proj_rev, 2),
            "Proj OCF":  round(proj_ocf, 2),
            "ROI Now":   round(roi_now, 1),
            "ROI Next":  round(roi_next, 1),
            "Trend":     trend,
            "IP Score":  s.ip_score,
            "Auto":      auto_dec,
            "Decision":  student_dec,
        })

    decisions_df = pd.DataFrame(rows)

    # Inline decision editor
    with st.expander("🎛️ Override Renewal Decisions", expanded=True):
        st.markdown('<span style="font-size:11px;color:#e0e2ea;">Change any show\'s decision. The budget impact recalculates live below.</span>', unsafe_allow_html=True)

        nc = 4
        chunks = [rows[i:i+nc] for i in range(0,len(rows),nc)]
        for chunk in chunks:
            cols = st.columns(nc)
            for col, r in zip(cols, chunk):
                with col:
                    current = ss.renewal_decisions.get(r["_id"], "Renew")
                    choice  = st.selectbox(
                        f"{r['Show'][:18]}",
                        ["Renew","Watch","Cancel"],
                        index=["Renew","Watch","Cancel"].index(current),
                        key=f"ren_{r['_id']}",
                        help=f"Auto: {r['Auto']} · ROI: {r['ROI Next']:.1f}% · IP: {r['IP Score']}"
                    )
                    ss.renewal_decisions[r["_id"]] = choice
                    color = "#81c784" if choice=="Renew" else ("#ffb74d" if choice=="Watch" else "#ef9a9a")
                    st.markdown(f'<div style="font-size:10px;font-family:DM Mono,monospace;color:{color};">'
                                f'OCF: ${r["Proj OCF"]:+.1f}M · IP: {r["IP Score"]}</div>', unsafe_allow_html=True)

    # ── Budget Impact ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">Budget Impact of Your Decisions</div>', unsafe_allow_html=True)

    renewed_shows  = [r for r in rows if ss.renewal_decisions.get(r["_id"],"Renew") == "Renew"]
    cancelled      = [r for r in rows if ss.renewal_decisions.get(r["_id"],"Renew") == "Cancel"]
    watch_shows    = [r for r in rows if ss.renewal_decisions.get(r["_id"],"Renew") == "Watch"]

    renewed_cost  = sum(r["Renew Cost"] for r in renewed_shows)
    freed_budget  = sum(r["Renew Cost"] for r in cancelled)
    watch_cost    = sum(r["Renew Cost"] for r in watch_shows)
    new_show_cap  = budget_next - renewed_cost - watch_cost - mkt
    dev_shows_est = max(0, int(new_show_cap / 8))

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Shows Renewed",    str(len(renewed_shows)), f"${renewed_cost:.1f}M cost")
    c2.metric("Shows Cancelled",  str(len(cancelled)),     f"${freed_budget:.1f}M freed")
    c3.metric("Shows on Watch",   str(len(watch_shows)),   f"${watch_cost:.1f}M at risk")
    c4.metric("New Show Capacity",f"~{dev_shows_est} shows", f"${new_show_cap:.1f}M available")

    # Budget waterfall
    wf_labels = ["Y{} Budget".format(next_year), "Renewed Shows", "Watch Shows",
                 "Marketing", "Available for Growth"]
    wf_values = [budget_next, -renewed_cost, -watch_cost, -mkt, new_show_cap]

    fig_wf = go.Figure(go.Waterfall(
        x=wf_labels, y=[round(v,1) for v in wf_values],
        measure=["absolute","relative","relative","relative","total"],
        connector=dict(line=dict(color="#252836")),
        increasing=dict(marker_color=SUCCESS),
        decreasing=dict(marker_color=DANGER),
        totals=dict(marker_color=ACCENT),
        texttemplate="%{y:+.1f}M",
        textposition="outside",
        textfont=dict(size=10, color="#e8eaf0"),
    ))
    fig_wf.update_layout(**base_layout("Year {} Budget Waterfall ($M)".format(next_year), height=300))
    st.plotly_chart(fig_wf, use_container_width=True, config={"displayModeBar":False})

    # ── Full Decision Table ───────────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">Full Renewal Analysis Table</div>', unsafe_allow_html=True)

    display_df = decisions_df[[
        "Show","Network","Genre","Curr Cost","Renew Cost","Δ Cost",
        "Proj Rating","Proj Rev","Proj OCF","ROI Now","ROI Next","Trend","IP Score","Auto","Decision"
    ]].copy()
    display_df["Decision"] = display_df["_id"].apply(lambda i: ss.renewal_decisions.get(i,"Renew")) if "_id" in display_df else display_df["Decision"]

    def style_dec(val):
        if val=="Renew":  return "color:#81c784;font-weight:600;"
        if val=="Watch":  return "color:#ffb74d;font-weight:600;"
        return "color:#ef9a9a;font-weight:600;"

    def style_ocf(val):
        return "color:#81c784;" if val >= 0 else "color:#ef9a9a;"

    styled = (
        display_df.drop(columns=["_id"] if "_id" in display_df else [])
        .style
        .map(style_dec,  subset=["Decision"])
        .map(style_ocf,  subset=["Proj OCF"])
        .format({
            "Curr Cost":"${:.2f}M","Renew Cost":"${:.2f}M","Δ Cost":"${:.2f}M",
            "Proj Rating":"{:.2f}","Proj Rev":"${:.2f}M","Proj OCF":"${:.2f}M",
            "ROI Now":"{:.1f}%","ROI Next":"{:.1f}%"
        })
        .set_properties(**{"font-size":"11px","font-family":"DM Mono, monospace"})
    )
    st.dataframe(styled, use_container_width=True, height=400)

    # Download
    st.download_button(
        "⬇️ Download Renewal Decisions CSV",
        display_df.to_csv(index=False),
        file_name=f"cableos_renewal_year{year}.csv", mime="text/csv"
    )

    # ── IP Value vs. OCF Scatter ──────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">IP Value vs. Projected OCF — Franchise Potential</div>', unsafe_allow_html=True)
    st.markdown('<span style="font-size:11px;color:#e0e2ea;">High IP + negative OCF = renew for franchise value. Low IP + negative OCF = cancel.</span>', unsafe_allow_html=True)

    import plotly.express as px
    scatter_data = pd.DataFrame([{
        "Show": r["Show"],
        "IP Score": r["IP Score"],
        "Projected OCF": r["Proj OCF"],
        "Cost $M": r["Renew Cost"],
        "Decision": ss.renewal_decisions.get(r["_id"], "Renew"),
        "Genre": r["Genre"],
    } for r in rows])

    dec_colors = {"Renew": SUCCESS, "Watch": WARN, "Cancel": DANGER}
    fig_ip = px.scatter(scatter_data, x="IP Score", y="Projected OCF",
                         size="Cost $M", color="Decision", hover_name="Show",
                         color_discrete_map=dec_colors, size_max=28)
    fig_ip.add_hline(y=0, line_dash="dash", line_color=DANGER, opacity=0.4)
    fig_ip.add_vline(x=60, line_dash="dash", line_color=TEXT2, opacity=0.3,
                     annotation_text="IP threshold", annotation_font_color=TEXT2)
    fig_ip.update_layout(**base_layout("IP Score vs. Projected OCF — Bubble = Cost", height=360))
    fig_ip.update_traces(marker=dict(line=dict(width=1, color="#12141a")))
    st.plotly_chart(fig_ip, use_container_width=True, config={"displayModeBar":False})
