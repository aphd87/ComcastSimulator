"""
Tab 4 — Green Light Model
Student builds a show concept and compares Linear vs. SVOD P&L.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.models import (
    greenlight_linear, greenlight_svod, ltv_curve, HOURLY_INDEX, HOUR_LABELS, Show, MONTHS,
    TV_PITCH_CATALOG, tv_pitch_acquisition_fee_m, genre_demo,
)
from utils.charts import base_layout, queue_supplement, ACCENT, ACCENT2, SUCCESS, DANGER, WARN, TEXT2
from utils.data import BRAVO_SLATE, OXYGEN_SLATE, PEACOCK_SLATE
from utils.game_state import NETWORK_INFO, MAX_NEW_SHOWS_PER_YEAR, YEARS_PER_LEVEL, LEVEL_START_YEAR
from utils.pitch_market import (
    contested_fee, rival_for, resolve_rival_signings, RIVAL_FEE_PREMIUM, RIVAL_POACH_CHANCE,
)

_GENRES = ["Reality", "Competition", "Talk", "Scripted", "True Crime", "Drama"]
_NEW_SHOW_IP_SCORE = 40   # unproven new IP -- just above the ~33 flat-maturation threshold
                           # (Show.projected_rating's decay formula), so a fresh concept trends
                           # mildly upward rather than assuming instant franchise value

# Protected titles — every real show name already in this game's own data.
# Zach Schlessel's feedback: "Risk = 0 score: take an existing show title
# without permission (gets sued) — originality matters." Reuses existing
# data rather than a separate hardcoded list, so it stays in sync if the
# slates change.
_PROTECTED_TITLES = {s.name.strip().lower() for s in (BRAVO_SLATE + OXYGEN_SLATE + PEACOCK_SLATE)}


def _taken_titles() -> set:
    """Every title a new show can't reuse: the original slates, the pitch
    marketplace, and anything already on this team's rosters (2026-10-01)."""
    ss = st.session_state
    taken = set(_PROTECTED_TITLES) | {p["name"].strip().lower() for p in TV_PITCH_CATALOG.values()}
    for key in ("oxygen_shows", "bravo_shows", "peacock_shows"):
        taken |= {s.name.strip().lower() for s in ss.get(key, [])}
    return taken


