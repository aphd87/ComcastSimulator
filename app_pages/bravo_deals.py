"""
Bravo-only decision section: Brand Partnerships + Casting Unknowns
(2026-11-03, per user). Mechanics and fictional catalogs live in
utils/bravo_deals.py; this module is the UI. Rendered by
app_pages/simulation.py::_decisions right after Greenlighting, because
casting applies to the new shows a team just acquired or greenlit.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.bravo_deals import (
    BRAND_CATALOG, CAST_POOL, CASTABLE_GENRES, MAX_BRAND_DEALS_PER_YEAR, MAX_CAST_PER_SHOW,
    EMOTION_LIFT, CHEMISTRY_BONUS, brand_fit, brand_terms, cast_lift_range, ensure_state,
    rival_cast_bid,
)
from utils.charts import html_table, takeaway

_NONE = "— none —"
_BOX = ('background:#1a1d26;border:1px solid #252836;border-radius:6px;padding:12px 16px;'
        'margin-bottom:12px;font-size:15px;color:#ffffff;line-height:1.7;')


def render(ss, shows, year: int, sec_num: int, cancelled: set) -> None:
    ensure_state(ss)
    active = [s for s in shows if s.id not in cancelled]
    st.markdown(f'<div class="section-title decision">{sec_num} · 🤝 Brand Partnerships &amp; Casting '
                '<span style="font-size:14px;color:#ffffff;">(optional)</span></div>', unsafe_allow_html=True)
    _brand_partnerships(ss, active, year)
    st.divider()
    _casting(ss, active, year)


# ── Brand partnerships ──────────────────────────────────────────────────────
def _brand_partnerships(ss, active, year: int) -> None:
    st.markdown('<div class="section-title">Brand Partnerships — Product Placement</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="{_BOX}">
    Brands will pay to appear inside your shows: a cast member drinking their rosé, cooking with their pans,
    taking a trip to their resort. Attach a brand to up to <b>{MAX_BRAND_DEALS_PER_YEAR} shows</b> this year.
    <br>• <b>If the integration lands</b>, the brand pays part of that show's cost this year. That money is
    booked as revenue.
    <br>• <b>If the audience rejects it</b> (it feels forced, or fans mock it online), the brand demands a
    <b>make-good</b>: extra integrations and free ad spots. That <b>adds</b> cost.
    <br>• <b>Fit</b> is the chance it lands. It depends on how well the brand matches the show's genre and
    Bravo's affluent, female-skewing audience. The biggest checks come from the worst-fitting brands.
    <br>The outcome is revealed when you Simulate the year. It is not in the Expected This Year preview.
    </div>
    """, unsafe_allow_html=True)

    eligible = sorted(active, key=lambda s: -s.annual_amort_expense(year))
    if not eligible:
        st.caption("No active shows to attach a brand to.")
        return
    genres = sorted({s.genre for s in eligible})
    ref = [{"Brand": b["name"], "Category": b["category"],
            "Pays if it lands": f"{b['pay_pct']:.0%} of show cost",
            "Make-good if it flops": f"{b['makegood_pct']:.0%} of show cost",
            **{f"Fit: {g}": f"{brand_fit(k, g):.0%}" for g in genres},
            "Pitch": b["pitch"]} for k, b in BRAND_CATALOG.items()]
    html_table(pd.DataFrame(ref), max_height=320)
    takeaway("Read across a row: a brand that pays more usually fits your audience worse. "
             "Expected value = fit × payment − (1 − fit) × make-good. A 30% check at 25% fit is a worse "
             "bet than a 15% check at 85% fit.")

    deals = ss.brand_deals.setdefault(str(year), {})
    by_label = {f"{s.name} ({s.genre}, ${s.annual_amort_expense(year):.1f}M)": s for s in eligible}
    brand_labels = {b["name"]: k for k, b in BRAND_CATALOG.items()}
    current = list(deals.items())
    picks = []
    for i in range(MAX_BRAND_DEALS_PER_YEAR):
        cur_sid, cur_brand = current[i] if i < len(current) else (None, None)
        cur_show_label = next((l for l, s in by_label.items() if str(s.id) == cur_sid), _NONE)
        c1, c2 = st.columns([3, 2])
        show_label = c1.selectbox(f"Deal {i + 1}: show", [_NONE] + list(by_label),
                                  index=([_NONE] + list(by_label)).index(cur_show_label),
                                  key=f"brand_show_{year}_{i}")
        brand_options = [_NONE] + list(brand_labels)
        cur_brand_label = BRAND_CATALOG[cur_brand]["name"] if cur_brand in BRAND_CATALOG else _NONE
        brand_label = c2.selectbox(f"Deal {i + 1}: brand", brand_options,
                                   index=brand_options.index(cur_brand_label), key=f"brand_pick_{year}_{i}")
        if show_label != _NONE and brand_label != _NONE:
            picks.append((by_label[show_label], brand_labels[brand_label]))

    # One brand per show; first pick wins if a show is chosen twice.
    new_deals, seen = {}, set()
    for s, bkey in picks:
        if s.id not in seen:
            new_deals[str(s.id)] = bkey
            seen.add(s.id)
    ss.brand_deals[str(year)] = new_deals

    if new_deals:
        rows, ev_total = [], 0.0
        for sid, bkey in new_deals.items():
            s = next(x for x in eligible if x.id == int(sid))
            t = brand_terms(bkey, s.annual_amort_expense(year), s.genre)
            ev_total += t["expected_m"]
            rows.append({"Show": s.name, "Brand": BRAND_CATALOG[bkey]["name"], "Fit": f"{t['fit']:.0%}",
                         "If it lands": f"+${t['gain_m']:.2f}M", "If it flops": f"−${t['loss_m']:.2f}M",
                         "Expected": f"{'+' if t['expected_m'] >= 0 else '−'}${abs(t['expected_m']):.2f}M"})
        html_table(pd.DataFrame(rows))
        best = max(rows, key=lambda r: float(r["Expected"].replace("−", "-").replace("+", "").replace("$", "").replace("M", "")))
        takeaway(f"Your {len(rows)} deal{'s are' if len(rows) != 1 else ' is'} worth "
                 f"<b>{'+' if ev_total >= 0 else '−'}${abs(ev_total):.2f}M</b> on average. "
                 f"Your safest bet is <b>{best['Brand']}</b> on {best['Show']} ({best['Fit']} fit). "
                 + ("At least one deal is expected to lose money: swap in a better-fitting brand."
                    if any(r["Expected"].startswith("−") for r in rows) else
                    "Every deal is expected to make money, but any one can still flop."))


