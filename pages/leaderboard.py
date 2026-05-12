"""
Tab 7 — Leaderboard
Per-network rankings using official (first attempt) scores only.
FERPA-safe: displays team names (pseudonyms) only.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from utils.game_state import (
    get_network_leaderboard, NETWORK_ORDER, NETWORK_INFO,
    get_team_network_status, load_leaderboard
)
from utils.charts import base_layout, SUCCESS, DANGER, WARN, ACCENT, ACCENT2, TEXT2


RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
RANK_COLORS = {1: "#e8c547", 2: "#c0c0c0", 3: "#cd7f32"}


def render():
    ss   = st.session_state
    team = ss.team_name

    st.markdown("""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #e8c547;
         border-radius:6px;padding:10px 16px;margin-bottom:16px;font-size:12px;color:#8b90a0;">
    🏆 <b style="color:#e8eaf0;">Official Leaderboard:</b> Rankings use your <b>first attempt only</b>.  
    Retries are practice — they don't change your leaderboard position.  
    FERPA: Only team names (student-chosen pseudonyms) are stored — no student IDs or names.
    </div>
    """, unsafe_allow_html=True)

    # ── My Status ─────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">My Team Status</div>', unsafe_allow_html=True)
    status = get_team_network_status(team)

    cols = st.columns(3)
    for i, net in enumerate(NETWORK_ORDER):
        info  = NETWORK_INFO[net]
        stat  = status.get(net, {})
        off   = stat.get("official_score")
        att   = stat.get("attempts", 0)
        pas   = stat.get("passed", False)

        with cols[i]:
            border_c = info["color"] if pas else ("#252836")
            score_c  = "#66bb6a" if pas else ("#ffa726" if att > 0 else "#555a6e")
            st.markdown(f"""
            <div style="background:#1a1d26;border:2px solid {border_c};border-radius:10px;
                 padding:16px;text-align:center;">
              <div style="font-size:22px;margin-bottom:4px;">{info['emoji']}</div>
              <div style="font-family:DM Mono,monospace;font-size:13px;font-weight:600;
                   color:{info['color2']};">{info['display_name']}</div>
              <div style="font-family:DM Serif Display,serif;font-size:28px;
                   color:{score_c};margin:8px 0;">{f"{off:.0f}" if off else '—'}</div>
              <div style="font-size:10px;font-family:DM Mono,monospace;color:#555a6e;">
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

    # ── Per-Network Leaderboards ───────────────────────────────────────────────
    net_tabs = st.tabs([f"{NETWORK_INFO[n]['emoji']} {NETWORK_INFO[n]['display_name']}" for n in NETWORK_ORDER])

    for tab, net in zip(net_tabs, NETWORK_ORDER):
        with tab:
            info   = NETWORK_INFO[net]
            board  = get_network_leaderboard(net)

            if not board:
                st.markdown(f"""
                <div style="text-align:center;padding:40px;color:#555a6e;
                     font-family:DM Mono,monospace;font-size:12px;">
                  No submissions yet for {info['display_name']}.
                </div>
                """, unsafe_allow_html=True)
                continue

            # Top 3 podium
            top3 = board[:3]
            pcols = st.columns(3)
            for idx, entry in enumerate(top3):
                with pcols[idx]:
                    medal  = RANK_MEDALS.get(entry["rank"], "")
                    mc     = RANK_COLORS.get(entry["rank"], TEXT2)
                    ts     = datetime.fromtimestamp(entry["timestamp"]).strftime("%b %d %H:%M")
                    passes = "✅" if entry["passed"] else "❌"
                    st.markdown(f"""
                    <div style="background:#1a1d26;border:2px solid {mc};border-radius:10px;
                         padding:16px;text-align:center;margin-bottom:8px;">
                      <div style="font-size:28px;">{medal}</div>
                      <div style="font-size:14px;font-weight:600;color:{mc};margin:4px 0;">
                        {entry['team_name']}
                      </div>
                      <div style="font-family:DM Serif Display,serif;font-size:32px;color:{mc};">
                        {entry['score']:.0f}
                      </div>
                      <div style="font-size:10px;color:#555a6e;font-family:DM Mono,monospace;">pts</div>
                      <div style="margin-top:8px;font-size:11px;color:#8b90a0;">{passes} · {ts}</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.divider()

            # Full leaderboard table
            st.markdown('<div class="section-title">Full Rankings — Official Scores</div>', unsafe_allow_html=True)

            for entry in board:
                rank_c = RANK_COLORS.get(entry["rank"], "#e8eaf0")
                medal  = RANK_MEDALS.get(entry["rank"], f"#{entry['rank']}")
                is_me  = entry["team_name"] == team
                bg     = "rgba(232,197,71,.08)" if is_me else "#1a1d26"
                border = "border:1px solid rgba(232,197,71,.3);" if is_me else "border:1px solid #252836;"
                ts     = datetime.fromtimestamp(entry["timestamp"]).strftime("%b %d")
                passes = "✅" if entry["passed"] else "❌"

                # Score bar
                bar_w  = entry["score"]
                bar_c  = SUCCESS if entry["score"] >= 70 else (WARN if entry["score"] >= 50 else DANGER)

                details = entry.get("details", {})
                st.markdown(f"""
                <div style="background:{bg};{border}border-radius:8px;
                     padding:10px 16px;margin-bottom:6px;">
                  <div style="display:flex;align-items:center;gap:14px;">
                    <div style="font-family:DM Mono,monospace;font-size:14px;
                         color:{rank_c};min-width:32px;font-weight:700;">{medal}</div>
                    <div style="flex:1;">
                      <div style="font-size:13px;font-weight:600;
                           color:{'#e8c547' if is_me else '#e8eaf0'};">
                        {entry['team_name']} {'← YOU' if is_me else ''}
                      </div>
                      <div style="height:4px;background:#252836;border-radius:2px;
                           margin-top:5px;overflow:hidden;">
                        <div style="width:{bar_w}%;height:100%;background:{bar_c};border-radius:2px;"></div>
                      </div>
                    </div>
                    <div style="text-align:right;">
                      <div style="font-family:DM Serif Display,serif;font-size:20px;color:{bar_c};">
                        {entry['score']:.0f}
                      </div>
                      <div style="font-size:10px;color:#555a6e;font-family:DM Mono,monospace;">
                        {passes} · {ts}
                      </div>
                    </div>
                  </div>
                  {'<div style="display:flex;gap:12px;margin-top:6px;flex-wrap:wrap;">' +
                   ''.join([f'<span style="font-size:10px;font-family:DM Mono,monospace;color:#555a6e;">{k}: {v:.0f}</span>'
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

    st.divider()

    # ── All-Network Summary ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">All Submissions — Raw Data</div>', unsafe_allow_html=True)

    all_entries = load_leaderboard()
    if all_entries:
        raw_df = pd.DataFrame([{
            "Team":      e["team_name"],
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
        st.markdown('<div style="color:#555a6e;font-family:DM Mono,monospace;font-size:12px;">No submissions recorded yet.</div>', unsafe_allow_html=True)
