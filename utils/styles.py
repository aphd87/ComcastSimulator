"""
Shared CSS injected into every page.
"""

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [data-testid="stApp"] {
    background-color: #0b0c10 !important;
    color: #e8eaf0;
    font-family: 'DM Sans', sans-serif;
}
[data-testid="stSidebar"] {
    background-color: #12141a !important;
    border-right: 1px solid #252836;
}
[data-testid="stSidebar"] * { color: #e8eaf0 !important; }

h1,h2,h3 { font-family:'DM Serif Display',serif !important; color:#e8eaf0 !important; }
h4,h5,h6 { font-family:'DM Sans',sans-serif !important; color:#e8eaf0 !important; }

[data-testid="stMetric"] {
    background:#12141a;border:1px solid #252836;border-radius:8px;padding:14px 16px !important;
}
[data-testid="stMetricLabel"] { color:#8b90a0 !important;font-size:11px !important;text-transform:uppercase;letter-spacing:.08em; }
[data-testid="stMetricValue"] { color:#e8eaf0 !important;font-family:'DM Serif Display',serif !important; }

[data-testid="stTabs"] button {
    color:#8b90a0 !important;font-family:'DM Mono',monospace !important;font-size:12px !important;
    border-bottom:2px solid transparent !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color:#e8c547 !important;border-bottom-color:#e8c547 !important;
}

.stDataFrame { border:1px solid #252836 !important;border-radius:6px; }
.stDataFrame thead th { background:#1a1d26 !important;color:#8b90a0 !important;
    font-family:'DM Mono',monospace;font-size:11px; }

[data-testid="stSlider"] > div > div { background:#252836 !important; }

[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] div,
[data-testid="stTextInput"] input {
    background:#1a1d26 !important;border-color:#252836 !important;
    color:#e8eaf0 !important;font-family:'DM Mono',monospace !important;
}
[data-testid="stExpander"] {
    background:#12141a !important;border:1px solid #252836 !important;border-radius:6px !important;
}
.stAlert { border-radius:6px !important;font-family:'DM Mono',monospace !important;font-size:12px; }
.stButton button {
    background:#1a1d26 !important;color:#e8eaf0 !important;border:1px solid #252836 !important;
    font-family:'DM Mono',monospace !important;font-size:12px !important;border-radius:5px !important;
    transition: all .15s;
}
.stButton button:hover { border-color:#e8c547 !important;color:#e8c547 !important; }

/* Submit button special styling */
.submit-btn button {
    background:rgba(232,197,71,.15) !important;border:2px solid #e8c547 !important;
    color:#e8c547 !important;font-weight:600 !important;font-size:14px !important;
    padding:8px 24px !important;
}
.submit-btn button:hover { background:rgba(232,197,71,.3) !important; }

/* Network logo */
.net-logo-wrap {
    display:flex;align-items:center;gap:16px;
    padding:16px 20px;
    border-radius:10px;margin-bottom:16px;
    border:1px solid rgba(255,255,255,.08);
}
.net-logo-text {
    font-family:'DM Serif Display',serif;
    font-size:36px;letter-spacing:.12em;
    font-weight:700;
}
.net-tagline { font-family:'DM Mono',monospace;font-size:11px;color:#8b90a0;margin-top:2px; }

/* Badge pills */
.badge { display:inline-block;padding:2px 8px;border-radius:4px;
    font-family:'DM Mono',monospace;font-size:11px;font-weight:500; }
.badge-green  { background:rgba(102,187,106,.15);color:#81c784;border:1px solid rgba(102,187,106,.3); }
.badge-yellow { background:rgba(255,167,38,.15);color:#ffb74d;border:1px solid rgba(255,167,38,.3); }
.badge-red    { background:rgba(239,83,80,.15);color:#ef9a9a;border:1px solid rgba(239,83,80,.3); }
.badge-blue   { background:rgba(79,195,247,.15);color:#81d4fa;border:1px solid rgba(79,195,247,.3); }
.badge-gray   { background:rgba(139,144,160,.15);color:#8b90a0;border:1px solid rgba(139,144,160,.3); }
.badge-gold   { background:rgba(232,197,71,.15);color:#e8c547;border:1px solid rgba(232,197,71,.3); }

.section-title {
    font-family:'DM Mono',monospace;font-size:10px;text-transform:uppercase;
    letter-spacing:.12em;color:#555a6e;margin-bottom:8px;
    padding-bottom:6px;border-bottom:1px solid #252836;
}
.phase-banner { padding:8px 16px;border-radius:6px;font-family:'DM Mono',monospace;font-size:12px;margin-bottom:12px; }
.phase-1 { background:rgba(192,57,43,.15);color:#e57373;border:1px solid rgba(192,57,43,.3); }
.phase-2 { background:rgba(142,68,173,.15);color:#ba68c8;border:1px solid rgba(142,68,173,.3); }
.phase-3 { background:rgba(26,107,181,.15);color:#4fc3f7;border:1px solid rgba(26,107,181,.3); }

/* Score ring */
.score-ring {
    width:90px;height:90px;border-radius:50%;
    display:flex;align-items:center;justify-content:center;flex-direction:column;
    font-family:'DM Serif Display',serif;font-size:26px;
    border:3px solid;margin:0 auto;
}

/* Leaderboard rows */
.lb-row {
    display:flex;align-items:center;gap:12px;
    padding:8px 12px;border-radius:6px;margin-bottom:4px;
    background:#1a1d26;border:1px solid #252836;
}
.lb-rank { font-family:'DM Mono',monospace;font-size:13px;min-width:28px;font-weight:600; }
.lb-team { font-size:13px;flex:1;font-weight:500; }
.lb-score { font-family:'DM Mono',monospace;font-size:14px;font-weight:600; }

/* Theory card */
.theory-card {
    background:#12141a;border:1px solid #252836;border-radius:8px;
    padding:14px 16px;height:100%;
}
.theory-icon { font-size:24px;margin-bottom:6px; }
.theory-title { font-family:'DM Mono',monospace;font-size:11px;font-weight:600;
    color:#e8c547;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px; }
.theory-body { font-size:12px;color:#8b90a0;line-height:1.6; }

/* Real-time feedback pulse */
@keyframes pulse-green { 0%,100%{opacity:1} 50%{opacity:.6} }
.live-good { animation: pulse-green .8s ease 1; color:#66bb6a; }

/* Lock overlay */
.locked-overlay {
    background:rgba(11,12,16,.85);border:1px solid #252836;
    border-radius:10px;padding:40px;text-align:center;
}

#MainMenu,footer,header,[data-testid="stToolbar"] { display:none !important; }
</style>
"""
