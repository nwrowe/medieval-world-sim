"""Static city definitions and mutable world-city state."""
from dataclasses import dataclass, field
from ..catalog import CitySpec

@dataclass
class CityState:
    id: str
    definition: CitySpec
    deposits: dict[str, int] = field(default_factory=dict)
    security_level: int = 0
    population: int = 120
    household_gold: int = 600
    # Aggregated households are not simulated as individual NPCs.
    # Funds exist in the opening ledger; sales transfer rather than mint gold.

    @classmethod
    def create(cls, city_id: str, definition: CitySpec) -> "CityState":
        capital = city_id == "crownreach"
        return cls(city_id, definition, {resource: 8 for resource in definition.deposits},
                   population=500 if capital else 120,
                   household_gold=3600 if capital else 600)

    @property
    def gold(self) -> int:
        """Account adapter so city buyers use the same audited transfer primitive."""
        return self.household_gold

    @gold.setter
    def gold(self, amount: int) -> None:
        self.household_gold = amount

    @property
    def name(self) -> str:
        return self.definition.name
