"""Peacock Film Licensing section (2026-11-03). Mechanics: utils/film_licensing.py."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.charts import html_table, takeaway
from utils.film_licensing import (FILM_CATALOG, FILM_RETENTION_CREDIT, ensure_state, films_offered, held,
                                  resolve_film_bid, true_value_m)

_BOX = ('background:#1a1d26;border:1px solid #252836;border-radius:6px;padding:12px 16px;'
        'margin-bottom:12px;font-size:15px;color:#ffffff;line-height:1.7;')


def render(ss, year: int, sec_num: int) -> None:
    ensure_state(ss)
    st.markdown(f'<div class="section-title decision">{sec_num} · 🎞️ Film Licensing '
                '<span style="font-size:14px;color:#ffffff;">(optional)</span></div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="{_BOX}">
    Studios license finished movies to streamers for a few years after their theatrical run. Each year a few
    films come up. Bid an annual fee; one rival streamer bids too, sealed. Highest bid wins and pays its own
    bid every year of the license.
    <br>• A licensed film earns <b>subscription revenue</b> every year you hold it. Its exact value is only
    revealed once you sign it. <b>Critics score</b> and <b>box office</b> are your clues: well-reviewed films
    tend to keep subscribers longer than loud, poorly reviewed ones.
    <br>• <b>Content mix:</b> films also help keep sports fans subscribed. {FILM_RETENTION_CREDIT:.0%} of
    each license fee counts toward the originals spending your sports packages need, so a film is a cheaper
    (but weaker) way to hold onto sports subscribers than a new original series.
    <br>• Fees are charged to this year's P&amp;L and every year of the term.
    </div>
    """, unsafe_allow_html=True)

    holding = held(ss, year)
    if holding:
        rows = [{"Film": FILM_CATALOG[l["film"]]["title"], "Years": f"{l['start']}–{l['end']}",
                 "Fee / yr": f"${l['annual_cost_m']:.2f}M", "Earns / yr": f"${true_value_m(l['film']):.2f}M",
                 "Net / yr": f"{'+' if true_value_m(l['film']) >= l['annual_cost_m'] else '−'}"
                             f"${abs(true_value_m(l['film']) - l['annual_cost_m']):.2f}M"} for l in holding]
        st.markdown('<div style="font-size:14px;color:#ffffff;margin-bottom:6px;"><b>Your film library '
                    'this year</b> (level years)</div>', unsafe_allow_html=True)
        html_table(pd.DataFrame(rows))

    log = ss.film_bid_log.get(str(year))
    offers = films_offered(year)
    if log is None:
        st.markdown(f'<div style="font-size:14px;color:#ffffff;margin:6px 0;"><b>{len(offers)} films up for '
                    f'license this year:</b></div>', unsafe_allow_html=True)
        cols = st.columns(len(offers))
        for col, key in zip(cols, offers):
            f = FILM_CATALOG[key]
            with col:
                st.markdown(f"""
                <div style="background:#1a1d26;border:1px solid #252836;border-radius:8px;padding:12px;">
                  <div style="font-size:15px;font-weight:600;color:#ffffff;">{f['title']}</div>
                  <div style="font-size:13px;color:#ffffff;font-family:DM Mono,monospace;">{f['genre']}</div>
                  <div style="font-size:14px;color:#ffffff;margin:6px 0;line-height:1.5;">{f['logline']}</div>
                  <div style="font-size:13px;color:#ffffff;">Box office ${f['box_office_m']}M · Critics {f['critics']}/100</div>
                  <div style="font-size:13px;color:#e8c547;margin-top:4px;">{f['term']}-year license ·
                    asking ~${f['ask_m']:.1f}M/yr</div>
                </div>""", unsafe_allow_html=True)
                st.number_input("Your bid ($M/yr, 0 = pass)", min_value=0.0, max_value=50.0, value=0.0,
                                step=0.5, format="%.1f", key=f"film_bid_{year}_{key}")
        if st.button("🎞️ Submit Film Bids", key=f"film_submit_{year}", use_container_width=True):
            results = {}
            for key in offers:
                bid = float(ss.get(f"film_bid_{year}_{key}", 0.0))
                r = resolve_film_bid(key, bid)
                results[key] = r
                if r["won"]:
                    term = FILM_CATALOG[key]["term"]
                    ss.film_licenses.append({"film": key, "start": year, "end": year + term - 1,
                                             "annual_cost_m": r["bid_m"]})
            ss.film_bid_log[str(year)] = results
            st.rerun()
        return

    rows = []
    for key, r in log.items():
        f = FILM_CATALOG[key]
        rows.append({"Film": f["title"], "Your bid": f"${r['bid_m']:.2f}M" if r["bid_m"] else "passed",
                     "Rival": f"{r['rival']} ${r['rival_bid_m']:.2f}M",
                     "Result": ("✅ Licensed" if r["won"] else ("❌ Outbid" if r["bid_m"] else "—")),
                     "Actually earns / yr": f"${true_value_m(key):.2f}M" if r["won"] else "hidden"})
    html_table(pd.DataFrame(rows))
    won = [k for k, r in log.items() if r["won"]]
    if won:
        net = sum(true_value_m(k) - log[k]["bid_m"] for k in won)
        takeaway(f"You licensed {len(won)} film{'s' if len(won) != 1 else ''}, netting "
                 f"<b>{'+' if net >= 0 else '−'}${abs(net):.2f}M a year</b> before the sports-retention boost. "
                 + ("Paying more than a film earns is the winner's curse: bid what it's worth, not what wins."
                    if net < 0 else "You paid less than these films earn. That's a good library deal."))
    else:
        takeaway("No films licensed this year. That keeps cash free for originals and sports, but your sports fans "
                 "get no help from a film library.")
