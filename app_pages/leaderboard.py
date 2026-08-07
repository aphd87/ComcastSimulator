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
    get_network_leaderboard, get_school_rollup, get_overall_leaderboard,
    NETWORK_ORDER, NETWORK_INFO, get_team_network_status, load_leaderboard,
    get_attempt_count, MAX_ATTEMPTS, get_class_awards,
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


def _format_slate_item(item: dict) -> str:
    """One compact line per show/movie in a team's slate_summary — TV and
    Movies entries carry different fields (see the two record_attempt()
    call sites in pages/simulation.py and pages/movies.py), so this just
    renders whichever fields are actually present, in a sensible order,
    rather than assuming one fixed shape."""
    parts = [str(item.get("name", "?"))]
    for key, fmt in (
        ("genre", "{}"), ("network", "{}"), ("rating", "rating {}"),
        ("concept_type", "{}"), ("release_strategy", "{}"), ("npv", "NPV ${:+.1f}M"),
    ):
        if key in item and item[key] is not None:
            parts.append(fmt.format(item[key]))
    return " · ".join(parts)


def _format_notables_badges(notables: dict) -> str:
    """Small badge row for a leaderboard entry's stored `notables`
    (compute_level_notables for TV, compute_movie_notables for Movies —
    see the two record_attempt() call sites). Renders whichever fields
    are present rather than assuming one fixed shape, same approach as
    _format_slate_item: TV entries carry best_year/diversity_trend/
    shows_greenlit, Movies entries carry best_cycle/genre_variety, and
    entries submitted before this feature existed carry neither."""
    if not notables:
        return ""
    badges = []
    best = notables.get("best_year") or notables.get("best_cycle")
    if best:
        badges.append(f"🏆 Best: {best['label']}")
    mi = notables.get("most_improved")
    if mi is not None:
        badges.append(f"📈 {mi:+.1f} improvement")
    cs = notables.get("consistency_score")
    if cs is not None:
        badges.append(f"🎯 {cs:.0f}/100 consistency")
    sg = notables.get("shows_greenlit")
    if sg:
        badges.append(f"🎬 {sg} greenlit")
    gv = notables.get("genre_variety")
    if gv:
        badges.append(f"🎭 {gv} genre{'s' if gv != 1 else ''}")
    ow = notables.get("oscar_wins")
    if ow:
        badges.append(f"🏆 {ow} Oscar win{'s' if ow != 1 else ''}")
    on = notables.get("oscar_nominations")
    if on:
        badges.append(f"🎬 {on} Oscar nom{'s' if on != 1 else ''}")
    ew = notables.get("emmy_wins")
    if ew:
        badges.append(f"🏆 {ew} Emmy win{'s' if ew != 1 else ''}")
    en = notables.get("emmy_nominations")
    if en:
        badges.append(f"🎬 {en} Emmy nom{'s' if en != 1 else ''}")
    tr = notables.get("total_revenue")
    if tr:
        badges.append(f"💰 ${tr:,.0f}M revenue")
    if not badges:
        return ""
    return ('<div style="display:flex;gap:10px;margin-top:5px;flex-wrap:wrap;">' +
            "".join(f'<span style="font-size:14px;font-family:DM Mono,monospace;color:{ACCENT2};">{b}</span>'
                    for b in badges) +
            '</div>')


