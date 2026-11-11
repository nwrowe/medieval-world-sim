"""A seeded, geography-led chronicle of settlement, commerce, politics and ruins.

Historical years are Oathmere's fictional calendar, not real-world BCE/CE.
This is an *offline world-design projection*: it neither changes the playable
simulation nor rewrites the geography, existing site IDs or actual game saves.

The evolution is deliberately inspectable: land suitability and water lead
founding; complementarity and existing terrain-aware roads lead trade; access
and trade lead political influence; isolation, climate exposure and contested
routes generate crises and abandoned places.
"""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import ceil

from .hexgrid import hex_distance
from .terrain import _hash


ERAS = (
    (-600, "First Hearths"),
    (-400, "River Settlements"),
    (-200, "Merchant Trails"),
    (0, "Rise of the City Leagues"),
    (200, "The Contested Marches"),
    (400, "The Present Survey"),
)


@dataclass(frozen=True)
class HistoricTown:
    id: str
    name: str
    x: int
    y: int
    population: int
    status: str  # hamlet, village, town, city
    food_security: int  # 0..100 supply resilience proxy, not actual granary stock
    trade_volume: int  # relative annual exchange index, not gold or inventory
    polity_id: str
    founded_year: int


@dataclass(frozen=True)
class HistoricRoad:
    a: str
    b: str
    surface: str  # trail, dirt, cobblestone
    travel_minutes: int
    trade_volume: int


@dataclass(frozen=True)
class HistoricPolity:
    id: str
    name: str
    seat_id: str
    member_ids: tuple[str, ...]
    influence: int


@dataclass(frozen=True)
class ChronicleEvent:
    id: str
    year: int
    kind: str  # founding, road, commerce, alliance, crisis, dispute, abandonment
    title: str
    account: str
    settlement_ids: tuple[str, ...] = ()
    site_id: str | None = None


@dataclass(frozen=True)
class HistoricRuin:
    id: str
    name: str
    x: int
    y: int
    former_use: str
    founded_year: int
    abandoned_year: int
    cause: str
    linked_site_id: str | None = None


@dataclass(frozen=True)
class HistoricalEra:
    id: str
    year: int
    name: str
    towns: tuple[HistoricTown, ...]
    roads: tuple[HistoricRoad, ...]
    polities: tuple[HistoricPolity, ...]
    events: tuple[ChronicleEvent, ...]


@dataclass(frozen=True)
class WorldHistory:
    start_year: int
    present_year: int
    eras: tuple[HistoricalEra, ...]
    ruins: tuple[HistoricRuin, ...]


def _local_factors(world, town):
    """Quantify geographically relevant early settlement conditions."""
    t = world.tile(town.x, town.y)
    neighbors = [q for q in world.tiles
                 if q.elevation_m > 0 and q.waterbody != "lake"
                 and hex_distance((q.x, q.y), (town.x, town.y)) <= 2]
    soil = sum(q.soil for q in neighbors) / max(1, len(neighbors))
    water = 16 if town.water_access == "river" else 12 if town.water_access == "coast" else 2
    food = sum(town.production.get(k, 0) for k in ("grain", "vegetables", "meat"))
    ore = sum(town.production.get(k, 0) for k in ("iron_ore", "coal", "stone"))
    wood = town.production.get("timber", 0)
    terrain = t.natural_difficulty if t.natural_difficulty is not None else 65
    suitability = soil * .58 + water + food * 5.5 + ore * 2.3 + wood * 1.4 - terrain * .18
    capacity = int(110 + soil * 4.7 + food * 44 + ore * 26 + water * 6)
    resilience = max(5, min(100, round(soil * .68 + water + food * 3
                                      - max(0, 700 - t.rainfall_mm) / 28)))
    return suitability, capacity, resilience


def _route_schedule(world, founded):
    """Candidate modern road paths appear only after BOTH endpoints are founded.

    Trails precede earth roads; the existing cobblestone corridors are upgrades
    reserved for late high-trade eras. No historic shipping is asserted yet.
    """
    schedule = {}
    for road in world.roads:
        earliest = max(founded[road.a], founded[road.b])
        # Moving through the same pass is possible before paving the road.
        schedule[(road.a, road.b)] = max(1, earliest)
    return schedule


