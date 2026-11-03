"""
Bravo brand partnerships and casting unknowns (2026-11-03, per user).

Brand partnerships ("which brands to partner to increase rev by thinking
through product placement... maybe some of it works, and it defrays cost of
show, and maybe it doesn't, and it increases costs"):
  A team attaches a brand to up to MAX_BRAND_DEALS_PER_YEAR of this year's
  active shows. Each brand pays a share of the show's season cost if the
  integration lands, or forces a make-good (extra integrations / free spots)
  that ADDS cost if the audience rejects it. The chance it lands is the
  brand's fit with the show's genre/audience. Higher-paying brands fit
  Bravo's affluent, female-skewing audience worse: that's the trade-off.

Casting unknowns ("bidding on potential unknown actors for reality series to
cast in new shows you purchase... bio, hobbies, emotions, weirdness factor"):
  For new Reality/Competition shows added this level, a team bids against a
  rival network for fictional unknown cast members. A cast member's
  emotional type sets the expected rating lift; weirdness widens the range
  (a weird cast member can make a show or sink it). A volatile + warm mix
  adds a chemistry bonus. Losing a bid sends that person to the rival.

All draws use a stable hash, so outcomes are the same across restarts,
Redo and Restart. All brands and people are fictional.
"""
from __future__ import annotations

import hashlib

MAX_BRAND_DEALS_PER_YEAR = 3
MAX_CAST_PER_SHOW = 3
CASTABLE_GENRES = {"Reality", "Competition"}


def _unit(*parts) -> float:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


# ── Brand partnerships ──────────────────────────────────────────────────────
# pay_pct: share of the show's season cost the sponsor covers if it lands.
# makegood_pct: share of season cost ADDED if the integration flops.
# fit: chance the integration lands, by show genre (default_fit otherwise).
BRAND_CATALOG = {
    "maison_verre": {
        "name": "Maison Verre Rosé", "category": "Wine & spirits",
        "pay_pct": 0.18, "makegood_pct": 0.10, "default_fit": 0.45,
        "fit": {"Reality": 0.80, "Talk": 0.75, "Competition": 0.55},
        "pitch": "Rosé in every group dinner scene. Fits a wine-and-gossip crowd.",
    },
    "velour_beauty": {
        "name": "Velour Beauty", "category": "Cosmetics",
        "pay_pct": 0.16, "makegood_pct": 0.09, "default_fit": 0.45,
        "fit": {"Reality": 0.80, "Talk": 0.70, "Competition": 0.45},
        "pitch": "Glam-room product placement and a cast-member makeup line.",
    },
    "copperleaf": {
        "name": "Copperleaf Cookware", "category": "Kitchen",
        "pay_pct": 0.15, "makegood_pct": 0.08, "default_fit": 0.35,
        "fit": {"Competition": 0.85, "Reality": 0.45, "Talk": 0.50},
        "pitch": "Pans and knives on screen in every challenge. Great on a cooking show, odd elsewhere.",
    },
    "atlas_resorts": {
        "name": "Atlas Luxury Resorts", "category": "Travel",
        "pay_pct": 0.22, "makegood_pct": 0.12, "default_fit": 0.45,
        "fit": {"Reality": 0.70, "Competition": 0.50, "Talk": 0.45},
        "pitch": "A cast trip episode filmed at the resort. Pays well, needs the story to go there.",
    },
    "hearthstone": {
        "name": "Hearthstone Home", "category": "Home furnishings",
        "pay_pct": 0.12, "makegood_pct": 0.06, "default_fit": 0.55,
        "fit": {"Reality": 0.65, "Talk": 0.60, "Scripted": 0.55},
        "pitch": "Furniture and decor in cast homes. Low pay, low risk.",
    },
    "titanfuel": {
        "name": "TitanFuel Energy", "category": "Energy drinks",
        "pay_pct": 0.30, "makegood_pct": 0.18, "default_fit": 0.30,
        "fit": {"Competition": 0.40, "Reality": 0.25, "Talk": 0.30},
        "pitch": "The biggest check on the table, aimed at young men. Bravo's audience may not buy it.",
    },
    "ironclad_trucks": {
        "name": "Ironclad Trucks", "category": "Automotive",
        "pay_pct": 0.28, "makegood_pct": 0.16, "default_fit": 0.25,
        "fit": {"Competition": 0.35, "Reality": 0.20},
        "pitch": "Pickup trucks in the opening credits. Huge budget, poor match for this audience.",
    },
}


def brand_fit(brand_key: str, genre: str) -> float:
    b = BRAND_CATALOG[brand_key]
    return b["fit"].get(genre, b["default_fit"])


