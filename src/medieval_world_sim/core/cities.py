"""Static city definitions and mutable world-city state."""
from dataclasses import dataclass, field
from ..catalog import CitySpec

@dataclass
class CityState:
    id: str
    definition: CitySpec
    deposits: dict[str, int] = field(default_factory=dict)
    security_level: int = 0

    @classmethod
    def create(cls, city_id: str, definition: CitySpec) -> "CityState":
        return cls(city_id, definition, {resource: 8 for resource in definition.deposits})

    @property
    def name(self) -> str:
        return self.definition.name
