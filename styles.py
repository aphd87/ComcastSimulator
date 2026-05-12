"""
Shared CSS injected into every page — light theme.
"""

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

/* ── Base ── */
html, body, [data-testid="stApp"] {
    background-color: #ffffff !important;
    color: #111111 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 15px !important;
}

p, span, div, li { color: #111111 !important; }

[data-testid="stMarkdown"] p,
[data-testid="stMarkdown"] li,
[data-testid="stMarkdown"] span {
    color: #111111 !important;
    font-size: 15px !important;
    line-height: 1.75 !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #f4f5f7 !important;
    border-right: 1px solid #e0e2e8 !important;
}
[data-testid="stSidebar"] * { color: #111111 !important; font-size: 14px !important; }
[data-testid="stSidebar"] label { color: #111111 !important; font-size: 13px !important; font-weight: 600 !important; }

/* ── Headings ── */
h1 { font-family:'DM Serif Display',serif !important; color:#111111 !important; font-size:32px !important; }
h2 { font-family:'DM Serif Display',serif !important; color:#111111 !important; font-size:26px !important; }
h3 { font-family:'DM Serif Display',serif !important; color:#111111 !important; font-size:22px !important; }
h4 { font-family:'DM Sans',sans-serif !important;    color:#111111 !important; font-size:18px !important; font-weight:600 !important; }
h5 { font-family:'DM Sans',sans-serif !important;    color:#111111 !important; font-size:16px !important; }
h6 { font-family:'DM Sans',sans-serif !important;    color:#111111 !important; font-size:15px !important; }

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #f4f5f7 !important;
    border: 1px solid #e0e2e8 !important;
    border-radius: 8px !important;
    padding: 16px 18px !important;
}
[data-testid="stMetricLabel"] {
    color: #b0b5c4 !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: .08em !important;
}
[data-testid="stMetricValue"] {
    color: #111111 !important;
    font-family: 'DM Serif Display', serif !important;
    font-size: 28px !important;
}
[data-testid="stMetricDelta"] { color: #b0b5c4 !important; font-size: 13px !important; }

/* ── Tabs ── */
[data-testid="stTabs"] button {
    color: #b0b5c4 !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    border-bottom: 2px solid transparent !important;
    padding: 10px 16px !important;
    background: transparent !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #c0392b !important;
    border-bottom-color: #c0392b !important;
    font-weight: 700 !important;
}
[data-testid="stTabs"] button:hover { color: #111111 !important; }

/* ── Dataframes ── */
[data-testid="stDataFrame"] { border:1px solid #e0e2e8 !important; border-radius:6px !important; }
.stDataFrame thead th {
    background: #f4f5f7 !important; color: #b0b5c4 !important;
    font-family: 'DM Mono', monospace !important; font-size: 12px !important; font-weight: 700 !important;
}
.stDataFrame tbody td { color: #111111 !important; font-size: 13px !important; font-family: 'DM Mono', monospace !important; }
.stDataFrame tbody tr:hover td { background: #f4f5f7 !important; }

/* ── Sliders ── */
[data-testid="stSlider"] label { color: #111111 !important; font-size: 14px !important; font-weight: 600 !important; }
[data-testid="stSlider"] div[data-baseweb="slider"] div { color: #111111 !important; }

/* ── Inputs ── */
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {
    background: #ffffff !important; border: 1px solid #c8ccd8 !important;
    color: #111111 !important; font-family: 'DM Mono', monospace !important; font-size: 14px !important;
}
[data-testid="stSelectbox"] div[data-baseweb="select"] div { background: #ffffff !important; color: #111111 !important; font-size: 14px !important; border-color: #c8ccd8 !important; }
[data-testid="stSelectbox"] label,
[data-testid="stNumberInput"] label,
[data-testid="stTextInput"] label { color: #111111 !important; font-size: 14px !important; font-weight: 600 !important; }

/* ── Radio / Checkbox ── */
[data-testid="stRadio"] label,
[data-testid="stRadio"] > label,
[data-testid="stCheckbox"] label { color: #111111 !important; font-size: 14px !important; font-weight: 500 !important; }

/* ── Expanders ── */
[data-testid="stExpander"] { background: #f4f5f7 !important; border: 1px solid #e0e2e8 !important; border-radius: 6px !important; }
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p { color: #111111 !important; font-size: 14px !important; font-weight: 600 !important; }

/* ── Alerts ── */
.stAlert { border-radius: 6px !important; font-size: 14px !important; }
.stAlert p { color: #111111 !important; font-size: 14px !important; }

/* ── Buttons ── */
.stButton button {
    background: #ffffff !important; color: #111111 !important;
    border: 1px solid #c8ccd8 !important;
    font-family: 'DM Mono', monospace !important; font-size: 13px !important;
    border-radius: 5px !important; padding: 8px 16px !important; transition: all .15s !important;
}
.stButton button:hover { border-color: #c0392b !important; color: #c0392b !important; }

/* ── Submit button ── */
.submit-btn button {
    background: rgba(192,57,43,.08) !important; border: 2px solid #c0392b !important;
    color: #c0392b !important; font-weight: 700 !important;
    font-size: 15px !important; padding: 10px 24px !important;
}
.submit-btn button:hover { background: rgba(192,57,43,.16) !important; }

/* ── Caption / Download ── */
[data-testid="stCaptionContainer"] p { color: #b0b5c4 !important; font-size: 13px !important; }
[data-testid="stDownloadButton"] button { background: #ffffff !important; color: #111111 !important; border: 1px solid #c8ccd8 !important; font-size: 13px !important; }

/* ── Divider ── */
hr { border-color: #e0e2e8 !important; }

/* ── Network logo ── */
.net-logo-wrap {
    display: flex; align-items: center; gap: 16px;
    padding: 18px 22px; border-radius: 10px; margin-bottom: 16px;
    border: 1px solid #e0e2e8; background: #f4f5f7;
}
.net-logo-text { font-family: 'DM Serif Display', serif; font-size: 40px; letter-spacing: .12em; font-weight: 700; }
.net-tagline   { font-family: 'DM Mono', monospace; font-size: 13px; color: #b0b5c4; margin-top: 4px; }

/* ── Badges ── */
.badge { display:inline-block; padding:3px 9px; border-radius:4px; font-family:'DM Mono',monospace; font-size:12px; font-weight:600; }
.badge-green  { background:#e8f5e9; color:#2e7d32; border:1px solid #a5d6a7; }
.badge-yellow { background:#fff8e1; color:#e65100; border:1px solid #ffcc02; }
.badge-red    { background:#ffebee; color:#c62828; border:1px solid #ef9a9a; }
.badge-blue   { background:#e3f2fd; color:#1565c0; border:1px solid #90caf9; }
.badge-gray   { background:#f4f5f7; color:#b0b5c4; border:1px solid #c8ccd8; }
.badge-gold   { background:#fff8e1; color:#c0392b; border:1px solid #ffcc02; }

/* ── Section titles ── */
.section-title {
    font-family: 'DM Mono', monospace; font-size: 11px; text-transform: uppercase;
    letter-spacing: .12em; color: #b0b5c4; margin-bottom: 10px;
    padding-bottom: 6px; border-bottom: 2px solid #e0e2e8;
}

/* ── Phase banners ── */
.phase-banner { padding:10px 16px; border-radius:6px; font-family:'DM Mono',monospace; font-size:13px; margin-bottom:12px; font-weight:600; }
.phase-1 { background:#fff0ee; color:#c0392b; border:1px solid #f5c6c0; }
.phase-2 { background:#f5eeff; color:#6d28d9; border:1px solid #d8b4fe; }
.phase-3 { background:#e8f4ff; color:#1565c0; border:1px solid #90caf9; }

/* ── Score ring ── */
.score-ring {
    width:90px; height:90px; border-radius:50%;
    display:flex; align-items:center; justify-content:center; flex-direction:column;
    font-family:'DM Serif Display',serif; font-size:26px; border:3px solid; margin:0 auto;
}

/* ── Leaderboard rows ── */
.lb-row { display:flex; align-items:center; gap:12px; padding:10px 14px; border-radius:6px; margin-bottom:4px; background:#f4f5f7; border:1px solid #e0e2e8; }
.lb-rank  { font-family:'DM Mono',monospace; font-size:15px; min-width:30px; font-weight:700; color:#111111; }
.lb-team  { font-size:15px; flex:1; font-weight:500; color:#111111; }
.lb-score { font-family:'DM Mono',monospace; font-size:16px; font-weight:700; color:#c0392b; }

/* ── Theory cards ── */
.theory-card { background:#f4f5f7; border:1px solid #e0e2e8; border-radius:8px; padding:16px 18px; height:100%; }
.theory-icon  { font-size:26px; margin-bottom:8px; }
.theory-title { font-family:'DM Mono',monospace; font-size:12px; font-weight:700; color:#c0392b; text-transform:uppercase; letter-spacing:.08em; margin-bottom:10px; }
.theory-body  { font-size:14px; color:#333344; line-height:1.75; }

/* ── Inline card panels ── */
.info-card { background:#f4f5f7; border:1px solid #e0e2e8; border-radius:8px; padding:14px 16px; }

/* ── Pulse ── */
@keyframes pulse-green { 0%,100%{opacity:1} 50%{opacity:.6} }
.live-good { animation:pulse-green .8s ease 1; color:#2e7d32; }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header, [data-testid="stToolbar"] { display:none !important; }
</style>
"""
