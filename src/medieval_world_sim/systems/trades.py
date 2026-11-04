"""Atomic, two-party asset exchanges. Not exposed by the single-player HTTP app.

The caller/principal is supplied by an authenticated server, never read from
the client trade payload. The maker's assets are escrowed at proposal time.
The recipient accepts *exact immutable terms* or can reject. Direct transfers
are not possible without the recipient's explicit acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from ..catalog import GOODS
from ..errors import ActionError

MAX_TRADE_ASSETS = 16
MAX_TRADE_ITEMS = 100_000
MAX_TRADE_GOLD = 1_000_000_000_000
MAX_OPEN_TRADES_PER_USER = 10


@dataclass(frozen=True)
class TradeAssets:
    gold: int
    items: tuple[tuple[str, int], ...]
    gear_ids: tuple[int, ...]

    @classmethod
    def parse(cls, value: dict) -> "TradeAssets":
        if not isinstance(value, dict) or set(value) != {"gold", "items", "gear_ids"}:
            raise ActionError("Trade assets require gold, items, and gear_ids")
        gold, items, gear = value["gold"], value["items"], value["gear_ids"]
        if type(gold) is not int or not 0 <= gold <= MAX_TRADE_GOLD:
            raise ActionError("Invalid trade gold quantity")
        if not isinstance(items, list) or len(items) > MAX_TRADE_ASSETS:
            raise ActionError("Invalid trade item list")
        parsed = []
        seen = set()
        for entry in items:
            if not isinstance(entry, dict) or set(entry) != {"item", "quantity"}:
                raise ActionError("Invalid trade item")
            item, quantity = entry["item"], entry["quantity"]
            if (not isinstance(item, str) or item not in GOODS
                    or type(quantity) is not int or not 1 <= quantity <= MAX_TRADE_ITEMS
                    or item in seen):
                raise ActionError("Invalid or duplicate trade item")
            seen.add(item)
            parsed.append((item, quantity))
        if (not isinstance(gear, list) or len(gear) > MAX_TRADE_ASSETS
                or any(type(g) is not int or g <= 0 for g in gear)
                or len(set(gear)) != len(gear)):
            raise ActionError("Invalid or duplicate trade equipment")
        return cls(gold, tuple(sorted(parsed)), tuple(sorted(gear)))

    def export(self) -> dict:
        return {"gold": self.gold,
                "items": [{"item": item, "quantity": count} for item, count in self.items],
                "gear_ids": list(self.gear_ids)}

    def empty(self) -> bool:
        return not (self.gold or self.items or self.gear_ids)


@dataclass(frozen=True)
class TradeProposal:
    id: int
    maker: str
    recipient: str
    city: str
    offer: TradeAssets
    request: TradeAssets
    terms_hash: str

    def view(self) -> dict:
        return {"id": self.id, "maker": self.maker, "recipient": self.recipient,
                "city": self.city, "offer": self.offer.export(),
                "request": self.request.export(), "terms_hash": self.terms_hash}


class TradeSystem:
    def __init__(self, world):
        self.world = world

    def _actors(self, maker_id: str, recipient_id: str):
        if maker_id == recipient_id:
            raise ActionError("Cannot trade with yourself")
        maker, recipient = self.world._actor(maker_id), self.world._actor(recipient_id)
        if maker.kind != "human" or recipient.kind != "human":
            raise ActionError("Bilateral trade requires two player accounts")
        if self.world._at_city(maker) != self.world._at_city(recipient):
            raise ActionError("Both players must be in the same city")
        return maker, recipient

    def _verify_holdings(self, actor, assets: TradeAssets) -> None:
        if actor.gold < assets.gold:
            raise ActionError("Insufficient gold for proposed trade")
        for item, quantity in assets.items:
            if actor.inventory.get(item, 0) < quantity:
                raise ActionError("Insufficient inventory for proposed trade")
        if not set(assets.gear_ids).issubset(actor.gear_ids):
            raise ActionError("Player does not own all proposed equipment")

    def _withdraw(self, actor, assets: TradeAssets) -> None:
        self._verify_holdings(actor, assets)
        actor.gold -= assets.gold
        for item, quantity in assets.items:
            actor.inventory[item] -= quantity
        for gear_id in assets.gear_ids:
            actor.gear_ids.remove(gear_id)
            for slot, active_id in list(actor.equipped.items()):
                if active_id == gear_id:
                    del actor.equipped[slot]

    @staticmethod
    def _deposit(actor, assets: TradeAssets) -> None:
        actor.gold += assets.gold
        for item, quantity in assets.items:
            actor.inventory[item] = actor.inventory.get(item, 0) + quantity
        actor.gear_ids.extend(assets.gear_ids)

    @staticmethod
    def _hash(maker: str, recipient: str, city: str, offer: TradeAssets,
              request: TradeAssets) -> str:
        payload = json.dumps([maker, recipient, city, offer.export(), request.export()],
                             sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def propose(self, principal_id: str, recipient_id: str, offer_data: dict,
                request_data: dict) -> dict:
        maker, _ = self._actors(principal_id, recipient_id)
        if sum(t.maker == principal_id for t in self.world.state.trades.values()) >= MAX_OPEN_TRADES_PER_USER:
            raise ActionError("Too many outstanding trades")
        offer, request = TradeAssets.parse(offer_data), TradeAssets.parse(request_data)
        if offer.empty() and request.empty():
            raise ActionError("A trade must exchange or give at least one asset")
        if set(offer.gear_ids) & set(request.gear_ids):
            raise ActionError("Both sides cannot offer the same equipment")
        self._verify_holdings(maker, offer)
        trade_id = self.world.state.next_trade_id
        self.world.state.next_trade_id += 1
        proposal = TradeProposal(
            trade_id, principal_id, recipient_id, maker.city, offer, request,
            self._hash(principal_id, recipient_id, maker.city, offer, request),
        )
        self._withdraw(maker, offer)
        self.world.state.trades[trade_id] = proposal
        self.world._emit("trade_proposed", principal_id, recipient_id, trade_id)
        return proposal.view()

    def accept(self, principal_id: str, trade_id: int, terms_hash: str) -> dict:
        if type(trade_id) is not int:
            raise ActionError("Invalid trade ID")
        proposal = self.world.state.trades.get(trade_id)
        if proposal is None:
            raise ActionError("Trade is closed or does not exist")
        if principal_id != proposal.recipient:
            raise ActionError("Only the designated recipient can accept")
        if not isinstance(terms_hash, str) or terms_hash != proposal.terms_hash:
            raise ActionError("Trade terms have not been confirmed")
        maker, recipient = self._actors(proposal.maker, proposal.recipient)
        if maker.city != proposal.city:
            raise ActionError("Trade parties have changed city")
        self._verify_holdings(recipient, proposal.request)
        # Consume the recipient's requested assets and release maker escrow in
        # a single engine-level atomic_action, before the proposal is removed.
        self._withdraw(recipient, proposal.request)
        self._deposit(maker, proposal.request)
        self._deposit(recipient, proposal.offer)
        del self.world.state.trades[trade_id]
        self.world._emit("trade_settled", proposal.maker, principal_id, trade_id)
        return {"id": trade_id, "status": "accepted"}

    def close(self, principal_id: str, trade_id: int) -> dict:
        if type(trade_id) is not int:
            raise ActionError("Invalid trade ID")
        proposal = self.world.state.trades.get(trade_id)
        if proposal is None:
            raise ActionError("Trade is closed or does not exist")
        if principal_id not in (proposal.maker, proposal.recipient):
            raise ActionError("Not a participant in this trade")
        maker = self.world._actor(proposal.maker)
        self._deposit(maker, proposal.offer)
        del self.world.state.trades[trade_id]
        self.world._emit("trade_closed", principal_id, trade_id)
        return {"id": trade_id, "status": "closed"}

    def list_for(self, principal_id: str) -> list[dict]:
        self.world._actor(principal_id)
        return [trade.view() for trade in self.world.state.trades.values()
                if principal_id in (trade.maker, trade.recipient)]
