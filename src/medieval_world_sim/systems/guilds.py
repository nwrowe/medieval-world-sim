"""Guild membership, delegated permissions, and Banner Clash records.

Guild enrollment is opt-in. War state is owned and adjudicated by WarSystem;
this module intentionally contains no privileged administrative commands.
"""
from dataclasses import dataclass, field
from ..errors import ActionError
from ..core.transactions import transfer_gold

GUILD_FOUNDING_COST = 100
MAX_GUILD_MEMBERS = 20
WAR_MIN_MEMBERS = 10
RIGHTS = ("invite", "enlist", "milestones", "spoils")
ROLES = ("leader", "officer", "member")


@dataclass
class Guild:
    id: str
    name: str
    founder_id: str
    members: dict[str, str] = field(default_factory=dict)
    invited: set[str] = field(default_factory=set)
    rights: dict[str, set[str]] = field(default_factory=dict)
    enlisted: bool = False
    rating: int = 1000
    fortification: int = 0
    wins: int = 0
    losses: int = 0


@dataclass(frozen=True)
class WarRules:
    gain_hits: int = 10
    break_hits: int = 7
    route_min: int = 10
    route_max: int = 15
    control_minutes: int = 60
    week_minutes: int = 10080
    notice_minutes: int = 1440
    duration_minutes: int = 720


@dataclass
class WarRecord:
    id: str
    guild_a: str
    guild_b: str
    scheduled_minute: int
    end_minute: int
    roster_a: tuple[str, ...]
    roster_b: tuple[str, ...]
    practice: bool = False
    status: str = "notice"
    winner_id: str | None = None
    present: set[str] = field(default_factory=set)
    routed: dict[str, int] = field(default_factory=dict)
    pressure_a: int = 0
    pressure_b: int = 0
    advantage: str | None = None
    progress_a: int = 0  # half-minute units
    progress_b: int = 0
    honor: dict[str, int] = field(default_factory=dict)
    hits: dict[str, int] = field(default_factory=dict)
    unlocks: dict[str, set[str]] = field(default_factory=dict)
    used: dict[str, set[str]] = field(default_factory=dict)
    horn_until: int = 0
    dressings: dict[str, int] = field(default_factory=dict)
    dressing_cooldowns: dict[str, int] = field(default_factory=dict)
    heal_cooldowns: dict[str, int] = field(default_factory=dict)
    next_bot_tick: int = 0
    events: list[str] = field(default_factory=list)

    def roster(self, guild_id):
        return self.roster_a if guild_id == self.guild_a else self.roster_b

    def guild_of(self, actor_id):
        if actor_id in self.roster_a:
            return self.guild_a
        if actor_id in self.roster_b:
            return self.guild_b
        return None


