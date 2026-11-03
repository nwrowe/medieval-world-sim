"""Small, finite-budget civic contracts for the first playable city locations.

These are immediate jobs, not a quest ledger. Future contract chains can build
on this content registry without adding actor inheritance layers.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class CityContract:
    title: str
    venue: str
    description: str
    reward: int
    stamina: int = 0
    mana: int = 0
    material: str | None = None
    xp_kind: str = "work"
    cooldown_minutes: int = 60

CONTRACTS = {
    "warrior_patrol": CityContract(
        "Patrol the city gates", "warriors",
        "Join the watch along the city walls and report signs of trouble.",
        reward=10, stamina=18, xp_kind="combat"),
    "mage_copywork": CityContract(
        "Copy warding sigils", "mageguild",
        "Help the archivist inscribe warding runes into the guild ledger.",
        reward=8, mana=12, xp_kind="intelligence"),
    "church_supplies": CityContract(
        "Deliver herbs to the infirmary", "church",
        "Bring one bunch of herbs for the healers' stores.",
        reward=11, material="herbs", xp_kind="caregiving"),
    "labor_shift": CityContract(
        "Work a merchant loading shift", "job",
        "Spend an hour helping the city's carriers load and sort goods.",
        reward=9, stamina=20, xp_kind="manual"),
}
