"""
VideoOS — Video Network Portfolio Simulator
Streamlit entry point · app.py

Renamed from CableOS 2026-07-24, per the user: the simulator now spans both
TV/Streaming and Movies, so "Cable" undersold what it actually covers.

Run locally:
    pip install streamlit plotly pandas numpy
    streamlit run app.py

FERPA Note: No student PII is collected. Only team names (student-chosen pseudonyms).
Leaderboard stores: team_name, network, attempt#, score, timestamp, pass/fail.
"""
import streamlit as st

st.set_page_config(
    page_title="VideoOS — Video Network Portfolio Simulator",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded",
)

import sys, copy
sys.path.insert(0, ".")

from utils.styles     import GLOBAL_CSS, TAILWIND_INJECT
from utils.game_state import (
    NETWORK_INFO, NETWORK_ORDER, get_team_network_status,
    get_official_score, get_attempt_count, can_advance,
    get_network_leaderboard, THEORY_CONTENT, MAX_ATTEMPTS, SCHOOL_PRESETS
)
from utils.models import annual_budget, cable_subs, distribution_revenue
from utils.data   import BRAVO_SLATE, OXYGEN_SLATE, PEACOCK_SLATE

# st.iframe (added in a newer Streamlit release than st.components.v1.html)
# auto-detects that TAILWIND_INJECT doesn't match a URL/file-path pattern and
# embeds it as raw HTML directly, and is the eventual replacement for the
# deprecated components.v1.html. But this machine has two Streamlit
# installs on PATH at different versions (Anaconda's is old enough that
# st.iframe doesn't exist yet), so don't assume either API — try the newer
# one, fall back to the older one. st.iframe also rejects height=0 outright
# (StreamlitInvalidHeightError) where components.v1.html silently allowed
# it — 1px is the smallest valid value either way and is visually negligible.
if hasattr(st, "iframe"):
    st.iframe(TAILWIND_INJECT, height=1)
else:
    import streamlit.components.v1 as components
    components.html(TAILWIND_INJECT, height=1)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def _render_theory_grid():
    """Shared theory-card grid — used on the welcome screen and both the TV
    and Movies Theory tabs, so the reference content is identical everywhere."""
    theory_items = list(THEORY_CONTENT.values())
    cols = st.columns(3)
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