def _historic_routes(world, era_index, founded, populations):
    network = []
    schedule = _route_schedule(world, founded)
    for road in world.roads:
        ready = schedule[(road.a, road.b)]
        if era_index < ready or not populations[road.a] or not populations[road.b]:
            continue
        elapsed = era_index - ready
        surface = ("cobblestone" if road.surface == "cobblestone" and era_index >= 4
                   else "dirt" if elapsed >= 2 else "trail")
        factor = {"trail": 1.7, "dirt": 1.25, "cobblestone": 1.0}[surface]
        duration = max(1, round(road.travel_minutes * factor))
        town_a = next(s for s in world.settlements if s.id == road.a)
        town_b = next(s for s in world.settlements if s.id == road.b)
        goods = sum(abs(town_a.production.get(k, 0) - town_b.production.get(k, 0))
                    for k in ("grain", "vegetables", "meat", "iron_ore",
                              "coal", "stone", "timber", "herbs"))
        traffic = round(((populations[road.a] + populations[road.b]) / 220)
                        * (1 + goods * .4) * (1.0 if surface == "trail" else 1.3)
                        / (1 + duration / 320))
        network.append(HistoricRoad(road.a, road.b, surface, duration, max(1, traffic)))
    return tuple(network)


def _shortest(network, start):
    graph = {}
    for road in network:
        graph.setdefault(road.a, []).append((road.b, road.travel_minutes))
        graph.setdefault(road.b, []).append((road.a, road.travel_minutes))
    distances = {start: 0}
    heap = [(0, start)]
    while heap:
        cost, name = heappop(heap)
        if cost != distances[name]:
            continue
        for neighbor, distance in graph.get(name, ()):
            candidate = cost + distance
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                heappush(heap, (candidate, neighbor))
    return distances


def _polities(world, era_index, populations, trade, routes):
    active = [s for s in world.settlements if populations[s.id] > 0]
    if not active:
        return (), {}
    strength = {s.id: populations[s.id] + trade.get(s.id, 0) * 11
                for s in active}
    distance = {s.id: _shortest(routes, s.id) for s in active}
    if era_index < 2:
        centers = active  # Independent water-bound hamlets and valley towns.
    else:
        # Dominant markets attract neighboring settlements across accessible
        # passes. A central seat cannot cheaply absorb a distant isolated valley.
        desired = min(4, max(2, ceil(len(active) / 4)))
        contenders = sorted(active, key=lambda s: (-strength[s.id], s.id))
        centers = []
        for town in contenders:
            if len(centers) >= desired:
                break
            if not centers or all(distance[town.id].get(c.id, float("inf")) > 260
                                  for c in centers):
                centers.append(town)
        if era_index >= 4:
            crown = next((s for s in active if s.id == "crownreach"), None)
            if crown is not None and crown not in centers:
                centers.append(crown)
        if not centers:
            centers = contenders[:1]
    allegiance = {}
    members = {s.id: [] for s in centers}
    for town in active:
        choices = [
            (distance[seat.id].get(town.id, float("inf"))
             / (1 + min(1.0, strength[seat.id] / 1500) * .25),
             -strength[seat.id], seat.id)
            for seat in centers
        ]
        nearest = min(choices)
        seat_id = nearest[2] if nearest[0] != float("inf") else town.id
        if seat_id not in members:
            members[seat_id] = []
        allegiance[town.id] = f"polity-{seat_id}"
        members[seat_id].append(town.id)
    polities = []
    for sid in sorted(members):
        head = next(s for s in world.settlements if s.id == sid)
        suffix = ("Hearth" if era_index < 2 else "League" if era_index < 4
                  else "Crown" if sid == "crownreach" else "March")
        polities.append(HistoricPolity(
            f"polity-{sid}", f"{head.name} {suffix}", sid,
            tuple(sorted(members[sid])),
            strength.get(sid, populations.get(sid, 0))))
    return tuple(polities), allegiance