def _render_overall_tab(team: str, scope_school, scope_class, show_school_col: bool):
    """Combined TV/Streaming ranking — sum of official scores across
    Oxygen/Bravo/Peacock (get_overall_leaderboard). A team that's only
    cleared Oxygen still shows up, just with fewer networks counted — not
    zero-padded to look like a bad score. Movies is deliberately excluded
    (its own separate leaderboard tab, a genuinely different track)."""
    board = get_overall_leaderboard(scope_school, scope_class)

    if not board:
        st.markdown("""
        <div style="text-align:center;padding:40px;color:#b0b5c4;
             font-family:DM Mono,monospace;font-size:15px;">
          No submissions yet in this scope.
        </div>
        """, unsafe_allow_html=True)
        return

    top3 = board[:3]
    pcols = st.columns(3)
    for idx, entry in enumerate(top3):
        with pcols[idx]:
            icon = RANK_ICONS.get(entry["rank"], "")
            mc   = RANK_COLORS.get(entry["rank"], TEXT2)
            glow_class = "crown-glow" if entry["rank"] == 1 else ""
            abbrev      = entry.get("class_abbrev", "")
            school_line = (f'<div style="font-size:14px;color:#b0b5c4;margin-top:2px;">'
                            f'{entry.get("school","")} · {entry.get("class_section","")}'
                            f'{f" ({abbrev})" if abbrev else ""}</div>'
                            if show_school_col else "")
            st.markdown(f"""
            <div class="{glow_class}" style="background:#1a1d26;border:2px solid {mc};border-radius:10px;
                 padding:16px;text-align:center;margin-bottom:8px;">
              <div style="font-size:30px;">{icon}</div>
              <div style="font-size:16px;font-weight:600;color:{mc};margin:4px 0;">
                {entry['team_name']}
              </div>
              {school_line}
              <div style="font-family:DM Serif Display,serif;font-size:32px;color:{mc};">
                {entry['total_score']:.0f}
              </div>
              <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;">
                pts · {entry['networks_completed']} network{'s' if entry['networks_completed']!=1 else ''}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    st.markdown('<div class="section-title">Full Rankings — Combined Oxygen + Bravo + Peacock</div>', unsafe_allow_html=True)

    for entry in board:
        rank_c = RANK_COLORS.get(entry["rank"], "#e8eaf0")
        icon   = RANK_ICONS.get(entry["rank"], f"#{entry['rank']}")
        is_me  = entry["team_name"] == team
        bg     = "rgba(232,197,71,.08)" if is_me else "#1a1d26"
        border = "border:1px solid rgba(232,197,71,.3);" if is_me else "border:1px solid #252836;"
        abbrev     = entry.get("class_abbrev", "")
        school_tag = (f'<div style="font-size:14px;color:#b0b5c4;margin-top:1px;">'
                       f'{entry.get("school","")} · {entry.get("class_section","")}'
                       f'{f" ({abbrev})" if abbrev else ""}</div>'
                       if show_school_col else "")
        breakdown_badges = "".join(
            f'<span style="font-size:14px;font-family:DM Mono,monospace;color:#b0b5c4;">'
            f'{NETWORK_INFO[net]["display_name"]}: {score:.0f}</span>'
            for net, score in entry["breakdown"].items()
        )
        st.markdown(f"""
        <div style="background:{bg};{border}border-radius:8px;
             padding:10px 16px;margin-bottom:6px;">
          <div style="display:flex;align-items:center;gap:14px;">
            <div style="font-family:DM Mono,monospace;font-size:16px;
                 color:{rank_c};min-width:32px;font-weight:700;">{icon}</div>
            <div style="flex:1;">
              <div style="font-size:15px;font-weight:600;
                   color:{'#e8c547' if is_me else '#e8eaf0'};">
                {entry['team_name']} {'← YOU' if is_me else ''}
              </div>
              {school_tag}
              <div style="display:flex;gap:12px;margin-top:5px;flex-wrap:wrap;">{breakdown_badges}</div>
            </div>
            <div style="text-align:right;">
              <div style="font-family:DM Serif Display,serif;font-size:20px;color:{rank_c};">
                {entry['total_score']:.0f}
              </div>
              <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;">
                {entry['networks_completed']}/{len(NETWORK_ORDER)} networks
              </div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)


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
             font-family:DM Mono,monospace;font-size:15px;">
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
            abbrev      = entry.get("class_abbrev", "")
            school_line = (f'<div style="font-size:14px;color:#b0b5c4;margin-top:2px;">'
                            f'{entry.get("school","")} · {entry.get("class_section","")}'
                            f'{f" ({abbrev})" if abbrev else ""}</div>'
                            if show_school_col else "")
            st.markdown(f"""
            <div class="{glow_class}" style="background:#1a1d26;border:2px solid {mc};border-radius:10px;
                 padding:16px;text-align:center;margin-bottom:8px;">
              <div style="font-size:30px;">{icon}</div>
              <div style="font-size:16px;font-weight:600;color:{mc};margin:4px 0;">
                {entry['team_name']}
              </div>
              {school_line}
              <div style="font-family:DM Serif Display,serif;font-size:32px;color:{mc};">
                {entry['score']:.0f}
              </div>
              <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;">pts</div>
              <div style="margin-top:8px;font-size:14px;color:#e0e2ea;">{passes} · {ts}</div>
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
        abbrev     = entry.get("class_abbrev", "")
        school_tag = (f'<div style="font-size:14px;color:#b0b5c4;margin-top:1px;">'
                       f'{entry.get("school","")} · {entry.get("class_section","")}'
                       f'{f" ({abbrev})" if abbrev else ""}</div>'
                       if show_school_col else "")
        # Live attempt count -- entry['attempt'] is always 1 (the official
        # first attempt is all the leaderboard ranks on), so this looks up
        # the team's *current* total including retries made since.
        attempts_used = get_attempt_count(entry["team_name"], net,
                                           entry.get("school", ""), entry.get("class_section", ""))
        notables_html = _format_notables_badges(entry.get("notables", {}))
        st.markdown(f"""
        <div style="background:{bg};{border}border-radius:8px;
             padding:10px 16px;margin-bottom:6px;">
          <div style="display:flex;align-items:center;gap:14px;">
            <div style="font-family:DM Mono,monospace;font-size:16px;
                 color:{rank_c};min-width:32px;font-weight:700;">{icon}</div>
            <div style="flex:1;">
              <div style="font-size:15px;font-weight:600;
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
              <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;">
                {passes} · {ts} · {attempts_used}/{MAX_ATTEMPTS} used
              </div>
            </div>
          </div>
          {'<div style="display:flex;gap:12px;margin-top:6px;flex-wrap:wrap;">' +
           ''.join([f'<span style="font-size:14px;font-family:DM Mono,monospace;color:#b0b5c4;">{k}: {v:.0f}</span>'
                    for k,v in details.items() if k not in ("total","passed")]) +
           '</div>' if details else ''}
          {notables_html}
        </div>
        """, unsafe_allow_html=True)

        # ── View this team's slate — comparative analysis, added 2026-07-27 ──
        # Older entries (submitted before slate_summary existed) fall back to
        # a plain "not available" note rather than a blank/broken expander.
        # No `key=` param on st.expander in this Streamlit version — a
        # timestamp in the label (unique per submission) is enough to keep
        # two teams that happen to share a pseudonym from rendering
        # identical expander labels.
        slate = entry.get("slate_summary")
        ts_short = datetime.fromtimestamp(entry["timestamp"]).strftime("%H:%M:%S")
        with st.expander(f"📋 View {entry['team_name']}'s slate ({ts_short})", expanded=False):
            if slate:
                for item in slate:
                    st.markdown(
                        f'<div style="font-size:14px;color:#e0e2ea;padding:3px 0;'
                        f'border-bottom:1px solid rgba(37,40,54,.4);">{_format_slate_item(item)}</div>',
                        unsafe_allow_html=True)
            else:
                st.caption("Slate details aren't available for this entry (submitted before this feature existed).")

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

    # ── Class Awards — superlatives, one per metric ─────────────────────────
    # Complements the single composite Score ranking above: "who's #1
    # overall" vs. "who leads this specific thing." Each award only shows
    # up if at least one team has a real value for it (see
    # get_class_awards's docstring) -- a class with no Emmy recognition
    # yet just won't show that award, rather than crowning a hollow winner.
    awards = get_class_awards(net, scope_school, scope_class)
    if awards:
        st.markdown('<div class="section-title" style="margin-top:12px;">🏆 Class Awards</div>',
                    unsafe_allow_html=True)
        award_cols = st.columns(min(len(awards), 4))
        for i, award in enumerate(awards):
            with award_cols[i % len(award_cols)]:
                st.markdown(f"""
                <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;
                     padding:12px;margin-bottom:10px;height:100%;">
                  <div style="font-size:13px;color:#b0b5c4;font-family:DM Mono,monospace;
                       margin-bottom:4px;">{award['title']}</div>
                  <div style="font-size:16px;font-weight:600;color:#e8c547;">{award['team']}</div>
                  <div style="font-size:14px;color:#e0e2ea;font-family:DM Mono,monospace;">{award['value']}</div>
                </div>
                """, unsafe_allow_html=True)


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
            '<div style="text-align:center;padding:30px;color:#b0b5c4;font-family:DM Mono,monospace;font-size:15px;">'
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
         border-radius:6px;padding:10px 16px;margin-bottom:16px;font-size:15px;color:#e0e2ea;">
    🏆 <b style="color:#e8eaf0;">Official Leaderboard:</b> Rankings use your <b>first attempt only</b>.
    Retries are practice — they don't change your leaderboard position.
    FERPA: Only team names (student-chosen pseudonyms) are stored — no student IDs or names.
    </div>
    """, unsafe_allow_html=True)

    # ── My Status ─────────────────────────────────────────────────────────────
    # Skipped entirely for an anonymous visitor (reachable via "Just check the
    # Leaderboard" on the sign-in screen without registering) -- there's no
    # team to show status for, and get_team_network_status("", "", "") would
    # just render three misleading "Not started" cards for a team that
    # doesn't exist.
    if ss.get("registered"):
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
                  <div style="font-size:40px;margin-bottom:6px;">{info['emoji']}</div>
                  <div style="font-family:DM Mono,monospace;font-size:20px;font-weight:700;
                       color:{info['color2']};">{info['display_name']}</div>
                  <div style="font-family:DM Serif Display,serif;font-size:28px;
                       color:{score_c};margin:8px 0;">{f"{off:.0f}" if off else '—'}</div>
                  <div style="font-size:14px;font-family:DM Mono,monospace;color:#b0b5c4;">
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
    # Anonymous visitors have no school/class to scope "My Class"/"My School"
    # to, so default them straight to "All Schools" instead of a scope that
    # would just come back empty.
    st.markdown('<div class="section-title">Leaderboard Scope</div>', unsafe_allow_html=True)
    scope_options = ["My Class", "My School", "All Schools"]
    scope = st.radio(
        "View", scope_options, horizontal=True, key="lb_scope",
        index=scope_options.index("All Schools") if not ss.get("registered") else 0,
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

    # ── Overall + Per-Network Leaderboards (TV networks + Day 2 Movies) ───────
    # Overall = sum of official scores across Oxygen/Bravo/Peacock only
    # (get_overall_leaderboard) — Movies stays its own separate track, not
    # folded in, per explicit user request.
    all_nets  = list(NETWORK_ORDER) + ["movies"]
    all_infos = {**{n: NETWORK_INFO[n] for n in NETWORK_ORDER}, "movies": MOVIES_INFO}
    tab_labels = ["🌐 Overall"] + [f"{all_infos[n]['emoji']} {all_infos[n]['display_name']}" for n in all_nets]
    overall_tab, *net_tabs = st.tabs(tab_labels)

    with overall_tab:
        _render_overall_tab(team, scope_school, scope_class, show_school_col)

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
        st.markdown('<div style="color:#b0b5c4;font-family:DM Mono,monospace;font-size:15px;">No submissions recorded yet.</div>', unsafe_allow_html=True)
