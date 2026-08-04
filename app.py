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
    get_network_leaderboard, THEORY_CONTENT, MAX_ATTEMPTS,
    YEARS_PER_LEVEL, LEVEL_START_YEAR,
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
        "class_abbrev":    "",
        "registered":      False,
        "active_section":  None,   # "leaderboard" / "tv" / "movies" — chosen on the post-registration landing screen
        "active_network":  "oxygen",
        "bravo_shows":     copy.deepcopy(BRAVO_SLATE),
        "oxygen_shows":    copy.deepcopy(OXYGEN_SLATE),
        "peacock_shows":   copy.deepcopy(PEACOCK_SLATE),
        "year":            1,   # real turn counter within a level (1-YEARS_PER_LEVEL), not frozen — see utils/game_state.py
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

# ── TOP HEADER — replaces the old left sidebar (2026-07-30, per explicit user
# request: "We don't need a left hand panel, but people should be able to
# sign in and see leaderboards for TV and movies respectively"). Registration
# and section nav now render inline in the main content flow instead of
# st.sidebar, so there's no separate panel that can fail to render or be
# left collapsed with no way back open (the underlying complaint — "I can't
# see the left panel at all, and I can't register my team either" — was one
# problem, not two: registration and nav both lived only in the sidebar).
st.markdown(
    '<div style="text-align:center;margin-bottom:2px;">'
    '<span style="font-family:DM Serif Display,serif;font-size:28px;color:#e8c547;">VideoOS</span>'
    '</div>'
    '<div style="text-align:center;font-family:DM Mono,monospace;font-size:14px;color:#b0b5c4;'
    'letter-spacing:.1em;margin-bottom:16px;">VIDEO NETWORK PORTFOLIO SIMULATOR · 2012</div>',
    unsafe_allow_html=True
)