def brand_terms(brand_key: str, season_cost_m: float, genre: str) -> dict:
    """What a deal is worth before the outcome is known."""
    b = BRAND_CATALOG[brand_key]
    p = brand_fit(brand_key, genre)
    gain, loss = b["pay_pct"] * season_cost_m, b["makegood_pct"] * season_cost_m
    return {"fit": p, "gain_m": gain, "loss_m": loss, "expected_m": p * gain - (1 - p) * loss}


def brand_outcome(team: str, year: int, show_id: int, brand_key: str,
                  season_cost_m: float, genre: str) -> dict:
    """Resolve one deal. Positive net_m lowers this year's cost (sponsor
    money), negative net_m is a make-good cost."""
    t = brand_terms(brand_key, season_cost_m, genre)
    landed = _unit("brand", team, year, show_id, brand_key) < t["fit"]
    return {"brand": brand_key, "landed": landed,
            "net_m": round(t["gain_m"] if landed else -t["loss_m"], 2), "fit": t["fit"]}


# ── Casting unknowns ────────────────────────────────────────────────────────
# Expected rating lift by emotional type; weirdness (1-10) widens the range.
EMOTION_LIFT = {"Volatile": 0.06, "Scheming": 0.05, "Bubbly": 0.03, "Warm": 0.02, "Guarded": 0.0}
WEIRDNESS_SPREAD = 0.015          # +/- this much lift per weirdness point
CHEMISTRY_BONUS = 0.03            # volatile/scheming + warm/bubbly on the same show
RIVAL_BID_RANGE = (0.85, 1.50)    # rival's bid as a multiple of the asking fee
RIVAL_CASTING_NETWORKS = ["Lumen Channel", "Northstar TV", "Crestline Network"]

CAST_POOL = {
    "dana_m": {"name": "Dana Mercer", "age": 34, "city": "Miami", "job": "Yacht broker",
               "bio": "Sold a boat to a rapper, then sued him. Won.",
               "hobbies": "Deep-sea fishing, tarot, reality-TV recaps", "emotion": "Volatile",
               "weirdness": 6, "ask_m": 0.45},
    "priya_s": {"name": "Priya Sethi", "age": 29, "city": "Houston", "job": "Pastry chef",
                "bio": "Opened a bakery at 22; it has a two-hour line and one terrible Yelp review she can recite.",
                "hobbies": "Ballroom dancing, true-crime podcasts", "emotion": "Warm",
                "weirdness": 3, "ask_m": 0.25},
    "brock_l": {"name": "Brock Lindqvist", "age": 41, "city": "Scottsdale", "job": "Golf-course developer",
                "bio": "Twice divorced, once engaged on a jumbotron. Says he's 'done with drama.'",
                "hobbies": "Cigars, vintage watches, rescue greyhounds", "emotion": "Scheming",
                "weirdness": 5, "ask_m": 0.40},
    "tasha_w": {"name": "Tasha Wells", "age": 37, "city": "Atlanta", "job": "Event planner",
                "bio": "Planned three celebrity weddings and knows which ones won't last.",
                "hobbies": "Spin class, karaoke, collecting hot sauce", "emotion": "Bubbly",
                "weirdness": 4, "ask_m": 0.30},
    "milo_r": {"name": "Milo Reyes", "age": 26, "city": "Los Angeles", "job": "Influencer / DJ",
               "bio": "1.2M followers, zero close friends. Wants to 'show the real me.'",
               "hobbies": "Crystals, sneaker reselling, cold plunges", "emotion": "Volatile",
               "weirdness": 9, "ask_m": 0.35},
    "evelyn_c": {"name": "Evelyn Cho", "age": 52, "city": "New York", "job": "Divorce attorney",
                 "bio": "Represented half the Upper East Side. Calm, precise, quietly terrifying.",
                 "hobbies": "Opera, competitive bridge", "emotion": "Guarded",
                 "weirdness": 2, "ask_m": 0.50},
    "jolene_b": {"name": "Jolene Banks", "age": 45, "city": "Nashville", "job": "Boutique owner",
                 "bio": "Former pageant queen who still wears the sash to brunch.",
                 "hobbies": "Taxidermy, gospel choir, line dancing", "emotion": "Bubbly",
                 "weirdness": 8, "ask_m": 0.28},
    "marcus_d": {"name": "Marcus Dale", "age": 33, "city": "Chicago", "job": "Sommelier",
                 "bio": "Can name a wine's vintage blindfolded and a friend's lie the same way.",
                 "hobbies": "Boxing, jazz vinyl", "emotion": "Scheming",
                 "weirdness": 3, "ask_m": 0.38},
    "rosa_v": {"name": "Rosa Vidal", "age": 39, "city": "San Diego", "job": "Nurse turned realtor",
               "bio": "Left the ER for real estate and says the patients were nicer.",
               "hobbies": "Surfing, telenovelas, baking for neighbors", "emotion": "Warm",
               "weirdness": 2, "ask_m": 0.22},
    "kip_h": {"name": "Kip Hollister", "age": 30, "city": "Charleston", "job": "Old-money heir",
              "bio": "Has never had a job interview. Is about to have his first one on camera.",
              "hobbies": "Sailing, ghost tours, collecting antique dueling pistols", "emotion": "Volatile",
              "weirdness": 7, "ask_m": 0.42},
    "nadia_k": {"name": "Nadia Kova", "age": 31, "city": "Las Vegas", "job": "Cocktail-bar owner",
                "bio": "Ran away to join a circus at 17. Came back with a business plan.",
                "hobbies": "Aerial silks, poker", "emotion": "Guarded",
                "weirdness": 6, "ask_m": 0.26},
    "glen_t": {"name": "Glen Tibbs", "age": 58, "city": "Palm Springs", "job": "Retired soap-opera actor",
               "bio": "Played the same evil twin for 19 years. Still signs autographs as the twin.",
               "hobbies": "Bonsai, mahjong, writing his memoir", "emotion": "Bubbly",
               "weirdness": 10, "ask_m": 0.20},
}


