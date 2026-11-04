"""World-authoritative chat channels with participant-only access.

Local browser mode can post self-authored preview messages. Real multiplayer
requires separate account identities and shared durable storage before chat
between independently authenticated humans may be enabled.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ActionError

MAX_MESSAGE_LENGTH = 400
MAX_MESSAGES_SAVED = 1000
MAX_ROOM_MEMBERS = 20
MAX_ROOMS_PER_CREATOR = 5


@dataclass(frozen=True)
class ChatMessage:
    id: int
    kind: str
    target: str
    author: str
    recipient: str
    body: str
    minute: int


@dataclass
class ChatRoom:
    id: str
    creator: str
    name: str
    members: set[str] = field(default_factory=set)


class ChatSystem:
    def __init__(self, world):
        self.world = world

    def _human(self, principal_id: str):
        actor = self.world._actor(principal_id)
        if actor.kind != "human":
            raise ActionError("Only players may use chat")
        return actor

    def _company_member(self, principal_id: str, company_id: str) -> bool:
        company = self.world.companies.get(company_id)
        return bool(company and (company.owner_id == principal_id or
                                 principal_id in company.employees))

    def _can_read(self, principal_id: str, record: ChatMessage) -> bool:
        if record.kind == "global":
            return True
        if record.kind == "direct":
            return principal_id in (record.author, record.recipient)
        if record.kind == "company":
            return self._company_member(principal_id, record.target)
        if record.kind == "guild":
            guild = self.world.state.guilds.get(record.target)
            return bool(guild and principal_id in guild.members)
        if record.kind == "room":
            room = self.world.state.chat_rooms.get(record.target)
            return bool(room and principal_id in room.members)
        return False

    def _validate_channel(self, principal_id: str, kind: str, target: str) -> str:
        if kind not in ("global", "direct", "company", "guild", "room"):
            raise ActionError("Unknown chat channel")
        if not isinstance(target, str) or len(target) > 100:
            raise ActionError("Invalid channel target")
        if kind == "global":
            if target:
                raise ActionError("Global chat has no channel target")
            return ""
        if kind == "direct":
            recipient = self.world._actor(target)
            if recipient.kind != "human" or target == principal_id:
                raise ActionError("Direct messages require another real player")
            return target
        if kind == "company":
            if not self._company_member(principal_id, target):
                raise ActionError("Company chat membership is required")
            return target
        if kind == "guild":
            guild = self.world.state.guilds.get(target)
            if guild is None or principal_id not in guild.members:
                raise ActionError("Guild chat membership is required")
            return target
        room = self.world.state.chat_rooms.get(target)
        if room is None or principal_id not in room.members:
            raise ActionError("Custom room membership is required")
        return target

    def send(self, principal_id: str, kind: str, target: str, text: str) -> dict:
        self._human(principal_id)
        target = self._validate_channel(principal_id, kind, target)
        if (not isinstance(text, str) or not 1 <= len(text.strip()) <= MAX_MESSAGE_LENGTH
                or any(ord(ch) < 32 and ch not in "\n\t" for ch in text)):
            raise ActionError("Message must contain 1–400 printable characters")
        message = ChatMessage(self.world.state.next_chat_id, kind, target, principal_id,
                              target if kind == "direct" else "", text.strip(),
                              self.world.minute)
        self.world.state.next_chat_id += 1
        self.world.state.chat_messages.append(message)
        if len(self.world.state.chat_messages) > MAX_MESSAGES_SAVED:
            del self.world.state.chat_messages[:len(self.world.state.chat_messages) - MAX_MESSAGES_SAVED]
        return {"id": message.id, "posted": True}

    def create_room(self, principal_id: str, name: str, members: list[str]) -> dict:
        self._human(principal_id)
        if (not isinstance(name, str) or not 3 <= len(name.strip()) <= 40
                or any(ord(c) < 32 for c in name)):
            raise ActionError("Room name must contain 3–40 printable characters")
        if (not isinstance(members, list) or len(members) > MAX_ROOM_MEMBERS - 1
                or any(not isinstance(m, str) or len(m) > 100 for m in members)
                or len(members) != len(set(members)) or principal_id in members):
            raise ActionError("Invalid custom chat membership")
        for member in members:
            if self.world._actor(member).kind != "human":
                raise ActionError("Custom rooms may invite only real player accounts")
        if sum(room.creator == principal_id for room in
               self.world.state.chat_rooms.values()) >= MAX_ROOMS_PER_CREATOR:
            raise ActionError("Custom room limit reached")
        room_id = "room:" + str(self.world.state.next_chat_room_id)
        self.world.state.next_chat_room_id += 1
        room = ChatRoom(room_id, principal_id, name.strip(), set(members) | {principal_id})
        self.world.state.chat_rooms[room_id] = room
        return {"id": room_id, "name": room.name}

    def view(self, principal_id: str) -> dict:
        self._human(principal_id)
        channels = [{"key": "global", "kind": "global", "target": "",
                     "label": "Global"}]
        guild = self.world.guild_system.membership(principal_id)
        if guild:
            channels.append({"key": "guild:" + guild.id, "kind": "guild",
                             "target": guild.id, "label": guild.name})
        for company in self.world.companies.values():
            if self._company_member(principal_id, company.id):
                channels.append({"key": "company:" + company.id, "kind": "company",
                                 "target": company.id, "label": company.id})
        for room in self.world.state.chat_rooms.values():
            if principal_id in room.members:
                channels.append({"key": room.id, "kind": "room",
                                 "target": room.id, "label": room.name})
        peers = set()
        for msg in self.world.state.chat_messages:
            if msg.kind == "direct" and self._can_read(principal_id, msg):
                peers.add(msg.recipient if msg.author == principal_id else msg.author)
        for peer in sorted(peers):
            channels.append({"key": "direct:" + peer, "kind": "direct",
                             "target": peer, "label": peer})
        visible = []
        for msg in self.world.state.chat_messages:
            if not self._can_read(principal_id, msg):
                continue
            key = ("direct:" + (msg.recipient if msg.author == principal_id else msg.author)
                   if msg.kind == "direct"
                   else msg.kind if msg.kind == "global" else msg.kind + ":" + msg.target)
            visible.append({"id": msg.id, "channel_key": key,
                            "sender": msg.author, "body": msg.body, "minute": msg.minute})
        return {"channels": channels, "messages": visible[-100:]}
