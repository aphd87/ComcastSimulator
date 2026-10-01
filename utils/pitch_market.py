"""
Competitor interest in the TV pitch marketplace (2026-10-01).

Some pitches in utils.models.TV_PITCH_CATALOG have a rival network circling
them. That creates a real timing decision for a slot-limited team:

- Acquire now and pay a competitive premium on the acquisition fee, or
- Pass this year and risk the rival signing it before next year, in which
  case it leaves the marketplace for good.

TV-side parallel to Movies' Scouted Concepts poaching (utils/movie_models.py).
Rival networks are fictional, same posture as RIVAL_STUDIOS there.

Draws use a stable hash (hashlib), not Python's per-process randomized
hash(), so a team's outcome is the same across app restarts, Redo, and
Restart. Each (network, year) transition is drawn once per team.
"""
from __future__ import annotations

import hashlib

RIVAL_FEE_PREMIUM  = 0.25   # +25% on the acquisition fee while a rival is bidding
RIVAL_POACH_CHANCE = 0.50   # chance a passed-on contested pitch is signed by the rival each new year

# Pitch key -> the rival network circling it.
PITCH_RIVAL_INTEREST = {
    "the_estate":            "Northstar TV",
    "second_chance_kitchen": "Lumen Channel",
    "peak_condition":        "Crestline Network",
}


def rival_for(pitch_key: str) -> str | None:
    return PITCH_RIVAL_INTEREST.get(pitch_key)


def contested_fee(base_fee_m: float, pitch_key: str) -> float:
    """Acquisition fee including the competitive premium, if a rival is circling."""
    return base_fee_m * (1 + RIVAL_FEE_PREMIUM) if rival_for(pitch_key) else base_fee_m


def _unit(*parts) -> float:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def rival_signs_it(team_key: str, pitch_key: str, network: str, year: int) -> bool:
    """Whether the rival signs this passed-on pitch at the start of `year`."""
    if not rival_for(pitch_key):
        return False
    return _unit("pitch-rival", team_key, pitch_key, network, year) < RIVAL_POACH_CHANCE


def resolve_rival_signings(ss, team_key: str, network: str, year: int, available: list[str]) -> dict:
    """Run this year's rival draws once (year 2+ of a level). Records losses
    in ss.tv_pitches_lost {pitch_key: {"rival", "network", "year"}} and
    returns the ones newly lost this call."""
    if "tv_pitches_lost" not in ss:
        ss.tv_pitches_lost = {}
    if "tv_pitch_rival_checks" not in ss:
        ss.tv_pitch_rival_checks = set()
    check = (network, year)
    if year <= 1 or check in ss.tv_pitch_rival_checks:
        return {}
    ss.tv_pitch_rival_checks.add(check)
    newly = {}
    for key in available:
        if key not in ss.tv_pitches_lost and rival_signs_it(team_key, key, network, year):
            newly[key] = {"rival": rival_for(key), "network": network, "year": year}
    ss.tv_pitches_lost.update(newly)
    return newly
