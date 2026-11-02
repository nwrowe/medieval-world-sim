"""Simple executable combat example: starter sword, armor, XP and finite loot.

python -m medieval_world_sim.combat_demo
"""
from .regional_world import Actor, RegionalWorld


def main() -> None:
    world = RegionalWorld([
        Actor("hero", "human", gold=100),
        Actor("bandit", "npc", hostile=True, gold=25),
    ])
    sword = world.buy_starter_gear("hero", "sword")
    armor = world.buy_starter_gear("hero", "leather_armor")
    world.equip("hero", sword)
    world.equip("hero", armor)
    foe = world.buy_starter_gear("bandit", "axe")
    world.equip("bandit", foe)
    total = world.total_gold
    print(f"Starting: hero gold={world.actors['hero'].gold}, sword quality={world.gear[sword].quality}")
    for turn in range(12):
        result = world.attack("hero", "bandit")
        print(f"Round {turn+1}: dealt {result.damage}, took {result.retaliation}, "
              f"+{result.xp_gained} XP, +{result.gold_looted} gold")
        if result.opponent_defeated or result.attacker_defeated:
            break
        world.advance(5)
    print(f"Ending: hero gold={world.actors['hero'].gold}, XP={world.actors['hero'].combat_xp}, "
          f"world gold={world.total_gold} (was {total})")
    world.assert_invariants()


if __name__ == "__main__":
    main()
