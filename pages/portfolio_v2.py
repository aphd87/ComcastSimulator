"""
Portfolio tab v2 — real-time OCF updates + Submit for Score button.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from utils.models import (
    annual_budget, cable_subs, distribution_revenue,
    portfolio_ad_rev, portfolio_cost,
)
from utils.game_state import (
    NETWORK_INFO, compute_score_for_network, record_attempt,
    get_attempt_count, can_advance, MAX_ATTEMPTS, hhi_from_genres,
    get_official_score, SCORE_WEIGHTS,
)
from utils.charts import (
    bar_chart, donut_chart, scatter_chart,
    SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2, base_layout
)

# re-import hhi correctly
from utils.game_state import hhi_from_genres

MAX_SIM_YEARS = {"oxygen": 3, "bravo": 4, "peacock": 3}


def _run_year(ss, net, shows, year, mkt, sim_yr):
    """Apply seeded market variance and store year results — does not modify show objects."""
    seed = (abs(hash(ss.team_name)) + sim_yr * 1337) % (2 ** 31)
    rng  = np.random.default_rng(seed)

    show_results = []
    for s in shows:
        v   = float(rng.uniform(0.93, 1.08))
        per = mkt / max(len(shows), 1)
        show_results.append({
            "name":        s.name,
            "network":     s.network,
            "rating_base": s.rating,
            "rating_adj":  round(s.rating * v, 2),
            "variance":    round(v, 3),
            "revenue":     round(s.ad_revenue(year, per) * v, 2),
        })

    from utils.models import portfolio_cost, portfolio_ad_rev, distribution_revenue
    total_adj_rev = sum(r["revenue"] for r in show_results) + distribution_revenue(year)
    cost          = portfolio_cost(shows, year)
    ga            = total_adj_rev * 0.06
    ocf           = total_adj_rev - cost - mkt - ga
    margin        = (ocf / total_adj_rev * 100) if total_adj_rev > 0 else 0

    if "year_results" not in ss or ss.year_results is None:
        ss.year_results = {}
    ss.year_results[sim_yr] = {
        "revenue": round(total_adj_rev, 2),
        "cost":    round(cost, 2),
        "ocf":     round(ocf, 2),
        "margin":  round(margin, 1),
        "shows":   show_results,
    }
    ss.sim_phase = "results"


def _live_kpis(shows, year, mkt, network):
    """Compute all KPIs in one place — called on every rerun for real-time feel."""
    ad_rev   = portfolio_ad_rev(shows, year, mkt)
    dist_rev = distribution_revenue(year)
    total_rev= ad_rev + dist_rev
    cost     = portfolio_cost(shows, year)
    ga       = total_rev * 0.06
    ocf      = total_rev - cost - mkt - ga
    margin   = (ocf / total_rev * 100) if total_rev > 0 else 0

    per      = mkt / max(len(shows), 1)
    rois     = [s.roi(year, per) for s in shows]
    avg_roi  = sum(rois) / len(rois) if rois else 0

    genre_costs = {}
    for s in shows:
        genre_costs[s.genre] = genre_costs.get(s.genre, 0) + s.total_cost(year)
    hhi = hhi_from_genres(genre_costs)

    positive_shows = sum(1 for r in rois if r > 0)
    renewal_pct    = (positive_shows / len(rois) * 100) if rois else 0

    mkt_eff = (ad_rev / mkt) if mkt > 0 else 0  # $M ad rev per $M marketing

    score_data = compute_score_for_network(
        network, margin, avg_roi, hhi, renewal_pct, mkt_eff
    )
    return {
        "ad_rev": ad_rev, "dist_rev": dist_rev, "total_rev": total_rev,
        "cost": cost, "ga": ga, "ocf": ocf, "margin": margin,
        "avg_roi": avg_roi, "hhi": hhi, "renewal_pct": renewal_pct,
        "mkt_eff": mkt_eff, "score_data": score_data,
    }


def render():
    ss      = st.session_state
    net     = ss.active_network
    year    = ss.year
    mkt     = ss.mkt_budget
    net_info= NETWORK_INFO[net]
    team    = ss.team_name

    shows = ss.oxygen_shows[:]
    if net in ("bravo", "peacock"):
        shows += ss.bravo_shows
    if net == "peacock":
        shows += ss.get("peacock_shows", [])

    kpis    = _live_kpis(shows, year, mkt, net)
    score_d = kpis["score_data"]
    attempts= get_attempt_count(team, net)
    passed        = any(a for a in [get_official_score(team, net)] if a and a.get("passed"))
    can_sub       = attempts < MAX_ATTEMPTS and not passed
    advance_ready = can_advance(team, net) and not passed

    # ── Year Simulation Panel ─────────────────────────────────────────────────
    sim_yr   = ss.get("sim_year", 1)
    sim_ph   = ss.get("sim_phase", "setup")
    max_yrs  = MAX_SIM_YEARS.get(net, 3)

    if sim_ph == "setup":
        st.markdown(f"""
        <div style="background:rgba(232,197,71,.05);border:1px solid rgba(232,197,71,.25);
             border-radius:8px;padding:14px 18px;margin-bottom:14px;">
          <div style="font-family:DM Mono,monospace;font-size:10px;color:#555a6e;
               text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px;">
            Year {sim_yr} of {max_yrs} — Decision Phase
          </div>
          <div style="font-size:12px;color:#8b90a0;line-height:1.7;">
            Adjust your show slate, budget sliders, and renewal decisions. When ready,
            click <b style="color:#e8eaf0;">Run Year {sim_yr}</b> to see how the market responds —
            ratings will shift ±7% based on market conditions.
          </div>
        </div>
        """, unsafe_allow_html=True)

        run_col, _ = st.columns([1, 2])
        with run_col:
            if st.button(f"▶  Run Year {sim_yr}  ({2011 + sim_yr})",
                         use_container_width=True, type="primary"):
                _run_year(ss, net, shows, year, mkt, sim_yr)
                st.rerun()

    else:
        # Results phase — show year outcome banner
        result  = (ss.get("year_results") or {}).get(sim_yr, {})
        ocf_ok  = result.get("ocf", 0) >= 0
        ocf_c   = "#66bb6a" if ocf_ok else "#ef5350"
        margin  = result.get("margin", 0)

        st.markdown(f"""
        <div style="background:rgba({'102,187,106' if ocf_ok else '239,83,80'},.07);
             border:1px solid rgba({'102,187,106' if ocf_ok else '239,83,80'},.3);
             border-radius:8px;padding:14px 18px;margin-bottom:14px;">
          <div style="font-family:DM Mono,monospace;font-size:10px;color:#555a6e;
               text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px;">
            Year {sim_yr} Results · {2011 + sim_yr}
          </div>
          <div style="display:flex;gap:32px;flex-wrap:wrap;margin-bottom:10px;">
            <div><div style="font-size:10px;color:#555a6e;font-family:DM Mono,monospace;">Revenue</div>
                 <div style="font-size:20px;font-family:DM Serif Display,serif;color:#e8eaf0;">${result.get('revenue',0):.1f}M</div></div>
            <div><div style="font-size:10px;color:#555a6e;font-family:DM Mono,monospace;">Cost</div>
                 <div style="font-size:20px;font-family:DM Serif Display,serif;color:#ffa726;">${result.get('cost',0):.1f}M</div></div>
            <div><div style="font-size:10px;color:#555a6e;font-family:DM Mono,monospace;">OCF</div>
                 <div style="font-size:20px;font-family:DM Serif Display,serif;color:{ocf_c};">${result.get('ocf',0):+.1f}M</div></div>
            <div><div style="font-size:10px;color:#555a6e;font-family:DM Mono,monospace;">Margin</div>
                 <div style="font-size:20px;font-family:DM Serif Display,serif;color:{ocf_c};">{margin:.1f}%</div></div>
          </div>
          <div style="font-size:11px;color:#8b90a0;">
            Ratings shifted with market variance (±7%). Submit your score to lock this year in, or advance to the next year.
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Show movers — biggest rating shifts
        show_res = result.get("shows", [])
        if show_res:
            movers = sorted(show_res, key=lambda x: abs(x["variance"] - 1.0), reverse=True)[:4]
            mover_html = "".join([
                f'<span style="font-size:10px;font-family:DM Mono,monospace;'
                f'color:{"#66bb6a" if m["variance"] >= 1.0 else "#ef5350"};">'
                f'{m["name"][:14]}: {m["rating_base"]:.1f}→{m["rating_adj"]:.1f}'
                f'</span>'
                for m in movers
            ])
            st.markdown(
                f'<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;">'
                f'<span style="font-size:10px;color:#555a6e;font-family:DM Mono,monospace;">Rating shifts:</span>'
                f'{mover_html}</div>',
                unsafe_allow_html=True
            )

        adv_col, reset_col = st.columns([1, 1])
        with adv_col:
            if sim_yr < max_yrs:
                if st.button(f"→ Advance to Year {sim_yr + 1}", use_container_width=True):
                    ss.sim_year  = sim_yr + 1
                    ss.sim_phase = "setup"
                    ss.year      = sim_yr + 1
                    st.rerun()
            else:
                st.markdown(
                    '<div style="font-size:12px;color:#66bb6a;font-family:DM Mono,monospace;padding:8px 0;">'
                    '✅ Final year complete — submit your score below.</div>',
                    unsafe_allow_html=True
                )
        with reset_col:
            if st.button("↺ Re-run Year (adjust decisions)", use_container_width=True):
                ss.sim_phase = "setup"
                st.rerun()

    st.divider()

    # ── Real-time KPI Row ─────────────────────────────────────────────────────
    st.markdown(
        f'<div style="font-family:DM Mono,monospace;font-size:10px;color:#555a6e;'
        f'margin-bottom:8px;letter-spacing:.1em;">LIVE · Year {year} · {2011+year}</div>',
        unsafe_allow_html=True
    )

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    ocf_color = "#66bb6a" if kpis["ocf"] >= 0 else "#ef5350"
    margin_color = "#66bb6a" if kpis["margin"] >= net_info["pass_threshold"] else "#ffa726"

    c1.metric("Total Revenue",  f"${kpis['total_rev']:.1f}M", "Ad + Distribution")
    c2.metric("Content Cost",   f"${kpis['cost']:.1f}M",      "Amortized")
    c3.metric("Operating CF",   f"${kpis['ocf']:.1f}M",       f"{kpis['margin']:+.1f}% margin")
    c4.metric("Avg Show ROI",   f"{kpis['avg_roi']:.1f}%",    "portfolio avg")
    c5.metric("Genre HHI",      f"{kpis['hhi']:.2f}",         "1.0=concentrated")
    c6.metric("Live Score",     f"{score_d['total']:.0f} pts", "↻ updates live")

    # Inline margin progress bar
    threshold = net_info["pass_threshold"]
    pct = min(kpis["margin"] / (threshold * 1.5), 1.0) * 100
    bar_color = "#66bb6a" if kpis["margin"] >= threshold else ("#ffa726" if kpis["margin"] >= 0 else "#ef5350")
    st.markdown(f"""
    <div style="margin:8px 0 4px;">
      <div style="display:flex;justify-content:space-between;font-family:DM Mono,monospace;font-size:10px;color:#555a6e;margin-bottom:4px;">
        <span>OCF Margin</span>
        <span style="color:{bar_color};">{kpis['margin']:.1f}% / {threshold:.0f}% target</span>
      </div>
      <div style="height:6px;background:#252836;border-radius:3px;overflow:hidden;">
        <div style="width:{pct}%;height:100%;background:{bar_color};border-radius:3px;transition:width .4s ease;"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Score Breakdown + Submit ──────────────────────────────────────────────
    sub_col, score_col = st.columns([2, 3])

    with sub_col:
        st.markdown('<div class="section-title">Submit for Official Score</div>', unsafe_allow_html=True)

        if passed:
            st.markdown(f"""
            <div style="background:rgba(102,187,106,.12);border:1px solid rgba(102,187,106,.3);
                 border-radius:8px;padding:16px;text-align:center;">
              <div style="font-size:28px;margin-bottom:6px;">✅</div>
              <div style="font-family:DM Serif Display,serif;font-size:18px;color:#66bb6a;">Level Passed!</div>
              <div style="font-family:DM Mono,monospace;font-size:13px;color:#8b90a0;margin-top:4px;">
                {net_info['display_name']} complete. Check Leaderboard tab.
              </div>
            </div>
            """, unsafe_allow_html=True)
            if net != "peacock":
                next_net = NETWORK_ORDER[NETWORK_ORDER.index(net) + 1]
                next_info = NETWORK_INFO[next_net]
                if st.button(f"→ Advance to {next_info['display_name']}", use_container_width=True):
                    ss.active_network = next_net
                    ss.submitted      = False
                    st.rerun()

        elif advance_ready:
            # Completed required retry — may advance even if not passing score
            off_sc = (get_official_score(team, net) or {}).get("score", 0)
            st.markdown(f"""
            <div style="background:rgba(255,167,38,.1);border:1px solid rgba(255,167,38,.3);
                 border-radius:8px;padding:16px;text-align:center;">
              <div style="font-size:24px;">🔄</div>
              <div style="font-family:DM Mono,monospace;font-size:13px;color:#ffb74d;">
                Retry complete. You may advance to the next level.
              </div>
              <div style="font-size:11px;color:#8b90a0;margin-top:6px;">
                Official score: {off_sc:.0f} pts — did not meet {threshold:.0f}% OCF target.
              </div>
            </div>
            """, unsafe_allow_html=True)
            if net != "peacock":
                next_net = NETWORK_ORDER[NETWORK_ORDER.index(net) + 1]
                next_info = NETWORK_INFO[next_net]
                if st.button(f"→ Advance to {next_info['display_name']}", use_container_width=True):
                    ss.active_network = next_net
                    ss.submitted = False
                    st.rerun()
            if can_sub:
                st.markdown(f"""
                <div style="font-size:11px;color:#555a6e;margin-top:8px;text-align:center;">
                  Attempt {attempts+1} of {MAX_ATTEMPTS} still available (practice only).
                </div>
                """, unsafe_allow_html=True)

        elif not can_sub:
            # All 3 attempts used — safety net (shouldn't normally reach here with new logic)
            st.markdown(f"""
            <div style="background:rgba(255,167,38,.1);border:1px solid rgba(255,167,38,.3);
                 border-radius:8px;padding:16px;text-align:center;">
              <div style="font-size:24px;">⏱️</div>
              <div style="font-family:DM Mono,monospace;font-size:13px;color:#ffb74d;">
                All {MAX_ATTEMPTS} attempts used.
              </div>
              <div style="font-size:11px;color:#8b90a0;margin-top:6px;">
                Official score: {(get_official_score(team,net) or {}).get('score',0):.0f} pts
              </div>
            </div>
            """, unsafe_allow_html=True)
            if net != "peacock":
                next_net = NETWORK_ORDER[NETWORK_ORDER.index(net) + 1]
                if st.button(f"→ Advance to {NETWORK_INFO[next_net]['display_name']}", use_container_width=True):
                    ss.active_network = next_net
                    st.rerun()
        else:
            # Can still submit
            if attempts == 0:
                st.markdown("""
                <div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;
                     padding:12px;font-size:12px;color:#8b90a0;margin-bottom:10px;">
                ⚠️ <b style="color:#e8eaf0;">Your FIRST submission is your official score</b>
                for the leaderboard. You may retry up to 2 more times, but only your
                first attempt counts for ranking.
                </div>
                """, unsafe_allow_html=True)
            elif attempts == 1:
                st.markdown(f"""
                <div style="background:rgba(239,83,80,.1);border:1px solid rgba(239,83,80,.3);
                     border-radius:6px;padding:10px;font-size:12px;color:#ef9a9a;margin-bottom:10px;">
                ❌ Attempt 1 did not pass. <b style="color:#e8eaf0;">Complete this retry before advancing.</b>
                After retrying, you may move to the next level regardless of score.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background:rgba(255,167,38,.1);border:1px solid rgba(255,167,38,.3);
                     border-radius:6px;padding:10px;font-size:12px;color:#ffb74d;margin-bottom:10px;">
                🔄 Attempt {attempts+1} of {MAX_ATTEMPTS}. Practice only — first score stands.
                </div>
                """, unsafe_allow_html=True)

            st.markdown(
                f'<div style="font-size:12px;color:#8b90a0;margin-bottom:8px;">'
                f'Target: ≥{threshold:.0f}% OCF margin to pass {net_info["display_name"]}.<br>'
                f'Current: <b style="color:{margin_color};">{kpis["margin"]:.1f}%</b></div>',
                unsafe_allow_html=True
            )

            st.markdown('<div class="submit-btn">', unsafe_allow_html=True)
            if st.button(
                f"{'🎯 Submit Official Score' if attempts==0 else '🔄 Retry Submission'}  ({score_d['total']:.0f} pts)",
                use_container_width=True,
                key="submit_btn"
            ):
                passed_this = score_d["passed"]
                entry = record_attempt(
                    team_name=team,
                    network=net,
                    attempt_num=attempts + 1,
                    score=score_d["total"],
                    passed=passed_this,
                    details=score_d,
                )
                ss.last_score = entry
                ss.submitted  = True
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # Post-submit feedback
        if ss.submitted and ss.last_score:
            e            = ss.last_score
            passed_sub   = e["passed"]
            result_color = "#66bb6a" if passed_sub else "#ef5350"
            result_text  = "PASSED ✅" if passed_sub else "DID NOT PASS ❌"

            st.markdown(f"""
            <div style="background:rgba({'102,187,106' if passed_sub else '239,83,80'},.1);
                 border:1px solid rgba({'102,187,106' if passed_sub else '239,83,80'},.3);
                 border-radius:8px;padding:14px;margin-top:10px;text-align:center;">
              <div style="font-family:DM Serif Display,serif;font-size:20px;color:{result_color};">
                {result_text}
              </div>
              <div style="font-family:DM Mono,monospace;font-size:24px;color:{result_color};margin:8px 0;">
                {e['score']:.0f} pts
              </div>
              {'<div style="font-size:11px;color:#8b90a0;">Official score locked. See Leaderboard tab.</div>' if e["attempt"]==1 else ""}
            </div>
            """, unsafe_allow_html=True)

            if not passed_sub:
                details = e.get("details", {})
                HINTS = {
                    "ocf_margin":    ("OCF Margin (35%)",    "Cancel low-ROI shows and reduce reserve to improve margin."),
                    "roi":           ("Portfolio ROI (25%)", "Cut shows with negative ROI — even Watch-listed ones hurt."),
                    "diversity":     ("Genre Diversity (15%)","Add a non-True Crime show to lower your HHI score."),
                    "renewal":       ("Renewal Quality (10%)","Renew only ROI-positive shows; cancel the rest."),
                    "marketing":     ("Mkt Efficiency (15%)", "Lower marketing spend if ad revenue lift isn't worth it."),
                }
                weak = [(k, v) for k, v in details.items()
                        if k in HINTS and isinstance(v, (int, float)) and v < 60]
                weak.sort(key=lambda x: x[1])

                if weak:
                    st.markdown(
                        '<div style="font-family:DM Mono,monospace;font-size:10px;color:#555a6e;'
                        'text-transform:uppercase;letter-spacing:.08em;margin:10px 0 6px;">Where to improve</div>',
                        unsafe_allow_html=True
                    )
                    for k, score_val in weak[:3]:
                        label, hint = HINTS[k]
                        st.markdown(
                            f'<div style="background:#12141a;border-left:2px solid #ef5350;'
                            f'border-radius:4px;padding:8px 12px;margin-bottom:5px;">'
                            f'<div style="font-size:11px;color:#ef9a9a;font-family:DM Mono,monospace;">'
                            f'{label} — {score_val:.0f}/100</div>'
                            f'<div style="font-size:11px;color:#8b90a0;margin-top:2px;">{hint}</div>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

    with score_col:
        st.markdown('<div class="section-title">Live Score Breakdown</div>', unsafe_allow_html=True)
        components = [
            ("OCF Margin",      score_d["ocf_margin"],  SCORE_WEIGHTS["ocf_margin"],    "35%"),
            ("Portfolio ROI",   score_d["roi"],         SCORE_WEIGHTS["roi_avg"],       "25%"),
            ("Genre Diversity", score_d["diversity"],   SCORE_WEIGHTS["genre_mix"],     "15%"),
            ("Renewal Quality", score_d["renewal"],     SCORE_WEIGHTS["renewal_pct"],   "10%"),
            ("Mkt Efficiency",  score_d["marketing"],   SCORE_WEIGHTS["mkt_efficiency"],"15%"),
        ]
        for label, comp_score, weight, pct_label in components:
            weighted = comp_score * weight
            bar_c    = SUCCESS if comp_score >= 70 else (WARN if comp_score >= 40 else DANGER)
            st.markdown(f"""
            <div style="margin-bottom:10px;">
              <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">
                <span style="color:#8b90a0;">{label} <span style="color:#555a6e;">({pct_label})</span></span>
                <span style="font-family:DM Mono,monospace;color:{bar_c};">{comp_score:.0f}/100 → {weighted:.1f}pts</span>
              </div>
              <div style="height:5px;background:#252836;border-radius:3px;overflow:hidden;">
                <div style="width:{comp_score}%;height:100%;background:{bar_c};border-radius:3px;"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        total_c = SUCCESS if score_d["total"] >= 70 else (WARN if score_d["total"] >= 50 else DANGER)
        st.markdown(f"""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;
             padding:12px;text-align:center;margin-top:8px;">
          <div style="font-size:10px;color:#555a6e;font-family:DM Mono,monospace;margin-bottom:4px;">TOTAL SCORE</div>
          <div style="font-family:DM Serif Display,serif;font-size:36px;color:{total_c};">{score_d['total']:.0f}</div>
          <div style="font-family:DM Mono,monospace;font-size:10px;color:#555a6e;">/ 100 points</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Show Slate Table ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Active Show Slate</div>', unsafe_allow_html=True)

    sort_by = st.selectbox("Sort by", ["ROI %","Rating","Cost $M","OCF $M","Name"],
                            label_visibility="collapsed")
    per = mkt / max(len(shows), 1)
    rows = []
    for s in shows:
        cost_m = s.total_cost(year)
        rev_m  = s.ad_revenue(year, per)
        ocf_s  = s.ocf(year, per)
        roi_s  = s.roi(year, per)
        status = "✅ Cash Cow" if roi_s > 20 else ("⚠️ Renew?" if roi_s > 0 else "❌ Cancel")
        rows.append({
            "Show": s.name, "Network": s.network, "Genre": s.genre,
            "Eps": s.episodes, "Ep $K": int(s.ep_cost_k),
            "Rating": round(s.rating, 2),
            "Ad Rev $M": round(rev_m, 2),
            "Cost $M": round(cost_m, 2),
            "OCF $M": round(ocf_s, 2),
            "ROI %": round(roi_s, 1),
            "IP Score": s.ip_score,
            "Status": status,
        })

    df = pd.DataFrame(rows)
    sm = {"ROI %":"ROI %","Rating":"Rating","Cost $M":"Cost $M","OCF $M":"OCF $M","Name":"Show"}
    df = df.sort_values(sm[sort_by], ascending=(sort_by=="Name"))

    styled = (
        df.style
        .map(lambda v: "color:#81c784;" if "Cow" in str(v) else ("color:#ffb74d;" if "Renew" in str(v) else "color:#ef9a9a;"), subset=["Status"])
        .map(lambda v: "color:#81c784;" if v >= 0 else "color:#ef9a9a;", subset=["OCF $M"])
        .format({"Rating":"{:.2f}","Ad Rev $M":"${:.2f}M","Cost $M":"${:.2f}M","OCF $M":"${:.2f}M","ROI %":"{:.1f}%"})
        .set_properties(**{"font-family":"DM Mono,monospace","font-size":"11px"})
    )
    st.dataframe(styled, use_container_width=True, height=380)

    # ── Portfolio charts ──────────────────────────────────────────────────────
    st.markdown("""
    <div style="font-size:12px;color:#8b90a0;margin-bottom:10px;">
    <b style="color:#e8eaf0;">Genre Mix (left):</b> Concentration in one genre pushes HHI above 0.5 — a penalty in your diversity score. Aim for 4+ genres at roughly equal cost weight.
    &nbsp;&nbsp;<b style="color:#e8eaf0;">Rating vs. ROI Map (right):</b> Bubble size = season cost. Upper-right quadrant = cash cows to protect; lower-left = cancel candidates.
    </div>
    """, unsafe_allow_html=True)
    c1, c2 = st.columns(2)

    with c1:
        genre_costs = {}
        for s in shows:
            genre_costs[s.genre] = genre_costs.get(s.genre, 0) + s.total_cost(year)
        fig_g = donut_chart(list(genre_costs.keys()),
                             [round(v,2) for v in genre_costs.values()],
                             "Content Cost by Genre ($M)", height=260)
        st.plotly_chart(fig_g, use_container_width=True, config={"displayModeBar":False})

    with c2:
        sdf = pd.DataFrame([{
            "Show": s.name, "Rating": s.rating,
            "ROI %": round(s.roi(year, per), 1),
            "Cost $M": round(s.total_cost(year), 2),
            "Genre": s.genre,
        } for s in shows])
        fig_s = scatter_chart(sdf, "Rating", "ROI %", "Cost $M", "Genre", "Show",
                               "Portfolio Map: Rating vs. ROI", height=260)
        fig_s.add_hline(y=0, line_dash="dash", line_color=DANGER, opacity=0.4)
        st.plotly_chart(fig_s, use_container_width=True, config={"displayModeBar":False})

    # ── Show Editor ────────────────────────────────────────────────────────────
    with st.expander("✏️ Show Editor — Adjust Parameters (changes update score live)", expanded=False):
        ed_shows = (ss.oxygen_shows if net == "oxygen"
                    else ss.bravo_shows if net == "bravo"
                    else ss.get("peacock_shows", ss.oxygen_shows))
        ed_sel   = st.selectbox("Select Show", [s.name for s in ed_shows])
        ed_show  = next(s for s in ed_shows if s.name == ed_sel)
        c1,c2,c3,c4 = st.columns(4)
        new_eps  = c1.number_input("Episodes", 1, 30, ed_show.episodes)
        new_cost = c2.number_input("Cost/Ep ($K)", 100, 5000, int(ed_show.ep_cost_k))
        new_rate = c3.number_input("Rating", 0.1, 5.0, ed_show.rating, step=0.1, format="%.2f")
        new_ip   = c4.number_input("IP Score", 0, 100, ed_show.ip_score)
        if st.button("Apply Changes"):
            ed_show.episodes  = new_eps
            ed_show.ep_cost_k = new_cost
            ed_show.rating    = new_rate
            ed_show.ip_score  = new_ip
            st.success(f"✅ {ed_sel} updated — score recalculates above.")
            st.rerun()
        c1p,c2p,c3p = st.columns(3)
        c1p.metric("Season Cost", f"${ed_show.total_cost(year):.2f}M")
        c2p.metric("Ad Revenue",  f"${ed_show.ad_revenue(year, per):.2f}M")
        c3p.metric("OCF",         f"${ed_show.ocf(year, per):.2f}M")

