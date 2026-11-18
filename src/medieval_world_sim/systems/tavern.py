"""City tavern rooms and mead, measured exclusively in simulation minutes."""
from ..errors import ActionError
from ..core.transactions import transfer_gold

ROOM_PRICE, ROOM_COOLDOWN, ROOM_DURATION = 12, 1440, 30
MEAD_PRICE, MEAD_STAMINA, MEAD_DAMAGE, MEAD_DAILY_LIMIT = 3, 6, 2, 6


def mead_day(minute):
    return (minute - 720) // 1440


def bonus_ticks(start, end, until, interval):
    cutoff = min(end, until)
    return max(0, cutoff // interval - start // interval) if cutoff > start else 0


class TavernSystem:
    def __init__(self, world):
        self.world = world

    def view(self, actor_id):
        actor = self.world._actor(actor_id)
        state, minute = self.world.state, self.world.minute
        last = state.tavern_last_room.get(actor_id)
        remaining = max(0, last + ROOM_COOLDOWN - minute) if last is not None else 0
        period, count = state.tavern_mead.get(actor_id, (-99, 0))
        used = count if period == mead_day(minute) else 0
        local = (actor.destination is None and actor.wilderness_hex is None
                 and actor.hp > 0 and actor.defeated_until is None)
        return {"room_price": ROOM_PRICE, "room_duration": ROOM_DURATION,
                "room_cooldown_remaining": remaining,
                "room_boost_remaining": max(0, state.tavern_room_until.get(actor_id, 0) - minute),
                "room_available": local and not remaining and actor.gold >= ROOM_PRICE,
                "mead_price": MEAD_PRICE, "mead_remaining": MEAD_DAILY_LIMIT - used,
                "mead_limit": MEAD_DAILY_LIMIT,
                "mead_available": (local and actor.gold >= MEAD_PRICE and
                                   used < MEAD_DAILY_LIMIT and actor.hp > MEAD_DAMAGE
                                   and actor.stamina < actor.max_stamina)}

    def rent_room(self, actor_id):
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        minute = self.world.minute
        last = self.world.state.tavern_last_room.get(actor_id)
        if last is not None and minute < last + ROOM_COOLDOWN:
            raise ActionError("A room can be rented once every 24 game hours")
        transfer_gold(self.world, actor, None, ROOM_PRICE)
        self.world.state.tavern_last_room[actor_id] = minute
        self.world.state.tavern_room_until[actor_id] = minute + ROOM_DURATION
        self.world._emit("tavern_room_rented", actor_id, ROOM_PRICE, minute + ROOM_DURATION)
        return {"gold_spent": ROOM_PRICE, "boost_until": minute + ROOM_DURATION}

    def buy_mead(self, actor_id):
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        period = mead_day(self.world.minute)
        prior_day, used = self.world.state.tavern_mead.get(actor_id, (period, 0))
        if prior_day != period:
            used = 0
        if used >= MEAD_DAILY_LIMIT:
            raise ActionError("You're cut off until noon Oathmere time")
        if actor.hp <= MEAD_DAMAGE or actor.stamina >= actor.max_stamina:
            raise ActionError("Not healthy enough to drink, or stamina is full")
        transfer_gold(self.world, actor, None, MEAD_PRICE)
        gained = min(MEAD_STAMINA, actor.max_stamina - actor.stamina)
        actor.stamina += gained
        actor.hp -= MEAD_DAMAGE
        self.world.state.tavern_mead[actor_id] = (period, used + 1)
        self.world._emit("tavern_mead_bought", actor_id, MEAD_PRICE, gained, MEAD_DAMAGE)
        return {"gold_spent": MEAD_PRICE, "stamina_gained": gained,
                "health_lost": MEAD_DAMAGE, "remaining": MEAD_DAILY_LIMIT - used - 1}