if ss.registered:
    tcol1, tcol2 = st.columns([5, 1])
    with tcol1:
        st.markdown(
            f'<div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;'
            f'padding:10px 14px;">'
            f'<span style="font-size:14px;color:#b0b5c4;text-transform:uppercase;letter-spacing:.08em;">Active Team</span>'
            f'&nbsp;&nbsp;<span style="font-size:16px;font-weight:600;color:#e8c547;font-family:DM Serif Display,serif;">{ss.team_name}</span>'
            f'&nbsp;&nbsp;<span style="font-size:14px;color:#e0e2ea;">{ss.school} · {ss.class_section}</span>'
            f'</div>',
            unsafe_allow_html=True
        )
    with tcol2:
        if st.button("Change Team", use_container_width=True):
            ss.registered     = False
            ss.team_name      = ""
            ss.school         = ""
            ss.class_section  = ""
            ss.class_abbrev   = ""
            ss.active_section = None   # back to the landing screen for the next team
            st.rerun()

    # ── Top-level nav ─────────────────────────────────────────────────────────
    # Same three peer sections as before (Leaderboard, TV/Streaming, Movies,
    # plus App/Home) — now a horizontal button row instead of a stacked
    # sidebar list.
    section_defs = [
        ("app",         "🏠 App"),
        ("leaderboard", "🏆 Leaderboard"),
        ("tv",          "📺 TV / Streaming"),
        ("movies",      "🎬 Movies"),
    ]
    nav_cols = st.columns(len(section_defs))
    for col, (section_key, section_label) in zip(nav_cols, section_defs):
        is_active = ss.active_section == section_key or (
            section_key == "app" and ss.active_section is None
        )
        with col:
            if st.button(f"{'🎯' if is_active else ''} {section_label}".strip(),
                         key=f"section_{section_key}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                ss.active_section = section_key
                st.rerun()

    # ── TV network sub-selector — only shown once TV/Streaming is picked ────
    if ss.active_section == "tv":
        net_status = get_team_network_status(ss.team_name, ss.school, ss.class_section)
        net_cols = st.columns(len(NETWORK_ORDER))
        for col, net in zip(net_cols, NETWORK_ORDER):
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
            if attempts: label += f" ({attempts})"

            with col:
                if not locked:
                    is_active_net = ss.active_network == net
                    if st.button(label, key=f"net_{net}", use_container_width=True,
                                 type="primary" if is_active_net else "secondary"):
                        ss.active_network       = net
                        ss.submitted            = False
                        ss.sim_phase            = "decisions"
                        ss.yearly_log           = []
                        ss.cancelled_shows      = set()
                        ss.renewal_decisions    = {}
                        ss.research_revealed    = {}
                        ss.emergency_shock_years = set()
                        ss.greenlit_ids_this_year  = set()
                        ss.greenlit_ids_this_level = set()
                        ss.total_shows_greenlit    = 0
                        ss.year                 = 1
                        ss.level_budget         = None   # re-derived from the new network's budget_base
                        st.rerun()
                else:
                    st.markdown(
                        f'<div style="opacity:.4;padding:6px 10px;border-radius:5px;'
                        f'border:1px solid #252836;font-family:DM Mono,monospace;font-size:15px;'
                        f'text-align:center;">{lock_icon} {info["display_name"]} — Locked</div>',
                        unsafe_allow_html=True
                    )

    st.divider()

# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
# The leaderboard is viewable without registering -- "Just check the
# Leaderboard" on the sign-in screen below sets active_section="leaderboard"
# without ever setting ss.registered, so that branch has to win over the
# not-registered branch rather than the reverse (2026-07-30).
if not ss.registered and ss.active_section != "leaderboard":
    # ── Sign In / Team Registration ─────────────────────────────────────────────
    # School + Class Section: a team's real identity for gating/leaderboard
    # purposes is (school, class_section, team_name), not just team_name
    # alone, so the same "Team Alpha" pseudonym at two different schools (or
    # two sections of the same school) never collides. FERPA-safe:
    # self-reported classroom context, not tied to any student identity.
    st.markdown('<div class="section-title" style="text-align:center;">Sign In — Register Your Team</div>',
                unsafe_allow_html=True)
    rcol1, rcol2, rcol3 = st.columns([1, 2, 1])
    with rcol2, st.container(key="registration_form"):
        st.markdown(
            '<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;text-align:center;">'
            '🔒 FERPA note: Enter a team name only — no student names or IDs.</div>',
            unsafe_allow_html=True
        )
        icol1, icol2 = st.columns(2)
        with icol1:
            university_input = st.text_input(
                "University", placeholder="e.g. University of Virginia", key="university_input_field",
                help="Your parent institution — scopes your leaderboard to your own school."
            )
            college_input = st.text_input(
                "School / College", placeholder="e.g. Darden School of Business", key="college_input_field",
                help="The specific business school within your university."
            )
        with icol2:
            team_input = st.text_input("Team Name", placeholder="e.g. Team Alpha, Studio 5...",
                                        max_chars=30, key="team_input_field")

        # Class Title / Semester-Year / Class Abbreviation as their own boxes
        # (previously one merged "Class / Section" field, split out 2026-08-04
        # per user request for a dedicated Semester/Year box) — combined back
        # into ss.class_section on submit below, since class_section is the
        # identity-key field read everywhere else in the app (leaderboard,
        # game_state gating) and splitting the underlying data model isn't
        # worth the churn for what's really just a display-clarity change.
        ccol1, ccol2, ccol3 = st.columns(3)
        with ccol1:
            class_title_input = st.text_input(
                "Class Title", placeholder="e.g. Media Strategy, Section A",
                max_chars=40, key="class_title_input_field"
            )
        with ccol2:
            semester_input = st.text_input(
                "Semester / Year", placeholder="e.g. Fall 2026",
                max_chars=20, key="semester_input_field"
            )
        with ccol3:
            class_abbrev_input = st.text_input(
                "Class Abbreviation (optional)", placeholder="e.g. MBA6120",
                max_chars=20, key="class_abbrev_input_field",
                help="A short course code, if your class has one. Optional — just an extra way "
                     "for your instructor to find your team later."
            )
        if st.button("Register Team →", use_container_width=True, type="primary"):
            if not team_input.strip():
                st.error("Please enter a team name.")
            elif not university_input.strip():
                st.error("Please enter your university.")
            elif not college_input.strip():
                st.error("Please enter your school/college.")
            elif not class_title_input.strip():
                st.error("Please enter your class title.")
            elif not semester_input.strip():
                st.error("Please enter your semester/year.")
            else:
                ss.team_name     = team_input.strip()
                ss.school        = f"{college_input.strip()}, {university_input.strip()}"
                ss.class_section = f"{semester_input.strip()} — {class_title_input.strip()}"
                ss.class_abbrev  = class_abbrev_input.strip()
                ss.registered    = True
                st.rerun()
        st.caption("FERPA: No PII collected. Team names are pseudonyms only. Scores stored locally in leaderboard.json")

    st.divider()
    lcol, _ = st.columns([1, 2])
    with lcol:
        if st.button("🏆 Just check the Leaderboard", use_container_width=True):
            ss.active_section = "leaderboard"
            st.rerun()

    st.divider()

    # Theory section
    # Rewritten 2026-07-30 -- the old copy here was Oxygen's specific mission
    # narrative ("You are the General Manager of Oxygen..."), which belongs
    # on the Oxygen level brief (see LEVEL_BRIEFS below), not on a shared
    # landing page a visitor sees before choosing TV/Streaming vs. Movies at
    # all. This is the frameworks section -- it should frame the toolkit
    # both simulations share, not narrate one specific level.
    st.markdown('<div class="section-title">Strategic Foundation — Business Theory</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #e8c547;
         border-radius:6px;padding:14px 18px;margin-bottom:20px;font-size:15px;color:#e0e2ea;line-height:1.7;">
    <b style="color:#e8eaf0;font-size:15px;">Two simulations. One inflection point.</b><br><br>
    It's 2012 — the start of a decade-long shift from linear, ad-supported TV toward streaming that
    will reshape how media companies allocate capital, greenlight content, and manage risk.
    <b style="color:#e8c547;">TV / Streaming</b> puts you in the network GM's seat, running a
    portfolio (Oxygen → Bravo → Peacock) through amortization timing, genre diversification, and the
    linear-vs-SVOD tradeoff. <b style="color:#e8c547;">Movies</b> puts you in the studio's seat at
    Universal Pictures, making concentrated, front-loaded bets under risk-adjusted NPV and
    release-window strategy. Both draw on the same underlying toolkit — the frameworks below are the
    lens for every decision you'll make in either simulation.
    </div>
    """, unsafe_allow_html=True)

    # Theory cards
    _render_theory_grid()

elif ss.active_section in (None, "app"):
    # ── Choose Your Simulation — landing screen, reachable via the "App" nav
    # button at any time, not just once right after registering ────────────────
    st.markdown(f"""
    <div style="text-align:center;margin-bottom:20px;">
      <div style="font-family:DM Serif Display,serif;font-size:24px;color:#e8eaf0;">
        Welcome, {ss.team_name}
      </div>
      <div style="font-size:15px;color:#e0e2ea;margin-top:6px;">
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
          <div style="font-size:15px;color:#e0e2ea;line-height:1.6;">
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
          <div style="font-size:15px;color:#e0e2ea;line-height:1.6;">
            Universal Pictures — risk-adjusted NPV under bull/base/bear variance, theatrical
            vs. streaming release-window strategy, and award-season reception. A concentrated,
            front-loaded bet, in contrast to TV's steady, amortized portfolio.
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("→ Start Movies", use_container_width=True, type="primary"):
            ss.active_section = "movies"
            st.rerun()

elif ss.active_section == "leaderboard":
    # ── Leaderboard — standalone top-level section ──────────────────────────────
    # pages/leaderboard.py already covers TV networks and Movies internally
    # via its own tabs (_render_board_tab, MOVIES_INFO) — no wrapping needed.
    # Reachable without registering (see the not-registered branch's guard
    # above) -- an anonymous visitor needs a way back to Sign In, since the
    # top nav row (which would normally get them there) only renders once
    # ss.registered is true.
    if not ss.registered:
        if st.button("← Back to Sign In", key="leaderboard_back_to_signin"):
            ss.active_section = None
            st.rerun()
    st.markdown('<h2 style="margin-bottom:4px;">🏆 Leaderboard</h2>', unsafe_allow_html=True)
    from app_pages.leaderboard import render as render_leaderboard
    render_leaderboard()

elif ss.active_section == "movies":
    # ── Movies — peer section, independent of TV network progress ──────────────
    st.markdown("""
    <div style="background:#12141a;border:1px solid #252836;border-radius:10px;
         padding:20px 24px;margin-bottom:16px;">
      <div style="font-family:DM Serif Display,serif;font-size:22px;color:#e8c547;">
        🎬 Universal Pictures — Day 2
      </div>
      <div style="font-size:15px;color:#e0e2ea;margin-top:6px;line-height:1.7;">
        Theatrical vs. streaming economics: risk-adjusted NPV, release-window strategy, and
        award-season reception — a concentrated, front-loaded bet, in contrast to TV's
        steady, amortized portfolio.
      </div>
    </div>
    """, unsafe_allow_html=True)

    tabs = st.tabs(["🎬 Movies", "📖 Theory"])

    from app_pages.movies import render as render_movies

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
              <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;margin-bottom:3px;">KEY DEMO</div>
              <div style="font-size:14px;color:#e0e2ea;">{net_info['demographics']}</div>
            </div>
            <div style="margin-top:8px;">
              <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;margin-bottom:3px;">EP COST RANGE</div>
              <div style="font-size:14px;color:#e0e2ea;">{net_info['avg_ep_cost']}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Attempt status
        att_color = "#66bb6a" if passed else ("#ffa726" if attempts > 0 else "#e0e2ea")
        st.markdown(f"""
        <div style="background:#1a1d26;border:1px solid #252836;border-radius:6px;padding:10px 14px;">
          <div style="font-size:14px;color:#b0b5c4;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;">Attempt Status</div>
          <div style="font-size:15px;color:{att_color};font-family:DM Mono,monospace;">
            {'✅ PASSED' if passed else f'Attempt {attempts+1} of {MAX_ATTEMPTS}' if can_sub else '🔒 All attempts used'}
          </div>
          {'<div style="font-size:14px;color:#e0e2ea;margin-top:4px;">First attempt score is official.</div>' if attempts == 0 else ''}
          {'<div style="font-size:14px;color:#ffa726;margin-top:4px;">⚠️ Retries are practice only — first score counts.</div>' if attempts > 0 and not passed else ''}
        </div>
        """, unsafe_allow_html=True)

    with hcol2:
        st.markdown(f"""
        <div style="background:#12141a;border:1px solid #252836;border-radius:10px;padding:18px 20px;">
          <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;
               text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px;">Network Biography</div>
          <div style="font-size:15px;color:#c8cad4;line-height:1.75;">{net_info['bio']}</div>
          <div style="margin-top:12px;">
            <div style="font-size:14px;color:#b0b5c4;font-family:DM Mono,monospace;margin-bottom:6px;">SIGNATURE SHOWS</div>
            <div style="font-size:15px;color:#e0e2ea;">{net_info['hit_shows']}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Level Brief ──────────────────────────────────────────────────────────
    # Calendar spans read from utils.game_state.LEVEL_START_YEAR/YEARS_PER_LEVEL
    # (single source of truth, also drives pages/simulation.py's year engine) —
    # reshaped 2026-07-27 to real per-network eras (each starting exactly
    # YEARS_PER_LEVEL after the last, clean handoff, no overlap) rather than
    # every network resetting to 2012. YEARS_PER_LEVEL defaults to 4 but is
    # instructor-tailorable per deployment (2026-08-03) — see README.md.
    _end_year = {n: LEVEL_START_YEAR[n] + YEARS_PER_LEVEL - 1 for n in NETWORK_ORDER}
    LEVEL_BRIEFS = {
        "oxygen": {
            "color": "#8e44ad",
            "objective": f"Level 1 — {LEVEL_START_YEAR['oxygen']}–{_end_year['oxygen']}. Save a sinking channel.",
            "mission": (
                f"It's {LEVEL_START_YEAR['oxygen']}. Oxygen is bleeding — 20 true crime & reality shows, "
                f"$95M budget, and a network on the edge of cancellation. Your mandate: turn it around "
                f"before {_end_year['oxygen']}. Content uses a <b style='color:#e8eaf0;'>3-year amortization curve</b> — "
                "your annual expense is 1/3 of production cost, giving you more breathing room than Bravo. "
                "Hit a <b style='color:#e8eaf0;'>12% OCF margin</b> to pass."
            ),
            "steps": [
                "💰 <b>Financing</b> — see your revenue streams, set marketing spend",
                "🔄 <b>Renewal</b> — renew, watch, or cancel; pay for research if unsure",
                "🎬 <b>Greenlighting</b> — decide which new shows go linear vs. SVOD",
                "📅 <b>Scheduling</b> — check premiere timing and amortization impact",
                f"🎯 <b>End Year → Results</b> — repeat for {YEARS_PER_LEVEL} years "
                f"({LEVEL_START_YEAR['oxygen']}–{_end_year['oxygen']}), then submit your score",
            ],
        },
        "bravo": {
            "color": "#c0392b",
            "objective": f"Level 2 — {LEVEL_START_YEAR['bravo']}–{_end_year['bravo']}. You've earned Bravo.",
            "mission": (
                f"It's {LEVEL_START_YEAR['bravo']}. You now run both Oxygen and Bravo: 40 shows, "
                "~$315M combined budget. Bravo uses a <b style='color:#e8eaf0;'>12-month amortization</b> — "
                "costs hit harder each year. Real Housewives and Top Chef are your cash cows. "
                "Hit a <b style='color:#e8eaf0;'>15% OCF margin</b> to pass."
            ),
            "steps": [
                "💰 <b>Financing</b> — separate Oxygen shows from Bravo, watch the combined budget",
                "🔄 <b>Renewal</b> — be aggressive cancelling Bravo dogs; costs escalate 5%/yr",
                "🎬 <b>Greenlighting</b> — decide which new shows go linear vs. SVOD",
                "📅 <b>Scheduling</b> — watch the dual-network cost structure",
                f"🎯 <b>End Year → Results</b> — repeat for {YEARS_PER_LEVEL} years "
                f"({LEVEL_START_YEAR['bravo']}–{_end_year['bravo']}), then submit your score",
            ],
        },
        "peacock": {
            "color": "#1a6bb5",
            "objective": f"Level 3 — {LEVEL_START_YEAR['peacock']}–{_end_year['peacock']}. Launch Peacock.",
            "mission": (
                f"It's {LEVEL_START_YEAR['peacock']}. Add SVOD to your portfolio. Peacock content uses "
                "<b style='color:#e8eaf0;'>36-month amortization</b> and earns subscription LTV instead of ad revenue. "
                "Linear revenue will keep eroding — Peacock is your hedge. "
                "Hit a <b style='color:#e8eaf0;'>10% OCF margin</b> across all three networks to pass."
            ),
            "steps": [
                "🎬 <b>Greenlighting</b> — build the linear vs. Peacock P&L for each new show",
                "💰 <b>Financing</b> — check the linear-vs-streaming economics chart",
                "🔄 <b>Renewal</b> — decide which linear shows to wind down",
                "📅 <b>Scheduling</b> — track the cannibalization impact on Bravo & Oxygen",
                f"🎯 <b>End Year → Results</b> — repeat for {YEARS_PER_LEVEL} years "
                f"({LEVEL_START_YEAR['peacock']}–{_end_year['peacock']}), then submit your score",
            ],
        },
    }

    brief = LEVEL_BRIEFS.get(net, LEVEL_BRIEFS["oxygen"])
    steps_html = "".join(
        f'<div style="display:flex;gap:8px;margin-bottom:5px;font-size:15px;">'
        f'<span style="color:#b0b5c4;font-family:DM Mono,monospace;min-width:16px;">{i+1}.</span>'
        f'<span style="color:#c8cad4;">{s}</span></div>'
        for i, s in enumerate(brief["steps"])
    )
    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid {brief['color']};
         border-radius:8px;padding:16px 20px;margin-bottom:16px;">
      <div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;">
        <div style="flex:2;min-width:260px;">
          <div style="font-family:DM Mono,monospace;font-size:14px;color:#b0b5c4;
               text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px;">Mission Brief</div>
          <div style="font-size:15px;color:{brief['color']};font-weight:600;margin-bottom:6px;">{brief['objective']}</div>
          <div style="font-size:15px;color:#e0e2ea;line-height:1.7;">{brief['mission']}</div>
        </div>
        <div style="flex:1;min-width:220px;">
          <div style="font-family:DM Mono,monospace;font-size:14px;color:#b0b5c4;
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
        "💹 P&L / OCF",
        "📈 10-Yr Forecast",
        "📖 Theory",
    ])

    from app_pages.simulation import render as render_simulation
    from app_pages.finance    import render as render_finance
    from app_pages.forecast   import render as render_forecast

    with tabs[0]:
        render_simulation()

    with tabs[1]:
        render_finance()

    with tabs[2]:
        render_forecast()

    with tabs[3]:
        st.markdown('<div class="section-title">Business Theory — Key Concepts</div>', unsafe_allow_html=True)
        _render_theory_grid()
