"""Stackable, independent action cooldowns in simulation minutes.

Each channel has a 24-hour maximum queue. A new use adds to the remaining
cooldown, and is refused if it would exceed that maximum. Time only elapses
when the simulation advances; there are no hidden wall-clock side effects.
"""
from ..errors import ActionError

MAX_COOLDOWN_MINUTES = 24 * 60
FOOD_MINUTES = {"bread": 30, "meal": 60}
POTION_MINUTES = {"healing_potion": 120}


def remaining(actor, channel: str, minute: int) -> int:
    return max(0, getattr(actor.cooldowns, channel) - minute)


def can_add(actor, channel: str, duration: int, minute: int) -> bool:
    return 0 <= duration <= MAX_COOLDOWN_MINUTES and (
        remaining(actor, channel, minute) + duration <= MAX_COOLDOWN_MINUTES
    )


def stack(actor, channel: str, duration: int, minute: int) -> None:
    if channel not in ("job", "food", "potion") or not can_add(actor, channel, duration, minute):
        raise ActionError(f"{channel.title()} cooldown cannot exceed 24 hours")
    setattr(actor.cooldowns, channel, minute + remaining(actor, channel, minute) + duration)
