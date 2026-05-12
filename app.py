"""
CableOS v2 — Cable Network Portfolio Simulator
Streamlit entry point · app.py

Run locally:
    pip install streamlit plotly pandas numpy
    streamlit run app.py

FERPA Note: No student PII is collected. Only team names (student-chosen pseudonyms).
Leaderboard stores: team_name, network, attempt#, score, timestamp, pass/fail.
"""
import streamlit as st

st.set_page_config(
    page_title="CableOS — Network Portfolio Simulator",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded",
)

import sys, copy
sys.path.insert(0, ".")

from utils.styles     import GLOBAL_CSS
from utils.game_state import (
    NETWORK_INFO, NETWORK_ORDER, get_team_network_status,
    get_official_score, get_attempt_count, can_advance,
    get_network_leaderboard, THEORY_CONTENT, MAX_ATTEMPTS
)
from utils.models import annual_budget, cable_subs, distribution_revenue
from utils.data   import BRAVO_SLATE, OXYGEN_SLATE, PEACOCK_SLATE

st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Session state defaults ────────────────────────────────────────────────────
def init_state():
    defaults = {
        "team_name":       "",
        "registered":      False,
        "active_network":  "oxygen",
        "bravo_shows":     copy.deepcopy(BRAVO_SLATE),
        "oxygen_shows":    copy.deepcopy(OXYGEN_SLATE),
        "peacock_shows":   copy.deepcopy(PEACOCK_SLATE),
        "year":            1,
        "mkt_budget":      5.0,
        "dev_budget":      3.0,
        "res_budget":      1.0,
        "renewal_decisions": {},
        "last_score":      None,
        "submitted":       False,
        "sim_month":       1,
        "sim_phase":       "decisions",
        "monthly_log":     [],
        "cancelled_shows": set(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()
ss = st.session_state

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="font-family:DM Serif Display,serif;font-size:24px;'
        'color:#e8c547;margin-bottom:2px;">CableOS</div>'
        '<div style="font-family:DM Mono,monospace;font-size:10px;color:#b0b5c4;'
        'margin-bottom:20px;letter-spacing:.1em;">NETWORK PORTFOLIO SIMULATOR · 2012</div>',
        unsafe_allow_html=True
    )
    st.divider()

    # ── Team Registration ─────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Team Registration</div>', unsafe_allow_html=True)

    if not ss.registered:
        st.markdown(
            '<div style="font-size:11px;color:#e0e2ea;margin-bottom:8px;">'
            '🔒 FERPA note: Enter a team name only — no student names or IDs.</div>',
            unsafe_allow_html=True
        )
        team_input = st.text_input("Team Name", placeholder="e.g. Team Alpha, Studio 5...",
                                    max_chars=30, key="team_input_field")
        if st.button("Register Team →", use_container_width=True):
            if team_input.strip():
                ss.team_name  = team_input.strip()
                ss.registered = True
                st.rerun()
            else:
                st.error("Please enter a team name.")
    else:
        st.markdown(
            f'<div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;'
            f'padding:10px 14px;">'
            f'<div style="font-size:10px;color:#b0b5c4;text-transform:uppercase;letter-spacing:.08em;">Active Team</div>'
            f'<div style="font-size:16px;font-weight:600;color:#e8c547;font-family:DM Serif Display,serif;">{ss.team_name}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        if st.button("Change Team", use_container_width=True):
            ss.registered = False
            ss.team_name  = ""
            st.rerun()

    st.divider()

    # ── Network Selector ──────────────────────────────────────────────────────
    if ss.registered:
        st.markdown('<div class="section-title">Active Network</div>', unsafe_allow_html=True)
        net_status = get_team_network_status(ss.team_name) if ss.registered else {}

        for net in NETWORK_ORDER:
            info     = NETWORK_INFO[net]
            status   = net_status.get(net, {})
            locked   = status.get("locked", net != "oxygen")
            attempts = status.get("attempts", 0)
            passed   = status.get("passed", False)
            off_sc   = status.get("official_score")

            if net == "oxygen":
                locked = False   # Oxygen always unlocked (Level 1)

            lock_icon = "🔒" if locked else ("✅" if passed else ("⚠️" if attempts > 0 else "▶️"))
            active    = ss.active_network == net

            btn_style = (
                f"background:rgba({','.join(str(int(info['color'][i:i+2],16)) for i in (1,3,5))},.2);"
                f"border:2px solid {info['color']};"
                if active else ""
            )

            label = f"{lock_icon} {info['display_name']}"
            if off_sc:   label += f" · {off_sc:.0f}pts"
            if attempts: label += f" ({attempts} attempt{'s' if attempts>1 else ''})"

            if not locked:
                if st.button(label, key=f"net_{net}", use_container_width=True):
                    ss.active_network  = net
                    ss.submitted       = False
                    ss.sim_month       = 1
                    ss.sim_phase       = "decisions"
                    ss.monthly_log     = []
                    ss.cancelled_shows = set()
                    ss.year            = 1
                    st.rerun()
            else:
                st.markdown(
                    f'<div style="opacity:.4;padding:6px 10px;border-radius:5px;'
                    f'border:1px solid #252836;font-family:DM Mono,monospace;font-size:12px;">'
                    f'{lock_icon} {info["display_name"]} — Locked</div>',
                    unsafe_allow_html=True
                )

        st.divider()

        # ── Simulation Controls ───────────────────────────────────────────────
        st.markdown('<div class="section-title">Simulation Year</div>', unsafe_allow_html=True)
        max_year = 4 if ss.active_network == "oxygen" else (7 if ss.active_network == "bravo" else 10)
        ss.year  = st.slider("Year", 1, max_year, ss.year, key="year_slider")
        st.markdown(
            f'<div style="font-family:DM Mono,monospace;font-size:10px;color:#b0b5c4;">'
            f'Calendar year: {2011+ss.year}</div>', unsafe_allow_html=True
        )

        st.divider()

        # ── Budget Controls ───────────────────────────────────────────────────
        st.markdown('<div class="section-title">Budget Allocation ($M)</div>', unsafe_allow_html=True)

        net_info = NETWORK_INFO[ss.active_network]
        base_budget = net_info["budget_base"] * (1.03 ** (ss.year - 1))

        from utils.models import portfolio_cost
        _net = ss.active_network
        shows = ss.oxygen_shows[:]
        if _net in ("bravo", "peacock"):
            shows += ss.bravo_shows
        if _net == "peacock":
            shows += ss.peacock_shows
        content_cost = portfolio_cost(shows, ss.year)

        ss.mkt_budget = st.slider("📣 Marketing ($M)", 0.0, 20.0, ss.mkt_budget, 0.5)
        ss.dev_budget = st.slider("🎬 Development ($M)", 0.0, 15.0, ss.dev_budget, 0.5)
        ss.res_budget = st.slider("🏦 Reserve ($M)", 0.0, 10.0, ss.res_budget, 0.5)

        allocated = content_cost + ss.mkt_budget + ss.dev_budget + ss.res_budget
        remaining = base_budget - allocated
        rem_color = "#66bb6a" if remaining >= 0 else "#ef5350"

        st.markdown(f"""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;padding:10px;margin-top:6px;">
          <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px;">
            <span style="color:#e0e2ea;">Total Budget</span>
            <span style="font-family:DM Mono,monospace;">${base_budget:.1f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px;">
            <span style="color:#e0e2ea;">Content Cost</span>
            <span style="font-family:DM Mono,monospace;color:#ef5350;">-${content_cost:.1f}M</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:600;
               border-top:1px solid #252836;padding-top:6px;margin-top:4px;">
            <span>Remaining</span>
            <span style="font-family:DM Mono,monospace;color:{rem_color};">{'+'if remaining>=0 else ''}${remaining:.1f}M</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if remaining < -5:
            st.error("⚠️ Significantly over budget!")
        elif remaining < 0:
            st.warning("Over budget — reduce marketing or development.")
        elif remaining > 30:
            st.info(f"${remaining:.0f}M unallocated. Add marketing or new shows.")

    st.divider()

    # ── Quick checklist ───────────────────────────────────────────────────────
    if ss.registered:
        st.markdown('<div class="section-title">Quick Checklist</div>', unsafe_allow_html=True)
        checklist = [
            ("📊", "Portfolio",  "Review show slate — find cash cows & dogs"),
            ("🔄", "Renewal",    "Cancel low-ROI shows, free up budget"),
            ("📣", "Sidebar",    "Tune marketing & reserve sliders"),
            ("💰", "P&L",        "Confirm revenue covers costs"),
            ("🎯", "Portfolio",  "Submit your score"),
        ]
        for icon, tab, desc in checklist:
            st.markdown(
                f'<div style="display:flex;gap:8px;padding:4px 0;border-bottom:1px solid #1a1d26;">'
                f'<span style="font-size:13px;">{icon}</span>'
                f'<div><div style="font-size:11px;color:#e8eaf0;font-family:DM Mono,monospace;">{tab}</div>'
                f'<div style="font-size:10px;color:#b0b5c4;">{desc}</div></div></div>',
                unsafe_allow_html=True
            )

    st.divider()
    st.markdown(
        '<div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;line-height:1.6;">'
        'FERPA: No PII collected.<br>Team names are pseudonyms only.<br>'
        'Scores stored locally in leaderboard.json</div>',
        unsafe_allow_html=True
    )

# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
if not ss.registered:
    # ── Welcome / Theory screen ────────────────────────────────────────────────
    st.markdown(
        '<h1 style="text-align:center;margin-bottom:4px;">CableOS</h1>'
        '<div style="text-align:center;font-family:DM Mono,monospace;font-size:13px;'
        'color:#e0e2ea;margin-bottom:32px;">Cable Network Portfolio Simulator · 2012</div>',
        unsafe_allow_html=True
    )

    # Theory section
    st.markdown('<div class="section-title">Strategic Foundation — Business Theory</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #e8c547;
         border-radius:6px;padding:14px 18px;margin-bottom:20px;font-size:13px;color:#e0e2ea;line-height:1.7;">
    <b style="color:#e8eaf0;font-size:15px;">It's 2012. The linear TV era is ending.</b><br><br>
    Cable networks are facing their first existential threat. Subscribers are cutting the cord. 
    Netflix is spending aggressively. The iPad is two years old. You are the General Manager of 
    <b style="color:#e8c547;">Oxygen</b> — responsible for the P&L, the show slate, and the budget.
    Your job: maximize Operating Cash Flow while building IP that survives the transition to streaming.
    Prove yourself on Oxygen, earn Bravo, then decide whether to launch Peacock.
    </div>
    """, unsafe_allow_html=True)

    # Theory cards
    cols = st.columns(3)
    theory_items = list(THEORY_CONTENT.values())
    for i, col in enumerate(cols):
        if i < len(theory_items):
            t = theory_items[i]
            col.markdown(f"""
            <div class="theory-card">
              <div class="theory-icon">{t['icon']}</div>
              <div class="theory-title">{t['title']}</div>
              <div class="theory-body">{t['brief']}</div>
            </div>
            """, unsafe_allow_html=True)
    cols2 = st.columns(2)
    for i, col in enumerate(cols2):
        idx = i + 3
        if idx < len(theory_items):
            t = theory_items[idx]
            col.markdown(f"""
            <div class="theory-card">
              <div class="theory-icon">{t['icon']}</div>
              <div class="theory-title">{t['title']}</div>
              <div class="theory-body">{t['brief']}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    st.markdown(
        '<div style="text-align:center;font-size:13px;color:#e0e2ea;padding:20px;">'
        '← Register your team in the sidebar to begin.</div>',
        unsafe_allow_html=True
    )

else:
    # ── Registered — show active network dashboard ─────────────────────────────
    net      = ss.active_network
    net_info = NETWORK_INFO[net]
    attempts = get_attempt_count(ss.team_name, net)
    status   = get_team_network_status(ss.team_name)
    net_stat = status.get(net, {})
    passed   = net_stat.get("passed", False)
    can_sub  = attempts < MAX_ATTEMPTS and not passed

    # ── Network Header ────────────────────────────────────────────────────────
    hcol1, hcol2 = st.columns([1, 2])

    with hcol1:
        st.markdown(f"""
        <div class="net-logo-wrap" style="background:linear-gradient(135deg,
             rgba({','.join(str(int(net_info['color'][i:i+2],16)) for i in (1,3,5))},.15),
             rgba(26,29,38,.95));">
          <div>
            <div class="net-logo-text" style="color:{net_info['color2']};">{net_info['logo_text']}</div>
            <div class="net-tagline">{net_info['tagline']}</div>
            <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:4px;">
              <span class="badge badge-gray">Est. {net_info['founded']}</span>
              <span class="badge badge-gray">{net_info['parent']}</span>
              <span class="badge badge-gray">{net_info['hq']}</span>
            </div>
            <div style="margin-top:8px;">
              <div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;margin-bottom:3px;">KEY DEMO</div>
              <div style="font-size:11px;color:#e0e2ea;">{net_info['demographics']}</div>
            </div>
            <div style="margin-top:8px;">
              <div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;margin-bottom:3px;">EP COST RANGE</div>
              <div style="font-size:11px;color:#e0e2ea;">{net_info['avg_ep_cost']}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Attempt status
        att_color = "#66bb6a" if passed else ("#ffa726" if attempts > 0 else "#e0e2ea")
        st.markdown(f"""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;padding:10px 14px;">
          <div style="font-size:10px;color:#b0b5c4;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;">Attempt Status</div>
          <div style="font-size:13px;color:{att_color};font-family:DM Mono,monospace;">
            {'✅ PASSED' if passed else f'Attempt {attempts+1} of {MAX_ATTEMPTS}' if can_sub else '🔒 All attempts used'}
          </div>
          {'<div style="font-size:11px;color:#e0e2ea;margin-top:4px;">First attempt score is official.</div>' if attempts == 0 else ''}
          {'<div style="font-size:11px;color:#ffa726;margin-top:4px;">⚠️ Retries are practice only — first score counts.</div>' if attempts > 0 and not passed else ''}
        </div>
        """, unsafe_allow_html=True)

    with hcol2:
        st.markdown(f"""
        <div style="background:#12141a;border:1px solid #252836;border-radius:10px;padding:18px 20px;">
          <div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;
               text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px;">Network Biography</div>
          <div style="font-size:13px;color:#c8cad4;line-height:1.75;">{net_info['bio']}</div>
          <div style="margin-top:12px;">
            <div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;margin-bottom:6px;">SIGNATURE SHOWS</div>
            <div style="font-size:12px;color:#e0e2ea;">{net_info['hit_shows']}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Level Brief ──────────────────────────────────────────────────────────
    LEVEL_BRIEFS = {
        "oxygen": {
            "color": "#8e44ad",
            "objective": "Level 1 — Your first assignment.",
            "mission": (
                "You run Oxygen: 20 true crime & reality shows, $95M budget. "
                "Content uses a <b style='color:#e8eaf0;'>3-year amortization curve</b> — "
                "your annual expense is 1/3 of production cost, giving you more breathing room than Bravo. "
                "Hit a <b style='color:#e8eaf0;'>12% OCF margin</b> to pass."
            ),
            "steps": [
                "📊 <b>Portfolio</b> — review your slate, spot cash cows vs. dogs",
                "🔄 <b>Renewal</b> — cancel low-ROI shows to free budget",
                "📣 <b>Sidebar</b> — adjust marketing and reserve allocation",
                "💰 <b>P&L</b> — confirm your income statement looks healthy",
                "🎯 <b>Portfolio → Submit</b> — lock in your official score",
            ],
        },
        "bravo": {
            "color": "#c0392b",
            "objective": "Level 2 — You've earned Bravo.",
            "mission": (
                "You now run both Oxygen and Bravo: 40 shows, ~$315M combined budget. "
                "Bravo uses a <b style='color:#e8eaf0;'>12-month amortization</b> — costs hit harder each year. "
                "Real Housewives and Top Chef are your cash cows. "
                "Hit a <b style='color:#e8eaf0;'>15% OCF margin</b> to pass."
            ),
            "steps": [
                "📊 <b>Portfolio</b> — separate Oxygen shows from Bravo, protect cash cows",
                "🔄 <b>Renewal</b> — be aggressive cancelling Bravo dogs; costs escalate 5%/yr",
                "🎬 <b>Green Light</b> — decide which new shows go linear vs. SVOD",
                "💰 <b>P&L</b> — watch the dual-network cost structure",
                "🎯 <b>Portfolio → Submit</b> — lock in your official score",
            ],
        },
        "peacock": {
            "color": "#1a6bb5",
            "objective": "Level 3 — Launch Peacock.",
            "mission": (
                "Add SVOD to your portfolio. Peacock content uses "
                "<b style='color:#e8eaf0;'>36-month amortization</b> and earns subscription LTV instead of ad revenue. "
                "Linear revenue will keep eroding — Peacock is your hedge. "
                "Hit a <b style='color:#e8eaf0;'>10% OCF margin</b> across all three networks to pass."
            ),
            "steps": [
                "🎬 <b>Green Light</b> — build the linear vs. Peacock P&L for each new show",
                "📈 <b>Forecast</b> — model the SVOD crossover year",
                "🔄 <b>Renewal</b> — decide which linear shows to wind down",
                "💰 <b>P&L</b> — track the cannibalization impact on Bravo & Oxygen",
                "🎯 <b>Portfolio → Submit</b> — lock in your official score",
            ],
        },
    }

    brief = LEVEL_BRIEFS.get(net, LEVEL_BRIEFS["oxygen"])
    steps_html = "".join(
        f'<div style="display:flex;gap:8px;margin-bottom:5px;font-size:12px;">'
        f'<span style="color:#b0b5c4;font-family:DM Mono,monospace;min-width:16px;">{i+1}.</span>'
        f'<span style="color:#c8cad4;">{s}</span></div>'
        for i, s in enumerate(brief["steps"])
    )
    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid {brief['color']};
         border-radius:8px;padding:16px 20px;margin-bottom:16px;">
      <div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;">
        <div style="flex:2;min-width:260px;">
          <div style="font-family:DM Mono,monospace;font-size:10px;color:#b0b5c4;
               text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px;">Mission Brief</div>
          <div style="font-size:12px;color:{brief['color']};font-weight:600;margin-bottom:6px;">{brief['objective']}</div>
          <div style="font-size:12px;color:#e0e2ea;line-height:1.7;">{brief['mission']}</div>
        </div>
        <div style="flex:1;min-width:220px;">
          <div style="font-family:DM Mono,monospace;font-size:10px;color:#b0b5c4;
               text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px;">Suggested Order of Play</div>
          {steps_html}
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Main Tabs ─────────────────────────────────────────────────────────────
    tabs = st.tabs([
        "📊 Simulation",
        "🏆 Leaderboard",
        "📖 Theory",
    ])

    from pages.simulation  import render as render_simulation
    from pages.leaderboard import render as render_leaderboard

    with tabs[0]:
        render_simulation()

    with tabs[1]:
        render_leaderboard()

    with tabs[2]:
        st.markdown('<div class="section-title">Business Theory — Key Concepts</div>', unsafe_allow_html=True)
        cols = st.columns(3)
        theory_items = list(THEORY_CONTENT.values())
        for i, col in enumerate(cols):
            if i < len(theory_items):
                t = theory_items[i]
                col.markdown(f"""
                <div class="theory-card">
                  <div class="theory-icon">{t['icon']}</div>
                  <div class="theory-title">{t['title']}</div>
                  <div class="theory-body">{t['brief']}</div>
                </div>
                """, unsafe_allow_html=True)
        cols2 = st.columns(2)
        for i, col in enumerate(cols2):
            idx = i + 3
            if idx < len(theory_items):
                t = theory_items[idx]
                col.markdown(f"""
                <div class="theory-card">
                  <div class="theory-icon">{t['icon']}</div>
                  <div class="theory-title">{t['title']}</div>
                  <div class="theory-body">{t['brief']}</div>
                </div>
                """, unsafe_allow_html=True)