def _historic_ruins(world, founding_years):
    """Give genuine geographic sites a dated history, plus abandoned hamlets."""
    ruins = []
    occupied = [(s.x, s.y) for s in world.settlements]
    eligible = [s for s in world.sites
                if s.kind in ("abandoned_mine", "ruined_watch", "summit_ruin",
                              "sunken_crypt")]
    for site in eligible[:5]:
        if site.kind == "abandoned_mine":
            use = "mining settlement"
            cause = "Steep ore-hauling routes made distant markets uneconomical."
        elif site.kind == "ruined_watch":
            use = "road watchtower"
            cause = "A changing trade frontier left the old guarded crossing unused."
        elif site.kind == "sunken_crypt":
            use = "riverside burial settlement"
            cause = "Flood-prone lowlands forced its inhabitants onto higher ground."
        else:
            use = "mountain observatory"
            cause = "Harsh winters and unreliable passes severed the highland supply line."
        abandoned = 0 if site.kind in ("summit_ruin", "sunken_crypt") else 200
        ruins.append(HistoricRuin(
            f"history-{site.id}", site.name, site.x, site.y, use,
            -400, abandoned, cause, site.id))
        occupied.append((site.x, site.y))

    road_cells = {point for road in world.roads for point in road.path}
    # Expand each road cell by two hex rings *once*, rather than testing
    # every candidate against every road point (important on larger maps).
    road_near = set(road_cells)
    from .hexgrid import neighbors
    frontier = set(road_cells)
    for _ in range(2):
        frontier = {neighbor for x, y in frontier
                    for neighbor in neighbors(x, y, world.width, world.height)}
        road_near.update(frontier)
    candidates = []
    for t in world.tiles:
        if t.waterbody in ("sea", "lake") or t.elevation_m <= 0:
            continue
        nearest = min(hex_distance((t.x, t.y), p) for p in occupied[:len(world.settlements)])
        if not 5 <= nearest <= 16 or t.soil < 36:
            continue
        if (t.x, t.y) not in road_near:
            continue
        # The places that briefly flourished had enough farmland for a hamlet
        # but relatively poor access to the later regional markets.
        difficulty = t.natural_difficulty or 55
        score = (t.soil * .47 + difficulty * .24 + nearest * 1.6
                 + (8 if t.river else 0) - t.rainfall_mm / 160)
        candidates.append((score, t.x, t.y))
    for _, x, y in sorted(candidates, key=lambda v: (-v[0], v[2], v[1])):
        if len([r for r in ruins if r.linked_site_id is None]) >= 3:
            break
        if any(hex_distance((x, y), p) < 5 for p in occupied):
            continue
        near = min(world.settlements, key=lambda s:
                   hex_distance((x, y), (s.x, s.y)))
        t = world.tile(x, y)
        cause = ("High overland travel costs diverted merchants toward the main roads."
                 if (t.natural_difficulty or 0) > 38 else
                 "Trade and population shifted toward the larger river and market towns.")
        ruins.append(HistoricRuin(
            f"lost-hamlet-{len(ruins)+1:02d}",
            f"Old {near.name} Steading", x, y, "agricultural hamlet",
            -400, 200, cause))
        occupied.append((x, y))
    return tuple(ruins)


