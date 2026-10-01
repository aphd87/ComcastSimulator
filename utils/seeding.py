"""Stable random seeds (2026-10-01).

Every game draw used to seed off Python's built-in hash(team_name), which is
randomized per process (PYTHONHASHSEED). A server restart therefore re-rolled
every team's future draws mid-class. stable_seed() gives the same value for
the same input on every run, machine, and restart.
"""
import hashlib


def stable_seed(value) -> int:
    """Deterministic non-negative 31-bit integer for any value (drop-in for abs(hash(x)))."""
    digest = hashlib.sha256(str(value).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % (2 ** 31)
