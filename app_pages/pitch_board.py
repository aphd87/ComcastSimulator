"""Peer Pitch Board (2026-10-01): browse the pitches other teams in your class
have committed, across TV / Streaming and Movies.

Replaces AI pitch feedback. Pitches are posted by app_pages/greenlight.py (a
TV show a team greenlights from its own pitch) and app_pages/movies.py (a film
a team simulates, with its logline and actual result). Scoped to the viewer's
own school + class section. Renders no expanders, so callers can place it
inside one.
"""
from html import escape

import streamlit as st

from utils.game_state import class_pitches

_SIM_LABEL = {"tv": "📺 TV / Streaming", "movies": "🎬 Movies"}


def _detail_line(e: dict) -> str:
    d = e.get("details", {})
    if e.get("sim") == "tv":
        parts = [d.get("network"), d.get("year_label"),
                 f'{d["episodes"]} eps · ${d["ep_cost_k"]}K/ep' if "episodes" in d and "ep_cost_k" in d else None,
                 f'rating {d["rating"]:.1f}' if isinstance(d.get("rating"), (int, float)) else None]
    else:
        parts = [d.get("cycle_label"), d.get("concept_type"),
                 f'${d["budget_m"]:.0f}M budget' if isinstance(d.get("budget_m"), (int, float)) else None,
                 f'${d["pa_spend_m"]:.0f}M P&A' if isinstance(d.get("pa_spend_m"), (int, float)) else None,
                 d.get("release_label")]
    return " · ".join(escape(str(p)) for p in parts if p)


def _outcome_line(e: dict) -> str:
    d = e.get("details", {})
    if e.get("sim") == "movies" and isinstance(d.get("npv"), (int, float)):
        color = "#66bb6a" if d["npv"] >= 0 else "#ef5350"
        crit = f' · critics {d["critical_score"]:.0f}/100' if isinstance(d.get("critical_score"), (int, float)) else ""
        return (f'<div style="font-size:13px;color:{color};margin-top:6px;">'
                f'Result: NPV ${d["npv"]:+.1f}M{crit}</div>')
    return ""


def render_pitch_board(ss, sim: str | None = None, limit: int | None = None, key: str = "pitch_board") -> None:
    """Cards for every pitch posted in the viewer's class. `sim` fixes the
    simulation ("tv" / "movies"); None shows a filter. `limit` caps the count."""
    if not ss.get("registered") or not ss.get("school"):
        st.markdown('<div style="font-size:14px;color:#ffffff;">Register a team to see the pitches '
                    'posted in your class.</div>', unsafe_allow_html=True)
        return

    if sim is None:
        choice = st.radio("Show pitches from", ["All", "📺 TV / Streaming", "🎬 Movies"],
                          horizontal=True, key=f"{key}_filter")
        sim = {"📺 TV / Streaming": "tv", "🎬 Movies": "movies"}.get(choice)

    pitches = class_pitches(ss.school, ss.class_section, sim=sim)
    if not pitches:
        empty_msg = {"movies": "No movie pitches posted in your class yet. A pitch appears here when a "
                               "team simulates its film.",
                     "tv": "No TV pitches posted in your class yet. A pitch appears here when a team "
                           "greenlights its own show."}.get(
            sim, "No pitches posted in your class yet. A pitch appears here when a team greenlights its "
                 "own TV show or simulates a film.")
        st.markdown(f'<div style="font-size:14px;color:#ffffff;">{empty_msg}</div>', unsafe_allow_html=True)
        return

    shown = pitches[:limit] if limit else pitches
    st.markdown(f'<div style="font-size:13px;color:#ffffff;margin-bottom:6px;">{len(pitches)} pitch'
                f'{"es" if len(pitches) != 1 else ""} from {ss.class_section}'
                f'{" — showing the latest " + str(len(shown)) if len(shown) < len(pitches) else ""}.</div>',
                unsafe_allow_html=True)
    cols = st.columns(2)
    for i, e in enumerate(shown):
        mine = e.get("team_name") == ss.get("team_name")
        border = "#e8c547" if mine else "#252836"
        team = escape(e.get("team_name", "")) + (" (your team)" if mine else "")
        with cols[i % 2]:
            st.markdown(f"""
            <div style="background:#1a1d26;border:1px solid {border};border-radius:8px;padding:12px 14px;margin-bottom:10px;">
              <div style="font-size:12px;color:#ffffff;font-family:DM Mono,monospace;">
                {_SIM_LABEL.get(e.get("sim"), "")} · {team}</div>
              <div style="font-size:15px;font-weight:600;color:#ffffff;margin-top:2px;">{escape(e.get("title", ""))}</div>
              <div style="font-size:12px;color:#ffffff;font-family:DM Mono,monospace;margin:2px 0 6px;">
                {escape(e.get("genre", ""))}{" · " + _detail_line(e) if _detail_line(e) else ""}</div>
              <div style="font-size:14px;color:#ffffff;line-height:1.5;">{escape(e.get("pitch", ""))}</div>
              {_outcome_line(e)}
            </div>
            """, unsafe_allow_html=True)
