"""Per-level add-on state (Bravo brand deals/casting, Peacock film licenses):
one place for the reset and snapshot key list, so Advance / Restart /
Switch Network / Follow Along all handle every add-on the same way."""
from utils import bravo_deals, film_licensing

STATE_KEYS = bravo_deals.STATE_KEYS + film_licensing.STATE_KEYS


def reset_state(ss) -> None:
    bravo_deals.reset_state(ss)
    ss["film_licenses"] = []
    ss["film_bid_log"] = {}
