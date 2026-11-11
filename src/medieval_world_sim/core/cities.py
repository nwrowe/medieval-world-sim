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
    # Merchant stock represents tangible, collectively owned city inventory.
    merchant_stock: dict[str, int] = field(default_factory=dict)
    merchant_purchases_today: int = 0  # goods bought FROM players
    merchant_sales_today: int = 0  # goods sold TO players
    # Aggregated households are not simulated as individual NPCs.
    # Funds exist in the opening ledger; sales transfer rather than mint gold.

    @classmethod
    def create(cls, city_id: str, definition: CitySpec) -> "CityState":
        capital = city_id == "crownreach"
        return cls(city_id, definition, {resource: 8 for resource in definition.deposits},
                   population=definition.population,
                   household_gold=max(600, definition.population * 5),
                   merchant_stock={item: 10 for item in definition.deposits})

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
