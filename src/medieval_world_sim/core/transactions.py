"""Atomic in-memory world actions and one auditable gold transfer primitive.

The snapshot approach is intentionally simple for this small test harness.
The multiplayer adapter adds a durable SQLite journal, asset/escrow records,
receipts and checkpoints in its outer transaction. This in-memory rollback
still incurs a full state copy; replacing it with granular mutations belongs
to the later scaling work.
"""
from copy import deepcopy
from functools import wraps
from ..errors import ActionError


def atomic_action(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._action_lock:
            # In multiplayer the outer SQLite transaction already owns a
            # complete rollback snapshot, invariant validation and commit.
            # Cloning again here doubles the cost and memory of every action.
            # Replay and single-player actions continue to use the normal
            # independent snapshot and rollback path.
            if getattr(self, "_external_transaction_active", False):
                return method(self, *args, **kwargs)
            original = deepcopy(self.state)
            try:
                result = method(self, *args, **kwargs)
                self.assert_invariants()
                return result
            except Exception:
                self.state = original
                raise
    return wrapped


def transfer_gold(world, payer, payee, amount: int) -> None:
    """Move gold between actor/company accounts; None denotes the crown treasury."""
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise ActionError("Invalid gold amount")
    if payer is payee:
        raise ActionError("Self-payment is not a transfer")
    available = world.crown_gold if payer is None else payer.gold
    if available < amount:
        raise ActionError("Insufficient gold")
    if payer is None:
        world.crown_gold -= amount
    else:
        payer.gold -= amount
    if payee is None:
        world.crown_gold += amount
    else:
        payee.gold += amount
