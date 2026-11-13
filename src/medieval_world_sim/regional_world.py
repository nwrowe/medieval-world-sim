"""Compatibility facade: authoritative generated-realm WorldEngine.

New code should import WorldEngine from core.engine and domain entities from core.entities.
"""
from .core.engine import WorldEngine
from .core.entities import Actor, Company, Offer, Wage, WorldEvent
from .errors import ActionError
from .systems.resources import HARVEST_LIMIT
from .systems.travel import HOUR, DEPOSIT_CAP, TRAVEL_CARGO_LIMIT
from .core.engine import CARRY_LIMIT

RegionalWorld = WorldEngine
