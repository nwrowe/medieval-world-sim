"""Shared validation error for user, NPC and domain actions."""


class ActionError(ValueError):
    """An invalid action must not change state."""