def generate_history(world):
    """Simulate six inspectable eras from geography and authored settlements.

    Uses only local, deterministic arithmetic and existing road geometry.
    No RNG state, external time, currency, live population or gameplay mutation.
    """
    settlements = tuple(world.settlements)
    factors = {s.id: _local_factors(world, s) for s in settlements}
    # High-water-access, fertile, productive sites attract settlers earlier.
    # Seeded variation breaks close ties but cannot overwhelm geography.
    rank = sorted(settlements, key=lambda s: (
        -(factors[s.id][0] + (7 if s.id == "crownreach" else 0)
          + 3.0 * _hash(world.seed + 71, s.x, s.y)), s.id))
    founding_index = {town.id: min(3, i * 4 // len(rank)) for i, town in enumerate(rank)}
    founded = {sid: ERAS[index][0] for sid, index in founding_index.items()}
    populations = {s.id: 0 for s in settlements}
    ruins = _historic_ruins(world, founded)
    eras = []
    prior_polities = {}
    prior_roads = set()
    for phase, (year, era_name) in enumerate(ERAS):
        events = []

        def event(kind, title, account, ids=(), site_id=None):
            events.append(ChronicleEvent(
                f"historical-event-{phase:02d}-{len(events)+1:03d}",
                year, kind, title, account, tuple(ids), site_id))

        for town in settlements:
            if founding_index[town.id] == phase:
                tile = world.tile(town.x, town.y)
                soil = round(factors[town.id][0])
                populations[town.id] = max(40, int(52 + factors[town.id][1] * .12))
                water = ("sheltered coastline" if town.water_access == "coast" else
                         "freshwater" if town.water_access == "river" else
                         "accessible upland wells")
                event("founding", f"{town.name} is settled",
                      f"Farms and workshops take hold near {water}; the "
                      f"site's soil, climate and resources give a suitability index of {soil}.",
                      (town.id,))
        roads = _historic_routes(world, phase, founding_index, populations)
        trade = {s.id: 0 for s in settlements}
        for road in roads:
            trade[road.a] += road.trade_volume
            trade[road.b] += road.trade_volume
            key = tuple(sorted((road.a, road.b)))
            if key not in prior_roads:
                a = next(s for s in settlements if s.id == road.a)
                b = next(s for s in settlements if s.id == road.b)
                event("road", f"Trail joins {a.name} and {b.name}",
                      f"An accessible route crosses the terrain in about "
                      f"{road.travel_minutes} minutes, opening exchange "
                      "between complementary local production.", key)
                prior_roads.add(key)

        polities, allegiance = _polities(world, phase, populations, trade, roads)
        if phase >= 2:
            for polity in polities:
                for sid in polity.member_ids:
                    former = prior_polities.get(sid)
                    if former is not None and former != polity.id:
                        town = next(s for s in settlements if s.id == sid)
                        event("alliance", f"{town.name} changes allegiance",
                              f"Road access and the market influence of "
                              f"{polity.name} outweigh the former local center.",
                              (sid, polity.seat_id))
        prior_polities = allegiance

        # Crops, floodplains, road trade and transport costs change the
        # carrying capacity over centuries. Regional climate stress is also
        # tied to rainfall, not independent random catastrophes.
        risk = {}
        security = {}
        for town in settlements:
            if populations[town.id] == 0:
                continue
            _, capacity, base_security = factors[town.id]
            tile = world.tile(town.x, town.y)
            seasonal = _hash(world.seed + 2001 + phase * 67,
                             town.x * 3, town.y * 5)
            drought_pressure = max(0, 790 - tile.rainfall_mm) / 520
            flood_pressure = (.29 if town.water_access == "river" and
                              tile.elevation_m < 320 else .0)
            climate = drought_pressure * (.45 + seasonal) + flood_pressure * seasonal
            stress = min(.44, climate * (.23 if phase in (2, 4) else .11))
            security[town.id] = max(0, min(100, round(base_security -
                                     65 * stress + trade[town.id] * .12)))
            risk[town.id] = stress
            target = capacity + min(180, trade[town.id] * 2.3)
            # Diminishing growth near carrying capacity; shocks create
            # slowdowns or decline, never arbitrary positive/negative rolls.
            before = populations[town.id]
            growth = .33 * (target - before) + trade[town.id] * .14
            after = max(25, round((before + growth) * (1 - stress)))
            populations[town.id] = after
            if stress >= .16:
                kind = "drought" if drought_pressure >= flood_pressure else "flood"
                reason = ("low rainfall and limited crop surplus" if kind == "drought"
                          else "exposed riverside farmland and high seasonal flow")
                event("crisis", f"{kind.capitalize()} strains {town.name}",
                      f"The settlement loses momentum because of {reason}; "
                      f"estimated population changes from {before} to {after}.",
                      (town.id,))

        if phase >= 3 and roads:
            border = [r for r in roads
                      if allegiance.get(r.a) != allegiance.get(r.b)
                      and allegiance.get(r.a) and allegiance.get(r.b)]
            if border:
                crossing = max(border, key=lambda r:
                               (r.trade_volume, -r.travel_minutes, r.a, r.b))
                a = next(s for s in settlements if s.id == crossing.a)
                b = next(s for s in settlements if s.id == crossing.b)
                event("dispute", f"Tariffs contested on the {a.name}–{b.name} road",
                      "Two political centers claim revenue from a busy "
                      f"{crossing.surface} corridor carrying an estimated "
                      f"{crossing.trade_volume} units of regional exchange.",
                      (a.id, b.id))

        for ruin in ruins:
            if ruin.abandoned_year == year:
                event("abandonment", f"{ruin.name} falls silent",
                      f"The former {ruin.former_use} is abandoned. {ruin.cause}",
                      (), ruin.id)

        towns = []
        for town in settlements:
            pop = populations[town.id]
            if pop <= 0:
                continue
            status = ("city" if pop >= 1050 else "town" if pop >= 470 else
                      "village" if pop >= 180 else "hamlet")
            towns.append(HistoricTown(
                town.id, town.name, town.x, town.y, pop, status,
                security[town.id], trade[town.id],
                allegiance.get(town.id, f"polity-{town.id}"), founded[town.id]))
        eras.append(HistoricalEra(
            f"era-{phase:02d}", year, era_name,
            tuple(towns), roads, polities, tuple(events)))
    return WorldHistory(ERAS[0][0], ERAS[-1][0], tuple(eras), ruins)