def rival_cast_bid(team: str, cast_key: str) -> tuple[float, str]:
    """The rival's sealed bid for this cast member, and who it is."""
    ask = CAST_POOL[cast_key]["ask_m"]
    lo, hi = RIVAL_BID_RANGE
    bid = ask * (lo + (hi - lo) * _unit("castbid", team, cast_key))
    rival = RIVAL_CASTING_NETWORKS[int(_unit("castrival", team, cast_key) * len(RIVAL_CASTING_NETWORKS))]
    return round(bid, 3), rival


def cast_lift_range(cast_key: str) -> tuple[float, float]:
    c = CAST_POOL[cast_key]
    mid, spread = EMOTION_LIFT[c["emotion"]], c["weirdness"] * WEIRDNESS_SPREAD
    return mid - spread, mid + spread


def cast_multiplier(team: str, show_id: int, cast_keys: list[str]) -> float:
    """Rating multiplier a show's signed cast gives it (fixed once drawn, so
    the cast's effect is the same every year they're on the show)."""
    if not cast_keys:
        return 1.0
    lift = 0.0
    for k in cast_keys:
        lo, hi = cast_lift_range(k)
        lift += lo + (hi - lo) * _unit("castlift", team, show_id, k)
    emotions = {CAST_POOL[k]["emotion"] for k in cast_keys}
    if emotions & {"Volatile", "Scheming"} and emotions & {"Warm", "Bubbly"}:
        lift += CHEMISTRY_BONUS
    return max(0.7, 1.0 + lift)


# ── Session state (JSON-safe: string keys) ──────────────────────────────────
#   brand_deals   {"<year>": {"<show_id>": brand_key}}
#   cast_signings {"<show_id>": [cast_key, ...]}
#   cast_fees     {"<year>": $M paid that year}
#   cast_lost     {cast_key: rival network}
STATE_KEYS = ("brand_deals", "cast_signings", "cast_fees", "cast_lost")


def ensure_state(ss) -> None:
    for k in STATE_KEYS:
        if not isinstance(ss.get(k), dict):
            ss[k] = {}


def reset_state(ss) -> None:
    """Fresh level: every deal and signing belongs to the level it was made in."""
    for k in STATE_KEYS:
        ss[k] = {}


def year_extras(ss, shows, year: int, active_ids: set) -> dict:
    """This year's brand-deal outcomes and casting fees for the P&L.
    Brand money that lands is booked as revenue; a make-good is a cost."""
    ensure_state(ss)
    team = ss.get("team_name", "")
    by_id = {s.id: s for s in shows}
    rows, brand_rev, brand_cost = [], 0.0, 0.0
    for sid, bkey in ss.brand_deals.get(str(year), {}).items():
        s = by_id.get(int(sid))
        if s is None or s.id not in active_ids or bkey not in BRAND_CATALOG:
            continue
        o = brand_outcome(team, year, s.id, bkey, s.annual_amort_expense(year), s.genre)
        if o["net_m"] >= 0:
            brand_rev += o["net_m"]
        else:
            brand_cost += -o["net_m"]
        rows.append({"show": s.name, "brand": BRAND_CATALOG[bkey]["name"], **o})
    return {"brand_rev": round(brand_rev, 2), "brand_cost": round(brand_cost, 2),
            "brand_rows": rows, "cast_cost": round(float(ss.cast_fees.get(str(year), 0.0)), 2)}
