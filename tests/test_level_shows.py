"""Level rosters (2026-11-03): Bravo's level is Bravo's own slate only, no
Oxygen True Crime shows; Peacock still runs the full portfolio."""
import copy
from types import SimpleNamespace

from utils.data import OXYGEN_SLATE, BRAVO_SLATE, PEACOCK_SLATE
from utils.game_state import level_shows


class _SS(SimpleNamespace):
    def get(self, k, d=None):
        return getattr(self, k, d)


def _ss():
    return _SS(oxygen_shows=copy.deepcopy(OXYGEN_SLATE), bravo_shows=copy.deepcopy(BRAVO_SLATE),
               peacock_shows=copy.deepcopy(PEACOCK_SLATE))


def test_bravo_level_is_bravo_only_with_no_true_crime():
    shows = level_shows(_ss(), "bravo")
    assert len(shows) == len(BRAVO_SLATE)
    assert {s.network for s in shows} == {"Bravo"}
    assert not any(s.genre == "True Crime" for s in shows)


def test_oxygen_and_peacock_rosters():
    ss = _ss()
    assert {s.network for s in level_shows(ss, "oxygen")} == {"Oxygen"}
    assert {s.network for s in level_shows(ss, "peacock")} == {"Peacock"}


def test_level_shows_shares_show_objects_with_session_state():
    ss = _ss()
    level_shows(ss, "bravo")[0].air_month = 9
    assert ss.bravo_shows[0].air_month == 9
