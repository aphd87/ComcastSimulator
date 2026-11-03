"""
Movies Follow Along (2026-11-03, per user: "build out movies follow along view").

TV/Streaming already lets one Driver play while teammates on other laptops
watch read-only (app.py's _build_live_snapshot / _render_follow_along_summary).
This is the Movies parallel:

- The Driver's movie_* session state is snapshotted to JSON at the end of
  every Movies render and saved under its own team-state key (TV's live
  state is untouched, so a team can be in TV on one laptop and Movies on
  another without either overwriting the other).
- A Follow Along viewer's Movies screen auto-refreshes every 5 seconds,
  loads that snapshot, and shows a read-only view built from the same
  display helpers the Driver sees (progress bar, slate strip, last result,
  NPV-by-year chart, Your Slate, the film in development). No decision
  widgets render, so a viewer can never change the Driver's game.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.charts import html_table, takeaway

# Every piece of Movies game state lives in a "movie_" key initialized by
# app_pages/movies.py::_init, plus submit flags. Widget keys are excluded
# (they're per-cycle "movie_*_<n>" inputs the viewer never renders).
MOVIE_STATE_KEYS = (
    "movie_cycle", "movie_phase", "movie_log", "movie_draft", "movie_overall_deal",
    "movie_overall_deal_signed_cycle", "movie_overall_renewed_through", "movie_greenlit",
    "movie_deal_ledger", "movie_partner_releases", "movie_talent_holds", "movie_rival_exclusive",
    "movie_rival_poach_checked_through", "movie_talent_total_spend", "movie_research_paid",
    "movie_scouted_optioned", "movie_scouted_poached", "movie_scouted_resolved_through",
    "movie_multi_picture_deals", "movie_studio_budget_m", "movie_studio_budget_updated_through",
    "movie_theatrical_resolved", "movie_pvod_checkpoints", "movie_pvod_pending_rejection",
    "movie_licensing_auction", "movie_festival_log", "movie_festival_rival_log",
    "movie_festival_resolved_through", "movie_submitted", "movie_last_score",
)


# ── JSON-safe encoding (sets, tuples, int-keyed dicts, numpy scalars) ───────
def _enc(o):
    if isinstance(o, dict):
        if all(isinstance(k, str) for k in o):
            return {k: _enc(v) for k, v in o.items()}
        return {"__map__": [[_enc(k), _enc(v)] for k, v in o.items()]}
    if isinstance(o, (set, frozenset)):
        return {"__set__": [_enc(v) for v in o]}
    if isinstance(o, tuple):
        return {"__tuple__": [_enc(v) for v in o]}
    if isinstance(o, list):
        return [_enc(v) for v in o]
    if hasattr(o, "item") and callable(o.item) and type(o).__module__ == "numpy":
        return o.item()
    if o is None or isinstance(o, (str, int, float, bool)):
        return o
    if hasattr(o, "__dataclass_fields__"):
        from dataclasses import asdict
        return _enc(asdict(o))
    return str(o)


def _dec(o):
    if isinstance(o, list):
        return [_dec(v) for v in o]
    if isinstance(o, dict):
        if set(o) == {"__map__"}:
            return {_dec(k): _dec(v) for k, v in o["__map__"]}
        if set(o) == {"__set__"}:
            return {_dec(v) for v in o["__set__"]}
        if set(o) == {"__tuple__"}:
            return tuple(_dec(v) for v in o["__tuple__"])
        return {k: _dec(v) for k, v in o.items()}
    return o


def build_snapshot(ss) -> dict:
    return {k: _enc(ss.get(k)) for k in MOVIE_STATE_KEYS if k in ss}


def apply_snapshot(ss, snap: dict) -> None:
    for k in MOVIE_STATE_KEYS:
        if k in snap:
            ss[k] = _dec(snap[k])


# ── Read-only viewer screen ─────────────────────────────────────────────────
def render_viewer(ss) -> None:
    from app_pages import movies as mv

    st.markdown(
        '<div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #ffa726;'
        'border-radius:6px;padding:10px 16px;margin-bottom:16px;font-size:15px;color:#ffffff;">'
        '👀 <b>Follow Along mode:</b> you\'re watching your Driver\'s studio live, read-only. This screen '
        'updates every few seconds. Talk through each decision with your Driver; only their clicks count.'
        '</div>', unsafe_allow_html=True)
    if not ss.get("movie_follow_has_state"):
        st.info("Your Driver hasn't opened the Movies simulation yet. This screen will fill in as soon as they do. "
                "Check that you registered with exactly the same University, School, Class and Team Name.")
        return
    if st.button("🔄 Refresh now", key="movie_viewer_refresh", use_container_width=True):
        st.rerun()

    mv._init(ss)
    st.markdown(mv._MOVIES_LAYOUT_CSS, unsafe_allow_html=True)
    mv._progress_bar(ss)

    phase = ss.movie_phase
    cycle = ss.movie_cycle
    log = sorted(ss.movie_log, key=lambda r: r["cycle"])
    phase_text = {"decisions": f"is making decisions for {mv._cycle_years_label(cycle)}",
                  "results": f"is looking at the results for {mv._cycle_years_label(cycle)}",
                  "complete": "has finished the slate"}.get(phase, phase)
    st.markdown(f'<div style="font-size:16px;color:#ffffff;margin:6px 0 12px;">Your Driver <b>{phase_text}</b>. '
                f'Studio budget: <b>${ss.get("movie_studio_budget_m", 0):.0f}M</b>.</div>',
                unsafe_allow_html=True)
    st.markdown(mv._slate_strip_html(ss), unsafe_allow_html=True)

    # The film being developed right now (decisions phase).
    draft = ss.get("movie_draft") or {}
    if phase == "decisions" and draft:
        labels = [("Title", "title"), ("Genre", "genre"), ("Concept", "concept_type"),
                  ("Source", "source_material"), ("Production budget", "production_budget_m"),
                  ("P&A (marketing)", "pa_spend_m"), ("Star power", "star_power"),
                  ("Release strategy", "release_strategy"), ("Theatrical run (days)", "theatrical_run_days"),
                  ("Debut season", "debut_season"), ("Logline", "logline")]
        rows = []
        for lbl, k in labels:
            v = draft.get(k)
            if v in (None, ""):
                continue
            if k.endswith("_m") and isinstance(v, (int, float)):
                v = f"${v:,.1f}M"
            elif k == "release_strategy":
                v = mv.RELEASE_LABELS.get(v, v)
            rows.append({"Decision": lbl, "Driver's current choice": v})
        if rows:
            st.markdown('<div class="section-title">🎬 The film in development</div>', unsafe_allow_html=True)
            html_table(pd.DataFrame(rows))
            takeaway("These are the Driver's choices so far for this film. Ask: does the budget fit the genre, "
                     "and is the marketing (P&amp;A) big enough for the release they're planning?")

    if log:
        st.markdown('<div class="section-title">Last result</div>', unsafe_allow_html=True)
        mv._last_cycle_recap(log[-1])
        if len(log) >= 2:
            mv._progress_chart(ss)
        mv._section_your_slate(ss)
    else:
        st.caption("No films released yet. Results will appear here after your Driver simulates the first period.")

    if phase == "complete" and ss.get("movie_last_score"):
        sc = ss.movie_last_score
        st.success(f"Final slate score: {sc.get('score', 0):.1f} "
                   f"({'passed' if sc.get('passed') else 'did not pass'}). See the 🏆 Leaderboard for your rank.")
