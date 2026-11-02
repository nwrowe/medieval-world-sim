"""Runnable demonstration: raw materials travel to capital and become a sword.

Usage:
    python -m medieval_world_sim.regional_demo
"""
from .catalog import CAPITAL
from .regional_world import Actor, RegionalWorld, Wage


def run() -> RegionalWorld:
    world = RegionalWorld([
        Actor("player", "human", gold=500),
        Actor("ore_miner", "npc", city="ironvale", gold=30),
        Actor("coal_miner", "npc", city="emberfall", gold=30),
        Actor("woodcutter", "npc", city="greenhollow", gold=30),
        Actor("farmer", "npc", city="goldmeadow", gold=30),
    ])
    starting_gold = world.total_gold
    world.found_company("player", "royal_steelworks", "steelworks", investment=180)
    world.found_company("player", "royal_forge", "forge", investment=180)

    for actor, resource, count in (
        ("ore_miner", "iron_ore", 2),
        ("coal_miner", "coal", 1),
        ("woodcutter", "timber", 1),
        ("farmer", "grain", 1),
    ):
        world.gather(actor, resource, count)
        world.start_travel(actor, CAPITAL)

    world.advance(90)  # all arrive within 90 simulated minutes

    for actor, resource, count, price, buyer in (
        ("ore_miner", "iron_ore", 2, 4, "royal_steelworks"),
        ("coal_miner", "coal", 1, 3, "royal_steelworks"),
        ("woodcutter", "timber", 1, 4, "royal_forge"),
    ):
        offer = world.post_offer(actor, actor, resource, count, price)
        world.accept_offer("player", buyer, offer, count)

    world.hire("player", "royal_steelworks", "coal_miner", Wage(gold=5))
    world.shift("coal_miner", "royal_steelworks")
    steel_offer = world.post_offer("player", "royal_steelworks", "steel", 1, 20)
    world.accept_offer("player", "royal_forge", steel_offer, 1)
    world.hire("player", "royal_forge", "woodcutter", Wage(item="sword", quantity=1))
    world.shift("woodcutter", "royal_forge")

    # Capital can also trade grain, although a food-consumption loop is not ready.
    grain_offer = world.post_offer("farmer", "farmer", "grain", 1, 2)
    world.accept_offer("player", "player", grain_offer, 1)

    world.assert_invariants()
    assert world.total_gold == starting_gold
    assert len(world.actors["woodcutter"].gear_ids) == 1
    sword = world.gear[world.actors["woodcutter"].gear_ids[0]]
    assert sword.kind == "sword" and sword.quality >= 20
    return world


def main() -> None:
    world = run()
    print("Five-city medieval economy | in-memory demo")
    print(f"Simulated time: {world.minute} minutes")
    print(f"Gold conserved: {world.total_gold}")
    print(f"Companies: {', '.join(world.companies)}")
    print("Final equipment: sword earned as wages by NPC woodcutter")
    print("Event log:")
    for event in world.events:
        print(f"  t={event.minute:>3}m {event.kind}: {event.details}")


if __name__ == "__main__":
    main()