# ── Casting unknowns ────────────────────────────────────────────────────────
def _casting(ss, active, year: int) -> None:
    st.markdown('<div class="section-title">Cast Your New Shows — Bid on Unknowns</div>', unsafe_allow_html=True)
    lifts = ", ".join(f"{e} {v:+.0%}" for e, v in EMOTION_LIFT.items())
    st.markdown(f"""
    <div style="{_BOX}">
    New reality and competition shows live or die by their cast. For any <b>new</b> Reality or Competition
    show you added this level (acquired or greenlit above), you can bid on up to <b>{MAX_CAST_PER_SHOW}
    unknowns</b>. A rival network bids too, with a sealed bid you can't see. Bid at least what they bid and
    the person is yours; bid less and they sign with the rival for good.
    <br>• <b>Emotional type</b> sets the expected rating boost: {lifts}.
    <br>• <b>Weirdness</b> (1–10) widens the range. A very weird cast member might be a breakout star or a
    turn-off. The cards show the full range.
    <br>• <b>Chemistry:</b> pairing a Volatile or Scheming person with a Warm or Bubbly one adds
    {CHEMISTRY_BONUS:+.0%} more.
    <br>• The boost applies to the show's ad revenue every year the cast is on it. The fee you bid is
    charged to this year's budget and P&amp;L.
    </div>
    """, unsafe_allow_html=True)

    new_ids = ss.get("greenlit_ids_this_level", set())
    castable = [s for s in active if s.id in new_ids and s.genre in CASTABLE_GENRES]
    if not castable:
        st.info("Acquire or greenlight a new Reality or Competition show in Greenlighting above, then come "
                "back here to cast it.")
        return

    team = ss.get("team_name", "")
    show_labels = {f"{s.name} ({s.genre})": s for s in castable}
    show = show_labels[st.selectbox("Show to cast", list(show_labels), key=f"cast_show_{year}")]
    signed = ss.cast_signings.setdefault(str(show.id), [])
    if ss.get("cast_last_msg"):
        st.markdown(f'<div style="font-size:15px;color:#ffffff;margin:4px 0 10px;">{ss.pop("cast_last_msg")}</div>',
                    unsafe_allow_html=True)
    taken = {k for v in ss.cast_signings.values() for k in v} | set(ss.cast_lost)

    if signed:
        lo = sum(cast_lift_range(k)[0] for k in signed)
        hi = sum(cast_lift_range(k)[1] for k in signed)
        emos = {CAST_POOL[k]["emotion"] for k in signed}
        chem = bool(emos & {"Volatile", "Scheming"} and emos & {"Warm", "Bubbly"})
        names = ", ".join(f"<b>{CAST_POOL[k]['name']}</b> ({CAST_POOL[k]['emotion']})" for k in signed)
        takeaway(f"{show.name}'s cast: {names}. Expected rating effect {lo:+.0%} to {hi:+.0%}"
                 + (f", plus {CHEMISTRY_BONUS:+.0%} chemistry." if chem else
                    ". Add a contrasting personality for the chemistry bonus." if len(signed) < MAX_CAST_PER_SHOW
                    else "."))
    if len(signed) >= MAX_CAST_PER_SHOW:
        st.caption(f"{show.name} has a full cast ({MAX_CAST_PER_SHOW}).")
        return
    if ss.cast_lost:
        st.markdown('<div style="font-size:14px;color:#ef5350;margin-bottom:8px;">🚫 Signed by rivals: '
                    + ", ".join(f'<span style="color:#ffffff;">{CAST_POOL[k]["name"]} → {r}</span>'
                                for k, r in ss.cast_lost.items()) + '</div>', unsafe_allow_html=True)

    pool = [k for k in CAST_POOL if k not in taken]
    if not pool:
        st.caption("Everyone in this year's casting pool has signed somewhere.")
        return
    for i in range(0, len(pool), 3):
        cols = st.columns(3)
        for col, key in zip(cols, pool[i:i + 3]):
            c = CAST_POOL[key]
            lo, hi = cast_lift_range(key)
            with col:
                st.markdown(f"""
                <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;padding:12px;">
                  <div style="font-size:15px;font-weight:600;color:#ffffff;">{c['name']}, {c['age']}</div>
                  <div style="font-size:13px;color:#ffffff;font-family:DM Mono,monospace;">{c['job']} · {c['city']}</div>
                  <div style="font-size:14px;color:#ffffff;margin:6px 0;line-height:1.5;">{c['bio']}</div>
                  <div style="font-size:13px;color:#ffffff;"><b>Hobbies:</b> {c['hobbies']}</div>
                  <div style="font-size:13px;color:#ffffff;"><b>Emotional type:</b> {c['emotion']} ·
                    <b>Weirdness:</b> {c['weirdness']}/10</div>
                  <div style="font-size:13px;color:#e8c547;margin-top:4px;">Rating effect {lo:+.1%} to {hi:+.1%} ·
                    asking ${c['ask_m']:.2f}M</div>
                </div>
                """, unsafe_allow_html=True)
                bid = st.number_input("Your bid ($M)", min_value=0.0, max_value=5.0, value=float(c["ask_m"]),
                                      step=0.05, format="%.2f", key=f"cast_bid_{key}")
                if st.button(f"🎤 Bid ${bid:.2f}M for {c['name'].split()[0]}", key=f"cast_btn_{key}",
                             use_container_width=True):
                    rival_bid, rival = rival_cast_bid(team, key)
                    if bid >= rival_bid:
                        signed.append(key)
                        ss.cast_fees[str(year)] = round(float(ss.cast_fees.get(str(year), 0.0)) + bid, 3)
                        ss.level_budget = (ss.get("level_budget") or 0) - bid
                        ss.cast_last_msg = (f"✅ You signed {c['name']} for ${bid:.2f}M "
                                            f"({rival} bid ${rival_bid:.2f}M).")
                    else:
                        ss.cast_lost[key] = rival
                        ss.cast_last_msg = (f"❌ {rival} outbid you for {c['name']} "
                                            f"(${rival_bid:.2f}M vs. your ${bid:.2f}M). No fee charged.")
                    st.rerun()
