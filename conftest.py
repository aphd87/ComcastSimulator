"""
Pins PYTHONHASHSEED for reproducible test runs.

Several functions in utils/movie_models.py and utils/sports_models.py seed
their RNG off Python's built-in hash(team_name)/hash(league_key). String
hashing is per-process-randomized by default (PYTHONHASHSEED, a security
hardening measure since Python 3.3) -- perfectly deterministic *within* one
process run, but the exact outcome of those draws (and any statistical test
assertion built around a specific literal string like "AppTest Team") can
legitimately differ between separate `python`/`pytest` invocations.

This surfaced three separate times in one 2026-08-04 session as confusing,
unrelated-looking test failures before the shared root cause was diagnosed:
tests/test_sports_models.py::TestCycles::test_most_years_nothing_is_up_for_bid,
tests/test_models.py::TestProductionRiskEvent::test_independent_of_rating_variance_seed,
and early drafts of tests/test_movies_page.py's Talent Partnership tests
(fixed properly there by seeding session_state directly / monkeypatching
instead of hardcoding an expected outcome for "AppTest Team"). See
DESIGN_NOTES.md's 2026-08-04 entries for the full story.

Re-runs pytest once, as a genuine child process, with a fixed
PYTHONHASHSEED if one isn't already set, so every run -- local or CI --
sees the same hash-seeded outcomes every time. Uses subprocess.run rather
than os.execv deliberately: execv (process-image replacement) was tried
first and silently swallowed the child's stdout/stderr in this sandboxed
Windows dev environment (confirmed via a minimal repro -- the exec'd
process's output never reached the parent's pipe, with no error raised),
which would have made every real test run look like a silent hang or empty
output. subprocess.run spawns a true child process and correctly passes
output through instead.
"""
import os
import subprocess
import sys

if os.environ.get("PYTHONHASHSEED") is None:
    # Only acts when unset -- an explicit PYTHONHASHSEED (any value,
    # including one a developer set on purpose to probe seed-dependence)
    # is always respected, never silently overridden.
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    result = subprocess.run([sys.executable, "-m", "pytest"] + sys.argv[1:], env=env)
    sys.exit(result.returncode)
