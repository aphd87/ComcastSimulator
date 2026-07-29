"""
Tab 5 — Renewal Engine
Student decides which shows to renew/cancel, models cost escalation, budget impact.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.models import (
    portfolio_ad_rev, portfolio_cost,
    distribution_revenue, renewal_decision, CONTENT_COST_ESC,
    performance_linked_growth,
)
from utils.game_state import NETWORK_INFO
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

    next_year   = year + 1
    threshold   = NETWORK_INFO[net]["pass_threshold"]
    # Budget is performance-linked (2026-07-24) — next year's figure isn't
    # knowable yet, since it depends on how THIS year's decisions play out.
    # budget_now is real (pages/simulation.py sets ss.level_budget); the
    # range below shows the best/worst case rather than a false-precision
    # single number.
    budget_now    = ss.get("level_budget") or NETWORK_INFO[net]["budget_base"]
    budget_next_lo = budget_now * performance_linked_growth(-1, threshold)      # miss margin entirely
    budget_next_hi = budget_now * performance_linked_growth(threshold, threshold)  # clear the target

    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #ffa726;
         border-radius:6px;padding:12px 16px;margin-bottom:16px;font-size:15px;color:#e0e2ea;">
    💡 <b style="color:#e8eaf0;">Renewal Economics:</b> Each renewed show costs 5% more next year.
    Your budget is performance-linked, not a flat raise — clear {threshold:.0f}% margin this year and
    next year's budget grows faster; miss it and it shrinks. Cancel low-ROI shows to free capacity
    for new IP or marketing. The IP Value score captures long-term franchise potential — sometimes a
    show worth renewing at a loss because it's building a franchise (e.g., Below Deck → 4 spinoffs).
    </div>
    """, unsafe_allow_html=True)

    # ── Budget Bridge ─────────────────────────────────────────────────────────
    c1,c2,c3,c4 = st.columns(4)
    c1.metric(f"Budget Year {year}",    f"${budget_now:.1f}M")
    c2.metric(f"Est. Year {next_year} Budget", f"${budget_next_lo:.0f}–{budget_next_hi:.0f}M",
              "depends on this year's margin")
    renewal_delta = sum(s.total_cost(next_year)-s.total_cost(year) for s in shows)
    c3.metric("Renewal Cost Increase",  f"+${renewal_delta:.1f}M", f"+{CONTENT_COST_ESC*100:.0f}% per show")
    slots = max(0, int((budget_next_lo - portfolio_cost(shows, next_year)) / 8))
    c4.metric("New Show Capacity",       f"~{slots} shows",        "worst-case budget")

    st.divider()

    # ── Genre Decay Curves ────────────────────────────────────────────────────
    # Ratings drift year over year via Show.projected_rating() (ip_score-driven
    # maturation) — that math already existed but was never plotted anywhere,
    # so decay was fully invisible to students. Surfacing it here, grouped by
    # genre, answers "how visible should decay curves be?" from Zach
    # Schlessel's feedback (DESIGN_NOTES.md) without changing the formula.
    st.markdown('<div class="section-title">Genre Decay Curves — Rating Trajectory</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:14px;color:#e0e2ea;margin-bottom:10px;">'
        'Every show\'s rating drifts year over year based on its IP score — high-IP genres '
        'compound upward (franchise value), low-IP genres decay. This is the same math behind '
        'the "Proj Rating" column below, plotted forward so the trend is visible before you decide.</div>',
        unsafe_allow_html=True)

    active_for_decay = [s for s in shows if s.id not in ss.get("cancelled_shows", set())]
    if active_for_decay:
        genre_groups = {}
        for s in active_for_decay:
            genre_groups.setdefault(s.genre, []).append(s)

        horizon = list(range(year, year + 6))
        fig_decay = go.Figure()
        palette = [ACCENT, ACCENT2, SUCCESS, WARN, DANGER, "#8e44ad", "#1a6bb5", "#c0392b"]
        for i, (genre, gshows) in enumerate(sorted(genre_groups.items())):
            avg_rating   = sum(s.rating for s in gshows) / len(gshows)
            avg_ip       = sum(s.ip_score for s in gshows) / len(gshows)
            maturation   = 1 + (avg_ip / 100) * 0.06 - 0.02
            trajectory   = [avg_rating * (maturation ** (y - year)) for y in horizon]
            fig_decay.add_trace(go.Scatter(
                x=horizon, y=[round(v, 2) for v in trajectory],
                name=f"{genre} (avg IP {avg_ip:.0f})",
                mode="lines+markers",
                line=dict(color=palette[i % len(palette)], width=2),
                marker=dict(size=6),
            ))
        fig_decay.add_vline(x=year, line_dash="dot", line_color=TEXT2, opacity=0.4,
                            annotation_text="You are here", annotation_font_color=TEXT2)
        fig_decay.update_layout(**base_layout("Projected Rating by Genre — 6-Year Trajectory", height=280))
        fig_decay.update_xaxes(title_text="Year", dtick=1)
        st.plotly_chart(fig_decay, use_container_width=True, config={"displayModeBar": False})
        st.caption("Maturation = 1 + (avg IP score / 100) × 0.06 − 0.02 per year — genres above ~33 avg IP grow, below decay. Same formula as Show.projected_rating().")

    st.divider()

    # ── Research ───────────────────────────────────────────────────────────────
    # Zach Schlessel's feedback: "Research Option: pay for a 1-5 star rating
    # prediction... students balance risk: pay for research or gamble on
    # instinct." Real stakes, not decorative — reveals the actual variance
    # draw this year's Results phase will use (utils/models.py::
    # preview_show_variance mirrors _compute_year()'s exact seeded RNG
    # sequence), and costs real budget (deducted from ss.level_budget
    # immediately, so it shows up in Financing's over-budget warning).
    RESEARCH_FEE = 2.0  # $M per show
    if "research_revealed" not in ss:
        ss.research_revealed = {}

    active_for_research = [s for s in shows if s.id not in ss.get("cancelled_shows", set())]
    if active_for_research:
        st.markdown('<div class="section-title">🔬 Research — Preview This Year\'s Variance</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:14px;color:#e0e2ea;margin-bottom:10px;">'
            f'${RESEARCH_FEE:.0f}M per show, deducted from this year\'s budget immediately. Reveals a real '
            f'1-5 star signal for how that show\'s rating will actually move this year — not a decorative '
            f'guess. Low stars mean brace for a rough year; high stars mean lean into it. Sometimes also '
            f'flags 1-2 regions the show may play well in, with a basic demo profile.</div>',
            unsafe_allow_html=True)

        with st.expander(f"🔬 Pay for Research (${RESEARCH_FEE:.0f}M/show)", expanded=False):
            from utils.models import preview_show_variance, variance_to_stars, preview_regional_signal
            nc = 4
            chunks = [active_for_research[i:i+nc] for i in range(0, len(active_for_research), nc)]
            for chunk in chunks:
                cols = st.columns(nc)
                for col, s in zip(cols, chunk):
                    with col:
                        revealed = ss.research_revealed.get(s.id)
                        if revealed and revealed.get("year") == year:
                            stars = revealed["stars"]
                            star_str = "⭐" * stars + "☆" * (5 - stars)
                            hint_c = SUCCESS if stars >= 4 else (WARN if stars == 3 else DANGER)
                            regional_html = ""
                            for r in revealed.get("regions") or []:
                                fit_c = SUCCESS if r["fit"] == "strong" else TEXT2
                                regional_html += (
                                    f'<div style="font-size:13px;color:{fit_c};font-family:DM Mono,monospace;'
                                    f'margin-top:3px;">🌍 {r["region"]} ({r["fit"]} fit)<br>'
                                    f'Median age {r["median_age"]} · HH income ${r["household_income_k"]}K</div>'
                                )
                            st.markdown(
                                f'<div style="font-size:15px;color:#e0e2ea;">{s.name[:18]}</div>'
                                f'<div style="font-size:16px;color:{hint_c};">{star_str}</div>'
                                f'{regional_html}',
                                unsafe_allow_html=True)
                        else:
                            if st.button(f"🔬 {s.name[:16]}", key=f"research_{s.id}_{year}",
                                         help=f"${RESEARCH_FEE:.0f}M — reveal this year's variance signal "
                                              f"(and sometimes a regional fit hint)"):
                                v = preview_show_variance(ss.team_name, year, shows, s.id)
                                ss.research_revealed[s.id] = {
                                    "year": year, "variance": v, "stars": variance_to_stars(v),
                                    "regions": preview_regional_signal(ss.team_name, year, s),
                                }
                                ss.level_budget = ss.get("level_budget", 0) - RESEARCH_FEE
                                st.rerun()

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

    # ── Show slate — click-to-decide cards ────────────────────────────────────
    # Replaces the old column-of-selectboxes table (2026-07-24, per user
    # feedback: "click each show, make a decision, see a schedule populate").
    # Each card carries its Renew/Watch/Cancel decision (same
    # ss.renewal_decisions mechanism as before) plus a premiere-month
    # control that writes directly to the Show object's air_month — these
    # are the same objects living in ss.oxygen_shows/etc., so the change
    # persists and immediately feeds the live schedule below and the real
    # amortization-timing math everywhere else in the app.
    st.markdown('<div class="section-title">Your Slate — Decide & Schedule Each Show</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:14px;color:#e0e2ea;margin-bottom:10px;">'
        'For each show: Renew, Watch, or Cancel, and confirm which month it premieres. '
        'The schedule below updates live as you set premiere months.</div>',
        unsafe_allow_html=True)

    show_by_id = {s.id: s for s in shows}
    nc = 3
    chunks = [rows[i:i+nc] for i in range(0, len(rows), nc)]
    for chunk in chunks:
        cols = st.columns(nc)
        for col, r in zip(cols, chunk):
            with col:
                with st.container(border=True):
                    s     = show_by_id[r["_id"]]
                    ocf_c = SUCCESS if r["Proj OCF"] >= 0 else DANGER
                    st.markdown(f"""
                    <div style="font-size:15px;font-weight:600;color:#e8eaf0;">{r['Show']}</div>
                    <div style="display:flex;gap:6px;margin:4px 0;">
                      <span class="badge badge-gray">{r['Genre']}</span>
                      <span class="badge badge-gray">{r['Network']}</span>
                    </div>
                    <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;">
                      Rating {r['Proj Rating']:.2f} · IP {r['IP Score']}
                    </div>
                    <div style="font-size:15px;font-family:DM Mono,monospace;color:{ocf_c};margin:4px 0 8px;">
                      Proj OCF ${r['Proj OCF']:+.1f}M · Auto: {r['Auto'].split()[1]}
                    </div>
                    """, unsafe_allow_html=True)

                    current = ss.renewal_decisions.get(r["_id"], "Renew")
                    choice = st.selectbox(
                        "Your decision", ["Renew", "Watch", "Cancel"],
                        index=["Renew", "Watch", "Cancel"].index(current),
                        key=f"ren_{r['_id']}",
                        help="Renew: keep it for next year at the escalated cost. Watch: keep it "
                             "for now, flagged for a closer look. Cancel: drop it (a 25% sunk-cost "
                             "penalty applies if you cancel a show mid-production).",
                    )
                    ss.renewal_decisions[r["_id"]] = choice

                    if choice != "Cancel":
                        new_month = st.number_input(
                            "Premiere month (1-12)", 1, 12, value=s.air_month,
                            key=f"premiere_{r['_id']}",
                            help="Which calendar month this show premieres — affects the amortization "
                                 "cash trough (see Scheduling): a late-month premiere means a full "
                                 "month's cost with only a few days of revenue.",
                        )
                        if new_month != s.air_month:
                            s.air_month = new_month

    # ── Live mini-schedule ────────────────────────────────────────────────────
    st.markdown('<div class="section-title" style="margin-top:14px;">This Year\'s Schedule</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;">'
        'Which shows premiere each month, updating live as you set premiere months above. '
        'Months stacked with several premieres pile up amortization cost — spread them out if '
        'your cash cows can\'t cover the gap.</div>',
        unsafe_allow_html=True)

    month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    active_this_year = [show_by_id[r["_id"]] for r in rows
                         if ss.renewal_decisions.get(r["_id"], "Renew") != "Cancel"]
    month_map = {m: [] for m in range(1, 13)}
    for s in active_this_year:
        month_map[s.air_month].append(s.name)

    sched_cols = st.columns(12)
    for i, col in enumerate(sched_cols):
        m = i + 1
        names = month_map[m]
        count = len(names)
        bg = "rgba(232,197,71,.18)" if count >= 3 else ("rgba(232,197,71,.07)" if count >= 1 else "#12141a")
        title_attr = ", ".join(names) if names else "No premieres"
        col.markdown(f"""
        <div title="{title_attr}" style="background:{bg};border:1px solid #252836;border-radius:6px;
             padding:6px 2px;text-align:center;min-height:56px;">
          <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;">{month_names[i]}</div>
          <div style="font-size:16px;font-family:DM Serif Display,serif;color:#e8eaf0;margin-top:4px;">{count}</div>
        </div>
        """, unsafe_allow_html=True)
    st.caption("Number = shows premiering that month. Hover a column for names.")

    # ── Budget Impact ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">Budget Impact of Your Decisions</div>', unsafe_allow_html=True)

    renewed_shows  = [r for r in rows if ss.renewal_decisions.get(r["_id"],"Renew") == "Renew"]
    cancelled      = [r for r in rows if ss.renewal_decisions.get(r["_id"],"Renew") == "Cancel"]
    watch_shows    = [r for r in rows if ss.renewal_decisions.get(r["_id"],"Renew") == "Watch"]

    renewed_cost  = sum(r["Renew Cost"] for r in renewed_shows)
    freed_budget  = sum(r["Renew Cost"] for r in cancelled)
    watch_cost    = sum(r["Renew Cost"] for r in watch_shows)
    new_show_cap  = budget_next_lo - renewed_cost - watch_cost - mkt
    dev_shows_est = max(0, int(new_show_cap / 8))

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Shows Renewed",    str(len(renewed_shows)), f"${renewed_cost:.1f}M cost")
    c2.metric("Shows Cancelled",  str(len(cancelled)),     f"${freed_budget:.1f}M freed")
    c3.metric("Shows on Watch",   str(len(watch_shows)),   f"${watch_cost:.1f}M at risk")
    c4.metric("New Show Capacity",f"~{dev_shows_est} shows", f"${new_show_cap:.1f}M available (worst-case budget)")

    # Budget waterfall
    wf_labels = ["Y{} Budget (worst-case)".format(next_year), "Renewed Shows", "Watch Shows",
                 "Marketing", "Available for Growth"]
    wf_values = [budget_next_lo, -renewed_cost, -watch_cost, -mkt, new_show_cap]

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
    st.markdown('<span style="font-size:14px;color:#e0e2ea;">High IP + negative OCF = renew for franchise value. Low IP + negative OCF = cancel.</span>', unsafe_allow_html=True)

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
