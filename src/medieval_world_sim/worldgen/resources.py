"""Explain the natural-resource economy of every geography-generated town.

This is a *potential* resource/trade survey, never actual market inventories.
Source ratings use precisely the same five-tile dry-land catchment and the
same candidate extraction rates as settlement generation. Future industry
logic can consume stable raw resource and recipe IDs without inventing stock.
"""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush

from ..content.catalog import RAW_RESOURCES, RECIPES
from .society import _nearby

PRIMARY_COUNT = 2

RESOURCE_LABELS = {
    "iron_ore": "Iron ore", "coal": "Coal", "stone": "Stone",
    "timber": "Timber", "herbs": "Herbs", "grain": "Grain",
    "hides": "Hides", "vegetables": "Vegetables", "meat": "Meat",
}
# These observations are *conditional on actual supporting map tiles*.
EXPLANATIONS = {
    "iron_ore": ("mountain hard-rock outcrops", "igneous", "metamorphic"),
    "coal": ("coal-bearing sedimentary basins", "coal_basin"),
    "stone": ("quarryable rock and exposed hillsides", "limestone",
              "igneous", "metamorphic"),
    "timber": ("forested woodland", "forest", "taiga", "rainforest"),
    "herbs": ("wild herb habitat", "forest", "wetland", "grassland"),
    "grain": ("fertile cropping ground", "grassland", "forest"),
    "hides": ("pasture and grazing land", "grassland", "steppe",
              "forest", "taiga"),
    "vegetables": ("productive cultivated soils", "grassland",
                   "forest", "wetland"),
    "meat": ("pasture and livestock habitat", "grassland", "steppe",
             "forest", "taiga"),
}


@dataclass(frozen=True)
class ResourceAssessment:
    resource: str
    tier: str  # primary, secondary or lacking
    potential: float  # mean map resource potential in the town's five-tile catchment
    estimated_units_per_hour: int  # proposal, never real inventory/surplus
    supporting_hexes: int
    surveyed_hexes: int
    explanation: str


@dataclass(frozen=True)
class IndustryOpportunity:
    recipe: str  # stable existing company recipe ID
    outputs: tuple[str, ...]
    raw_inputs_per_craft: dict[str, int]  # expanded through intermediate recipes
    available_locally: tuple[str, ...]
    imports_needed: tuple[str, ...]
    classification: str  # local_inputs, import_dependent, no_local_inputs


@dataclass(frozen=True)
class SupplierCandidate:
    resource: str
    source_id: str
    source_name: str
    estimated_source_units_per_hour: int
    route_minutes: int
    # Geography-derived *opportunity*, not a guaranteed market listing.


@dataclass(frozen=True)
class TownResourceProfile:
    settlement_id: str
    settlement_name: str
    primary: tuple[ResourceAssessment, ...]
    secondary: tuple[ResourceAssessment, ...]
    lacking: tuple[ResourceAssessment, ...]
    industries: tuple[IndustryOpportunity, ...]
    supplier_candidates: tuple[SupplierCandidate, ...]
    catchment_radius_hexes: int = 5


def _reasons(resource: str, catchment, supporters, potential: float, producing: bool):
    label = EXPLANATIONS[resource][0]
    supported = len(supporters)
    count = len(catchment)
    if not producing:
        if supported:
            return (f"Only {supported} of {count} surveyed dry-land hexes show "
                    f"{label}; catchment-wide mean potential ({potential:.1f}/100) "
                    "is below the local production threshold. Import is likely "
                    "needed for industries using this material.")
        return (f"0 of {count} surveyed dry-land hexes within five tiles support "
                f"{label}. This is a local production shortage, not proof "
                "the resource is absent everywhere.")
    if resource in ("iron_ore", "coal", "stone"):
        geology = {}
        for tile in supporters:
            geology[tile.geology] = geology.get(tile.geology, 0) + 1
        dominant = sorted(geology.items(), key=lambda p: (-p[1], p[0]))[0][0]
        evidence = f"predominantly {dominant.replace('_', ' ')} geology"
    elif resource in ("grain", "vegetables"):
        fertility = sum(tile.soil for tile in supporters) / supported
        evidence = f"productive soils averaging {fertility:.0f}/100 fertility"
    else:
        biomes = {}
        for tile in supporters:
            biomes[tile.biome] = biomes.get(tile.biome, 0) + 1
        dominant = sorted(biomes.items(), key=lambda p: (-p[1], p[0]))[0][0]
        evidence = f"{dominant.replace('_', ' ')} habitat"
    return (f"{supported} of {count} nearby dry-land hexes support {label}, "
            f"with {evidence}; mean resource potential is "
            f"{potential:.1f}/100. Estimated extraction is a production "
            "rate, not automatically an exportable surplus.")


