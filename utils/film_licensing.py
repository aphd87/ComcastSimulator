"""
Peacock film licensing (2026-11-03, per user: "are there movie licenses to
bid on too?").

Each year of the Peacock level a few fictional studio films come up for a
streaming license (the Pay-1 / library window the Movies simulation models
from the studio side). A team places sealed bids against one rival streamer;
highest bid wins and pays its own bid every year of the term.

Economics:
- A licensed film earns subscription revenue each year of the term. Its
  true value is hidden until signed: it centers on the asking price scaled
  by the film's critics score and box office (the signals students see),
  with seeded noise, so a cheap well-reviewed film can beat a pricey
  blockbuster.
- Content-mix angle: licensed films also help keep sports subscribers from
  churning (FILM_RETENTION_CREDIT of the license fee counts toward the
  originals spend that sports retention needs), at half the effect of
  originals.

Draws are seeded PER TEAM (2026-11-03): a film's true value and the rival's
bid differ by team, so one team can't learn them (or scout with a throwaway
team name) and hand the answers to the class. All films are fictional.
"""
from __future__ import annotations

import hashlib

FILM_RETENTION_CREDIT = 0.5
OFFERS_PER_YEAR = 3

FILM_CATALOG = {
    "starfall": {"title": "Starfall Protocol", "genre": "Sci-Fi Action", "box_office_m": 610, "critics": 58,
                 "term": 2, "ask_m": 14.0, "logline": "A satellite engineer races a rogue AI to stop an orbital strike."},
    "the_long_table": {"title": "The Long Table", "genre": "Family Drama", "box_office_m": 85, "critics": 91,
                       "term": 3, "ask_m": 4.0, "logline": "Four estranged siblings cater their father's last dinner party."},
    "cheer_up": {"title": "Cheer Up, Coach", "genre": "Comedy", "box_office_m": 140, "critics": 74,
                 "term": 2, "ask_m": 5.5, "logline": "A disgraced NFL coach takes over a middle-school cheer squad."},
    "black_ice": {"title": "Black Ice", "genre": "Thriller", "box_office_m": 230, "critics": 66,
                  "term": 2, "ask_m": 8.0, "logline": "A trucker on a frozen highway realizes her cargo is breathing."},
    "paper_crowns": {"title": "Paper Crowns", "genre": "Animated Family", "box_office_m": 480, "critics": 88,
                     "term": 3, "ask_m": 12.0, "logline": "Two kids build a kingdom out of cardboard, and it starts to grow."},
    "midnight_sermon": {"title": "Midnight Sermon", "genre": "Horror", "box_office_m": 120, "critics": 79,
                        "term": 2, "ask_m": 3.5, "logline": "A small-town pastor's late-night broadcasts summon the wrong listeners."},
    "gold_rush_92": {"title": "Gold Rush '92", "genre": "Sports Drama", "box_office_m": 175, "critics": 83,
                     "term": 3, "ask_m": 6.0, "logline": "The true-to-life story of a scrappy Olympic bobsled team. Great next to sports."},
    "velvet_heist": {"title": "The Velvet Heist", "genre": "Caper", "box_office_m": 340, "critics": 52,
                     "term": 2, "ask_m": 10.0, "logline": "Retired con artists reunite to rob an art auction run by their old mark."},
    "rom_com_redo": {"title": "Second Draft", "genre": "Romantic Comedy", "box_office_m": 95, "critics": 70,
                     "term": 2, "ask_m": 3.0, "logline": "A screenwriter gets to rewrite her real love life, one scene at a time."},
    "iron_meridian": {"title": "Iron Meridian", "genre": "War Epic", "box_office_m": 390, "critics": 85,
                      "term": 3, "ask_m": 11.0, "logline": "A WWII codebreaker hides her work from both sides of the war."},
    "neon_drift": {"title": "Neon Drift", "genre": "Action", "box_office_m": 270, "critics": 41,
                   "term": 2, "ask_m": 7.5, "logline": "Street racers smuggle a witness across a city that never sleeps."},
    "quiet_harbor": {"title": "Quiet Harbor", "genre": "Indie Drama", "box_office_m": 22, "critics": 95,
                     "term": 3, "ask_m": 1.5, "logline": "A lighthouse keeper's daughter decides whether to leave home."},
}


def _unit(*parts) -> float:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def films_offered(year: int) -> list[str]:
    """Films up for license in this level year (1-based), in a fixed order."""
    keys = list(FILM_CATALOG)
    start = ((year - 1) * OFFERS_PER_YEAR) % len(keys)
    return [keys[(start + i) % len(keys)] for i in range(OFFERS_PER_YEAR)]


def true_value_m(film_key: str, team: str = "") -> float:
    """Annual subscription revenue the film actually earns (hidden until signed)."""
    f = FILM_CATALOG[film_key]
    quality = 0.55 + f["critics"] / 100 * 0.6 + min(f["box_office_m"], 600) / 600 * 0.25
    noise = 0.8 + 0.4 * _unit("filmvalue", team, film_key)
    return round(f["ask_m"] * quality * noise, 2)


def rival_bid_m(film_key: str, team: str = "") -> tuple[float, str]:
    f = FILM_CATALOG[film_key]
    bid = f["ask_m"] * (0.8 + 0.55 * _unit("filmrival", team, film_key))
    rival = ["Netflix", "Max", "Prime Video", "Paramount+"][int(_unit("filmrivalname", team, film_key) * 4)]
    return round(bid, 2), rival


def resolve_film_bid(film_key: str, bid_m: float, team: str = "") -> dict:
    rb, rival = rival_bid_m(film_key, team)
    won = bid_m > 0 and bid_m >= rb
    return {"film": film_key, "bid_m": round(bid_m, 2), "rival": rival, "rival_bid_m": rb, "won": won}


# ── Session state (JSON-safe) ───────────────────────────────────────────────
#   film_licenses  [{"film", "start", "end", "annual_cost_m"}]  (level years)
#   film_bid_log   {"<year>": {film_key: result}}
STATE_KEYS = ("film_licenses", "film_bid_log")


def ensure_state(ss) -> None:
    if not isinstance(ss.get("film_licenses"), list):
        ss["film_licenses"] = []
    if not isinstance(ss.get("film_bid_log"), dict):
        ss["film_bid_log"] = {}


def held(ss, year: int) -> list[dict]:
    ensure_state(ss)
    return [l for l in ss.film_licenses if l["start"] <= year <= l["end"]]


def year_film_pnl(ss, year: int) -> dict:
    rows = [{"title": FILM_CATALOG[l["film"]]["title"], "cost_m": l["annual_cost_m"],
             "revenue_m": true_value_m(l["film"], ss.get("team_name", ""))} for l in held(ss, year)]
    cost = round(sum(r["cost_m"] for r in rows), 2)
    rev = round(sum(r["revenue_m"] for r in rows), 2)
    return {"film_rev": rev, "film_cost": cost, "film_rows": rows,
            "retention_credit_m": round(cost * FILM_RETENTION_CREDIT, 2)}
