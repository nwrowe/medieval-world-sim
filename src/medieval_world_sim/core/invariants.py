"""Read-only conservation and integrity checks for authoritative world state.

The engine owns mutation; this module owns validating cross-system invariants.
Do not add storage, HTTP, account management or gameplay actions here.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..catalog import CITIES, GOODS
from ..content.lineages import LINEAGES
from ..combat import MAX_STAMINA
from ..core.entities import Actor
from ..equipment import GEAR
from ..systems.guilds import ROLES, MAX_GUILD_MEMBERS, RIGHTS
from ..systems.merits import ACHIEVEMENTS, MERIT_UPGRADES, perk_level
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
            if (account.lineage not in LINEAGES or type(account.lineage_selected) is not bool
                    or type(account.discovered_cities) is not set
                    or not account.discovered_cities <= CITIES.keys()
                    or account.city not in account.discovered_cities):
                raise AssertionError("Invalid lineage or explored atlas")
            if (type(account.explored_hexes) is not set
                    or any(type(i) is not int or not 0 <= i < len(world.geography.tiles)
                           for i in account.explored_hexes)):
                raise AssertionError("Invalid per-character discovered hex set")
            if account.wilderness_hex is not None:
                p = account.wilderness_hex
                if (not isinstance(p, tuple) or len(p) != 2
                        or any(type(n) is not int for n in p)
                        or not 0 <= p[0] < world.geography.width
                        or not 0 <= p[1] < world.geography.height
                        or world.geography.tile(*p).elevation_m <= 0
                        or world.geography.tile(*p).waterbody in ("sea", "lake")
                        or p[1] * world.geography.width + p[0]
                        not in account.explored_hexes):
                    raise AssertionError("Invalid wilderness location")
                if account.destination is not None and account.travel.hex_target is None:
                    raise AssertionError("Cannot travel between towns from wilderness")
            route = account.travel.route_hexes
            if not isinstance(route, tuple):
                raise AssertionError("Travel route must be immutable")
            if account.destination is None:
                if (route or account.travel.departure_minute is not None
                        or account.travel.route_revealed_index != 0
                        or account.travel.hex_target is not None
                        or account.travel.route_durations):
                    raise AssertionError("Inactive journey retains a route")
            else:
                if (not route or account.travel.departure_minute is None
                        or not 0 <= account.travel.route_revealed_index < len(route)
                        or any(type(x) is not int or type(y) is not int
                               or not 0 <= x < world.geography.width
                               or not 0 <= y < world.geography.height
                               for x, y in route)):
                    raise AssertionError("Invalid or out-of-bounds active journey")
            durations = account.travel.route_durations
            if (type(durations) is not tuple
                    or any(type(t) is not int or t <= 0 for t in durations)
                    or (durations and (len(durations) != len(route) - 1
                        or sum(durations) != account.arrival_minute
                           - account.travel.departure_minute))):
                raise AssertionError("Invalid per-hex terrain crossing times")
            target = account.travel.hex_target
            if target is not None:
                if (type(target) is not tuple or len(target) != 2
                        or any(type(v) is not int for v in target)
                        or not 0 <= target[0] < world.geography.width
                        or not 0 <= target[1] < world.geography.height
                        or world.geography.tile(*target).elevation_m <= 0
                        or world.geography.tile(*target).waterbody in ("sea", "lake")
                        or account.destination is None
                        or not route or route[-1] != target):
                    raise AssertionError("Invalid hex journey target")
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
            if any(city not in CITIES or type(ids) is not list
                   or any(type(gid) is not int for gid in ids)
                   for city, ids in account.stored_gear.items()):
                raise AssertionError("Invalid stored equipment")
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
                or guild.rating < 0 or guild.wins < 0 or guild.losses < 0
                or any(member not in guild.members or not granted <= set(RIGHTS)
                       or not isinstance(granted, set)
                       for member, granted in guild.rights.items())
                or type(guild.enlisted) is not bool):
            raise AssertionError("Invalid guild state")
        membership.extend(guild.members)
    if len(membership) != len(set(membership)):
        raise AssertionError("Character has multiple guilds")
    for war_id, war in world.state.wars.items():
        both = set(war.roster_a) | set(war.roster_b)
        if (war_id != war.id or war.guild_a == war.guild_b
                or war.status not in ("notice", "live", "finished")
                or not war.roster_a or not war.roster_b
                or set(war.roster_a) & set(war.roster_b)
                or not both <= world.actors.keys()
                or not war.present <= both
                or any(p not in both or type(t) is not int or t < 0
                       for p, t in war.routed.items())
                or any(p not in both or type(h) is not int or h < 0
                       for p, h in war.honor.items())
                or war.advantage not in (None, war.guild_a, war.guild_b)
                or any(type(v) is not int or v < 0 for v in (
                    war.pressure_a, war.pressure_b, war.progress_a, war.progress_b))
                or any(t not in (war.guild_a, war.guild_b)
                       for t in war.unlocks.keys() | war.used.keys())):
            raise AssertionError("Invalid Banner Clash state")
    for actor_id, claimed in world.state.merit_claims.items():
        if (actor_id not in world.actors or not claimed <= ACHIEVEMENTS.keys()
                or type(world.state.merit_balance.get(actor_id, 0)) is not int
                or world.state.merit_balance.get(actor_id, 0) < 0):
            raise AssertionError("Invalid merit claims")
        bought = world.state.merit_upgrades.get(actor_id, set())
        if not bought <= MERIT_UPGRADES.keys():
            raise AssertionError("Unknown merit perk")
        if any(MERIT_UPGRADES[k]["level"] > perk_level(bought, MERIT_UPGRADES[k]["track"])
               for k in bought):
            raise AssertionError("Renown levels must be sequential")
        issued = sum(ACHIEVEMENTS[k].award for k in claimed)
        spent = sum(MERIT_UPGRADES[k]["cost"] for k in bought)
        if issued - spent != world.state.merit_balance.get(actor_id, 0):
            raise AssertionError("Merit conservation mismatch")
    for actor_id, courses in world.state.chosen_courses.items():
        if actor_id not in world.actors or any(
                school not in CURRENT_SCHOOLS or
                not isinstance(indices, set) or
                any(type(i) is not int or i < 0 or i >= 8 for i in indices)
                for school, indices in courses.items()):
            raise AssertionError("Invalid freely chosen courses")
    for actor_id, course in world.state.active_courses.items():
        if (actor_id not in world.actors or course.school not in CURRENT_SCHOOLS
                or not 0 <= course.index < 8 or course.ends_at <= world.minute
                or course.index in world.curriculum_system.completed_indices(
                    actor_id, course.school)):
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
    from ..content.contracts import CONTRACTS
    reserved = 0
    for actor_id, record in world.state.active_contracts.items():
        if (actor_id not in world.actors or type(record) is not tuple or
                len(record) != 4 or record[0] not in CONTRACTS or
                record[1] not in world.cities or
                type(record[2]) is not int or record[2] <= world.minute or
                type(record[3]) is not int or
                record[3] != CONTRACTS[record[0]].reward):
            raise AssertionError("Invalid active civic assignment")
        reserved += record[3]
    if reserved != world.state.contract_escrow_gold:
        raise AssertionError("Civic contract funds are not fully escrowed")
    for actor_id, starts in world.state.contract_last_started.items():
        if (actor_id not in world.actors or type(starts) is not dict or
                any(key not in CONTRACTS or type(minute) is not int or
                    minute < 0 or minute > world.minute for key, minute in starts.items())):
            raise AssertionError("Invalid civic contract cooldown ledger")
    for actor_id, day in world.state.church_healed_day.items():
        if actor_id not in world.actors or type(day) is not int or not 0 <= day <= world.minute // 1440:
            raise AssertionError("Invalid church healing day")
    # Bounded material stock derived from immutable tile potentials; only
    # legitimately explored sites may have a character decision on record.
    from ..systems.wilderness import SITE_APPROACHES, supply_cap
    for key, record in world.state.wilderness_stock.items():
        if (type(key) is not tuple or len(key) != 2
                or type(key[0]) is not int or type(key[1]) is not str
                or not 0 <= key[0] < len(world.geography.tiles)
                or type(record) is not tuple or len(record) != 2
                or any(type(v) is not int for v in record)):
            raise AssertionError("Invalid wilderness stock entry")
        tile = world.geography.tiles[key[0]]
        potential = tile.resources.get(key[1], 0)
        if (potential <= 0 or not 0 <= record[0] <= supply_cap(potential)
                or not 0 <= record[1] <= world.minute // 1440):
            raise AssertionError("Invalid wilderness stock balance")
    site_ids = {site.id for site in world.geography.sites}
    for actor_id, attempts in world.state.site_attempts.items():
        if actor_id not in world.actors or type(attempts) is not dict:
            raise AssertionError("Invalid wilderness actor record")
        if not set(attempts).issubset(site_ids):
            raise AssertionError("Unknown investigated site")
        for result in attempts.values():
            if (type(result) is not tuple or len(result) != 5
                    or result[0] not in SITE_APPROACHES
                    or type(result[1]) is not bool
                    or type(result[2]) is not str
                    or type(result[3]) is not int or result[3] < 0
                    or type(result[4]) is not int or result[4] < 0
                    or (result[3] > 0 and result[2] not in GOODS)):
                raise AssertionError("Invalid site resolution record")
    for actor_id, minute in world.state.tavern_last_room.items():
        if (actor_id not in world.actors or type(minute) is not int or
                not 0 <= minute <= world.minute or
                world.state.tavern_room_until.get(actor_id) != minute + 30):
            raise AssertionError("Invalid tavern room record")
    if set(world.state.tavern_room_until) != set(world.state.tavern_last_room):
        raise AssertionError("Invalid tavern boost records")
    from ..systems.tavern import MEAD_DAILY_LIMIT, mead_day
    for actor_id, record in world.state.tavern_mead.items():
        if (actor_id not in world.actors or type(record) is not tuple or len(record) != 2 or
                type(record[0]) is not int or type(record[1]) is not int or
                not 0 <= record[1] <= MEAD_DAILY_LIMIT or
                record[0] > mead_day(world.minute)):
            raise AssertionError("Invalid tavern drink tally")
    from ..content.industry import INDUSTRY_PRODUCTS
    from ..content.staffing import positions, occupancy, active_offer
    for company in world.companies.values():
        if (type(company.display_name) is not str or
                type(company.sale_price) is not int or
                not 0 <= company.sale_price <= 1_000_000_000 or
                type(company.hiring) is not bool or
                type(company.applicants) is not set or
                any(a not in world.actors or world.actors[a].kind != "human"
                    for a in company.applicants)):
            raise AssertionError("Invalid company listing or applicants")
        if (type(company.product) is not str or
                company.product and company.product not in INDUSTRY_PRODUCTS[company.industry]):
            raise AssertionError("Invalid company product selection")
        if not 1 <= company.facility_level <= 5 or company.shifts_completed < 0:
            raise AssertionError("Invalid company quality state")
        if (not set(company.employee_positions) <= set(company.employees)
                or not set(company.offer_positions) <= set(company.job_offers)
                or not set(company.offer_expires) <= set(company.job_offers)
                or not set(company.applicant_positions) <= company.applicants
                or any(type(t) is not int or t < 0
                       for t in company.offer_expires.values())):
            raise AssertionError("Invalid employment assignment metadata")
        valid_slots = {p["id"] for p in positions(company)}
        if (any(slot not in valid_slots for slot in company.employee_positions.values())
                or any(slot not in valid_slots for slot in company.offer_positions.values())
                or any(slot not in valid_slots for slot in company.applicant_positions.values())):
            raise AssertionError("Unknown career slot")
        occupied = occupancy(company, world.minute)
        if any(active_offer(company, worker, world.minute) and
               not any(value == ("offer", worker) for value in occupied.values())
               for worker in company.job_offers if worker in company.offer_positions):
            raise AssertionError("Competing employment offers for one position")
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
    holdings += [gear_id for a in world.actors.values()
                 for ids in a.stored_gear.values() for gear_id in ids]
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