class GuildSystem:
    def __init__(self, world):
        self.world = world

    def membership(self, actor_id):
        return next((g for g in self.world.state.guilds.values()
                     if actor_id in g.members), None)

    def can(self, guild, actor_id, right):
        return guild is not None and (
            guild.members.get(actor_id) == "leader"
            or right in guild.rights.get(actor_id, set()))

    def found(self, actor_id: str, name: str) -> dict:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        if self.membership(actor_id):
            raise ActionError("Leave your current guild before founding another")
        if not isinstance(name, str) or not 3 <= len(name.strip()) <= 40:
            raise ActionError("Guild name must have 3 to 40 characters")
        title = name.strip()
        if any(ord(ch) < 32 for ch in title):
            raise ActionError("Invalid guild name")
        if any(g.name.casefold() == title.casefold() for g in self.world.state.guilds.values()):
            raise ActionError("Guild name already claimed")
        transfer_gold(self.world, actor, None, GUILD_FOUNDING_COST)
        guild_id = "guild:" + str(self.world.state.next_guild_id)
        self.world.state.next_guild_id += 1
        guild = Guild(guild_id, title, actor_id, members={actor_id: "leader"})
        self.world.state.guilds[guild_id] = guild
        self.world._emit("guild_founded", actor_id, guild_id, title)
        return {"id": guild_id, "name": title}

    def invite(self, actor_id: str, candidate_id: str) -> None:
        guild = self.membership(actor_id)
        if not self.can(guild, actor_id, "invite"):
            raise ActionError("Invitation permission required")
        if candidate_id not in self.world.actors or candidate_id == actor_id:
            raise ActionError("Unknown invitee")
        if self.world.actors[candidate_id].kind != "human":
            raise ActionError("Only player characters can join guilds")
        if self.membership(candidate_id):
            raise ActionError("Character already belongs to a guild")
        if len(guild.members) >= MAX_GUILD_MEMBERS:
            raise ActionError("Guild roster is full")
        guild.invited.add(candidate_id)
        self.world._emit("guild_invited", guild.id, actor_id, candidate_id)

    def join(self, actor_id: str, guild_id: str) -> None:
        self.world._at_city(self.world._actor(actor_id))
        guild = self.world.state.guilds.get(guild_id)
        if guild is None or actor_id not in guild.invited:
            raise ActionError("A guild invitation is required")
        if self.membership(actor_id):
            raise ActionError("Character already belongs to a guild")
        if len(guild.members) >= MAX_GUILD_MEMBERS:
            raise ActionError("Guild roster is full")
        guild.invited.remove(actor_id)
        guild.members[actor_id] = "member"
        self.world._emit("guild_joined", guild.id, actor_id)

    def set_role(self, actor_id: str, member_id: str, role: str) -> None:
        guild = self.membership(actor_id)
        if guild is None or guild.members.get(actor_id) != "leader":
            raise ActionError("Only leader may appoint officers")
        if member_id not in guild.members or member_id == actor_id or role not in ("member", "officer"):
            raise ActionError("Invalid role or member")
        guild.members[member_id] = role
        self.world._emit("guild_role_changed", guild.id, member_id, role)

    def set_right(self, actor_id: str, member_id: str, right: str, enabled: bool):
        guild = self.membership(actor_id)
        if guild is None or guild.members.get(actor_id) != "leader":
            raise ActionError("Only the guild leader can delegate rights")
        if member_id not in guild.members or member_id == actor_id:
            raise ActionError("Select another guild member")
        if right not in RIGHTS or type(enabled) is not bool:
            raise ActionError("Unknown permission")
        granted = guild.rights.setdefault(member_id, set())
        if enabled:
            granted.add(right)
        else:
            granted.discard(right)
        self.world._emit("guild_right_changed", guild.id, actor_id, member_id, right, enabled)

    def enlist(self, actor_id: str, enabled: bool):
        guild = self.membership(actor_id)
        if not self.can(guild, actor_id, "enlist"):
            raise ActionError("War enrollment permission required")
        if type(enabled) is not bool:
            raise ActionError("Invalid enrollment value")
        if enabled and not WAR_MIN_MEMBERS <= len(guild.members) <= MAX_GUILD_MEMBERS:
            raise ActionError("Ranked wars require 10–20 guild members")
        if self.world.war_system.pending_for(guild.id):
            raise ActionError("Cannot change enrollment during a scheduled or live war")
        guild.enlisted = enabled
        self.world._emit("guild_enlisted", guild.id, actor_id, enabled)

    def leave(self, actor_id: str) -> None:
        guild = self.membership(actor_id)
        if guild is None:
            raise ActionError("You do not belong to a guild")
        if self.world.war_system.pending_for(guild.id):
            raise ActionError("Guild roster is locked during a war")
        if guild.members[actor_id] == "leader" and len(guild.members) > 1:
            raise ActionError("Transfer leadership before leaving a populated guild")
        del guild.members[actor_id]
        guild.rights.pop(actor_id, None)
        guild.enlisted = False
        if not guild.members:
            del self.world.state.guilds[guild.id]
        self.world._emit("guild_left", guild.id, actor_id)

    def view(self, actor_id: str) -> dict:
        guild = self.membership(actor_id)
        war = self.world.war_system.view(actor_id)
        return {"my_guild": None if guild is None else {
            "id": guild.id, "name": guild.name,
            "role": guild.members[actor_id], "members": dict(guild.members),
            "rights": {k: sorted(v) for k, v in guild.rights.items()},
            "my_rights": list(RIGHTS) if guild.members[actor_id] == "leader"
                         else sorted(guild.rights.get(actor_id, set())),
            "enlisted": guild.enlisted,
            "rating": guild.rating, "wins": guild.wins, "losses": guild.losses,
        }, "invitations": [{"id": g.id, "name": g.name}
                           for g in self.world.state.guilds.values()
                           if actor_id in g.invited],
        "directory": [{"id": g.id, "name": g.name, "members": len(g.members)}
                      for g in self.world.state.guilds.values()],
        "founding_cost": GUILD_FOUNDING_COST, "war_enabled": True,
        "rules": WarRules().__dict__.copy(),
        "next_match_minute": ((self.world.minute // 10080) + 1) * 10080,
        "war": war}
