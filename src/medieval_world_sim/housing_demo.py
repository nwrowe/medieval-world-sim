"""Live CLI example of paid property progression and carriage travel.

python -m medieval_world_sim --scenario housing
"""
from .core.engine import WorldEngine
from .core.entities import Actor
from .catalog import CAPITAL


def main() -> None:
    w = WorldEngine([Actor("resident", "human", city=CAPITAL, gold=8000)])
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
    print(f"  Crownreach -> Ironvale: {w.travel_minutes(CAPITAL, 'ironvale')} minutes on foot")
    print(f"  Crownreach -> Ironvale: {w.estimated_travel_minutes('resident', 'ironvale')} minutes by carriage")
    w.start_travel("resident", "ironvale")
    w.advance(54)
    w.assert_invariants()
    print(f"  Arrived in {w.actors['resident'].city}; gold conserved: {before == w.total_gold}")


if __name__ == "__main__":
    main()
