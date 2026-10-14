"""
Shared Plotly theme and chart helpers — matches the dark The Slate aesthetic.
"""
from __future__ import annotations   # list[...]/dict[...] type hints below need Python
                                       # 3.9+ without this — see utils/game_state.py
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import streamlit as st

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#0b0c10"
SURFACE  = "#12141a"
SURFACE2 = "#1a1d26"
BORDER   = "#252836"
ACCENT   = "#e8c547"
ACCENT2  = "#4fc3f7"
DANGER   = "#ef5350"
SUCCESS  = "#66bb6a"
WARN     = "#ffa726"
TEXT     = "#ffffff"
TEXT2    = "#ffffff"
BRAVO_C  = "#1a6bb5"
OXY_C    = "#f2c200"
SVOD_C   = "#8e44ad"


# ── Accessible color helpers (WCAG 2.1 AA, 2026-10-14) ──────────────────────
# Network brand colors (Bravo blue, Peacock purple) are too dark to read as
# text on the app's near-black surfaces. Keep them for bars/borders/logos;
# route any TEXT in a brand color through readable_text().
def _luminance(hex_c: str) -> float:
    h = hex_c.lstrip("#")
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def readable_text(hex_c: str, bg: str = SURFACE2, target: float = 4.5) -> str:
    """Lighten hex_c toward white just enough to reach `target` contrast
    against bg (default: the lightest card surface, so it passes on all)."""
    if not (isinstance(hex_c, str) and hex_c.startswith("#") and len(hex_c) == 7):
        return hex_c
    r, g, b = (int(hex_c[i:i + 2], 16) for i in (1, 3, 5))
    for step in range(0, 101, 5):
        t = step / 100
        c = "#{:02x}{:02x}{:02x}".format(round(r + (255 - r) * t),
                                         round(g + (255 - g) * t),
                                         round(b + (255 - b) * t))
        if contrast_ratio(c, bg) >= target:
            return c
    return "#ffffff"


def ink_on(bg_hex: str) -> str:
    """Black or white text, whichever reads better on a filled background."""
    return "#0b0c10" if contrast_ratio("#0b0c10", bg_hex) >= contrast_ratio("#ffffff", bg_hex) else "#ffffff"

GENRE_COLORS = {
    "Reality":     ACCENT,
    "Competition": ACCENT2,
    "Talk":        SUCCESS,
    "Scripted":    WARN,
    "True Crime":  OXY_C,
    "Drama":       DANGER,
    "Other":       TEXT2,
}

def base_layout(title: str = "", height: int = 320) -> dict:
    return dict(
        title=dict(text=title, font=dict(color=TEXT2, size=13,
                   family="DM Mono, monospace"), x=0),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Mono, monospace", color=TEXT2, size=12),
        margin=dict(l=40, r=20, t=36, b=36),
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0,
                    font=dict(size=12)),
        xaxis=dict(gridcolor=BORDER, zeroline=False,
                   tickfont=dict(size=12)),
        yaxis=dict(gridcolor=BORDER, zeroline=False,
                   tickfont=dict(size=12)),
    )

def bar_chart(df: pd.DataFrame, x: str, y: list[str],
              colors: list[str], title: str = "", height: int = 320,
              barmode: str = "group") -> go.Figure:
    fig = go.Figure()
    for col, color in zip(y, colors):
        fig.add_trace(go.Bar(
            x=df[x], y=df[col], name=col,
            marker_color=color,
            marker_line_width=0,
        ))
    fig.update_layout(**base_layout(title, height), barmode=barmode)
    return fig

def line_chart(df: pd.DataFrame, x: str, y_cols: list[str],
               colors: list[str], title: str = "", height: int = 320,
               fill_first: bool = False) -> go.Figure:
    fig = go.Figure()
    for i, (col, color) in enumerate(zip(y_cols, colors)):
        fig.add_trace(go.Scatter(
            x=df[x], y=df[col], name=col,
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=5),
            fill="tozeroy" if (fill_first and i == 0) else "none",
            fillcolor=color.replace(")", ",0.1)").replace("rgb", "rgba"),
        ))
    fig.update_layout(**base_layout(title, height))
    return fig

def queue_supplement(title: str, render_fn, when_to_use: str = "") -> None:
    """Show an explanatory, non-scored chart as its own collapsed "📊 Why?"
    box right where it's called, i.e. directly under the decision it explains.

    2026-10-01: these used to be collected into one "Supplementary Insights"
    box just above Simulate, so students only reached them after they'd
    already made the decisions they explain. Callers must not be inside
    another expander (nested expanders crash older Streamlit).
    render_fn is a no-arg callable (a closure over the values the chart needs)."""
    with st.expander(f"📊 Why? (optional) — {title}", expanded=False):
        if when_to_use:
            st.markdown(f'<div style="font-size:14px;color:#ffffff;margin-bottom:6px;">'
                        f'<b>Use this when:</b> {when_to_use} Not scored.</div>', unsafe_allow_html=True)
        render_fn()


def donut_chart(labels: list, values: list, title: str = "",
                height: int = 300) -> go.Figure:
    colors = [GENRE_COLORS.get(l, ACCENT) for l in labels]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color=SURFACE, width=2)),
        textfont=dict(size=12),
        hovertemplate="%{label}: $%{value:.1f}M<extra></extra>",
    ))
    fig.update_layout(**base_layout(title, height))
    fig.update_layout(showlegend=True)
    return fig

def waterfall_chart(labels: list, values: list,
                    title: str = "", height: int = 320) -> go.Figure:
    colors = [SUCCESS if v >= 0 else DANGER for v in values]
    # last bar is total
    measure = ["relative"] * (len(values) - 1) + ["total"]
    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=measure,
        connector=dict(line=dict(color=BORDER)),
        increasing=dict(marker_color=SUCCESS),
        decreasing=dict(marker_color=DANGER),
        totals=dict(marker_color=ACCENT),
        texttemplate="%{y:.1f}",
        textposition="outside",
        textfont=dict(size=12, color=TEXT),
    ))
    fig.update_layout(**base_layout(title, height))
    return fig

def scatter_chart(df: pd.DataFrame, x: str, y: str, size: str,
                  color: str, hover: str, title: str = "",
                  height: int = 340) -> go.Figure:
    fig = px.scatter(
        df, x=x, y=y, size=size, color=color,
        hover_name=hover,
        color_discrete_map=GENRE_COLORS,
        size_max=30,
    )
    fig.update_layout(**base_layout(title, height))
    fig.update_traces(marker=dict(line=dict(width=1, color=SURFACE)))
    return fig
