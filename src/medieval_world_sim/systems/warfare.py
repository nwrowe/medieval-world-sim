"""Server-authoritative Banner Clash, weekly pairing, and solo practice.

War results, rights and recovery live in durable WorldState. A win is credited
only by the trusted duel resolver, never by client-submitted score values.
"""
from __future__ import annotations

import hashlib

from ..errors import ActionError
from ..core.entities import Actor
from .guilds import WarRecord, WarRules, WAR_MIN_MEMBERS, MAX_GUILD_MEMBERS

WARFRONT = "crownreach"
MILESTONES = ((30, "field_hospital"), (60, "war_horn"), (90, "final_rally"))
CONTROL_TARGET = 120  # Half-minute score units.
MAX_EVENTS = 32


def _roll(*parts):
    return int.from_bytes(hashlib.sha256(
        ":".join(map(str, parts)).encode("utf-8")).digest()[:8], "big")


class WarSystem:
    def __init__(self, world):
        self.world = world
        self.rules = WarRules()

    def _log(self, war, message):
        war.events.append(message)
        if len(war.events) > MAX_EVENTS:
            del war.events[:-MAX_EVENTS]

    def pending_for(self, guild_id):
        return any(w.status in ("notice", "live")
                   and guild_id in (w.guild_a, w.guild_b)
                   for w in self.world.state.wars.values())

    def for_guild(self, guild_id):
        wars = [w for w in self.world.state.wars.values()
                if guild_id in (w.guild_a, w.guild_b)]
        if not wars:
            return None
        return sorted(wars, key=lambda w: (
            w.status in ("notice", "live"), w.scheduled_minute, w.id))[-1]

    def for_actor(self, actor_id):
        for war in self.world.state.wars.values():
            if war.status == "live" and war.guild_of(actor_id):
                return war
        return None

    def _require(self, actor_id):
        war = self.for_actor(actor_id)
        if war is None:
            raise ActionError("You are not in an active Banner Clash")
        return war

    def _ready(self, war, actor_id, now):
        return actor_id in war.present and war.routed.get(actor_id, 0) <= now

    def _eligible(self, war, actor_id, now):
        actor = self.world.actors[actor_id]
        return (self._ready(war, actor_id, now) and
                actor.destination is None and actor.city == WARFRONT
                and actor.defeated_until is None)

    def match_week(self, minute):
        """Deterministic rating-neighbor matches at the server's weekly boundary."""
        eligible = sorted((
            guild for guild in self.world.state.guilds.values()
            if guild.enlisted and WAR_MIN_MEMBERS <= len(guild.members) <= MAX_GUILD_MEMBERS
            and not self.pending_for(guild.id)
        ), key=lambda g: (g.rating, g.id))
        for left, right in zip(eligible[::2], eligible[1::2]):
            number = len(self.world.state.wars) + 1
            start = minute + self.rules.notice_minutes
            war = WarRecord("war:" + str(number), left.id, right.id, start,
                            start + self.rules.duration_minutes,
                            tuple(sorted(left.members)), tuple(sorted(right.members)))
            self.world.state.wars[war.id] = war
            left.enlisted = right.enlisted = False
            self._log(war, "Guilds matched; travel to Crownreach for the warfront.")
            self.world._emit("war_matched", war.id, left.id, right.id, start)
        # Leftovers stay enrolled for the next weekly pairing.

    def start_practice(self, actor_id):
        guild = self.world.guild_system.membership(actor_id)
        if not guild or guild.members.get(actor_id) != "leader":
            raise ActionError("Only the guild leader can start practice")
        if self.pending_for(guild.id):
            raise ActionError("Finish the current war before practicing")
        actor = self.world._actor(actor_id)
        if actor.city != WARFRONT or actor.destination is not None:
            raise ActionError("Start practice in Crownreach")
        # Reuse ten isolated training NPCs; they have no gold or accounts.
        roster = []
        for i in range(10):
            npc_id = "npc:war:" + guild.id + ":" + str(i + 1)
            if npc_id not in self.world.actors:
                bot = Actor(npc_id, "npc", city=WARFRONT, gold=0)
                bot.discovered_cities.add(WARFRONT)
                self.world.actors[npc_id] = bot
            else:
                bot = self.world.actors[npc_id]
                bot.city = WARFRONT
                bot.destination = None
                bot.defeated_until = None
                bot.hp = bot.max_hp
                bot.discovered_cities.add(WARFRONT)
            roster.append(npc_id)
        number = len(self.world.state.wars) + 1
        war = WarRecord("practice:" + str(number), guild.id,
                        "practice:" + guild.id, self.world.minute,
                        self.world.minute + 180, tuple(sorted(guild.members)),
                        tuple(roster), practice=True, status="live")
        war.present.update(roster)
        war.next_bot_tick = self.world.minute + 6
        self.world.state.wars[war.id] = war
        self._log(war, "Practice clash started against the Ashen Company.")
        self.world._emit("war_practice_started", war.id, guild.id, actor_id)
        return {"war_id": war.id}

    def join(self, actor_id):
        war = self._require(actor_id)
        actor = self.world._actor(actor_id)
        if actor.kind != "human":
            raise ActionError("Only players may join the warfront")
        if (actor.city != WARFRONT or actor.destination is not None
                or actor.wilderness_hex is not None):
            raise ActionError("Travel to Crownreach to enter the warfront")
        if actor.defeated_until is not None or actor.hp <= 0:
            raise ActionError("Recover from your ordinary injuries first")
        if war.routed.get(actor_id, 0) > self.world.minute:
            raise ActionError("You are still routed")
        war.present.add(actor_id)
        self._log(war, actor_id + " entered the warfront")
        return {"joined": True}

    def leave(self, actor_id, *, walking=False):
        war = self._require(actor_id)
        if actor_id not in war.present:
            if walking:
                return
            raise ActionError("You are not on the warfront")
        if any(actor_id in (d.attacker_id, d.defender_id)
               for d in self.world.state.duels.values()):
            raise ActionError("Finish your duel before leaving")
        own = war.guild_of(actor_id)
        enemies = [p for p in war.roster(war.guild_b if own == war.guild_a else war.guild_a)
                   if self._eligible(war, p, self.world.minute)]
        if enemies and war.routed.get(actor_id, 0) <= self.world.minute:
            # Retreat while contested concedes one *team* hit, but never
            # fabricates an individual's Honor or combat victory.
            enemy_guild = war.guild_of(enemies[0])
            war.hits[enemy_guild] = war.hits.get(enemy_guild, 0) + 1
            self._add_pressure(war, enemy_guild, self.world.minute)
            self._log(war, actor_id + " retreated under pressure (opponent +1 hit)")
        war.present.discard(actor_id)
        if war.advantage == own and not any(
                self._eligible(war, p, self.world.minute) for p in war.roster(own)):
            war.advantage = None
            war.pressure_a = war.pressure_b = 0
            war.horn_until = 0
            self._log(war, "Advantage forfeited: no defending fighters remain")
        return {"left": True, "contested": bool(enemies)}

    def duel_context(self, attacker_id, defender_id):
        war = self.for_actor(attacker_id) or self.for_actor(defender_id)
        if not war:
            return None
        if attacker_id in war.present or defender_id in war.present:
            if (war.guild_of(attacker_id) is None or war.guild_of(defender_id) is None
                    or war.guild_of(attacker_id) == war.guild_of(defender_id)
                    or not self._eligible(war, attacker_id, self.world.minute)
                    or not self._eligible(war, defender_id, self.world.minute)):
                raise ActionError("Both opponents must be ready at opposing warfronts")
            return war.id
        return None

    def assist(self, actor_id, leader_id):
        war = self._require(actor_id)
        if not self._eligible(war, actor_id, self.world.minute):
            raise ActionError("You must be ready at the warfront to assist")
        duel = self.world.state.duels.get(leader_id)
        if (duel is None or duel.war_id != war.id or
                war.guild_of(leader_id) != war.guild_of(actor_id)
                or actor_id == leader_id or actor_id in duel.assistants
                or len(duel.assistants) >= 2):
            raise ActionError("No available friendly attack to assist")
        if self.world.actors[actor_id].stamina < 3:
            raise ActionError("Assisting costs 3 stamina")
        if any(actor_id in (d.attacker_id, d.defender_id)
               for d in self.world.state.duels.values()):
            raise ActionError("Already fighting")
        self.world.actors[actor_id].stamina -= 3
        duel.assistants.append(actor_id)
        self._log(war, actor_id + " joined a group attack")
        return {"assistants": len(duel.assistants)}

    def _add_pressure(self, war, guild_id, minute):
        if war.advantage is None:
            if guild_id == war.guild_a:
                war.pressure_a += 1
                count = war.pressure_a
            else:
                war.pressure_b += 1
                count = war.pressure_b
            if count >= self.rules.gain_hits:
                war.advantage = guild_id
                war.pressure_a = war.pressure_b = 0
                self._log(war, guild_id + " seized the advantage")
        elif war.advantage != guild_id:
            if guild_id == war.guild_a:
                war.pressure_a += 1
                count = war.pressure_a
            else:
                war.pressure_b += 1
                count = war.pressure_b
            if count >= self.rules.break_hits:
                war.advantage = None
                war.pressure_a = war.pressure_b = 0
                war.horn_until = 0
                self._log(war, guild_id + " broke the advantage")

    def hit(self, war_id, winner_id, loser_id, assistants=(), *, minute=None,
            award_honor=True):
        war = self.world.state.wars.get(war_id)
        now = self.world.minute if minute is None else minute
        if (war is None or war.status != "live" or
                war.guild_of(winner_id) is None
                or war.guild_of(winner_id) == war.guild_of(loser_id)
                or not self._eligible(war, winner_id, now)
                or not self._eligible(war, loser_id, now)):
            raise ActionError("Invalid war hit")
        team = war.guild_of(winner_id)
        war.hits[team] = war.hits.get(team, 0) + 1
        self._add_pressure(war, team, now)
        if award_honor:
            winner = self.world.actors[winner_id]
            loser = self.world.actors[loser_id]
            attacking = max(1, winner.strength + winner.defense + winner.level * 3)
            defending = loser.strength + loser.defense + loser.level * 3
            honor = max(3, min(30, 10 + 8 * (defending - attacking) // attacking))
            if assistants:
                honor = max(3, honor * 3 // 4)
            war.honor[winner_id] = war.honor.get(winner_id, 0) + honor
            for helper in assistants:
                if helper in war.present and war.guild_of(helper) == team:
                    war.honor[helper] = war.honor.get(helper, 0) + max(1, honor // 3)
            self._log(war, winner_id + " defeated " + loser_id +
                      " (+" + str(honor) + " Honor)")
        duration = self.rules.route_min + _roll(war.id, winner_id, loser_id,
                                                war.hits[team]) % (
                                                    self.rules.route_max -
                                                    self.rules.route_min + 1)
        war.routed[loser_id] = now + duration
        return {"honor": war.honor.get(winner_id, 0), "routed_until": now + duration}

    def dressing(self, actor_id):
        war = self._require(actor_id)
        now = self.world.minute
        if war.routed.get(actor_id, 0) <= now:
            raise ActionError("You are not routed")
        if war.dressings.get(actor_id, 2) < 1:
            raise ActionError("No field dressings remaining")
        if war.dressing_cooldowns.get(actor_id, 0) > now:
            raise ActionError("Medical items are cooling down")
        war.dressings[actor_id] = war.dressings.get(actor_id, 2) - 1
        war.dressing_cooldowns[actor_id] = now + 30
        war.routed[actor_id] = max(now, war.routed[actor_id] - 8)
        self._log(war, actor_id + " used a field dressing")
        return {"remaining": max(0, war.routed[actor_id] - now)}

    def restore(self, actor_id, target_id):
        war = self._require(actor_id)
        now = self.world.minute
        if (not self._eligible(war, actor_id, now)
                or war.guild_of(target_id) != war.guild_of(actor_id)
                or war.routed.get(target_id, 0) <= now):
            raise ActionError("Choose a routed ally at your warfront")
        actor = self.world.actors[actor_id]
        if actor.magic.mana < 5 or war.heal_cooldowns.get(actor_id, 0) > now:
            raise ActionError("Restoration requires 5 mana and a ready cooldown")
        actor.magic.mana -= 5
        war.heal_cooldowns[actor_id] = now + 15
        war.routed[target_id] = max(now, war.routed[target_id] - 5)
        self._log(war, actor_id + " restored " + target_id)
        return {"remaining": max(0, war.routed[target_id] - now)}

    def milestone(self, actor_id, power):
        war = self._require(actor_id)
        team = war.guild_of(actor_id)
        guild = self.world.state.guilds.get(team)
        if not self.world.guild_system.can(guild, actor_id, "milestones"):
            raise ActionError("Milestone permission required")
        if power not in ("field_hospital", "war_horn", "final_rally"):
            raise ActionError("Unknown milestone power")
        if (power not in war.unlocks.get(team, set())
                or power in war.used.get(team, set())):
            raise ActionError("Milestone has not unlocked or is already used")
        if power == "war_horn" and war.advantage != team:
            raise ActionError("Hold the advantage to sound the War Horn")
        war.used.setdefault(team, set()).add(power)
        if power == "war_horn":
            war.horn_until = self.world.minute + 10
        else:
            reduction = 5 if power == "field_hospital" else 10**9
            for member in war.roster(team):
                if war.routed.get(member, 0) > self.world.minute:
                    war.routed[member] = max(
                        self.world.minute, war.routed[member] - reduction)
        self._log(war, team + " activated " + power.replace("_", " "))
        return {"activated": power}

    def _finish(self, war):
        if war.status == "finished":
            return
        war.status = "finished"
        war.advantage = None
        if war.progress_a > war.progress_b:
            war.winner_id = war.guild_a
        elif war.progress_b > war.progress_a:
            war.winner_id = war.guild_b
        if not war.practice and war.winner_id:
            winner = self.world.state.guilds.get(war.winner_id)
            loser_id = war.guild_b if war.winner_id == war.guild_a else war.guild_a
            loser = self.world.state.guilds.get(loser_id)
            if winner and loser:
                winner.wins += 1
                loser.losses += 1
                winner.rating += 16
                loser.rating = max(0, loser.rating - 16)
        self._log(war, "War concluded; Honor totals are final")
        self.world._emit("war_finished", war.id, war.winner_id or "")

    def settle(self, start, end):
        for minute in range(start + 1, end + 1):
            if minute % self.rules.week_minutes == 0:
                self.match_week(minute)
            for war in tuple(self.world.state.wars.values()):
                if war.status == "notice" and minute >= war.scheduled_minute:
                    war.status = "live"
                    self._log(war, "Banner Clash has begun at Crownreach")
                if war.status != "live":
                    continue
                if minute >= war.end_minute:
                    self._finish(war)
                    continue
                if war.advantage is not None:
                    team = war.advantage
                    if any(self._eligible(war, p, minute) for p in war.roster(team)):
                        extra = 1 if minute <= war.horn_until else 0
                        if team == war.guild_a:
                            war.progress_a += 2 + extra
                            score = war.progress_a
                        else:
                            war.progress_b += 2 + extra
                            score = war.progress_b
                        for threshold, power in MILESTONES:
                            if score >= threshold:
                                war.unlocks.setdefault(team, set()).add(power)
                        if score >= CONTROL_TARGET:
                            self._finish(war)
                            continue
                if war.practice and minute >= war.next_bot_tick:
                    war.next_bot_tick = minute + 6
                    bots = [p for p in war.roster_b if self._eligible(war, p, minute)]
                    engaged = {p for duel in self.world.state.duels.values()
                               for p in (duel.attacker_id, duel.defender_id)}
                    humans = [p for p in war.roster_a
                              if p not in engaged and self._eligible(war, p, minute)]
                    bots = [p for p in bots if p not in engaged]
                    if bots and humans:
                        bot = bots[_roll(war.id, minute, "bot") % len(bots)]
                        target = humans[_roll(war.id, minute, "target") % len(humans)]
                        if _roll(war.id, minute, "success") % 100 < 35:
                            self.hit(war.id, bot, target, minute=minute)

    def history(self, actor_id):
        guild = self.world.guild_system.membership(actor_id)
        if guild is None:
            return []
        recent = sorted((
            war for war in self.world.state.wars.values()
            if guild.id in (war.guild_a, war.guild_b) and war.status == "finished"
        ), key=lambda war: (war.scheduled_minute, war.id), reverse=True)[:5]
        return [{
            "id": war.id, "practice": war.practice,
            "result": ("Victory" if war.winner_id == guild.id
                       else "Draw" if war.winner_id is None else "Defeat"),
            "progress": (war.progress_a if war.guild_a == guild.id
                         else war.progress_b) * 100 // CONTROL_TARGET,
            "honor": [{"id": actor, "score": war.honor.get(actor, 0)}
                      for actor in war.roster(guild.id)],
        } for war in recent]

    def view(self, actor_id):
        guild = self.world.guild_system.membership(actor_id)
        if guild is None:
            return None
        war = self.for_guild(guild.id)
        if war is None:
            return None
        now = self.world.minute
        def roster(members):
            return [{"id": p, "name": ("Sparring Guard " + p.rsplit(":", 1)[-1]
                                        if p.startswith("npc:war:") else p),
                     "present": p in war.present,
                     "routed_remaining": max(0, war.routed.get(p, 0) - now),
                     "honor": war.honor.get(p, 0),
                     "hits": 0} for p in members]
        return {
            "id": war.id, "status": war.status, "practice": war.practice,
            "mine": guild.id, "guild_a": war.guild_a, "guild_b": war.guild_b,
            "name_a": (self.world.state.guilds[war.guild_a].name
                       if war.guild_a in self.world.state.guilds else "Ashen Company"),
            "name_b": (self.world.state.guilds[war.guild_b].name
                       if war.guild_b in self.world.state.guilds else "Ashen Company"),
            "start_minute": war.scheduled_minute,
            "end_minute": war.end_minute,
            "remaining_minutes": max(0, war.end_minute - now),
            "location": "Crownreach",
            "advantage": war.advantage,
            "pressure_a": war.pressure_a, "pressure_b": war.pressure_b,
            "progress_a": min(100, war.progress_a * 100 // CONTROL_TARGET),
            "progress_b": min(100, war.progress_b * 100 // CONTROL_TARGET),
            "hits": dict(war.hits),
            "roster_a": roster(war.roster_a), "roster_b": roster(war.roster_b),
            "present": actor_id in war.present,
            "my_routed": max(0, war.routed.get(actor_id, 0) - now),
            "my_dressings": war.dressings.get(actor_id, 2),
            "dressing_cooldown": max(0, war.dressing_cooldowns.get(actor_id, 0) - now),
            "restore_cooldown": max(0, war.heal_cooldowns.get(actor_id, 0) - now),
            "unlocks": {t: sorted(v) for t, v in war.unlocks.items()},
            "used": {t: sorted(v) for t, v in war.used.items()},
            "horn_remaining": max(0, war.horn_until - now),
            "honor": war.honor.get(actor_id, 0),
            "winner_id": war.winner_id,
            "recent": list(reversed(war.events[-14:])),
            "assistable": [
                d.attacker_id for d in self.world.state.duels.values()
                if d.war_id == war.id and d.attacker_id != actor_id
                and war.guild_of(d.attacker_id) == guild.id
                and actor_id not in d.assistants and len(d.assistants) < 2],
        }
