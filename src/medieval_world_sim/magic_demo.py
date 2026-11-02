"""Print all six magic trees and perform a zero-income novice practice.

python -m medieval_world_sim --scenario magic
"""
from .core.engine import WorldEngine
from .core.entities import Actor
from .content.magic_tree import SCHOOLS


def main() -> None:
    world = WorldEngine([Actor("apprentice", "human")], seed=42)
    for school in SCHOOLS:
        print(f"\n{school.title()}")
        for node in world.magic_tree("apprentice", school):
            print(f"  Tier {node.tier} | {node.title} | "
                  f"{'available' if node.eligible else 'locked'} | "
                  f"{node.insight_cost} Insight | {node.mana_cost} mana")
    apprentice = "restoration.soothe_wounds"
    world.execute("apprentice", "unlock_magic", {"node_id": apprentice}, "first-school")
    cast = world.execute("apprentice", "practice_magic", {"node_id": apprentice}, "first-practice")
    print(f"\nFirst practice: success={cast.success}, +{cast.xp_gained} school XP, "
          f"mana remaining={world.actors['apprentice'].magic.mana}.")
    print("Magic jobs and real world spell effects have not been implemented.")


if __name__ == "__main__":
    main()
