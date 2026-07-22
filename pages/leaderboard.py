"""
Tab 7 — Leaderboard
Per-network rankings using official (first attempt) scores only.
FERPA-safe: displays team names (pseudonyms) only.

Multi-school/multi-class scoping added 2026-07-22: a team's real identity
is (school, class_section, team_name) — see utils/game_state.py. This
page lets a team view their own class only, their whole school, or every
school (cross-school comparison), plus a school-vs-school rollup.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from utils.game_state import (
    get_network_leaderboard, get_school_rollup, NETWORK_ORDER, NETWORK_INFO,
    get_team_network_status, load_leaderboard
)
from utils.charts import base_layout, SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2


# Crown for #1 (with a CSS glow, see utils/styles.py .crown-glow) instead of
# a plain gold medal — "something fun" per user request, and visually
# distinct from silver/bronze rather than just three medal variants.
RANK_ICONS  = {1: "👑", 2: "🥈", 3: "🥉"}
RANK_COLORS = {1: "#e8c547", 2: "#c0c0c0", 3: "#cd7f32"}

# Day 2's leaderboard entries use network key "movies" (pages/movies.py) —
# not part of NETWORK_ORDER/NETWORK_INFO since Movies is a separate
# top-level tab, not one of the sidebar's Oxygen/Bravo/Peacock TV networks.
# Kept as its own minimal info dict rather than added to NETWORK_INFO, so it
# can't leak into the sidebar's Active Network selector or LEVEL_BRIEFS.
MOVIES_INFO = {"emoji": "🎬", "display_name": "Universal Pictures", "color": "#1a6bb5", "color2": "#4fc3f7"}


def _render_board_tab(team: str, net: str, info: dict,
                       scope_school, scope_class, show_school_col: bool):
    """One network's full leaderboard tab body — shared by the TV networks
    (NETWORK_ORDER) and the Day 2 Movies leaderboard. scope_school/
    scope_class of None means unfiltered (cross-school); a value scopes
    down to that school, or that school+class."""
    board = get_network_leaderboard(net, scope_school, scope_class)

    if not board:
        st.markdown(f"""
        <div style="text-align:center;padding:40px;color:#b0b5c4;
             font-family:DM Mono,monospace;font-size:12px;">
          No submissions yet for {info['display_name']} in this scope.
        </div>
        """, unsafe_allow_html=True)
        return

    # Top 3 podium
    top3 = board[:3]
    pcols = st.columns(3)
    for idx, entry in enumerate(top3):
        with pcols[idx]:
            icon   = RANK_ICONS.get(entry["rank"], "")
            mc     = RANK_COLORS.get(entry["rank"], TEXT2)
            ts     = datetime.fromtimestamp(entry["timestamp"]).strftime("%b %d %H:%M")
            passes = "✅" if entry["passed"] else "❌"
            glow_class = "crown-glow" if entry["rank"] == 1 else ""
            school_line = (f'<div style="font-size:10px;color:#b0b5c4;margin-top:2px;">'
                            f'{entry.get("school","")} · {entry.get("class_section","")}</div>'
                            if show_school_col else "")
            st.markdown(f"""
            <div class="{glow_class}" style="background:#1a1d26;border:2px solid {mc};border-radius:10px;
                 padding:16px;text-align:center;margin-bottom:8px;">
              <div style="font-size:30px;">{icon}</div>
              <div style="font-size:14px;font-weight:600;color:{mc};margin:4px 0;">
                {entry['team_name']}
              </div>
              {school_line}
              <div style="font-family:DM Serif Display,serif;font-size:32px;color:{mc};">
                {entry['score']:.0f}
              </div>
              <div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;">pts</div>
              <div style="margin-top:8px;font-size:11px;color:#e0e2ea;">{passes} · {ts}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Full leaderboard table
    st.markdown('<div class="section-title">Full Rankings — Official Scores</div>', unsafe_allow_html=True)

    for entry in board:
        rank_c = RANK_COLORS.get(entry["rank"], "#e8eaf0")
        icon   = RANK_ICONS.get(entry["rank"], f"#{entry['rank']}")
        is_me  = entry["team_name"] == team
        bg     = "rgba(232,197,71,.08)" if is_me else "#1a1d26"
        border = "border:1px solid rgba(232,197,71,.3);" if is_me else "border:1px solid #252836;"
        ts     = datetime.fromtimestamp(entry["timestamp"]).strftime("%b %d")
        passes = "✅" if entry["passed"] else "❌"

        # Score bar
        bar_w  = entry["score"]
        bar_c  = SUCCESS if entry["score"] >= 70 else (WARN if entry["score"] >= 50 else DANGER)

        details = entry.get("details", {})
        school_tag = (f'<div style="font-size:10px;color:#b0b5c4;margin-top:1px;">'
                       f'{entry.get("school","")} · {entry.get("class_section","")}</div>'
                       if show_school_col else "")
        st.markdown(f"""
        <div style="background:{bg};{border}border-radius:8px;
             padding:10px 16px;margin-bottom:6px;">
          <div style="display:flex;align-items:center;gap:14px;">
            <div style="font-family:DM Mono,monospace;font-size:16px;
                 color:{rank_c};min-width:32px;font-weight:700;">{icon}</div>
            <div style="flex:1;">
              <div style="font-size:13px;font-weight:600;
                   color:{'#e8c547' if is_me else '#e8eaf0'};">
                {entry['team_name']} {'← YOU' if is_me else ''}
              </div>
              {school_tag}
              <div style="height:4px;background:#252836;border-radius:2px;
                   margin-top:5px;overflow:hidden;">
                <div style="width:{bar_w}%;height:100%;background:{bar_c};border-radius:2px;"></div>
              </div>
            </div>
            <div style="text-align:right;">
              <div style="font-family:DM Serif Display,serif;font-size:20px;color:{bar_c};">
                {entry['score']:.0f}
              </div>
              <div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;">
                {passes} · {ts}
              </div>
            </div>
          </div>
          {'<div style="display:flex;gap:12px;margin-top:6px;flex-wrap:wrap;">' +
           ''.join([f'<span style="font-size:10px;font-family:DM Mono,monospace;color:#b0b5c4;">{k}: {v:.0f}</span>'
                    for k,v in details.items() if k not in ("total","passed")]) +
           '</div>' if details else ''}
        </div>
        """, unsafe_allow_html=True)

    # Score distribution chart
    if len(board) >= 3:
        st.markdown('<div class="section-title" style="margin-top:12px;">Score Distribution</div>', unsafe_allow_html=True)
        scores = [e["score"] for e in board]
        teams  = [e["team_name"] for e in board]
        colors = [SUCCESS if s >= 70 else (WARN if s >= 50 else DANGER) for s in scores]

        fig = go.Figure(go.Bar(
            x=teams, y=scores,
            marker_color=colors, opacity=0.8,
            text=[f"{s:.0f}" for s in scores],
            textposition="outside",
            textfont=dict(size=11, color="#e8eaf0"),
        ))
        # Highlight my team
        if team in teams:
            my_idx = teams.index(team)
            fig.add_shape(type="rect",
                x0=my_idx-.4, x1=my_idx+.4, y0=0, y1=scores[my_idx],
                fillcolor="rgba(232,197,71,.2)", line=dict(color="#e8c547", width=2))

        fig.add_hline(y=70, line_dash="dash", line_color=SUCCESS, opacity=0.5,
                       annotation_text="Pass threshold", annotation_font_color=SUCCESS,
                       annotation_font_size=10)
        fig.update_layout(**base_layout(f"{info['display_name']} Score Distribution", height=280))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})


