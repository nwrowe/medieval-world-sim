"""Horse ownership and transparent seeded horse races; no wagering."""
from hashlib import sha256
import hmac
from ..errors import ActionError
from ..core.transactions import transfer_gold

HORSES = {
    "moor_pony": {"name": "Moor Pony", "price": 45, "speed": 4, "stamina": 8},
    "valley_runner": {"name": "Valley Runner", "price": 90, "speed": 7, "stamina": 6},
    "royal_courser": {"name": "Royal Courser", "price": 170, "speed": 9, "stamina": 7},
}
RACE_STAMINA_COST = 15
RACE_ENTRY = 10
RACE_PRIZE = 30
RACE_COOLDOWN = 60

class TrackSystem:
    def __init__(self, world):
        self.world = world

    def buy(self, actor_id: str, breed: str) -> dict:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        if type(breed) is not str or breed not in HORSES:
            raise ActionError("Unknown horse breed")
        if breed in self.world.state.horses.get(actor_id, []):
            raise ActionError("You already own this horse breed")
        price = HORSES[breed]["price"]
        transfer_gold(self.world, actor, None, price)
        self.world.state.horses.setdefault(actor_id, []).append(breed)
        self.world._emit("horse_purchased", actor_id, breed, price)
        return {"breed": breed, "gold_spent": price}

    def race(self, actor_id: str, breed: str) -> dict:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        if breed not in self.world.state.horses.get(actor_id, []):
            raise ActionError("You do not own that racehorse")
        if self.world.minute - self.world.state.last_race_minute.get(
                actor_id, -RACE_COOLDOWN) < RACE_COOLDOWN:
            raise ActionError("Your horse must rest 60 simulated minutes between races")
        if actor.stamina < RACE_STAMINA_COST:
            raise ActionError("Not enough stamina to race")
        if actor.gold < RACE_ENTRY:
            raise ActionError("Entry fee is 10 gold")
        if self.world.crown_gold + RACE_ENTRY < RACE_PRIZE:
            raise ActionError("The track treasury cannot fund the winner's purse")
        transfer_gold(self.world, actor, None, RACE_ENTRY)
        actor.stamina -= RACE_STAMINA_COST
        skill = self.world.state.riding_xp.get(actor_id, 0)
        base = HORSES[breed]
        seed = f"{self.world.seed}:{actor_id}:{breed}:{self.world.minute}:{skill}".encode()
        private_key = getattr(self.world, "_private_rng_key", None)
        values = [
            int.from_bytes(
                (hmac.digest(private_key, seed + bytes([i]), "sha256")
                 if private_key is not None else sha256(seed + bytes([i])).digest())[:4],
                "big") % 19
            for i in range(3)
        ]
        merit_bonus = 2 if "horsemanship" in self.world.state.merit_upgrades.get(actor_id, set()) else 0
        your_score = base["speed"] * 2 + base["stamina"] + min(12, skill // 10) + values[0] + merit_bonus
        rivals = [20 + values[1], 23 + values[2]]
        place = 1 + sum(score > your_score for score in rivals)
        prize = RACE_PRIZE if place == 1 else 0
        if prize:
            transfer_gold(self.world, None, actor, prize)
        earned = 3 + (2 if place == 1 else 0)
        self.world.state.riding_xp[actor_id] = skill + earned
        self.world.state.last_race_minute[actor_id] = self.world.minute
        result = {"breed": breed, "placing": place, "xp": earned, "prize": prize,
                  "score": your_score, "rival_scores": rivals,
                  "riding_xp": skill + earned}
        self.world.state.race_results[actor_id] = result
        self.world._emit("horse_raced", actor_id, breed, place, earned, prize)
        return result
