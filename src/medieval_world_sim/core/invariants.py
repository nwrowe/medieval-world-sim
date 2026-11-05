"""Read-only conservation and integrity checks for authoritative world state.

The engine owns mutation; this module owns validating cross-system invariants.
Do not add storage, HTTP, account management or gameplay actions here.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..catalog import CITIES, GOODS
from ..combat import MAX_STAMINA
from ..core.entities import Actor
from ..equipment import GEAR
from ..systems.guilds import ROLES, MAX_GUILD_MEMBERS
from ..systems.merits import ACHIEVEMENTS, MERIT_UPGRADES
from ..systems.chat import MAX_MESSAGES_SAVED, MAX_MESSAGE_LENGTH
from ..systems.curriculum import SCHOOLS, CURRENT_SCHOOLS
from ..systems.regional_trade import MERCHANT_STOCK_CAP, MERCHANT_DAILY_LIMIT
from ..systems.travel import DEPOSIT_CAP

if TYPE_CHECKING:
    from .engine import WorldEngine


def validate_world(world: WorldEngine) -> None:
    """Raise AssertionError if world conservation or component rules are broken."""
    if world.total_gold != world.initial_gold:
        raise AssertionError("Gold was created or destroyed")
    ids = list(world.actors) + list(world.companies)
    if len(set(ids)) != len(ids):
        raise AssertionError("Duplicate account IDs")
    for account in list(world.actors.values()) + list(world.companies.values()):
        if account.gold < 0 or any(k not in GOODS or v < 0 for k, v in account.inventory.items()):
            raise AssertionError("Negative or invalid asset")
        if isinstance(account, Actor):
            if any(type(getattr(account.cooldowns, channel)) is not int
                   or getattr(account.cooldowns, channel) < 0
                   or max(0, getattr(account.cooldowns, channel) - world.minute) > 1440
                   for channel in ("job", "food", "potion")):
                raise AssertionError("Cooldown exceeds 24-hour limit")
            if any(city not in CITIES or not isinstance(goods, dict)
                   or any(item not in GOODS or type(qty) is not int or qty < 0
                          for item, qty in goods.items())
                   for city, goods in account.storage.items()):
                raise AssertionError("Invalid personal city storage")
            world.magic_system.assert_valid(account, world.minute)
            world.housing_system.assert_valid(account)
            if account.destination is not None:
                load = sum(account.inventory.values()) + len(account.gear_ids)
                if load > world.housing_system.travel_cargo_limit(account):
                    raise AssertionError("Traveling actor over cargo limit")
            if (account.destination is None) != (account.arrival_minute is None):
                raise AssertionError("Inconsistent travel")
            if not (0 <= account.hp <= account.max_hp and
                    0 <= account.stamina <= account.max_stamina and
                    0 <= account.vitals.hunger <= 3 and
                    account.work.manual >= 0 and account.work.intelligence >= 0 and
                    account.work.endurance >= 0 and account.work.shifts >= 0 and
                    all(isinstance(v, int) and 0 <= v <= 100
                        for v in account.work.experience.values()) and
                    account.max_hp == 24 + 4 * (account.level - 1) + (
                        5 if "school:physical" in world.state.merit_claims.get(account.id, set())
                        else 0) and
                    account.max_stamina == MAX_STAMINA and
                    account.strength == account.level + (
                        1 if "school:weapons" in world.state.merit_claims.get(account.id, set())
                        else 0) and account.defense == account.level and
                    account.level_xp >= 0 and account.combat_xp >= 0):
                raise AssertionError("Invalid combat state")
            for slot, gear_id in account.equipped.items():
                if gear_id not in account.gear_ids or GEAR[world.gear[gear_id].kind].slot != slot:
                    raise AssertionError("Equipped item is not owned or is in wrong slot")
    membership = []
    if type(world.state.next_guild_id) is not int or world.state.next_guild_id < 1:
        raise AssertionError("Invalid guild sequence")
    for guild_id, guild in world.state.guilds.items():
        if (guild_id != guild.id or guild.founder_id not in world.actors
                or not 1 <= len(guild.members) <= MAX_GUILD_MEMBERS
                or len(guild.name) < 3 or len(guild.name) > 40
                or sum(role == "leader" for role in guild.members.values()) != 1
                or any(actor_id not in world.actors or role not in ROLES
                       for actor_id, role in guild.members.items())
                or any(invitee not in world.actors for invitee in guild.invited)
                or any(invitee in guild.members for invitee in guild.invited)
                or guild.rating < 0 or guild.wins < 0 or guild.losses < 0):
            raise AssertionError("Invalid guild state")
        membership.extend(guild.members)
    if len(membership) != len(set(membership)):
        raise AssertionError("Character has multiple guilds")
    for actor_id, claimed in world.state.merit_claims.items():
        if (actor_id not in world.actors or not claimed <= ACHIEVEMENTS.keys()
                or type(world.state.merit_balance.get(actor_id, 0)) is not int
                or world.state.merit_balance.get(actor_id, 0) < 0):
            raise AssertionError("Invalid merit claims")
        bought = world.state.merit_upgrades.get(actor_id, set())
        if not bought <= MERIT_UPGRADES.keys():
            raise AssertionError("Unknown merit perk")
        issued = sum(ACHIEVEMENTS[k].award for k in claimed)
        spent = sum(MERIT_UPGRADES[k]["cost"] for k in bought)
        if issued - spent != world.state.merit_balance.get(actor_id, 0):
            raise AssertionError("Merit conservation mismatch")
    for actor_id, courses in world.state.completed_courses.items():
        if actor_id not in world.actors or any(
                school not in SCHOOLS or type(count) is not int or not 0 <= count <= 8
                for school, count in courses.items()):
            raise AssertionError("Invalid completed curriculum")
    for actor_id, courses in world.state.chosen_courses.items():
        if actor_id not in world.actors or any(
                school not in CURRENT_SCHOOLS or
                not isinstance(indices, set) or
                any(type(i) is not int or i < 0 or i >= 8 for i in indices)
                for school, indices in courses.items()):
            raise AssertionError("Invalid freely chosen courses")
    if any(actor_id not in world.state.active_courses
           for actor_id in world.state.free_course_enrollments):
        raise AssertionError("Orphaned university enrollment")
    for actor_id, course in world.state.active_courses.items():
        legacy = actor_id not in world.state.free_course_enrollments
        if (actor_id not in world.actors or course.school not in SCHOOLS
                or not 0 <= course.index < 8 or course.ends_at <= world.minute
                or (legacy and world.state.completed_courses.get(actor_id, {}).get(
                    course.school, 0) != course.index)
                or (not legacy and (course.school not in CURRENT_SCHOOLS
                    or course.index in world.curriculum_system.completed_indices(
                        actor_id, course.school)))):
            raise AssertionError("Invalid active curriculum")
    if any(gid not in world.gear or type(count) is not int or not 0 <= count < 12
           for gid, count in world.state.gear_wear.items()):
        raise AssertionError("Invalid equipment wear")
    if (type(world.state.next_chat_id) is not int or world.state.next_chat_id < 1
            or len(world.state.chat_messages) > MAX_MESSAGES_SAVED
            or type(world.state.next_chat_room_id) is not int
            or world.state.next_chat_room_id < 1):
        raise AssertionError("Invalid chat sequence")
    chat_ids = []
    for msg in world.state.chat_messages:
        if (type(msg.id) is not int or msg.id <= 0
                or msg.id >= world.state.next_chat_id
                or msg.author not in world.actors
                or world.actors[msg.author].kind != "human"
                or msg.kind not in ("global", "direct", "guild", "company", "room")
                or type(msg.body) is not str or not 1 <= len(msg.body) <= MAX_MESSAGE_LENGTH
                or type(msg.minute) is not int or not 0 <= msg.minute <= world.minute):
            raise AssertionError("Invalid chat message")
        chat_ids.append(msg.id)
    if chat_ids != sorted(set(chat_ids)):
        raise AssertionError("Chat messages are not ordered")
    for room_id, room in world.state.chat_rooms.items():
        if (room.id != room_id or room.creator not in world.actors
                or not isinstance(room.members, set)
                or room.creator not in room.members or not 1 <= len(room.members) <= 20
                or any(actor_id not in world.actors or
                       world.actors[actor_id].kind != "human"
                       for actor_id in room.members)):
            raise AssertionError("Invalid chat room membership")
    participants = []
    for key, duel in world.state.duels.items():
        if (key != duel.attacker_id or duel.attacker_id == duel.defender_id
                or duel.attacker_id not in world.actors or duel.defender_id not in world.actors
                or duel.round < 0 or duel.xp_earned < 0 or duel.pending_ward < 0):
            raise AssertionError('Invalid active duel')
        attacker, defender = world.actors[duel.attacker_id], world.actors[duel.defender_id]
        if (attacker.city != defender.city or attacker.destination or defender.destination
                or attacker.hp <= 0 or defender.hp <= 0
                or attacker.defeated_until is not None
                or defender.defeated_until is not None):
            raise AssertionError('Invalid duel participants')
        participants.extend((duel.attacker_id, duel.defender_id))
    if len(participants) != len(set(participants)):
        raise AssertionError('Actor participating in multiple duels')
    from ..systems.track import HORSES
    for actor_id, breeds in world.state.horses.items():
        if (actor_id not in world.actors or not isinstance(breeds, list)
                or len(breeds) != len(set(breeds))
                or any(breed not in HORSES for breed in breeds)):
            raise AssertionError("Invalid horse ownership")
    for actor_id, xp in world.state.riding_xp.items():
        if actor_id not in world.actors or type(xp) is not int or xp < 0:
            raise AssertionError("Invalid riding experience")
    for actor_id, minute in world.state.last_race_minute.items():
        if actor_id not in world.actors or type(minute) is not int or not 0 <= minute <= world.minute:
            raise AssertionError("Invalid racing timestamp")
    for actor_id, day in world.state.church_healed_day.items():
        if actor_id not in world.actors or type(day) is not int or not 0 <= day <= world.minute // 1440:
            raise AssertionError("Invalid church healing day")
    for company in world.companies.values():
        if not 1 <= company.facility_level <= 5 or company.shifts_completed < 0:
            raise AssertionError("Invalid company quality state")
    for city in world.cities.values():
        if city.household_gold < 0 or city.population < 0:
            raise AssertionError("Invalid city household budget")
        if any(item not in GOODS or qty < 0 or qty > MERCHANT_STOCK_CAP
               or not isinstance(qty, int) for item, qty in city.merchant_stock.items()):
            raise AssertionError("Invalid merchant stock")
        if not (0 <= city.merchant_purchases_today <= MERCHANT_DAILY_LIMIT and
                0 <= city.merchant_sales_today <= MERCHANT_DAILY_LIMIT):
            raise AssertionError("Invalid daily merchant trading volume")
    for city, stock in world.deposits.items():
        if city not in CITIES or any(quantity < 0 or quantity > DEPOSIT_CAP for quantity in stock.values()):
            raise AssertionError("Invalid regional deposits")
    holdings = [gear_id for a in world.actors.values() for gear_id in a.gear_ids]
    holdings += [gear_id for company in world.companies.values() for gear_id in company.gear_ids]
    if (type(world.state.next_trade_id) is not int
            or world.state.next_trade_id < 1):
        raise AssertionError("Invalid next trade ID")
    for trade_id, proposal in world.state.trades.items():
        if (type(trade_id) is not int or trade_id <= 0
                or trade_id >= world.state.next_trade_id
                or proposal.id != trade_id
                or proposal.maker not in world.actors
                or proposal.recipient not in world.actors
                or proposal.maker == proposal.recipient
                or world.actors[proposal.maker].kind != "human"
                or world.actors[proposal.recipient].kind != "human"
                or proposal.city not in CITIES
                or proposal.terms_hash != world.trades_system._hash(
                    proposal.maker, proposal.recipient, proposal.city,
                    proposal.offer, proposal.request)):
            raise AssertionError("Corrupted trade proposal")
        if proposal.offer.empty() and proposal.request.empty():
            raise AssertionError("Empty trade proposal")
        for bundle in (proposal.offer, proposal.request):
            if (type(bundle.gold) is not int or not 0 <= bundle.gold <= 10**12
                    or len(bundle.items) > 16 or len(bundle.gear_ids) > 16
                    or len(set(bundle.gear_ids)) != len(bundle.gear_ids)
                    or any(item not in GOODS or type(qty) is not int or qty <= 0
                           for item, qty in bundle.items)):
                raise AssertionError("Invalid escrow asset bundle")
        holdings.extend(proposal.offer.gear_ids)
    for offer in world.offers.values():
        if offer.quantity <= 0:
            raise AssertionError("Invalid market escrow")
        if offer.gear_id is None:
            if offer.item not in GOODS:
                raise AssertionError("Unknown offered resource")
        else:
            if offer.quantity != 1 or offer.item != world.gear[offer.gear_id].kind:
                raise AssertionError("Invalid equipment offer")
            holdings.append(offer.gear_id)
    if len(holdings) != len(set(holdings)) or set(holdings) != set(world.gear):
        raise AssertionError("Equipment ownership / escrow mismatch")
    for gear_id, gear in world.gear.items():
        if gear.id != gear_id or not 1 <= gear.quality <= 100 or not 0 < gear.durability <= gear.max_durability:
            raise AssertionError("Corrupted equipment")