def _render_school_comparison(all_nets: list, all_infos: dict):
    """School-vs-school rollup — aggregate stats per school, across every
    class within it. Satisfies both 'schools compare aggregate scores
    against each other' and 'a leaderboard just for school overall' (your
    own school's row sits right alongside every other school's)."""
    net = st.selectbox(
        "Network", all_nets, format_func=lambda n: f"{all_infos[n]['emoji']} {all_infos[n]['display_name']}",
        key="school_cmp_net",
    )
    rollup = get_school_rollup(net)
    if len(rollup) < 2:
        st.markdown(
            '<div style="text-align:center;padding:30px;color:#b0b5c4;font-family:DM Mono,monospace;font-size:12px;">'
            'Only one school has submitted so far — comparison needs at least two.</div>',
            unsafe_allow_html=True)
        if rollup:
            st.caption(f"So far: {rollup[0]['school']} — avg {rollup[0]['avg_score']:.0f} pts across "
                       f"{rollup[0]['teams']} team(s), {rollup[0]['pass_rate']:.0f}% pass rate.")
        return

    df = pd.DataFrame(rollup)[["rank", "school", "teams", "avg_score", "pass_rate", "top_score"]]
    df.columns = ["Rank", "School", "Teams", "Avg Score", "Pass Rate %", "Top Score"]
    st.dataframe(
        df.style.format({"Avg Score": "{:.1f}", "Pass Rate %": "{:.0f}%", "Top Score": "{:.1f}"})
        .set_properties(**{"font-family": "DM Mono,monospace", "font-size": "12px"}),
        use_container_width=True, hide_index=True,
    )

    fig = go.Figure(go.Bar(
        x=[r["school"] for r in rollup], y=[r["avg_score"] for r in rollup],
        marker_color=[ACCENT if i == 0 else ACCENT2 for i in range(len(rollup))],
        text=[f"{r['avg_score']:.0f}" for r in rollup], textposition="outside",
        textfont=dict(size=11, color="#e8eaf0"),
    ))
    fig.update_layout(**base_layout(f"Avg Score by School — {all_infos[net]['display_name']}", height=280))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render():
    ss   = st.session_state
    team = ss.team_name

    st.markdown("""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #e8c547;
         border-radius:6px;padding:10px 16px;margin-bottom:16px;font-size:12px;color:#e0e2ea;">
    🏆 <b style="color:#e8eaf0;">Official Leaderboard:</b> Rankings use your <b>first attempt only</b>.
    Retries are practice — they don't change your leaderboard position.
    FERPA: Only team names (student-chosen pseudonyms) are stored — no student IDs or names.
    </div>
    """, unsafe_allow_html=True)

    # ── My Status ─────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">My Team Status</div>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="text-xs text-ink2 mb-2">{ss.school} · {ss.class_section}</p>'
        if ss.get("school") else "", unsafe_allow_html=True)
    status = get_team_network_status(team, ss.school, ss.class_section)

    cols = st.columns(3)
    for i, net in enumerate(NETWORK_ORDER):
        info  = NETWORK_INFO[net]
        stat  = status.get(net, {})
        off   = stat.get("official_score")
        att   = stat.get("attempts", 0)
        pas   = stat.get("passed", False)

        with cols[i]:
            border_c = info["color"] if pas else ("#252836")
            score_c  = "#66bb6a" if pas else ("#ffa726" if att > 0 else "#b0b5c4")
            st.markdown(f"""
            <div style="background:#1a1d26;border:2px solid {border_c};border-radius:10px;
                 padding:16px;text-align:center;">
              <div style="font-size:22px;margin-bottom:4px;">{info['emoji']}</div>
              <div style="font-family:DM Mono,monospace;font-size:13px;font-weight:600;
                   color:{info['color2']};">{info['display_name']}</div>
              <div style="font-family:DM Serif Display,serif;font-size:28px;
                   color:{score_c};margin:8px 0;">{f"{off:.0f}" if off else '—'}</div>
              <div style="font-size:10px;font-family:DM Mono,monospace;color:#b0b5c4;">
                {'OFFICIAL SCORE' if off else 'NOT SUBMITTED'}
              </div>
              <div style="margin-top:8px;">
                {'<span class="badge badge-green">✅ PASSED</span>' if pas else
                 f'<span class="badge badge-yellow">{att} attempt{"s" if att!=1 else ""}</span>' if att > 0 else
                 '<span class="badge badge-gray">Not started</span>'}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # ── Scope selector ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Leaderboard Scope</div>', unsafe_allow_html=True)
    scope = st.radio(
        "View", ["My Class", "My School", "All Schools"], horizontal=True, key="lb_scope",
        help="My Class: just your section. My School: every class at your school. "
             "All Schools: every team, everywhere — see how you stack up beyond your own campus.",
    )
    if scope == "My Class":
        scope_school, scope_class = ss.school, ss.class_section
    elif scope == "My School":
        scope_school, scope_class = ss.school, None
    else:
        scope_school, scope_class = None, None
    show_school_col = scope != "My Class"

    st.divider()

    # ── Per-Network Leaderboards (TV networks + Day 2 Movies) ─────────────────
    all_nets  = list(NETWORK_ORDER) + ["movies"]
    all_infos = {**{n: NETWORK_INFO[n] for n in NETWORK_ORDER}, "movies": MOVIES_INFO}
    net_tabs  = st.tabs([f"{all_infos[n]['emoji']} {all_infos[n]['display_name']}" for n in all_nets])

    for tab, net in zip(net_tabs, all_nets):
        with tab:
            _render_board_tab(team, net, all_infos[net], scope_school, scope_class, show_school_col)

    st.divider()

    # ── School Comparison ───────────────────────────────────────────────────────
    st.markdown('<div class="section-title">School Comparison</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="text-xs text-ink2 mb-2">Aggregate performance across every class at each school — '
        'your school\'s overall standing sits alongside every other school\'s.</p>',
        unsafe_allow_html=True)
    _render_school_comparison(all_nets, all_infos)

    st.divider()

    # ── All-Network Summary ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">All Submissions — Raw Data</div>', unsafe_allow_html=True)

    all_entries = load_leaderboard()
    if all_entries:
        raw_df = pd.DataFrame([{
            "Team":      e["team_name"],
            "School":    e.get("school", ""),
            "Class":     e.get("class_section", ""),
            "Network":   e["network"].title(),
            "Attempt":   e["attempt"],
            "Score":     e["score"],
            "Passed":    "✅" if e["passed"] else "❌",
            "Official":  "✅" if e["is_official"] else "—",
            "Time":      datetime.fromtimestamp(e["timestamp"]).strftime("%Y-%m-%d %H:%M"),
        } for e in all_entries])
        st.dataframe(raw_df.style.set_properties(**{"font-family":"DM Mono,monospace","font-size":"11px"}),
                     use_container_width=True, height=300)
        st.download_button(
            "⬇️ Export Leaderboard CSV",
            raw_df.to_csv(index=False),
            file_name="cableos_leaderboard.csv",
            mime="text/csv",
            help="FERPA: Contains team names only — no student PII."
        )
    else:
        st.markdown('<div style="color:#b0b5c4;font-family:DM Mono,monospace;font-size:12px;">No submissions recorded yet.</div>', unsafe_allow_html=True)
