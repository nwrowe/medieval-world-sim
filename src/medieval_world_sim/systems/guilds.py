"""Guild identity and membership, with ranked-war rules defined but not activated.

Do not use ordinary PvP hospitalization as ranked-war state. Ranked war
requires a separate combat resolver, snapshot roster, and trusted matchmaker.
"""
from dataclasses import dataclass, field
from ..errors import ActionError
from ..core.transactions import transfer_gold

GUILD_FOUNDING_COST = 100
MAX_GUILD_MEMBERS = 25
WAR_NOTICE_MINUTES = 1440
WAR_LENGTH_MINUTES = 1440
WAR_TARGET_PER_MEMBER = 500
ROLES = ("leader", "officer", "member")

@dataclass
class Guild:
    id: str
    name: str
    founder_id: str
    members: dict[str, str] = field(default_factory=dict)
    invited: set[str] = field(default_factory=set)
    rating: int = 1000
    fortification: int = 0
    wins: int = 0
    losses: int = 0

@dataclass(frozen=True)
class WarRules:
    notice_minutes: int = WAR_NOTICE_MINUTES
    duration_minutes: int = WAR_LENGTH_MINUTES
    target_per_roster_member: int = WAR_TARGET_PER_MEMBER
    cumulative_score: bool = True
    winner_by_high_score_at_timeout: bool = True
    allow_surrender: bool = True
    isolate_outside_interference: bool = True
    roster_snapshot_required: bool = True

@dataclass
class WarRecord:
    id: str
    guild_a: str
    guild_b: str
    scheduled_minute: int
    end_minute: int
    roster_a: tuple[str, ...]
    roster_b: tuple[str, ...]
    target_score: int
    score_a: int = 0
    score_b: int = 0
    contributions: dict[str, int] = field(default_factory=dict)
    status: str = "notice"  # notice, live, surrendered, completed
    winner_id: str | None = None

def reward_proposal(participation: int, contribution: int, winning: bool) -> dict:
    """A *non-paying* preview of the three-part reward allocation."""
    if any(type(x) is not int or x < 0 for x in (participation, contribution)):
        raise ValueError("Invalid contribution values")
    return {"participation": participation, "performance": contribution,
            "victory": contribution // 2 if winning else 0}

class GuildSystem:
    def __init__(self, world):
        self.world = world

    def membership(self, actor_id):
        return next((g for g in self.world.state.guilds.values()
                     if actor_id in g.members), None)

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
        if guild is None or guild.members[actor_id] not in ("leader", "officer"):
            raise ActionError("Only guild leadership may invite")
        if candidate_id not in self.world.actors or candidate_id == actor_id:
            raise ActionError("Unknown invitee")
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

    def leave(self, actor_id: str) -> None:
        guild = self.membership(actor_id)
        if guild is None:
            raise ActionError("You do not belong to a guild")
        if guild.members[actor_id] == "leader" and len(guild.members) > 1:
            raise ActionError("Transfer leadership before leaving a populated guild")
        del guild.members[actor_id]
        if not guild.members:
            del self.world.state.guilds[guild.id]
        self.world._emit("guild_left", guild.id, actor_id)

    def view(self, actor_id: str) -> dict:
        guild = self.membership(actor_id)
        return {"my_guild": None if guild is None else {
            "id": guild.id, "name": guild.name,
            "role": guild.members[actor_id], "members": dict(guild.members),
            "rating": guild.rating, "wins": guild.wins, "losses": guild.losses,
            "fortification": guild.fortification,
        }, "directory": [{"id": g.id, "name": g.name, "members": len(g.members)}
                         for g in self.world.state.guilds.values()],
        "founding_cost": GUILD_FOUNDING_COST, "war_enabled": False,
        "rules": WarRules().__dict__.copy()}