def _raw_requirements(recipe_name: str, stack: tuple[str, ...] = ()) -> dict[str, int]:
    """Expand existing crafting recipes into their raw-material dependency DAG."""
    if recipe_name in stack:
        raise ValueError(f"Recipe dependency cycle at {recipe_name}")
    recipe = RECIPES[recipe_name]
    requirements: dict[str, int] = {}
    outputs = {
        item: key for key, spec in RECIPES.items()
        for item in spec.outputs
    }
    for good, amount in recipe.inputs.items():
        if good in RAW_RESOURCES:
            requirements[good] = requirements.get(good, 0) + amount
        elif good in outputs:
            producer = RECIPES[outputs[good]]
            yield_per_batch = producer.outputs[good]
            if yield_per_batch <= 0:
                raise ValueError(f"Invalid recipe output for {good}")
            batches = (amount + yield_per_batch - 1) // yield_per_batch
            nested = _raw_requirements(outputs[good], stack + (recipe_name,))
            for material, qty in nested.items():
                requirements[material] = requirements.get(material, 0) + batches * qty
        else:
            raise ValueError(f"Unknown ingredient {good} in recipe {recipe_name}")
    return dict(sorted(requirements.items()))


def _road_distances(world, origin_id: str) -> dict[str, int]:
    graph: dict[str, list[tuple[str, int]]] = {}
    for road in world.roads:
        graph.setdefault(road.a, []).append((road.b, road.travel_minutes))
        graph.setdefault(road.b, []).append((road.a, road.travel_minutes))
    best = {origin_id: 0}
    queue = [(0, origin_id)]
    while queue:
        distance, node = heappop(queue)
        if distance != best[node]:
            continue
        for neighbor, cost in graph.get(node, ()):
            next_distance = distance + cost
            if next_distance < best.get(neighbor, float("inf")):
                best[neighbor] = next_distance
                heappush(queue, (next_distance, neighbor))
    return best


def generate_resource_profiles(world) -> tuple[TownResourceProfile, ...]:
    """Deterministic resource assessments, industry dependencies and trade leads."""
    producers = tuple(world.settlements)
    rate_by_id = {s.id: s.production for s in producers}
    result = []
    for settlement in producers:
        catchment = tuple(_nearby(world.tiles, world.width, world.height,
                                  settlement.x, settlement.y, 5))
        if not catchment:
            raise ValueError(f"No land resource catchment for {settlement.id}")
        local = {good for good in RAW_RESOURCES if settlement.production.get(good, 0) > 0}
        # A stronger production *rate* matters first; average potential breaks
        # ties. Every raw resource belongs to exactly one category.
        evidence = {}
        for good in RAW_RESOURCES:
            supporting = tuple(t for t in catchment if t.resources.get(good, 0) > 0)
            potential = sum(t.resources.get(good, 0) for t in catchment) / len(catchment)
            evidence[good] = (supporting, potential)
        ranked = sorted(local, key=lambda good:
                        (-settlement.production[good], -evidence[good][1], good))
        primary = set(ranked[:PRIMARY_COUNT])
        secondary = local - primary

        def assess(good):
            supporters, potential = evidence[good]
            tier = ("primary" if good in primary else "secondary" if good in secondary
                    else "lacking")
            return ResourceAssessment(
                good, tier, round(potential, 2),
                settlement.production.get(good, 0), len(supporters),
                len(catchment),
                _reasons(good, catchment, supporters, potential, good in local))

        primary_records = tuple(assess(good) for good in ranked if good in primary)
        secondary_records = tuple(assess(good) for good in ranked if good in secondary)
        lacking_records = tuple(assess(good) for good in RAW_RESOURCES if good not in local)
        industries = []
        # Include every existing industry, even if no inputs are local; this
        # allows a future company to work solely with imported materials.
        for recipe_name, recipe in sorted(RECIPES.items()):
            ingredients = _raw_requirements(recipe_name)
            locally_available = tuple(g for g in ingredients if g in local)
            imports = tuple(g for g in ingredients if g not in local)
            classification = ("local_inputs" if not imports else
                              "import_dependent" if locally_available else
                              "no_local_inputs")
            industries.append(IndustryOpportunity(
                recipe_name, tuple(sorted(recipe.outputs)), ingredients,
                locally_available, imports, classification))
        routes = _road_distances(world, settlement.id)
        candidates = []
        for good in RAW_RESOURCES:
            if good in local:
                continue
            options = [source for source in producers if source.id != settlement.id
                       and source.production.get(good, 0) > 0
                       and source.id in routes]
            if not options:
                continue
            best = min(options, key=lambda source:
                       (routes[source.id] / (1 + .2 * source.production[good]),
                        routes[source.id], source.id))
            candidates.append(SupplierCandidate(
                good, best.id, best.name,
                rate_by_id[best.id][good], routes[best.id]))
        result.append(TownResourceProfile(
            settlement.id, settlement.name, primary_records, secondary_records,
            lacking_records, tuple(industries), tuple(candidates)))
    return tuple(result)
