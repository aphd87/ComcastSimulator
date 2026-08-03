"""
Tests for utils/game_state.py's instructor-tailorable YEARS_PER_LEVEL
(2026-08-03) -- read once at import from this deployment's own Streamlit
secrets, defaulting to 4, clamped to [2, 8]. See README.md's "Instructor
settings" section for the deployment-facing instructions.
"""
import utils.game_state as gs


class _FakeSecrets:
    def __init__(self, value=None):
        self._value = value

    def get(self, key, default=None):
        if self._value is None:
            return default
        return self._value


def _with_secret(monkeypatch, value):
    monkeypatch.setattr(gs.st, "secrets", _FakeSecrets(value))


def test_default_is_four_when_unset(monkeypatch):
    _with_secret(monkeypatch, None)
    assert gs._read_years_per_level() == 4


def test_honors_a_configured_value(monkeypatch):
    _with_secret(monkeypatch, 6)
    assert gs._read_years_per_level() == 6


def test_clamps_out_of_range_high_value(monkeypatch):
    _with_secret(monkeypatch, 40)
    assert gs._read_years_per_level() == 8


def test_clamps_out_of_range_low_value(monkeypatch):
    _with_secret(monkeypatch, 0)
    assert gs._read_years_per_level() == 2


def test_falls_back_to_default_when_secrets_raise(monkeypatch):
    # Mirrors a deployment with no secrets.toml at all -- confirmed
    # directly against this Streamlit install that st.secrets.get() raises
    # StreamlitSecretNotFoundError in that case rather than returning the
    # default, so the try/except in _read_years_per_level() is load-bearing.
    class _RaisingSecrets:
        def get(self, key, default=None):
            raise RuntimeError("no secrets.toml found")
    monkeypatch.setattr(gs.st, "secrets", _RaisingSecrets())
    assert gs._read_years_per_level() == 4


def test_level_start_years_stay_clean_handoffs_for_any_level_length():
    # Independent of whatever YEARS_PER_LEVEL this test run actually
    # resolved to -- confirms the *relationship* between the three start
    # years always holds: each starts exactly YEARS_PER_LEVEL after the
    # last, so no network's era overlaps the previous one's.
    ypl = gs.YEARS_PER_LEVEL
    assert gs.LEVEL_START_YEAR["oxygen"] == 2012
    assert gs.LEVEL_START_YEAR["bravo"] == 2012 + ypl
    assert gs.LEVEL_START_YEAR["peacock"] == 2012 + ypl * 2
