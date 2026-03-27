"""
Shared Plotly theme and chart helpers — matches the dark CableOS aesthetic.
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

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
TEXT     = "#e8eaf0"
TEXT2    = "#8b90a0"
BRAVO_C  = "#c0392b"
OXY_C    = "#8e44ad"
SVOD_C   = "#1a6bb5"

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
        title=dict(text=title, font=dict(color=TEXT2, size=12,
                   family="DM Mono, monospace"), x=0),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Mono, monospace", color=TEXT2, size=11),
        margin=dict(l=40, r=20, t=36, b=36),
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0,
                    font=dict(size=10)),
        xaxis=dict(gridcolor=BORDER, zeroline=False,
                   tickfont=dict(size=10)),
        yaxis=dict(gridcolor=BORDER, zeroline=False,
                   tickfont=dict(size=10)),
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

def donut_chart(labels: list, values: list, title: str = "",
                height: int = 300) -> go.Figure:
    colors = [GENRE_COLORS.get(l, ACCENT) for l in labels]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color=SURFACE, width=2)),
        textfont=dict(size=10),
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
        textfont=dict(size=10, color=TEXT),
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
