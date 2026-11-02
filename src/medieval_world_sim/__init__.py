"""Medieval World Sim: five-city world engine and optional baseline experiment."""
from .core.engine import WorldEngine
from .core.entities import Actor, Company, Wage
from .simulation import World  # Legacy compatibility only

__all__ = ["WorldEngine", "Actor", "Company", "Wage", "World"]
