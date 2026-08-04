"""
Tab 4 — Green Light Model
Student builds a show concept and compares Linear vs. SVOD P&L.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.models import greenlight_linear, greenlight_svod, ltv_curve, HOURLY_INDEX, HOUR_LABELS, Show
from utils.charts import base_layout, ACCENT, ACCENT2, SUCCESS, DANGER, WARN, TEXT2
from utils.data import BRAVO_SLATE, OXYGEN_SLATE, PEACOCK_SLATE
from utils.game_state import NETWORK_INFO, MAX_NEW_SHOWS_PER_YEAR

_GENRES = ["Reality", "Competition", "Talk", "Scripted", "True Crime", "Drama"]
_NEW_SHOW_IP_SCORE = 40   # unproven new IP -- just above the ~33 flat-maturation threshold
                           # (Show.projected_rating's decay formula), so a fresh concept trends
                           # mildly upward rather than assuming instant franchise value

# Protected titles — every real show name already in this game's own data.
# Zach Schlessel's feedback: "Risk = 0 score: take an existing show title
# without permission (gets sued) — originality matters." Reuses existing
# data rather than a separate hardcoded list, so it stays in sync if the
# slates change.
_PROTECTED_TITLES = {s.name.strip().lower() for s in (BRAVO_SLATE + OXYGEN_SLATE + PEACOCK_SLATE)}


def render():
    ss   = st.session_state
    year = ss.get("year", 1)

    # Slot tracking moved up here (2026-08-04) so the AI Pitch Generator
    # below can know how many greenlight slots are left before generating
    # another idea — previously this only got computed right before the
    # Greenlight button, well after the pitch generator had already rendered.
    if "greenlit_ids_this_year" not in ss:
        ss.greenlit_ids_this_year = set()
    if "greenlit_ids_this_level" not in ss:
        ss.greenlit_ids_this_level = set()
    if "total_shows_greenlit" not in ss:
        ss.total_shows_greenlit = 0
    if "next_show_id" not in ss:
        ss.next_show_id = 51   # one past the highest ID in utils/data.py's original slates

    slots_used = len(ss.greenlit_ids_this_year)
    slots_left = MAX_NEW_SHOWS_PER_YEAR - slots_used

    st.markdown("""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #4fc3f7;
         border-radius:6px;padding:12px 16px;margin-bottom:16px;font-size:15px;color:#e0e2ea;">
    💡 <b style="color:#e8eaf0;">The Core Decision:</b> Do you put this show on Bravo (linear) or SVOD+?  
    In 2012, linear wins on immediate cash — faster ad revenue, no subscriber acquisition cost.  
    By Year 7+, SVOD subscription LTV starts to outpace a declining ad market. Build the P&L for both.
    </div>
    """, unsafe_allow_html=True)

    # ── AI Pitch Generator (optional, BYOK — see README.md) ─────────────────────
    # Complements AI Pitch Feedback below: that grades a pitch the student
    # already wrote, this proposes a starting concept for a student who's
    # stuck on ideation. Either path leads to the same concept builder below.
    from utils.ai_grading import api_key_configured, grade_show_concept, generate_show_pitch

    if api_key_configured():
        gp1, gp2 = st.columns([3, 1])
        with gp1:
            if slots_left > 0:
                st.markdown(
                    f'<div style="font-size:14px;color:#b0b5c4;">Stuck on an idea? Get an AI-proposed '
                    f'concept to start from — you can still edit every field below before greenlighting. '
                    f'You have <b style="color:#e8eaf0;">{slots_left} of {MAX_NEW_SHOWS_PER_YEAR}</b> '
                    f'greenlight slots left this year, so keep asking for another pitch until one '
                    f'clicks.</div>',
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div style="font-size:14px;color:#b0b5c4;">You\'ve filled all your greenlight '
                    'slots for this year — no need for another pitch until next year.</div>',
                    unsafe_allow_html=True)
        with gp2:
            pitch_label = "🎲 Hear Another Pitch" if ss.get("gl_ai_pitch_text") else "🤖 Get an AI Pitch Idea"
            if slots_left > 0 and st.button(pitch_label, key="gl_generate_pitch", use_container_width=True):
                with st.spinner("Generating a pitch..."):
                    idea = generate_show_pitch(NETWORK_INFO[ss.active_network]["display_name"])
                if idea is None:
                    st.error("AI pitch generation is temporarily unavailable. Try again later.")
                else:
                    st.session_state["gl_show_name"] = idea.show_name
                    st.session_state["gl_genre"]     = idea.genre if idea.genre in _GENRES else _GENRES[0]
                    st.session_state["gl_eps"]        = idea.suggested_episodes
                    st.session_state["gl_ep_cost"]    = idea.suggested_ep_cost_k
                    st.session_state["gl_rating"]     = idea.suggested_rating
                    st.session_state["gl_appeal"]     = idea.suggested_svod_appeal
                    ss.gl_ai_pitch_text = idea.pitch
                    st.rerun()
        if slots_left > 0 and ss.get("gl_ai_pitch_text"):
            st.markdown(
                f'<div style="background:#12141a;border:1px solid #252836;border-radius:6px;'
                f'padding:10px 14px;margin-bottom:10px;font-size:15px;color:#e0e2ea;">'
                f'💡 <b>AI pitch:</b> {ss.gl_ai_pitch_text}</div>', unsafe_allow_html=True)

    # ── Show Concept Builder ───────────────────────────────────────────────────
    st.markdown('<div class="section-title">Show Concept Inputs</div>', unsafe_allow_html=True)

    with st.container():
        c1,c2,c3 = st.columns(3)
        with c1:
            show_name = st.text_input("Show Name / Concept", "My New Show", key="gl_show_name")
            genre     = st.selectbox("Genre", _GENRES, key="gl_genre")
            eps       = st.number_input("Episode Count", 4, 24, 10, step=1, key="gl_eps")
        with c2:
            ep_cost   = st.number_input("Cost per Episode ($K)", 100, 5000, 750, step=50,
                                         help="Bravo reality ~$650-900K. Scripted ~$1-2M.", key="gl_ep_cost")
            rating    = st.slider("Projected Rating (18-49)", 0.3, 4.0, 1.2, step=0.1,
                                   help="Bravo avg: 1.0–1.5. Hit show: 2.0+. Mega-hit: 3.0+", key="gl_rating")
            mkt_spend = st.slider("Marketing Budget ($M)", 0.0, 10.0, 2.0, step=0.5,
                                   help="Each $1M adds ~1.5% rating lift on linear; also lifts SVOD sub acquisition.", key="gl_mkt_spend")
        with c3:
            appeal    = st.slider("Genre Appeal Score (SVOD)", 20, 100, 72, step=1,
                                   help="How well does this genre convert to streaming subscriptions? "
                                        "True Crime: 85. Scripted drama: 90. Reality: 60.", key="gl_appeal")
            air_month = st.slider("Premiere Month", 1, 12, 3, step=1,
                                   format="%d", help="Affects amortization cash trough (see Schedule tab).", key="gl_air_month")
            svod_prem = st.number_input("SVOD Monthly Premium ($/sub)", 5.0, 20.0, 8.0, step=0.5,
                                         help="Price premium vs. baseline. Higher = more LTV per acquired sub.", key="gl_svod_prem")

    # ── AI Pitch Feedback (optional, BYOK — see README.md) ──────────────────────
    from utils.ai_grading import api_key_configured, grade_show_concept

    st.divider()
    st.markdown(
        '<div class="section-title">AI Pitch Feedback '
        '<span style="font-size:14px;color:#b0b5c4;">(optional)</span></div>',
        unsafe_allow_html=True,
    )

    if not api_key_configured():
        st.markdown(
            '<div style="font-size:14px;color:#b0b5c4;">'
            'Ask your instructor to enable AI feedback for this class.</div>',
            unsafe_allow_html=True,
        )
    else:
        pitch = st.text_area(
            "Describe your show concept in your own words (2-4 sentences)",
            placeholder="e.g. A competition show where design students renovate a real "
                        "small business on a shoestring budget...",
            key="gl_pitch_text",
        )
        if st.button("🤖 Get AI Feedback", key="gl_grade_button"):
            if not pitch.strip():
                st.warning("Write a short pitch first.")
            else:
                with st.spinner("Grading your pitch..."):
                    grade = grade_show_concept(show_name, genre, pitch)
                if grade is None:
                    st.error("AI feedback is temporarily unavailable. Try again later.")
                else:
                    total = (grade.originality_score + grade.market_fit_score
                              + grade.feasibility_score + grade.presentation_score)
                    st.markdown(f"**Score: {total}/100**")
                    st.write(grade.feedback)
                    gc1, gc2 = st.columns(2)
                    with gc1:
                        st.markdown("**Strengths**")
                        for s in grade.strengths:
                            st.markdown(f"- {s}")
                    with gc2:
                        st.markdown("**Risks**")
                        for r in grade.risks:
                            st.markdown(f"- {r}")
                    if grade.research_recommended:
                        st.info(
                            f"🔬 **Worth paying for Research on this one** once it's in your "
                            f"portfolio — {grade.research_rationale}",
                        )
                    else:
                        st.caption(f"🔬 Probably not worth paying for Research on this one — "
                                   f"{grade.research_rationale}")

    st.divider()

    # ── Title / IP legal-risk check ─────────────────────────────────────────────
    title_collision = show_name.strip().lower() in _PROTECTED_TITLES
    if title_collision:
        st.markdown(f"""
        <div style="background:rgba(239,83,80,.08);border:1px solid rgba(239,83,80,.4);
             border-left:3px solid {DANGER};border-radius:6px;padding:14px 18px;margin-bottom:16px;">
          <div style="font-size:15px;color:{DANGER};font-weight:600;margin-bottom:4px;">
            🚫 Legal Risk — Title Already Exists
          </div>
          <div style="font-size:15px;color:#e0e2ea;">
            "<b>{show_name}</b>" is already an existing title in this universe. Using it without
            permission gets you sued — <b>Risk Score: 0</b>. Rename the concept to something
            original before building a P&L on it.
          </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Calculate ─────────────────────────────────────────────────────────────
    linear = greenlight_linear(eps, ep_cost, rating, mkt_spend, year)
    svod   = greenlight_svod(eps, ep_cost, rating, appeal, mkt_spend, year)
    # Override SVOD LTV with student's premium
    svod["ltv_3yr"] = svod["sub_lift"] * svod_prem * 12 * 0.15 * 3
    svod["revenue"] = svod["ltv_3yr"] / 3
    svod["ocf"]     = svod["revenue"] - linear["cost"] - mkt_spend
    svod["roi"]     = (svod["ocf"] / linear["cost"] * 100) if linear["cost"] else 0

    st.divider()

    # ── Greenlight This Show — actually adds it to the real roster ─────────────
    # Added 2026-07-27: Greenlighting was previously a standalone P&L
    # sandbox that never touched real game state. Cap of MAX_NEW_SHOWS_PER_YEAR
    # matches real network development slates (a handful of new titles per
    # season against a 20-40 show base) — budget already gates spending on
    # top of this, this caps pacing/portfolio growth. (Slot tracking itself
    # now lives at the top of render() -- see the comment there.)
    net_display = NETWORK_INFO[ss.active_network]["display_name"]

    st.markdown('<div class="section-title">🎬 Greenlight This Show</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;">'
        f'Adds this concept to {net_display}\'s real roster — production cost (${linear["cost"]:.2f}M) '
        f'comes out of this year\'s budget immediately, and it starts earning/costing real money '
        f'starting this year. You\'ve greenlit {slots_used} of {MAX_NEW_SHOWS_PER_YEAR} new shows this year.</div>',
        unsafe_allow_html=True)

    if slots_left <= 0:
        st.warning(f"⚠ You've used all {MAX_NEW_SHOWS_PER_YEAR} greenlight slots for this year — "
                    "come back next year for more.")
    elif st.button(f"🎬 Greenlight \"{show_name}\" for {net_display}", type="primary", use_container_width=True):
        new_show = Show(
            id=ss.next_show_id, name=show_name.strip(), genre=genre, episodes=eps,
            ep_cost_k=ep_cost, rating=rating, ip_score=_NEW_SHOW_IP_SCORE,
            air_month=air_month, network=net_display,
        )
        roster_key = f"{ss.active_network}_shows"
        ss[roster_key] = ss[roster_key] + [new_show]
        ss.level_budget = ss.get("level_budget", 0) - linear["cost"]   # production cost, unescalated (year-1 basis)
        ss.greenlit_ids_this_year.add(new_show.id)
        ss.greenlit_ids_this_level.add(new_show.id)
        ss.total_shows_greenlit += 1
        ss.next_show_id += 1
        st.rerun()   # note: a st.success() here would never render — rerun replaces the DOM
                     # immediately. The updated "X of N greenlit" count above is the confirmation.

    st.divider()

    # ── Side-by-side P&L ──────────────────────────────────────────────────────
    # Moved to after Greenlight This Show 2026-08-04 per user request -- the
    # comparison reads as reference/justification for the greenlight call,
    # so it belongs after the actual action, not gating it.
    st.markdown('<div class="section-title">Platform P&L Comparison</div>', unsafe_allow_html=True)

    def pl_card(title, color, data, winner=False):
        border = f"border:2px solid {color};" if winner else f"border:1px solid #252836;"
        rows = "".join([
            f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
            f'border-bottom:1px solid rgba(37,40,54,.5);font-size:15px;">'
            f'<span style="color:#e0e2ea;">{k}</span>'
            f'<span style="font-family:DM Mono,monospace;color:{vc};">{v}</span></div>'
            for k,v,vc in data
        ])
        w_badge = f'<span style="background:{color};color:#0b0c10;font-size:14px;padding:2px 8px;border-radius:3px;font-family:DM Mono,monospace;">WINNER</span>' if winner else ''
        return f"""
        <div style="background:#1a1d26;{border}border-radius:8px;padding:16px;height:100%;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <span style="font-family:DM Mono,monospace;font-size:14px;text-transform:uppercase;
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
    st.markdown('<span style="font-size:14px;color:#e0e2ea;">Linear OCF ($M) at different rating × cost combinations. Green = profitable, Red = cancel.</span>', unsafe_allow_html=True)

    rating_range = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
    cost_range   = [300, 500, 750, 1000, 1500, 2000]

    rating_cols = [f"{r:.1f}" for r in rating_range]
    sens_rows = []
    for ep_c in cost_range:
        row = {"Ep Cost": f"${ep_c}K"}
        for r in rating_range:
            lin = greenlight_linear(eps, ep_c, r, mkt_spend, year)
            row[f"{r:.1f}"] = round(lin["ocf"], 2)
        sens_rows.append(row)

    sens_df = pd.DataFrame(sens_rows)

    def color_cells(val):
        try:
            v = float(val)
            if v > 5:   return "background-color:rgba(102,187,106,.25);color:#81c784;"
            if v > 0:   return "background-color:rgba(255,167,38,.15);color:#ffb74d;"
            return "background-color:rgba(239,83,80,.2);color:#ef9a9a;"
        except: return ""

    st.dataframe(
        sens_df.style
        .map(color_cells, subset=rating_cols)
        .format("{:.2f}", subset=rating_cols)
        .hide(axis="index"),
        use_container_width=True
    )
    st.caption("Rows = episode cost (Ep Cost col). Columns = projected 18-49 rating. Cell = Linear OCF in $M.")

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
