"""Repeatable single-city civic contracts backed by real city funds."""
from dataclasses import asdict, dataclass
from ..content.contracts import CONTRACTS
from ..errors import ActionError
from ..content.lineages import work_experience_bonus
from ..core.transactions import transfer_gold
from ..systems.regional_trade import MERCHANT_STOCK_CAP
from .cooldowns import can_add, stack

@dataclass(frozen=True)
class CityContractResult:
    contract_id: str
    title: str
    reward: int
    stamina_spent: int
    mana_spent: int
    xp_gained: int
    material_delivered: str | None

class CityContractSystem:
    def __init__(self, world):
        self.world = world

    def active(self, actor_id: str) -> dict | None:
        record = self.world.state.active_contracts.get(actor_id)
        if not record:
            return None
        ident, city, ends, reward = record
        return {"contract_id": ident, "title": CONTRACTS[ident].title,
                "city": city, "ends_at": ends,
                "remaining_minutes": max(0, ends - self.world.minute),
                "reward": reward}

    def start(self, actor_id: str, contract_id: str) -> dict:
        actor = self.world._actor(actor_id)
        city_id = self.world._at_city(actor)
        if type(contract_id) is not str or contract_id not in CONTRACTS:
            raise ActionError("Unknown civic assignment")
        if actor_id in self.world.state.active_contracts:
            raise ActionError("Finish the active shift before starting another")
        spec = CONTRACTS[contract_id]
        last = self.world.state.contract_last_started.get(actor_id, {}).get(contract_id)
        if last is not None and self.world.minute - last < spec.repeat_cooldown_minutes:
            raise ActionError("This contract has a 24-hour repeat cooldown")
        if actor.stamina < spec.stamina or actor.magic.mana < spec.mana:
            raise ActionError("Insufficient stamina or mana")
        city = self.world.cities[city_id]
        if city.gold < spec.reward:
            raise ActionError("City cannot fund this shift")
        if spec.material:
            if actor.inventory.get(spec.material, 0) < 1:
                raise ActionError(f"Requires one {spec.material}")
            if city.merchant_stock.get(spec.material, 0) >= MERCHANT_STOCK_CAP:
                raise ActionError("The city's stores are full")
        actor.stamina -= spec.stamina
        actor.magic.mana -= spec.mana
        if spec.material:
            actor.inventory[spec.material] -= 1
            city.merchant_stock[spec.material] = city.merchant_stock.get(spec.material, 0) + 1
        # Wages are reserved in escrow until the shift completes.
        city.gold -= spec.reward
        self.world.state.contract_escrow_gold += spec.reward
        ends = self.world.minute + spec.duration_minutes
        self.world.state.active_contracts[actor_id] = (contract_id, city_id, ends, spec.reward)
        self.world.state.contract_last_started.setdefault(actor_id, {})[contract_id] = self.world.minute
        self.world._emit("city_contract_started", actor_id, city_id, contract_id, ends, spec.reward)
        return {"contract_id": contract_id, "title": spec.title,
                "ends_at": ends, "duration_minutes": spec.duration_minutes}

    def settle(self, minute: int) -> None:
        for actor_id, (ident, city_id, ends, reward) in sorted(
                tuple(self.world.state.active_contracts.items())):
            if ends > minute:
                continue
            actor = self.world._actor(actor_id)
            spec = CONTRACTS[ident]
            self.world.state.contract_escrow_gold -= reward
            actor.gold += reward
            if spec.xp_kind == "combat":
                xp = self.world.housing_system.training_xp(actor, 2, "combat")
                self.world.combat._award_xp(actor, xp)
            else:
                xp = self.world.housing_system.training_xp(actor, 1, "work:" + spec.xp_kind)
                xp += work_experience_bonus(actor)
                actor.work.experience[spec.xp_kind] = min(
                    100, actor.work.experience.get(spec.xp_kind, 0) + xp)
                actor.work.shifts += 1
                if spec.xp_kind == "manual":
                    actor.work.manual += 1
                elif spec.xp_kind == "intelligence":
                    actor.work.intelligence += 1
                else:
                    actor.work.endurance += 1
            del self.world.state.active_contracts[actor_id]
            self.world._emit("city_contract_completed", actor_id, city_id,
                             ident, reward, spec.stamina, spec.mana, xp, spec.material)

    def view(self, actor_id: str) -> list[dict]:
        actor = self.world._actor(actor_id)
        city = self.world.cities[actor.city]
        last = self.world.state.contract_last_started.get(actor_id, {})
        active = self.active(actor_id)
        return [{
            "id": key, **asdict(spec), "can_pay": city.gold >= spec.reward,
            "active": active is not None,
            "cooldown_remaining": max(
                0, last.get(key, -spec.repeat_cooldown_minutes) +
                spec.repeat_cooldown_minutes - self.world.minute),
            "cooldown_available": active is None and (
                key not in last or self.world.minute >=
                last[key] + spec.repeat_cooldown_minutes),
            "has_material": (not spec.material or
                             actor.inventory.get(spec.material, 0) >= 1),
        } for key, spec in CONTRACTS.items()]

    def complete(self, actor_id: str, contract_id: str) -> CityContractResult:
        actor = self.world._actor(actor_id)
        city_id = self.world._at_city(actor)
        if not isinstance(contract_id, str) or contract_id not in CONTRACTS:
            raise ActionError("Unknown civic contract")
        contract = CONTRACTS[contract_id]
        if not can_add(actor, "job", contract.cooldown_minutes, self.world.minute):
            raise ActionError("Job cooldown would exceed 24 hours")
        if actor.stamina < contract.stamina or actor.magic.mana < contract.mana:
            raise ActionError("Not enough stamina or mana for this assignment")
        city = self.world.cities[city_id]
        if city.gold < contract.reward:
            raise ActionError("The city treasury cannot currently fund this contract")
        if contract.material:
            if actor.inventory.get(contract.material, 0) < 1:
                raise ActionError(f"Requires one {contract.material} in your inventory")
            if city.merchant_stock.get(contract.material, 0) >= MERCHANT_STOCK_CAP:
                raise ActionError("The city's supplies are full")
        actor.stamina -= contract.stamina
        actor.magic.mana -= contract.mana
        if contract.material:
            actor.inventory[contract.material] -= 1
            city.merchant_stock[contract.material] = city.merchant_stock.get(contract.material, 0) + 1
        transfer_gold(self.world, city, actor, contract.reward)
        if contract.xp_kind == "combat":
            xp = self.world.housing_system.training_xp(actor, 2, "combat")
            self.world.combat._award_xp(actor, xp)
        else:
            xp = self.world.housing_system.training_xp(actor, 1, "work:" + contract.xp_kind)
            xp += work_experience_bonus(actor)
            actor.work.experience[contract.xp_kind] = min(100,
                actor.work.experience.get(contract.xp_kind, 0) + xp)
            actor.work.shifts += 1
            if contract.xp_kind == "manual":
                actor.work.manual += 1
            elif contract.xp_kind == "intelligence":
                actor.work.intelligence += 1
            else:
                actor.work.endurance += 1
        stack(actor, "job", contract.cooldown_minutes, self.world.minute)
        self.world._emit("city_contract_completed", actor_id, city_id,
                         contract_id, contract.reward, contract.stamina,
                         contract.mana, xp, contract.material)
        return CityContractResult(contract_id, contract.title, contract.reward,
                                  contract.stamina, contract.mana, xp, contract.material)
