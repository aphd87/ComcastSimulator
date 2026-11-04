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


def test_peacock_earns_subscriptions_not_cable_fees_and_baseline_misses_target():
    """2026-11-03: a streaming-only slate earns subscription revenue tied to
    its originals; renewing everything at default marketing misses 10%."""
    import app_pages.simulation as sim
    from utils.models import distribution_revenue, platform_revenue, platform_revenue_label, subscription_revenue
    ss = _ss()
    pk = level_shows(ss, "peacock")
    assert platform_revenue_label(pk) == "Subscriptions"
    assert platform_revenue(1, pk) == subscription_revenue(1, pk) != distribution_revenue(1)
    assert platform_revenue(2, pk) > platform_revenue(1, pk)            # subscriber base grows
    assert platform_revenue(1, pk[1:]) < platform_revenue(1, pk)         # cancelling loses subscribers
    rev = ocf = 0.0
    for y in range(1, 5):
        p = sim._preview_pnl(pk, y, 5.0, set(), set())
        rev += p["rev"]; ocf += p["ocf"]
    assert ocf / rev * 100 < 10.0
    assert platform_revenue_label(level_shows(ss, "bravo")) == "Distribution"
