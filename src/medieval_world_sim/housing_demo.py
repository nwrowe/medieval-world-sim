"""Live CLI example of paid property progression and carriage travel.

python -m medieval_world_sim --scenario housing
"""
from .core.engine import WorldEngine
from .core.entities import Actor
from .catalog import CAPITAL, CITIES


def main() -> None:
    w = WorldEngine([Actor("resident", "human", city=CAPITAL, gold=8000)])
    destination = min((c for c in CITIES if c != CAPITAL),
                      key=lambda c: w.travel_minutes(CAPITAL, c))
    before = w.total_gold
    print("Home price progression:")
    print("  Room -> Cottage -> Townhouse -> Estate -> Manor")
    w.execute("resident", "buy_home", {"tier": "cottage"}, "housing:1")
    w.execute("resident", "upgrade_home", {"tier": "estate"}, "housing:2")
    w.execute("resident", "build_home_facility", {"facility": "carriage_house"}, "housing:3")
    w.execute("resident", "buy_vehicle", {"vehicle": "carriage"}, "housing:4")
    w.execute("resident", "select_vehicle", {"vehicle": "carriage"}, "housing:5")
    view = w.housing_view("resident")
    print(f"  Owned: {view.tier} in {view.city}; training bonus {view.training_bonus_pct}%")
    print(f"  Selected: {view.active_vehicle}; cargo limit {view.travel_cargo_limit}")
    print(f"  Crownreach -> {CITIES[destination].name}: "
          f"{w.travel_minutes(CAPITAL, destination)} minutes on foot")
    print(f"  Crownreach -> {CITIES[destination].name}: "
          f"{w.estimated_travel_minutes('resident', destination)} minutes by carriage")
    trip = w.start_travel("resident", destination)
    w.advance(trip)
    w.assert_invariants()
    print(f"  Arrived in {w.actors['resident'].city}; gold conserved: {before == w.total_gold}")


if __name__ == "__main__":
    main()
