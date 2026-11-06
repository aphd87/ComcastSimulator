"""Up-front "How you're scored" panels (2026-11-05).

Student feedback after the Oxygen level: the score weights only appeared in
the Student Guide and the end-of-level Score Breakdown, so a student who went
all-in on True Crime didn't learn Genre Mix was 15% of the score until it was
already a 0. These panels show every component, its weight, and what earns
full marks before the first decision, on every track (Oxygen, Bravo,
Peacock, Universal Movies).

Weights are read from the same constants the scoring code uses
(utils/game_state.py::SCORE_WEIGHTS, utils/movie_models.py::
MOVIE_SCORE_WEIGHTS), so the panel can't drift from the real formula.
"""
from __future__ import annotations

import streamlit as st

from utils.game_state import (SCORE_WEIGHTS, PASS_THRESHOLD, GENRE_BASELINE_HHI,
                              genre_target_hhi, BRAND_CORE, MARGIN_FULL_MARKS)
from utils.movie_models import MOVIE_SCORE_WEIGHTS, MOVIE_LUCK_WEIGHT

NETWORK_NAME = {"oxygen": "Oxygen", "bravo": "Bravo", "peacock": "Peacock"}


def _pct(w: float) -> str:
    return f"{w * 100:.0f}%"


def tv_score_rows(net: str) -> list[tuple[str, str, str]]:
    """(component, weight, what earns points) for a TV/Streaming level."""
    core = BRAND_CORE.get(net, "your core genre")
    name = NETWORK_NAME.get(net, "this network")
    w = SCORE_WEIGHTS
    return [
        ("OCF Margin", _pct(w["ocf_margin"]),
         f"OCF ÷ revenue across all years of the level. A {MARGIN_FULL_MARKS.get(net, 40):.0f}% margin "
         f"earns full marks."),
        ("Portfolio ROI", _pct(w["roi_avg"]),
         "Average return on your active shows at the end of the level: −20% scores 0, +60% scores 100."),
        ("Genre Mix", _pct(w["genre_mix"]),
         f"Range across genres, measured by content spend. Keeping {name}'s inherited mix scores 50. "
         f"Keep {core} as the brand core but build real range around it to reach 100. "
         f"Narrowing to a single genre scores 0, even if it's on-brand."),
        ("Marketing Efficiency", _pct(w["mkt_efficiency"]),
         "Revenue per $1M of marketing across the level. $30M of revenue per $1M earns full marks."),
        ("Renewal Quality", _pct(w["renewal_pct"]),
         "Share of the shows you keep that have a positive ROI. Cancel the losers you can't fix."),
    ]


def movie_score_rows() -> list[tuple[str, str, str]]:
    w = MOVIE_SCORE_WEIGHTS
    return [
        ("Risk-Adj. NPV", _pct(w["risk_adjusted_npv"]),
         f"{1 - MOVIE_LUCK_WEIGHT:.0%} your decisions (bear case weighted 50%), {MOVIE_LUCK_WEIGHT:.0%} what "
         "each film actually earned. −$100M scores 0, +$200M scores 100."),
        ("Capital Efficiency", _pct(w["capital_efficiency"]),
         "Lifetime revenue per P&A dollar. 6x earns full marks."),
        ("Strategic Fit", _pct(w["strategic_fit"]),
         "Did your release strategy beat simply going wide theatrical, net of cannibalization?"),
        ("Portfolio Diversification", _pct(w["portfolio_diversification"]),
         "Range across Genre and Concept Type, weighted by capital. Every film in a different genre and "
         "concept type scores 100. Three films in one genre scores 0 on the genre half."),
    ]


def _rows_html(rows) -> str:
    return "".join(
        f'<div style="display:flex;gap:12px;padding:6px 0;border-bottom:1px solid rgba(37,40,54,.6);">'
        f'<span style="min-width:190px;color:#ffffff;font-weight:600;">{label} '
        f'<span style="font-family:DM Mono,monospace;color:#e8c547;">{weight}</span></span>'
        f'<span style="color:#ffffff;font-size:14px;line-height:1.45;">{desc}</span></div>'
        for label, weight, desc in rows)


def _card(title: str, intro: str, rows) -> str:
    return (f'<div class="score-guide" style="background:#12141a;border:1px solid #252836;'
            f'border-left:4px solid #e8c547;border-radius:8px;padding:10px 18px;margin-bottom:16px;">'
            f'<div style="font-family:DM Mono,monospace;font-size:14px;color:#ffffff;text-transform:uppercase;'
            f'letter-spacing:.08em;margin-bottom:6px;">📏 {title}</div>'
            f'<div style="font-size:14px;color:#ffffff;margin-bottom:6px;line-height:1.5;">{intro}</div>'
            f'{_rows_html(rows)}</div>')


def tv_intro(net: str) -> str:
    thr = PASS_THRESHOLD.get(net, 12)
    return (f"Your score is out of 100, built from the five parts below. Passing is separate: "
            f"your OCF margin across the level must reach <b>{thr:.0f}%</b>. "
            f"Your first finished level is your official score.")


def movie_intro() -> str:
    return ("Your slate score is out of 100, built from the four parts below. Passing is separate: your "
            "films' decision NPV must be positive. Your first finished slate is your official score.")


def render_tv_score_guide(net: str, expanded: bool):
    """Expanded card in Year 1; a collapsed expander every later year."""
    html = _card("How you're scored", tv_intro(net), tv_score_rows(net))
    if expanded:
        st.markdown(html, unsafe_allow_html=True)
    else:
        with st.expander("📏 How you're scored (reminder)", expanded=False):
            st.markdown(html, unsafe_allow_html=True)


def render_movie_score_guide(expanded: bool):
    html = _card("How you're scored", movie_intro(), movie_score_rows())
    if expanded:
        st.markdown(html, unsafe_allow_html=True)
    else:
        with st.expander("📏 How you're scored (reminder)", expanded=False):
            st.markdown(html, unsafe_allow_html=True)


__all__ = ["tv_score_rows", "movie_score_rows", "render_tv_score_guide", "render_movie_score_guide",
           "BRAND_CORE", "GENRE_BASELINE_HHI", "genre_target_hhi"]
