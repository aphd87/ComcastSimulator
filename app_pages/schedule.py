"""
Tab 2 — Schedule & Amortization
Premiere-day cash trough, monthly amortization grid, scheduling optimizer.
"""
import streamlit as st
from utils.game_state import level_shows
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from utils.models import (
    distribution_revenue, portfolio_ad_rev, AMORT_MONTHS_LINEAR, AMORT_MONTHS_SVOD,
    TRUE_CRIME_AMORT_MONTHS,
    MONTHS, HOUR_LABELS, HOURLY_INDEX,
)
from utils.charts import (
    base_layout, bar_chart, line_chart, takeaway, html_table,
    ACCENT, ACCENT2, SUCCESS, DANGER, WARN, TEXT2, BORDER, SURFACE, SURFACE2
)


def render():
    ss   = st.session_state
    year = ss.get("year", 1)
    mkt  = ss.get("mkt_budget", 5.0)

    net = ss.get("active_network", "oxygen")
    shows = level_shows(ss, net)
    # Explanations name only the amortization windows this level's slate
    # actually uses (2026-11-03: Bravo is Bravo-only now, so True Crime /
    # Peacock wording there would describe shows the student doesn't have).
    has_tc = any(s.genre == "True Crime" and s.network != "Peacock" for s in shows)
    has_pk = any(s.network == "Peacock" for s in shows)
    _win = ["12 for linear shows"] + (["24 for True Crime"] if has_tc else []) + (["36 for Peacock"] if has_pk else [])
    _long = " / ".join((["True Crime"] if has_tc else []) + (["Peacock"] if has_pk else []))

    # ── Section 1: Premiere Day Risk ─────────────────────────────────────────
    st.markdown('<div class="section-title">Premiere Day Cash Trough — The March Problem</div>', unsafe_allow_html=True)

    st.markdown(
        '<div style="font-size:14px;color:#ffffff;margin-bottom:10px;">'
        "This is a practice sandbox, not part of your score — it isolates just this one mechanic "
        "(launch day vs. monthly amortization billing, freely adjustable below) so you can see the "
        "cash-timing effect on its own, before applying the intuition for real in Renewal, where "
        "premiere month is bundled together with your actual renew/cancel/schedule decisions.</div>",
        unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #e8c547;
         border-radius:6px;padding:12px 16px;margin-bottom:12px;font-size:15px;color:#ffffff;">
    💡 <b style="color:#ffffff;">Key insight:</b> From its premiere month on, a show charges its season cost ÷ its
    amortization months ({", ".join(_win)}) on the 1st of every month,
    whatever day it premieres. A March 30 launch absorbs a full monthly charge with only 2 days of ad revenue.
    Your cash cows must fund this gap.
    </div>
    """, unsafe_allow_html=True)

    # Student inputs
    # A bordered container, not st.expander: this tool renders inside the
    # "Supplementary Insights" expander in simulation.py, and Streamlit
    # <= ~1.45 raises StreamlitAPIException for an expander nested in an
    # expander (newer versions allow it, which is why tests on 1.59 missed it).
    with st.container(border=True):
        st.markdown("**🎛️ Configure Premiere Day Scenario**")
        c1,c2,c3,c4 = st.columns(4)
        # Prioritize the currently active network's own shows before
        # truncating to 10 (2026-08-24 fix, found in a QA pass) -- `shows`
        # is always built Oxygen-first regardless of which network is
        # actually being played, so this dropdown could never surface a
        # Bravo or Peacock show without scrolling past 10 Oxygen titles
        # that aren't even part of the level currently in progress.
        active_display = net.capitalize()
        shows_for_dropdown = sorted(shows, key=lambda s: s.network != active_display)
        pd_show_name = c1.selectbox("Show", [s.name for s in shows_for_dropdown[:10]], key="sched_show",
                                     help="Loads this show's real episode count and per-episode cost below — "
                                          "still yours to edit if you want to explore a hypothetical instead.")
        pd_launch    = c2.radio("Launch Day", [1, 15, 30], horizontal=True,
                                help="Day of month the show premieres", key="sched_launch_day")
        # Defaults come from the selected show's real numbers, not a fixed
        # placeholder — the key is scoped to the show name so switching the
        # dropdown loads that show's actual figures instead of carrying over
        # whatever was typed for the previous selection.
        selected_show = next((s for s in shows if s.name == pd_show_name), None)
        eps_default   = selected_show.episodes if selected_show else 10
        cost_default  = int(selected_show.ep_cost_k) if selected_show else 750
        pd_eps       = c3.number_input("Episode Count", 6, 24, eps_default, key=f"sched_eps_{pd_show_name}")
        pd_cost_k    = c4.number_input("Cost/Episode ($K)", 100, 3000, cost_default, step=50,
                                        key=f"sched_cost_k_{pd_show_name}")

    total_season_cost = pd_eps * pd_cost_k / 1000     # $M
    amort_months      = selected_show.effective_amort_months() if selected_show else AMORT_MONTHS_LINEAR
    monthly_amort     = total_season_cost / amort_months   # $M per month, same rule as the P&L
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
          <div style="font-family:'DM Mono',monospace;font-size:14px;color:#ffffff;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;">Day {pd_launch} Launch</div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:15px;">
            <span style="color:#ffffff;">Monthly amort bill</span>
            <span style="font-family:'DM Mono',monospace;color:#ffa726;">${monthly_amort:.3f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:15px;">
            <span style="color:#ffffff;">Revenue days in month</span>
            <span style="font-family:'DM Mono',monospace;{'color:#66bb6a' if revenue_days > 15 else 'color:#ef5350'};">{revenue_days}</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:15px;">
            <span style="color:#ffffff;">Ad revenue earned</span>
            <span style="font-family:'DM Mono',monospace;color:#66bb6a;">${month_rev:.3f}M</span>
          </div>
          <div style="border-top:1px solid #252836;margin-top:10px;padding-top:10px;display:flex;justify-content:space-between;font-size:16px;font-weight:600;">
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
          <div style="font-family:'DM Mono',monospace;font-size:14px;color:#ffffff;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;">Day 1 Baseline</div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:15px;">
            <span style="color:#ffffff;">Monthly amort bill</span>
            <span style="font-family:'DM Mono',monospace;color:#ffa726;">${monthly_amort:.3f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:15px;">
            <span style="color:#ffffff;">Revenue days in month</span>
            <span style="font-family:'DM Mono',monospace;color:#66bb6a;">31</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:15px;">
            <span style="color:#ffffff;">Ad revenue earned</span>
            <span style="font-family:'DM Mono',monospace;color:#66bb6a;">${mar1_rev:.3f}M</span>
          </div>
          <div style="border-top:1px solid #252836;margin-top:10px;padding-top:10px;display:flex;justify-content:space-between;font-size:16px;font-weight:600;">
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
          <div style="font-family:'DM Mono',monospace;font-size:14px;color:#ffffff;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;">Cash Gap Analysis</div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:15px;">
            <span style="color:#ffffff;">Revenue shortfall vs. Day 1</span>
            <span style="font-family:'DM Mono',monospace;color:#ef5350;">${abs(gap):.3f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:15px;">
            <span style="color:#ffffff;">Cash cow monthly rev</span>
            <span style="font-family:'DM Mono',monospace;color:#66bb6a;">${cow_coverage:.3f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:15px;">
            <span style="color:#ffffff;">Reserve needed</span>
            <span style="font-family:'DM Mono',monospace;color:#ffa726;">${max(0,-net_position):.3f}M</span>
          </div>
          <div style="border-top:1px solid #252836;margin-top:10px;padding-top:10px;font-size:15px;">
            <span style="color:{'#66bb6a' if '✅' in funded else '#ef5350'};">{funded}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    if pd_launch == 1:
        takeaway(f"A day-1 launch earns a full month of ad revenue against the ${monthly_amort:.3f}M monthly "
                 f"charge. Try day 30 to see the trough: the charge is the same, but revenue shrinks to 2 days.")
    else:
        takeaway(f"Premiering on day {pd_launch} instead of day 1 costs <b>${abs(gap):.3f}M</b> of revenue in "
                 f"the premiere month, while the ${monthly_amort:.3f}M charge stays the same. "
                 + ("Your cash cows cover it this time." if "✅" in funded else
                    "Your cash cows can't cover it, so premiere earlier in the month or hold a reserve."))

    st.divider()

    # ── Section 2: Amortization Table (rebuilt 2026-11-03) ───────────────────
    # The old heatmap put each show's bill only in its on-air months and
    # divided by a different number than the P&L did, so its totals never
    # matched Content Cost. This table uses the P&L's own rule
    # (Show.annual_amort_expense) so its total IS the Content Cost line.
    st.markdown('<div class="section-title">Amortization Table — What Each Show Costs You This Year</div>',
                unsafe_allow_html=True)
    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;padding:12px 16px;
         margin-bottom:12px;font-size:15px;color:#ffffff;line-height:1.7;">
    <b>How amortization works here.</b> A season is paid for up front (episodes × cost per episode), but the
    P&amp;L doesn't take the whole hit at once. It spreads the season cost evenly over a set number of months:
    <br>• <b>{AMORT_MONTHS_LINEAR} months</b> for {"most " if (has_tc or has_pk) else ""}linear (cable) shows, so the full cost lands this year
    {f"<br>• <b>{TRUE_CRIME_AMORT_MONTHS} months</b> for True Crime, which keeps earning in reruns, so half lands this year" if has_tc else ""}
    {f"<br>• <b>{AMORT_MONTHS_SVOD} months</b> for Peacock (streaming) shows, so a third lands this year" if has_pk else ""}
    <br><b>Monthly charge</b> = season cost ÷ months. <b>Charged this year</b> = monthly charge × 12. The rest is
    pushed into later years. A show you cancel this year costs 25% of its normal charge (work already done).
    Premiere month does <b>not</b> change the yearly charge; it only changes <i>when</i> ad revenue arrives (chart below).
    </div>
    """, unsafe_allow_html=True)

    prev_cancel = ss.get("cancelled_shows", set())
    renew       = ss.get("renewal_decisions", {})
    new_ids     = ss.get("greenlit_ids_this_year", set())
    active      = [s for s in shows if s.id not in prev_cancel]

    def _rule(s):
        if s.network == "Peacock":
            return f"{AMORT_MONTHS_SVOD} (streaming)"
        if s.genre == "True Crime":
            return f"{TRUE_CRIME_AMORT_MONTHS} (True Crime)"
        return f"{AMORT_MONTHS_LINEAR} (linear)"

    def _air_span(s):
        months = s.cash_months(s.air_month, s.episodes)
        return f"{MONTHS[months[0]]}–{MONTHS[months[-1]]}" if len(months) > 1 else MONTHS[months[0]]

    amort_rows, totals = [], {"season": 0.0, "charged": 0.0, "later": 0.0}
    for s in sorted(active, key=lambda s: -s.annual_amort_expense(year)):
        season  = s.total_cost(year)
        A       = s.effective_amort_months()
        annual  = s.annual_amort_expense(year)
        cancel  = renew.get(s.id) == "Cancel"
        charged = annual * 0.25 if cancel else annual
        later   = 0.0 if cancel else max(season - annual, 0.0)
        totals["season"] += season; totals["charged"] += charged; totals["later"] += later
        amort_rows.append({
            "Show":              s.name,
            "Network":           s.network,
            "Genre":             s.genre,
            "Episodes × Cost":   f"{s.episodes} × ${s.ep_cost_k:,.0f}K",
            "Season Cost":       f"${season:.2f}M",
            "Spread Over (mo)":  _rule(s),
            "Monthly Charge":    f"${season / A:.3f}M",
            "Charged This Year": f"${charged:.2f}M",
            "Pushed to Later Years": f"${later:.2f}M" if later else "—",
            "On Air":            _air_span(s),
            "Status":            "Cancel (25% charge)" if cancel else ("New this year" if s.id in new_ids else "Returning"),
        })
    if amort_rows:
        html_table(pd.DataFrame(amort_rows), total_row={
            "Show": "TOTAL", "Season Cost": f"${totals['season']:.2f}M",
            "Charged This Year": f"${totals['charged']:.2f}M",
            "Pushed to Later Years": f"${totals['later']:.2f}M" if totals["later"] else "—"})
        top = max(active, key=lambda s: s.annual_amort_expense(year) * (0.25 if renew.get(s.id) == "Cancel" else 1))
        top_charge = top.annual_amort_expense(year) * (0.25 if renew.get(top.id) == "Cancel" else 1)
        share = top_charge / totals["charged"] * 100 if totals["charged"] else 0
        deferred = (f" <b>${totals['later']:.1f}M</b> is pushed into later years by the longer {_long} "
                    f"window{'s' if has_tc and has_pk else ''}, which flatters this year's margin but is a bill you still owe."
                    if totals["later"] > 0.05 else
                    " Nothing is pushed into later years: every show here is a 12-month linear show.")
        takeaway(
            f"Your active shows cost <b>${totals['season']:.1f}M</b> to make; <b>${totals['charged']:.1f}M</b> "
            f"of that hits this year's P&amp;L (the <b>Content Cost</b> line in Expected This Year, before any "
            f"sports rights).{deferred} Your biggest charge is <b>{top.name}</b> at ${top_charge:.1f}M "
            f"({share:.0f}% of the total), so it has to earn its keep in Renewal.")
    else:
        st.caption("No active shows yet.")

    st.divider()

    # ── Section 2b: Payoff Schedule (2026-11-03, per user request) ───────────
    # "How a TV series is paid off over time": this season's cost spread
    # across this year and the next one or two, by amortization window. Same
    # rule as the table above (season cost ÷ months, 12 months per year), so
    # the "This Year" column equals the table's "Charged This Year".
    st.markdown('<div class="section-title">Payoff Schedule — How This Season Gets Paid Off Over Time</div>',
                unsafe_allow_html=True)
    _longer = ("A True Crime show takes two years and a Peacock show three" if has_tc and has_pk else
               "A True Crime show takes two years" if has_tc else
               "A Peacock show takes three years" if has_pk else "")
    st.markdown(f"""
    <div style="font-size:15px;color:#ffffff;margin-bottom:10px;">
    Each bar is one year of P&amp;L charges for the seasons you're making <b>now</b>. A 12-month linear show is
    paid off within this year. {(_longer + ", so part of this year's spending keeps showing up in your future "
    "P&amp;Ls.") if _longer else "Every show on this slate is a 12-month linear show, so the whole cost lands "
    "this year and nothing carries into future P&amp;Ls (that's why Bravo's costs hit harder)."} Renewing a
    show adds <i>next</i> season's cost on top of these bars.
    </div>
    """, unsafe_allow_html=True)

    group_of = lambda s: ("Peacock (36 mo)" if s.network == "Peacock" else
                          "True Crime (24 mo)" if s.genre == "True Crime" else "Linear (12 mo)")
    group_colors = {"Linear (12 mo)": ACCENT, "True Crime (24 mo)": WARN, "Peacock (36 mo)": ACCENT2}
    paying = [s for s in active if renew.get(s.id) != "Cancel"]
    year_cols = [f"Year {year}", f"Year {year + 1}", f"Year {year + 2}"]
    by_group = {g: [0.0, 0.0, 0.0] for g in group_colors}
    payoff_rows = []
    for s in sorted(paying, key=lambda s: -s.total_cost(year)):
        season, A = s.total_cost(year), s.effective_amort_months()
        per_year = [season * min(12, max(A - 12 * k, 0)) / A for k in range(3)]
        for k in range(3):
            by_group[group_of(s)][k] += per_year[k]
        payoff_rows.append({
            "Show": s.name, "Window": group_of(s), "Season Cost": f"${season:.2f}M",
            **{c: (f"${v:.2f}M" if v else "—") for c, v in zip(year_cols, per_year)},
            "Paid Off By": f"End of Year {year + A // 12 - 1}",
        })

    if payoff_rows:
        fig_po = go.Figure()
        for g, vals in by_group.items():
            if any(vals):
                fig_po.add_trace(go.Bar(name=g, x=year_cols, y=[round(v, 2) for v in vals],
                                        marker_color=group_colors[g], opacity=0.85,
                                        text=[f"${v:.1f}M" if v else "" for v in vals],
                                        textposition="inside"))
        fig_po.update_layout(**base_layout("This Season's Cost, Charged by Year ($M)", height=300),
                             barmode="stack")
        st.plotly_chart(fig_po, use_container_width=True, config={"displayModeBar": False})

        st.dataframe(pd.DataFrame(payoff_rows), use_container_width=True, hide_index=True)
        later = sum(sum(v[1:]) for v in by_group.values())
        now = sum(v[0] for v in by_group.values())
        takeaway((f"<b>${now:.1f}M</b> of this season's cost is charged this year and <b>${later:.1f}M</b> "
                  f"rolls into the next two years. That deferred amount is already spent: it will lower "
                  f"future margins even if you make no new shows."
                  if later > 0.05 else
                  f"All <b>${now:.1f}M</b> of this season's cost is charged this year: every show is a "
                  f"12-month linear show, so nothing carries into future years."))
    else:
        st.caption("No shows being paid off this year.")

    st.divider()

    # ── Section 3: Monthly Cash Flow ────────────────────────────────────────
    # Costs are charged evenly every month; ad revenue only arrives while a
    # show is on air (its cash_months). That timing gap is the lesson; the
    # yearly totals match the P&L preview (before marketing and G&A).
    st.markdown('<div class="section-title">Monthly Cash Flow — When Money Comes In vs. Goes Out</div>',
                unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:15px;color:#ffffff;margin-bottom:10px;">
    <b>Red</b> = the amortization charge from the table above, the same every month.
    <b>Green</b> = ad revenue, earned only in the months each show is on air (about 2 episodes a month, from its
    premiere month). <b>Blue</b> = distribution fees from cable operators, steady all year.
    <b>Gold line</b> = net for the month. Months below zero are squeeze months your hit shows have to carry.
    </div>
    """, unsafe_allow_html=True)

    earning  = [s for s in active if renew.get(s.id) != "Cancel"]
    per_show = mkt / max(len(earning), 1)
    monthly_rev = [0.0] * 12
    for s in earning:
        months = s.cash_months(s.air_month, s.episodes)
        for m in months:
            monthly_rev[m] += s.ad_revenue(year, per_show) / len(months)
    monthly_dist = [distribution_revenue(year) / 12] * 12
    monthly_cost = [totals["charged"] / 12] * 12
    monthly_net  = [monthly_rev[i] + monthly_dist[i] - monthly_cost[i] for i in range(12)]

    bridge_df = pd.DataFrame({
        "Month": MONTHS,
        "Ad Revenue":    [round(v, 2) for v in monthly_rev],
        "Distribution":  [round(v, 2) for v in monthly_dist],
        "Content Cost":  [round(v, 2) for v in monthly_cost],
        "Net Cash Flow": [round(v, 2) for v in monthly_net],
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
    fig_b.update_layout(**base_layout("Monthly Cash Flow ($M), before marketing and G&A", height=320),
                        barmode="relative")
    st.plotly_chart(fig_b, use_container_width=True, config={"displayModeBar": False})

    squeeze = [MONTHS[i] for i in range(12) if monthly_net[i] < 0]
    best_i  = max(range(12), key=lambda i: monthly_rev[i])
    worst_i = min(range(12), key=lambda i: monthly_net[i])
    if squeeze:
        cushion = sum(-v for v in monthly_net if v < 0)
        msg = (f"<b>{len(squeeze)} squeeze month{'s' if len(squeeze) != 1 else ''}</b> ({', '.join(squeeze)}): "
               f"costs keep coming while few shows are on air. The worst is <b>{MONTHS[worst_i]}</b> at "
               f"${monthly_net[worst_i]:+.2f}M, and together they need a <b>${cushion:.2f}M</b> cushion. "
               f"Moving a premiere into a squeeze month (in Renewal) spreads revenue more evenly.")
    else:
        msg = (f"No month runs negative: on-air revenue plus distribution covers the monthly charge all year. "
               f"Your weakest month is <b>{MONTHS[worst_i]}</b> (${monthly_net[worst_i]:+.2f}M).")
    takeaway(f"{msg} Ad revenue peaks in <b>{MONTHS[best_i]}</b>, when the most shows are on air. "
             f"For the full year, net is <b>${sum(monthly_net):+.1f}M</b> before marketing and G&amp;A.")

    # Checkbox toggle instead of st.expander -- see the note on the scenario
    # container above (no expanders nested inside Supplementary Insights).
    if st.checkbox("📋 Show Monthly Detail Table", key="sched_show_detail_table"):
        st.dataframe(bridge_df.style.format({
            "Ad Revenue": "${:.2f}M", "Distribution": "${:.2f}M",
            "Content Cost": "${:.2f}M", "Net Cash Flow": "${:.2f}M"
        }).map(lambda v: "color:#66bb6a;" if v >= 0 else "color:#ef5350;",
               subset=["Net Cash Flow"]), use_container_width=True, hide_index=True)
        st.caption("Same numbers as the chart above, by month.")

    # Primetime Scheduling — Assign Your Shows moved to app_pages/renewal.py
    # (2026-08-03, per user request), right after the Full Renewal Analysis
    # Table, so it sits alongside this year's other real decisions instead of
    # here. This tab is cash-flow/amortization reference only now.

    # ── Hourly Revenue Index ──────────────────────────────────────────────────
    # Single divider here (2026-08-24 fix) -- the moved-out section above left
    # two dividers back to back with nothing between them, an extra visual
    # gap inconsistent with the single-divider spacing used elsewhere.
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
    _pk = max(range(len(HOURLY_INDEX)), key=lambda i: HOURLY_INDEX[i])
    takeaway(f"Ad revenue is concentrated in a few evening hours: <b>{HOUR_LABELS[_pk]}</b> is the single best "
             f"hour. That is why the primetime slots you assign in Renewal change real ad revenue, while "
             f"daytime slots barely move it. Premiere episodes earn a 1.5–2× premium on top.")