# ── Session state defaults ────────────────────────────────────────────────────
def init_state():
    defaults = {
        "team_name":       "",
        "school":          "",
        "class_section":   "",
        "registered":      False,
        "active_section":  None,   # "leaderboard" / "tv" / "movies" — chosen on the post-registration landing screen
        "active_network":  "oxygen",
        "bravo_shows":     copy.deepcopy(BRAVO_SLATE),
        "oxygen_shows":    copy.deepcopy(OXYGEN_SLATE),
        "peacock_shows":   copy.deepcopy(PEACOCK_SLATE),
        "year":            1,   # real turn counter within a level as of 2026-07-24 (1-4 years), not frozen
        "level_budget":    None,   # re-derived from net_info["budget_base"] on first render (pages/simulation.py::_init)
        "mkt_budget":      5.0,
        "renewal_decisions": {},
        "research_revealed": {},
        "last_score":      None,
        "submitted":       False,
        "sim_phase":       "decisions",
        "yearly_log":      [],
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
        'color:#e8c547;margin-bottom:2px;">VideoOS</div>'
        '<div style="font-family:DM Mono,monospace;font-size:10px;color:#b0b5c4;'
        'margin-bottom:20px;letter-spacing:.1em;">VIDEO NETWORK PORTFOLIO SIMULATOR · 2012</div>',
        unsafe_allow_html=True
    )
    st.divider()

    # ── Team Registration ─────────────────────────────────────────────────────
    # School + Class Section added 2026-07-22 — a team's real identity for
    # gating/leaderboard purposes is (school, class_section, team_name), not
    # just team_name alone, so the same "Team Alpha" pseudonym at two
    # different schools (or two sections of the same school) never
    # collides. Same FERPA posture as team_name itself: self-reported
    # classroom context, not tied to any student identity.
    st.markdown('<div class="section-title">Team Registration</div>', unsafe_allow_html=True)

    if not ss.registered:
        st.markdown(
            '<div style="font-size:11px;color:#e0e2ea;margin-bottom:8px;">'
            '🔒 FERPA note: Enter a team name only — no student names or IDs.</div>',
            unsafe_allow_html=True
        )
        school_choice = st.selectbox(
            "School", SCHOOL_PRESETS, key="school_select",
            help="Scopes your leaderboard to your own class/school — pick 'Other' to type your own."
        )
        if school_choice == "Other (type below)":
            school_input = st.text_input("School Name", placeholder="e.g. Your University", key="school_input_field")
        else:
            school_input = school_choice
        class_input = st.text_input("Class / Section", placeholder="e.g. Fall 2026 — Media Strategy, Section A",
                                     max_chars=60, key="class_input_field")
        team_input = st.text_input("Team Name", placeholder="e.g. Team Alpha, Studio 5...",
                                    max_chars=30, key="team_input_field")
        if st.button("Register Team →", use_container_width=True):
            if not team_input.strip():
                st.error("Please enter a team name.")
            elif not school_input.strip():
                st.error("Please enter a school name.")
            elif not class_input.strip():
                st.error("Please enter your class/section.")
            else:
                ss.team_name     = team_input.strip()
                ss.school        = school_input.strip()
                ss.class_section = class_input.strip()
                ss.registered    = True
                st.rerun()
    else:
        st.markdown(
            f'<div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;'
            f'padding:10px 14px;">'
            f'<div style="font-size:10px;color:#b0b5c4;text-transform:uppercase;letter-spacing:.08em;">Active Team</div>'
            f'<div style="font-size:16px;font-weight:600;color:#e8c547;font-family:DM Serif Display,serif;">{ss.team_name}</div>'
            f'<div style="font-size:11px;color:#e0e2ea;margin-top:4px;">{ss.school} · {ss.class_section}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        if st.button("Change Team", use_container_width=True):
            ss.registered     = False
            ss.team_name      = ""
            ss.school         = ""
            ss.class_section  = ""
            ss.active_section = None   # back to the landing screen for the next team
            st.rerun()

    st.divider()

    # ── Top-level nav ─────────────────────────────────────────────────────────
    # Restructured 2026-07-24 per user request: three peer sections on the
    # left — Leaderboard, TV/Streaming, Movies — instead of Movies being
    # buried as a peer of individual TV networks and Leaderboard only
    # reachable as a nested tab within whichever section was active.
    if ss.registered:
        st.markdown('<div class="section-title">Simulation</div>', unsafe_allow_html=True)

        section_defs = [
            ("leaderboard", "🏆 Leaderboard"),
            ("tv",          "📺 TV / Streaming"),
            ("movies",      "🎬 Movies"),
        ]
        for section_key, section_label in section_defs:
            is_active = ss.active_section == section_key
            if st.button(f"{'🎯' if is_active else ''} {section_label}".strip(),
                         key=f"section_{section_key}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                ss.active_section = section_key
                st.rerun()

        # ── TV network sub-selector — only shown once TV/Streaming is picked ────
        if ss.active_section == "tv":
            st.markdown(
                '<div style="font-size:10px;color:#b0b5c4;font-family:DM Mono,monospace;'
                'text-transform:uppercase;letter-spacing:.08em;margin:10px 0 6px 4px;">'
                'Active Network</div>', unsafe_allow_html=True)
            net_status = get_team_network_status(ss.team_name, ss.school, ss.class_section)

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

                label = f"{lock_icon} {info['display_name']}"
                if off_sc:   label += f" · {off_sc:.0f}pts"
                if attempts: label += f" ({attempts} attempt{'s' if attempts>1 else ''})"

                if not locked:
                    if st.button(label, key=f"net_{net}", use_container_width=True):
                        ss.active_network    = net
                        ss.submitted         = False
                        ss.sim_phase         = "decisions"
                        ss.yearly_log        = []
                        ss.cancelled_shows   = set()
                        ss.renewal_decisions = {}
                        ss.research_revealed = {}
                        ss.year              = 1
                        ss.level_budget      = None   # re-derived from the new network's budget_base
                        st.rerun()
                else:
                    st.markdown(
                        f'<div style="opacity:.4;padding:6px 10px;border-radius:5px;'
                        f'border:1px solid #252836;font-family:DM Mono,monospace;font-size:12px;">'
                        f'{lock_icon} {info["display_name"]} — Locked</div>',
                        unsafe_allow_html=True
                    )

        st.divider()

        # Budget Allocation removed 2026-07-24 — all gameplay decisions
        # (including Marketing spend) now live in the main page's quarterly
        # Financing section (pages/simulation.py), not the sidebar. This was
        # the last decision control still duplicated between sidebar and
        # main content; the sidebar is nav-only now (registration, section
        # select). ss.mkt_budget stays as the shared session-state value
        # simulation.py's Financing section reads/writes each quarter.

    # Quick Checklist removed 2026-07-22 — it referenced tab names
    # ("Portfolio", "Renewal", "P&L") from before the 7-tabs-to-3 redesign
    # and no longer matched the actual UI; also purely duplicated the
    # per-network "Suggested Order of Play" already shown prominently in
    # the main content's Mission Brief, which is dynamic per network where
    # this was static.
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
        '<h1 style="text-align:center;margin-bottom:4px;">VideoOS</h1>'
        '<div style="text-align:center;font-family:DM Mono,monospace;font-size:13px;'
        'color:#e0e2ea;margin-bottom:32px;">Video Network Portfolio Simulator · 2012</div>',
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
    _render_theory_grid()

    st.divider()
    st.markdown(
        '<div style="text-align:center;font-size:13px;color:#e0e2ea;padding:20px;">'
        '← Register your team in the sidebar to begin.</div>',
        unsafe_allow_html=True
    )

elif ss.active_section is None:
    # ── Choose Your Simulation — shown once, right after registering ───────────
    st.markdown(f"""
    <div style="text-align:center;margin-bottom:20px;">
      <div style="font-family:DM Serif Display,serif;font-size:24px;color:#e8eaf0;">
        Welcome, {ss.team_name}
      </div>
      <div style="font-size:13px;color:#e0e2ea;margin-top:6px;">
        Choose your simulation to begin — you can switch anytime from the sidebar.
      </div>
    </div>
    """, unsafe_allow_html=True)

    ccol1, ccol2 = st.columns(2)
    with ccol1:
        st.markdown("""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:10px;
             padding:28px 20px;text-align:center;height:100%;">
          <div style="font-size:42px;">📺</div>
          <div style="font-family:DM Serif Display,serif;font-size:20px;color:#e8eaf0;margin:10px 0 6px;">
            TV / Streaming
          </div>
          <div style="font-size:12px;color:#e0e2ea;line-height:1.6;">
            Run Oxygen → Bravo → Peacock as General Manager. Annual portfolio decisions —
            financing, renewal, greenlighting, scheduling — amortization timing, and the
            linear-vs-SVOD tradeoff.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("→ Start TV / Streaming", use_container_width=True, type="primary"):
            ss.active_section = "tv"
            st.rerun()
    with ccol2:
        st.markdown("""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:10px;
             padding:28px 20px;text-align:center;height:100%;">
          <div style="font-size:42px;">🎬</div>
          <div style="font-family:DM Serif Display,serif;font-size:20px;color:#e8eaf0;margin:10px 0 6px;">
            Movies
          </div>
          <div style="font-size:12px;color:#e0e2ea;line-height:1.6;">
            Universal Pictures — risk-adjusted NPV under bull/base/bear variance, theatrical
            vs. streaming release-window strategy, and award-season reception. A concentrated,
            front-loaded bet, in contrast to TV's steady, amortized portfolio.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("→ Start Movies", use_container_width=True, type="primary"):
            ss.active_section = "movies"
            st.rerun()

    st.divider()
    lcol, _ = st.columns([1, 2])
    with lcol:
        if st.button("🏆 Just check the Leaderboard", use_container_width=True):
            ss.active_section = "leaderboard"
            st.rerun()

elif ss.active_section == "leaderboard":
    # ── Leaderboard — standalone top-level section ──────────────────────────────
    # pages/leaderboard.py already covers TV networks and Movies internally
    # via its own tabs (_render_board_tab, MOVIES_INFO) — no wrapping needed.
    st.markdown('<h2 style="margin-bottom:4px;">🏆 Leaderboard</h2>', unsafe_allow_html=True)
    from pages.leaderboard import render as render_leaderboard
    render_leaderboard()

elif ss.active_section == "movies":
    # ── Movies — peer section, independent of TV network progress ──────────────
    st.markdown("""
    <div style="background:#12141a;border:1px solid #252836;border-radius:10px;
         padding:20px 24px;margin-bottom:16px;">
      <div style="font-family:DM Serif Display,serif;font-size:22px;color:#e8c547;">
        🎬 Universal Pictures — Day 2
      </div>
      <div style="font-size:12px;color:#e0e2ea;margin-top:6px;line-height:1.7;">
        Theatrical vs. streaming economics: risk-adjusted NPV, release-window strategy, and
        award-season reception — a concentrated, front-loaded bet, in contrast to TV's
        steady, amortized portfolio.
      </div>
    </div>
    """, unsafe_allow_html=True)

    tabs = st.tabs(["🎬 Movies", "📖 Theory"])

    from pages.movies import render as render_movies

    with tabs[0]:
        render_movies()
    with tabs[1]:
        st.markdown('<div class="section-title">Business Theory — Key Concepts</div>', unsafe_allow_html=True)
        _render_theory_grid()

else:
    # ── Registered — show active TV network dashboard ───────────────────────────
    net      = ss.active_network
    net_info = NETWORK_INFO[net]
    attempts = get_attempt_count(ss.team_name, net, ss.school, ss.class_section)
    status   = get_team_network_status(ss.team_name, ss.school, ss.class_section)
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
                "💰 <b>Financing</b> — see your revenue streams, set marketing spend",
                "🔄 <b>Renewal</b> — renew, watch, or cancel; pay for research if unsure",
                "🎬 <b>Greenlighting</b> — decide which new shows go linear vs. SVOD",
                "📅 <b>Scheduling</b> — check premiere timing and amortization impact",
                "🎯 <b>End Year → Results</b> — repeat for 4 years, then submit your score",
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
                "💰 <b>Financing</b> — separate Oxygen shows from Bravo, watch the combined budget",
                "🔄 <b>Renewal</b> — be aggressive cancelling Bravo dogs; costs escalate 5%/yr",
                "🎬 <b>Greenlighting</b> — decide which new shows go linear vs. SVOD",
                "📅 <b>Scheduling</b> — watch the dual-network cost structure",
                "🎯 <b>End Year → Results</b> — repeat for 4 years, then submit your score",
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
                "🎬 <b>Greenlighting</b> — build the linear vs. Peacock P&L for each new show",
                "💰 <b>Financing</b> — check the linear-vs-streaming economics chart",
                "🔄 <b>Renewal</b> — decide which linear shows to wind down",
                "📅 <b>Scheduling</b> — track the cannibalization impact on Bravo & Oxygen",
                "🎯 <b>End Year → Results</b> — repeat for 4 years, then submit your score",
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
    # Movies and Leaderboard are both top-level sidebar sections now
    # (2026-07-24), not tabs nested under whichever TV network is active —
    # see the ss.active_section == "movies"/"leaderboard" branches above.
    tabs = st.tabs([
        "📊 Simulation",
        "📖 Theory",
    ])

    from pages.simulation import render as render_simulation

    with tabs[0]:
        render_simulation()

    with tabs[1]:
        st.markdown('<div class="section-title">Business Theory — Key Concepts</div>', unsafe_allow_html=True)
        _render_theory_grid()
