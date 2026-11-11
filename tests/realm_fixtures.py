"""Dynamic geographic town fixtures replacing obsolete five-city test IDs.

The names IRONVALE / EMBERFALL / GREENHOLLOW / GOLDMEADOW denote test roles
only; their values are real, distinct generated town IDs selected by actual
resource potential. They are not runtime aliases or extra fictitious cities.
"""
from medieval_world_sim.catalog import CAPITAL, GEOGRAPHY

_available = [s for s in GEOGRAPHY.settlements if s.id != CAPITAL]


def _town(resource: str) -> str:
    global _available
    if not _available:
        raise AssertionError("Not enough geographical settlements for test roles")
    chosen = max(_available,
                 key=lambda s: (s.production.get(resource, 0),
                                s.population, s.id))
    _available.remove(chosen)
    return chosen.id


IRONVALE = _town("iron_ore")
EMBERFALL = _town("coal")
GREENHOLLOW = _town("timber")
GOLDMEADOW = _town("grain")