def render():
    ss   = st.session_state
    year = ss.get("year", 1)

    # Slot tracking computed up front so every section below (the pitch
    # marketplace, Greenlight This Show) reads the same slot count.
    if "greenlit_ids_this_year" not in ss:
        ss.greenlit_ids_this_year = set()
    if "greenlit_ids_this_level" not in ss:
        ss.greenlit_ids_this_level = set()
    if "total_shows_greenlit" not in ss:
        ss.total_shows_greenlit = 0
    if "next_show_id" not in ss:
        ss.next_show_id = 51   # one past the highest ID in utils/data.py's original slates

    if "tv_pitches_acquired" not in ss:
        ss.tv_pitches_acquired = set()

    slots_used = len(ss.greenlit_ids_this_year)
    slots_left = MAX_NEW_SHOWS_PER_YEAR - slots_used
    net_display_intro = NETWORK_INFO[ss.active_network]["display_name"]

    # ── Acquire a Pitched Show ───────────────────────────────────────────────
    # 2026-08-24, per explicit user question ("where are the TV series being
    # pitched to students...they should be able to pick up TV series too").
    # A second, distinct way to add a show -- alongside Build From Scratch
    # below -- for a fixed roster of already-pitched, fictional shows with
    # real audience demos, an origin (Domestic vs. an International Format
    # acquired from abroad), and an optional Brand Partnership. Shares the
    # same MAX_NEW_SHOWS_PER_YEAR slot cap and roster/budget bookkeeping as
    # Greenlight This Show below (see tv_pitch_acquisition_fee_m's docstring
    # for the cost model), same "adding a new show is adding a new show"
    # capacity constraint either way.
    st.markdown('<div class="section-title">📋 Acquire a Pitched Show</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:14px;color:#e0e2ea;margin-bottom:10px;">'
        'A second way to add a show, alongside building one from scratch below: pick up an '
        'already-pitched concept outright. <b style="color:#e8eaf0;">Domestic Original</b> pitches are '
        'cheaper to acquire but unproven. <b style="color:#e8eaf0;">International Format</b> pitches are '
        'adapted from a proven overseas hit — a real rights-licensing premium, but a higher, de-risked '
        'rating and IP Score. A <b style="color:#e8eaf0;">Brand Partnership</b> means a sponsor already '
        'attached, subsidizing part of the acquisition cost. Unlike Build From Scratch, an acquired '
        'show\'s numbers are fixed — you\'re paying for a de-risked concept, not a tunable one. '
        + (f'<b style="color:#e8c547;">You have {slots_left} of {MAX_NEW_SHOWS_PER_YEAR} new-show slots '
           f'left this year</b> — acquiring, building from scratch, and AI-pitched shows all share them.'
           if slots_left > 0 else
           f'<b style="color:#ef5350;">You\'ve used all {MAX_NEW_SHOWS_PER_YEAR} new-show slots this year</b> '
           f'— acquiring, building from scratch, and AI-pitched shows all share them.')
        + (f' There are more pitches below than slots, so choose carefully. You get {MAX_NEW_SHOWS_PER_YEAR} '
           f'fresh slots each new year, so across a {YEARS_PER_LEVEL}-year level you can add up to '
           f'{MAX_NEW_SHOWS_PER_YEAR * YEARS_PER_LEVEL} new shows. A pitch you pass on stays available '
           f'next year <b>unless a rival network is bidding on it (🔥)</b>, in which case the rival may sign it '
           f'first. Switching networks or restarting a level undoes the shows you added in it, so slots '
           f'can\'t be refilled that way.')
        + '<br><br><b style="color:#e8eaf0;">Reading a pitch card:</b>'
        '<ul style="margin:4px 0 0 18px;padding:0;line-height:1.6;">'
        '<li><b>Demo</b>: who watches. Age band · gender skew · where (e.g. 18-49 · Balanced · National US).</li>'
        '<li><b>eps · $/ep</b>: episodes per season and production cost per episode. Multiply them for the season cost.</li>'
        '<li><b>Rating</b>: 18-49 demo rating, the share of U.S. adults 18-49 watching an average episode '
        '(1.0 ≈ 1%). Higher rating = more ad revenue. Typical show 1.0-1.5, a hit 2.0+.</li>'
        '<li><b>SVOD appeal</b> (0-100): how well the show attracts and keeps streaming subscribers. '
        'Matters most on Peacock.</li>'
        '<li><b>IP Score</b> (0-100): franchise/brand value. Higher means spinoff potential and a show that ages better.</li>'
        '<li><b>Brand partnership</b>: a sponsor already attached. Cuts the acquisition fee 15% and adds a small rating bump.</li>'
        f'<li><b>🔥 Competitor interest</b>: a rival network is bidding. Winning it now costs '
        f'{RIVAL_FEE_PREMIUM:.0%} more; waiting risks losing it for good ({RIVAL_POACH_CHANCE:.0%} chance '
        f'each new year).</li>'
        '<li><b>Acquisition fee + season production cost</b>: what you pay. The fee buys the rights, the '
        'production cost makes this season. Both come out of this year\'s budget the moment you click Acquire.</li>'
        '</ul></div>',
        unsafe_allow_html=True)

    # Competitor interest (2026-10-01, utils/pitch_market.py): contested pitches
    # a team passed on may be signed by the rival at the start of a new year.
    team_key = f"{ss.get('school', '')}||{ss.get('class_section', '')}||{ss.get('team_name', '')}"
    still_open = [k for k in TV_PITCH_CATALOG if k not in ss.tv_pitches_acquired]
    resolve_rival_signings(ss, team_key, ss.active_network, year, still_open)
    lost = ss.get("tv_pitches_lost", {})
    if lost:
        gone = " · ".join(
            f'<b>{TV_PITCH_CATALOG[k]["name"]}</b> → {v["rival"]} '
            f'({NETWORK_INFO[v["network"]]["display_name"]} {LEVEL_START_YEAR[v["network"]] + v["year"] - 1})'
            for k, v in lost.items())
        st.markdown(
            f'<div style="font-size:14px;color:#ef5350;margin-bottom:10px;">🚫 Signed by rival networks '
            f'before you acquired them: <span style="color:#e8eaf0;">{gone}</span></div>',
            unsafe_allow_html=True)

    available_pitches = [k for k in still_open if k not in lost]
    if not available_pitches:
        st.caption("No pitches left to acquire — every show in this catalog has already been picked up.")
    else:
        nc = 3
        chunks = [available_pitches[i:i+nc] for i in range(0, len(available_pitches), nc)]
        for chunk in chunks:
            pcols = st.columns(nc)
            for col, key in zip(pcols, chunk):
                pitch = TV_PITCH_CATALOG[key]
                demo  = genre_demo(pitch["genre"])
                fee   = contested_fee(tv_pitch_acquisition_fee_m(pitch), key)
                rival = rival_for(key)
                rival_line = (
                    f'<div style="font-size:12px;color:#ffa726;margin-top:4px;">🔥 Competitor interest: '
                    f'{rival} is bidding. Fee includes a +{RIVAL_FEE_PREMIUM:.0%} competitive premium. '
                    f'Pass this year and there\'s a {RIVAL_POACH_CHANCE:.0%} chance {rival} signs it '
                    f'before next year.</div>' if rival else '<div></div>')
                season_cost = pitch["episodes"] * pitch["ep_cost_k"] / 1000
                origin_badge = (f'🌍 International Format ({pitch["format_source"]})'
                                if pitch["origin"] == "International Format" else "🏠 Domestic Original")
                bp = pitch.get("brand_partner")
                bp_line = (f'<div style="font-size:12px;color:#e8c547;margin-top:4px;">🤝 Brand Partnership: '
                           f'{bp["name"]} (+{bp["rating_bonus"]:.2f} rating)</div>' if bp else
                           '<div style="font-size:12px;color:#e0e2ea;margin-top:4px;">No brand partnership</div>')
                with col:
                    st.markdown(f"""
                    <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;
                         padding:14px;height:100%;">
                      <div style="font-size:15px;font-weight:600;color:#e8eaf0;">{pitch['name']}</div>
                      <div style="font-size:12px;color:#e0e2ea;font-family:DM Mono,monospace;margin:2px 0 6px;">
                        {pitch['genre']} · {origin_badge}</div>
                      <div style="font-size:12px;color:#e0e2ea;line-height:1.5;margin-bottom:6px;">{pitch['bio']}</div>
                      <div style="font-size:12px;color:#e0e2ea;font-family:DM Mono,monospace;">
                        Demo: {demo['age']} · {demo['gender']} · {demo['reach']}</div>
                      <div style="font-size:12px;color:#e0e2ea;font-family:DM Mono,monospace;">
                        {pitch['episodes']} eps · ${pitch['ep_cost_k']}K/ep · rating {pitch['rating']:.1f} ·
                        SVOD appeal {pitch['svod_appeal']} · IP Score {pitch['ip_score']}</div>
                      {bp_line}
                      {rival_line}
                      <div style="font-size:13px;color:#e8eaf0;margin-top:8px;">
                        Acquisition fee: <b>${fee:.2f}M</b> + ${season_cost:.2f}M season production cost
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if slots_left <= 0:
                        st.caption("No greenlight slots left this year.")
                        continue
                    acquire_month_label = st.select_slider(
                        "Premiere month", options=[f"{i} · {MONTHS[i-1]}" for i in range(1, 13)],
                        value="3 · Mar", key=f"acquire_month_{key}",
                    )
                    if st.button(f"Acquire \"{pitch['name']}\"", key=f"acquire_{key}", use_container_width=True):
                        bonus_rating = pitch["rating"] + (bp["rating_bonus"] if bp else 0.0)
                        acquire_month = int(acquire_month_label.split(" · ")[0])
                        new_show = Show(
                            id=ss.next_show_id, name=pitch["name"], genre=pitch["genre"],
                            episodes=pitch["episodes"], ep_cost_k=pitch["ep_cost_k"], rating=bonus_rating,
                            ip_score=pitch["ip_score"], air_month=acquire_month, network=net_display_intro,
                            description=pitch["bio"],
                        )
                        roster_key = f"{ss.active_network}_shows"
                        ss[roster_key] = ss[roster_key] + [new_show]
                        ss.level_budget = ss.get("level_budget", 0) - fee - season_cost
                        ss.greenlit_ids_this_year.add(new_show.id)
                        ss.greenlit_ids_this_level.add(new_show.id)
                        ss.total_shows_greenlit += 1
                        ss.next_show_id += 1
                        ss.tv_pitches_acquired.add(key)
                        st.rerun()

    st.divider()

    st.markdown(f"""
    <div style="background:#1a1d26;border:1px solid #252836;border-left:3px solid #4fc3f7;
         border-radius:6px;padding:12px 16px;margin-bottom:16px;font-size:15px;color:#e0e2ea;">
    💡 <b style="color:#e8eaf0;">The Core Decision:</b> this comparison is a <b>hypothetical</b> —
    what would this same show concept be worth as a <b>linear</b> show vs. an <b>SVOD+</b> show?
    In 2012, linear wins on immediate cash — faster ad revenue, no subscriber acquisition cost.
    By Year 7+, SVOD subscription LTV starts to outpace a declining ad market.
    <br><br>
    Clicking "Greenlight This Show" below always adds it to <b>{net_display_intro}'s</b> real
    roster (whichever network you're currently playing) — it never actually moves to SVOD.
    The Linear vs. SVOD comparison is purely for building intuition about the trade-off.
    </div>
    """, unsafe_allow_html=True)

    # ── Peer Pitch Board (2026-10-01; replaced AI pitch ideas/feedback) ─────────
    with st.expander("👀 See what other teams in your class have pitched (TV + Movies)", expanded=False):
        from app_pages.pitch_board import render_pitch_board
        render_pitch_board(ss, key="gl_pitch_board")

    # ── Show Concept Builder ───────────────────────────────────────────────────
    st.markdown('<div class="section-title">Show Concept Inputs</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:14px;color:#e8eaf0;line-height:1.6;margin-bottom:10px;">'
        '"18-49" is Nielsen\'s standard ad-buying demo — the age range advertisers pay the most to '
        'reach, so Projected Rating is really "how much of that specific audience tunes in," not '
        'raw viewership. These inputs are yours to set independently, but in the real world (and in '
        'this game\'s economics) a higher rating rarely comes cheap: top-tier talent, bigger sets, and '
        'more marketing all cost more, which is why Cost per Episode tends to climb alongside '
        'Projected Rating for a believable concept — a cheap show promising a mega-hit rating is the '
        'kind of pitch a real network would be skeptical of.</div>',
        unsafe_allow_html=True)

    with st.container():
        c1,c2,c3 = st.columns(3)
        with c1:
            show_name = st.text_input("Show Name / Concept", "My New Show", key="gl_show_name")
            genre     = st.selectbox("Genre", _GENRES, key="gl_genre")
            eps       = st.number_input("Episode Count", 4, 24, 10, step=1, key="gl_eps")
        with c2:
            ep_cost   = st.number_input("Cost per Episode ($K)", 100, 5000, 750, step=50,
                                         help="Bravo reality ~\\$650-900K. Scripted ~\\$1-2M.", key="gl_ep_cost")
            rating    = st.slider("Projected Rating (18-49)", 0.3, 4.0, 1.2, step=0.1,
                                   help="Share of the 18-49 ad-buying demo you expect to reach. "
                                        "Bravo avg: 1.0–1.5. Hit show: 2.0+. Mega-hit: 3.0+. Chasing a "
                                        "higher number here usually means paying for it — keep Cost per "
                                        "Episode realistic for the rating you're claiming.", key="gl_rating")
            mkt_spend = st.slider("Marketing Budget ($M)", 0.0, 10.0, 2.0, step=0.5,
                                   help="Each $1M adds ~1.5% rating lift on linear; also lifts SVOD sub acquisition.", key="gl_mkt_spend")
        with c3:
            appeal    = st.slider("Genre Appeal Score (SVOD)", 20, 100, 72, step=1,
                                   help="How well does this genre convert to streaming subscriptions? "
                                        "True Crime: 85. Scripted drama: 90. Reality: 60.", key="gl_appeal")
            air_month_label = st.select_slider(
                "Premiere Month", options=[f"{i} · {MONTHS[i-1]}" for i in range(1, 13)],
                value="3 · Mar", help="Affects amortization cash trough (see Schedule tab).", key="gl_air_month")
            air_month = int(air_month_label.split(" · ")[0])
            svod_prem = st.number_input("SVOD Monthly Premium ($/sub)", 5.0, 20.0, 8.0, step=0.5,
                                         help="Price premium vs. baseline. Higher = more LTV per acquired sub.", key="gl_svod_prem")

        # One pitch box for the whole concept (2026-10-01): required to greenlight,
        # saved as the show's description (shown on Renewal cards), and posted
        # to the class Pitch Board when the show is greenlit.
        pitch = st.text_area(
            "Your pitch (2-4 sentences): the concept, the hook, and who it's for",
            placeholder="e.g. A competition show where design students renovate a real "
                        "small business on a shoestring budget...",
            key="gl_pitch_text", max_chars=600,
        )

    # ── Title / IP legal-risk check ─────────────────────────────────────────────
    title_collision = show_name.strip().lower() in _taken_titles()
    if title_collision:
        st.markdown(f"""
        <div style="background:rgba(239,83,80,.08);border:1px solid rgba(239,83,80,.4);
             border-left:3px solid {DANGER};border-radius:6px;padding:14px 18px;margin-bottom:16px;">
          <div style="font-size:15px;color:{DANGER};font-weight:600;margin-bottom:4px;">
            🚫 Legal Risk — Title Already Exists
          </div>
          <div style="font-size:15px;color:#e0e2ea;">
            "<b>{show_name}</b>" is already an existing title in this universe. Using it without
            permission gets you sued — <b>Risk Score: 0</b>. Rename the concept to something
            original before building a P&L on it.
          </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Calculate ─────────────────────────────────────────────────────────────
    linear = greenlight_linear(eps, ep_cost, rating, mkt_spend, year)
    svod   = greenlight_svod(eps, ep_cost, rating, appeal, mkt_spend, year)
    # Override SVOD LTV with student's premium
    svod["ltv_3yr"] = svod["sub_lift"] * svod_prem * 12 * 0.15 * 3
    svod["revenue"] = svod["ltv_3yr"] / 3
    svod["ocf"]     = svod["revenue"] - linear["cost"] - mkt_spend
    svod["roi"]     = (svod["ocf"] / linear["cost"] * 100) if linear["cost"] else 0

    st.divider()

    # ── Greenlight This Show — actually adds it to the real roster ─────────────
    # Added 2026-07-27: Greenlighting was previously a standalone P&L
    # sandbox that never touched real game state. Cap of MAX_NEW_SHOWS_PER_YEAR
    # matches real network development slates (a handful of new titles per
    # season against a 20-40 show base) — budget already gates spending on
    # top of this, this caps pacing/portfolio growth. (Slot tracking itself
    # now lives at the top of render() -- see the comment there.)
    net_display = NETWORK_INFO[ss.active_network]["display_name"]

    st.markdown('<div class="section-title">🎬 Greenlight This Show</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:14px;color:#e0e2ea;margin-bottom:8px;">'
        f'Adds your concept to {net_display}\'s real roster <b>using the numbers in Show Concept Inputs '
        f'above</b> — production cost (${linear["cost"]:.2f}M) comes out of this year\'s budget '
        f'immediately, and it starts earning/costing real money this year. Your pitch becomes the '
        f'show\'s description on the Renewal cards. You\'ve greenlit {slots_used} of '
        f'{MAX_NEW_SHOWS_PER_YEAR} new shows this year.</div>',
        unsafe_allow_html=True)

    pitch_ok = len(pitch.strip()) >= 20
    if slots_left <= 0:
        st.warning(f"⚠ You've used all {MAX_NEW_SHOWS_PER_YEAR} greenlight slots for this year — "
                    "come back next year for more.")
    elif not pitch_ok:
        st.info("✍️ Write your pitch in **Show Concept Inputs** above (at least a sentence) to greenlight "
                "this show. A network never greenlights a concept nobody can describe.")
    elif st.button(f"🎬 Greenlight \"{show_name}\" for {net_display}", type="primary",
                   use_container_width=True, key="gl_greenlight_manual"):
        new_show = Show(
            id=ss.next_show_id, name=show_name.strip(), genre=genre, episodes=eps,
            ep_cost_k=ep_cost, rating=rating, ip_score=_NEW_SHOW_IP_SCORE,
            air_month=air_month, network=net_display, description=pitch.strip(),
        )
        roster_key = f"{ss.active_network}_shows"
        ss[roster_key] = ss[roster_key] + [new_show]
        ss.level_budget = ss.get("level_budget", 0) - linear["cost"]   # production cost, unescalated (year-1 basis)
        ss.greenlit_ids_this_year.add(new_show.id)
        ss.greenlit_ids_this_level.add(new_show.id)
        ss.total_shows_greenlit += 1
        ss.next_show_id += 1
        # Share it on the class Pitch Board (2026-10-01).
        from utils.game_state import post_pitch, LEVEL_START_YEAR as _LSY
        post_pitch(ss.get("team_name", ""), ss.get("school", ""), ss.get("class_section", ""), "tv",
                   key=f"{ss.active_network}-{new_show.id}", title=new_show.name, genre=genre, pitch=pitch.strip(),
                   details={"network": net_display, "year_label": str(_LSY[ss.active_network] + year - 1),
                            "episodes": eps, "ep_cost_k": ep_cost, "rating": rating})
        st.rerun()   # note: a st.success() here would never render — rerun replaces the DOM
                     # immediately. The updated "X of N greenlit" count above is the confirmation.

    st.divider()

    # ── Side-by-side P&L ──────────────────────────────────────────────────────
    # Moved to after Greenlight This Show 2026-08-04 per user request -- the
    # comparison reads as reference/justification for the greenlight call,
    # so it belongs after the actual action, not gating it.
    st.markdown('<div class="section-title">Platform P&L Comparison</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:13px;color:#e0e2ea;margin-bottom:10px;line-height:1.6;">'
        '<b style="color:#e0e2ea;">What each line means:</b> '
        '<b>Total Season Cost</b> = episode cost × episode count. '
        '<b>Ad Revenue (Y1)</b> = what Linear earns this year from ratings. '
        '<b>Sub Lift Est.</b> = subscribers SVOD is projected to add. '
        '<b>LTV (3-yr)</b> = the total 3-year value of those subs, SVOD\'s real revenue pot. '
        '<b>Y1 Revenue Share</b> = 1/3 of that LTV, booked in Year 1 so it can be compared fairly to Linear\'s Y1 number. '
        '<b>Net OCF</b> = revenue minus cost minus marketing — the actual cash this concept nets. '
        '<b>ROI</b> = Net OCF ÷ Total Cost. '
        '<b>Amortization</b> = months the production cost is spread over before it\'s fully expensed. '
        '<b>Cash Payback</b> = whether Year-1 cash alone covers the cost. '
        '<b>Revenue ceiling</b> = the structural cap on each model (Linear: shrinking ad market as cord-cutting continues; SVOD: total addressable subscribers). '
        '<b>Engagement Score</b> = a composite of rating and genre appeal — a rough proxy for how much a show drives usage beyond raw sub counts.'
        '</div>', unsafe_allow_html=True)

    def pl_card(title, color, data, winner=False):
        border = f"border:2px solid {color};" if winner else f"border:1px solid #252836;"
        rows = "".join([
            f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
            f'border-bottom:1px solid rgba(37,40,54,.5);font-size:15px;">'
            f'<span style="color:#e0e2ea;">{k}</span>'
            f'<span style="font-family:DM Mono,monospace;color:{vc};">{v}</span></div>'
            for k,v,vc in data
        ])
        w_badge = f'<span style="background:{color};color:#0b0c10;font-size:14px;padding:2px 8px;border-radius:3px;font-family:DM Mono,monospace;">WINNER</span>' if winner else ''
        return f"""
        <div style="background:#1a1d26;{border}border-radius:8px;padding:16px;height:100%;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <span style="font-family:DM Mono,monospace;font-size:14px;text-transform:uppercase;
                  letter-spacing:.1em;color:{color};">{title}</span>
            {w_badge}
          </div>
          {rows}
        </div>
        """

    lin_winner  = linear["ocf"] > svod["ocf"] and year < 7
    svod_winner = not lin_winner

    lin_rows = [
        ("Total Season Cost",   f"${linear['cost']:.2f}M",    WARN),
        ("Ad Revenue (Y1)",     f"${linear['revenue']:.2f}M", SUCCESS),
        ("Marketing",           f"-${mkt_spend:.1f}M",         DANGER),
        ("Net OCF",             f"${linear['ocf']:+.2f}M",    SUCCESS if linear["ocf"]>=0 else DANGER),
        ("ROI",                 f"{linear['roi']:+.1f}%",      SUCCESS if linear["roi"]>=0 else DANGER),
        ("Amortization",        "12 months",                  TEXT2),
        ("Cash Payback",        linear["payback"],             TEXT2),
        ("Revenue ceiling",     "Ad market (eroding)",        TEXT2),
    ]
    svod_rows = [
        ("Total Season Cost",   f"${svod['cost']:.2f}M",      WARN),
        ("Sub Lift Est.",       f"+{svod['sub_lift']:.2f}M subs", SUCCESS),
        ("LTV (3-year)",        f"${svod['ltv_3yr']:.2f}M",   SUCCESS),
        ("Y1 Revenue Share",    f"${svod['revenue']:.2f}M",   ACCENT2),
        ("Net OCF (Y1)",        f"${svod['ocf']:+.2f}M",      SUCCESS if svod["ocf"]>=0 else DANGER),
        ("ROI (3yr basis)",     f"{svod['roi']:+.1f}%",        SUCCESS if svod["roi"]>=0 else DANGER),
        ("Amortization",        "36 months",                  TEXT2),
        ("Engagement Score",    f"{svod['engagement']:.2f}",  TEXT2),
    ]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(pl_card(f"📺 Linear — {net_display}", ACCENT, lin_rows, lin_winner), unsafe_allow_html=True)
    with c2:
        st.markdown(pl_card("📱 SVOD+", ACCENT2, svod_rows, svod_winner), unsafe_allow_html=True)

    # Winner banner
    if lin_winner:
        st.success(f"📺 **Linear wins in Year {year}** — Faster cash recovery. Ad revenue beats SVOD LTV at current cord-cut levels.")
    else:
        st.info(f"📱 **SVOD+ wins in Year {year}** — Subscription LTV outpaces declining linear ad market. Long-term play.")

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">3-Year P&L Comparison</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:13px;color:#e0e2ea;margin-bottom:6px;">'
        'Same concept, extrapolated 3 years out: Linear\'s bars are Year-1 numbers × 3 (a flat '
        'run-rate). SVOD\'s "3yr Revenue" bar is its real 3-year LTV; its "3yr OCF" bar is Year-1 OCF '
        '× 3 for the same side-by-side comparison. SVOD often looks negative here because it only '
        'books 1/3 of its 3-year revenue pot in Year 1, against the full production cost paid up '
        'front — the same reason Linear usually wins the early cash race even when SVOD wins on '
        'total value over time.</div>', unsafe_allow_html=True)
    categories = ["Total Cost","Y1 Revenue","Y1 OCF","3yr Revenue","3yr OCF"]
    lin_vals   = [linear["cost"], linear["revenue"], linear["ocf"],
                  linear["revenue"]*3, linear["ocf"]*3]
    svod_vals  = [svod["cost"],   svod["revenue"],   svod["ocf"],
                  svod["ltv_3yr"], svod["ocf"]*3]

    fig_cmp = go.Figure()
    fig_cmp.add_trace(go.Bar(name="📺 Linear", x=categories,
                              y=[round(v,2) for v in lin_vals],
                              marker_color=ACCENT, opacity=0.8))
    fig_cmp.add_trace(go.Bar(name="📱 SVOD+",  x=categories,
                              y=[round(v,2) for v in svod_vals],
                              marker_color=ACCENT2, opacity=0.7))
    fig_cmp.update_layout(**base_layout("Linear vs. SVOD — Revenue, Cost, OCF ($M)", height=300))
    st.plotly_chart(fig_cmp, use_container_width=True, config={"displayModeBar":False})

    # Cumulative LTV Curve — explanatory, not a decision input. Deferred
    # (2026-08-25) to the consolidated "Supplementary Insights" expander in
    # simulation.py instead of sitting inline next to every concept a
    # student prices out. See utils/charts.py::queue_supplement.
    def _render_cumulative_ltv(linear=linear, svod=svod):
        st.markdown(
            '<div style="font-size:13px;color:#e0e2ea;margin-bottom:6px;">'
            'Running total of revenue over time, not a single-year number. Linear\'s line spreads its '
            'Year-1 ad revenue rate evenly across all 36 months; SVOD\'s line spreads its full 3-year LTV '
            'evenly across the same 36 months. The dashed <b style="color:#e0e2ea;">Crossover</b> line '
            'marks the month SVOD\'s cumulative total overtakes Linear\'s — visualizing "Linear wins early '
            'cash, SVOD wins the long game" as an actual point in time instead of just a claim.</div>',
            unsafe_allow_html=True)
        ltv_df = ltv_curve(linear, svod, months=36)
        fig_ltv = go.Figure()
        fig_ltv.add_trace(go.Scatter(
            x=ltv_df["Month"], y=ltv_df["Linear (cumul.)"],
            name="Linear (cumul.)", mode="lines",
            line=dict(color=ACCENT, width=2),
            fill="tozeroy", fillcolor="rgba(232,197,71,0.08)"))
        fig_ltv.add_trace(go.Scatter(
            x=ltv_df["Month"], y=ltv_df["SVOD LTV (cumul.)"],
            name="SVOD LTV (cumul.)", mode="lines",
            line=dict(color=ACCENT2, width=2),
            fill="tozeroy", fillcolor="rgba(79,195,247,0.08)"))
        crossover = ltv_df[ltv_df["SVOD LTV (cumul.)"] >= ltv_df["Linear (cumul.)"]]["Month"].min()
        if crossover and not pd.isna(crossover):
            fig_ltv.add_vline(x=crossover, line_dash="dash", line_color=WARN,
                               annotation_text=f"Crossover: M{crossover}", annotation_font_color=WARN)
        fig_ltv.update_layout(**base_layout("Cumulative Revenue: Linear vs. SVOD ($M)", height=300))
        st.plotly_chart(fig_ltv, use_container_width=True, config={"displayModeBar":False})

    queue_supplement(f"Cumulative LTV Curve (36 months) — \"{show_name}\"", _render_cumulative_ltv,
                     when_to_use="the 3-Year P&L makes streaming look bad; it shows when subscriber value catches up to linear.")

    st.divider()

    # ── Sensitivity Table ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Sensitivity Analysis — Rating vs. Episode Cost</div>', unsafe_allow_html=True)
    st.markdown('<span style="font-size:14px;color:#e0e2ea;">Linear OCF ($M) at different rating × cost combinations. Green = profitable, Red = cancel.</span>', unsafe_allow_html=True)

    rating_range = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
    cost_range   = [300, 500, 750, 1000, 1500, 2000]

    rating_cols = [f"{r:.1f}" for r in rating_range]
    sens_rows = []
    for ep_c in cost_range:
        row = {"Ep Cost": f"${ep_c}K"}
        for r in rating_range:
            lin = greenlight_linear(eps, ep_c, r, mkt_spend, year)
            row[f"{r:.1f}"] = round(lin["ocf"], 2)
        sens_rows.append(row)

    sens_df = pd.DataFrame(sens_rows)

    def color_cells(val):
        try:
            v = float(val)
            if v > 5:   return "background-color:rgba(102,187,106,.25);color:#81c784;"
            if v > 0:   return "background-color:rgba(255,167,38,.15);color:#ffb74d;"
            return "background-color:rgba(239,83,80,.2);color:#ef9a9a;"
        except: return ""

    st.dataframe(
        sens_df.style
        .map(color_cells, subset=rating_cols)
        .format("{:.2f}", subset=rating_cols)
        .hide(axis="index"),
        use_container_width=True
    )
    st.caption("Rows = episode cost (Ep Cost col). Columns = projected 18-49 rating. Cell = Linear OCF in $M.")

    # ── Marketing ROI ──────────────────────────────────────────────────────────
    # Explanatory sensitivity tool, not a decision input on its own — deferred
    # (2026-08-25) to the consolidated "Supplementary Insights" expander in
    # simulation.py. See utils/charts.py::queue_supplement.
    def _render_marketing_roi(eps=eps, ep_cost=ep_cost, rating=rating, appeal=appeal, year=year,
                               show_name=show_name):
        st.markdown(
            '<div style="font-size:13px;color:#e0e2ea;margin-bottom:6px;">'
            'Holds this concept\'s rating and cost fixed and reruns both P&Ls at increasing marketing '
            'budgets, so you can see where extra marketing dollars actually pay off. Linear OCF moves with '
            'the ad-rating lift marketing buys; SVOD OCF moves with the extra subscriber lift (and its 3-year '
            'LTV) that same spend buys — the two lines diverge because marketing pays back through two '
            'different revenue mechanics.</div>', unsafe_allow_html=True)
        mkt_levels = [0, 1, 2, 3, 5, 7, 10]
        mkt_rows = []
        for m in mkt_levels:
            l = greenlight_linear(eps, ep_cost, rating, m, year)
            s = greenlight_svod(eps, ep_cost, rating, appeal, m, year)
            mkt_rows.append({
                "Marketing ($M)": m,
                "Linear OCF":     round(l["ocf"],2),
                "Linear ROI %":   round(l["roi"],1),
                "SVOD OCF":       round(s["ocf"],2),
                "SVOD ROI %":     round(s["roi"],1),
            })
        mkt_df = pd.DataFrame(mkt_rows)

        c1, c2 = st.columns(2)
        with c1:
            fig_mkt = go.Figure()
            fig_mkt.add_trace(go.Scatter(x=mkt_df["Marketing ($M)"], y=mkt_df["Linear OCF"],
                                          name="Linear OCF", mode="lines+markers",
                                          line=dict(color=ACCENT,width=2),marker=dict(size=7)))
            fig_mkt.add_trace(go.Scatter(x=mkt_df["Marketing ($M)"], y=mkt_df["SVOD OCF"],
                                          name="SVOD OCF",   mode="lines+markers",
                                          line=dict(color=ACCENT2,width=2),marker=dict(size=7)))
            fig_mkt.add_hline(y=0, line_dash="dash", line_color=DANGER, opacity=0.5)
            fig_mkt.update_layout(**base_layout("OCF vs. Marketing Spend ($M)", height=280))
            st.plotly_chart(fig_mkt, use_container_width=True, config={"displayModeBar":False})
        with c2:
            st.dataframe(mkt_df.style.format({
                "Linear OCF":"${:.2f}M","Linear ROI %":"{:.1f}%",
                "SVOD OCF":"${:.2f}M","SVOD ROI %":"{:.1f}%"
            }), use_container_width=True, height=280)

    queue_supplement(f"Marketing ROI: Linear vs. SVOD — \"{show_name}\"", _render_marketing_roi,
                     when_to_use="setting this concept's Marketing Budget; it shows where extra marketing stops paying off.")
