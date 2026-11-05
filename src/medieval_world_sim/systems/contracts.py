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

    def view(self, actor_id: str) -> list[dict]:
        actor = self.world._actor(actor_id)
        city = self.world.cities[actor.city]
        return [{
            "id": key, **asdict(spec),
            "can_pay": city.gold >= spec.reward,
            "cooldown_available": can_add(actor, "job", spec.cooldown_minutes, self.world.minute),
            "has_material": (not spec.material or
                             actor.inventory.get(spec.material, 0) >= 1),
        } for key, spec in CONTRACTS.items()]

    def complete(self, actor_id: str, contract_id: str) -> CityContractResult:
        actor = self.world._actor(actor_id)
        city_id = self.world._at_city(actor)
        if not isinstance(contract_id, str) or contract_id not in CONTRACTS:
            raise ActionError("Unknown civic contract")
        contract = CONTRACTS[contract_id]
        legacy = getattr(self.world, "_legacy_cooldown_rules", False)
        if legacy:
            if actor.ready_minute > self.world.minute:
                raise ActionError("Wait for your next available work shift")
        elif not can_add(actor, "job", contract.cooldown_minutes, self.world.minute):
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
        if legacy:
            actor.ready_minute = self.world.minute + contract.cooldown_minutes
        else:
            stack(actor, "job", contract.cooldown_minutes, self.world.minute)
        self.world._emit("city_contract_completed", actor_id, city_id,
                         contract_id, contract.reward, contract.stamina,
                         contract.mana, xp, contract.material)
        return CityContractResult(contract_id, contract.title, contract.reward,
                                  contract.stamina, contract.mana, xp, contract.material)
