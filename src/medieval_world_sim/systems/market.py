from __future__ import annotations

from ..catalog import GOODS
from ..equipment import GEAR
from ..core.entities import Actor, Offer
from ..errors import ActionError
from ..core.transactions import transfer_gold


class MarketSystem:
    def __init__(self, world):
        self.world = world

    def post_offer(self, initiator_id: str, seller_id: str, item: str, quantity: int, unit_price: int) -> int:
        seller = self.world._account(seller_id)
        self.world._authorize(initiator_id, seller)
        city = self.world._at_city(seller)
        self.world._positive(quantity, "quantity")
        self.world._nonnegative(unit_price, "unit_price")
        if item not in GOODS or seller.inventory.get(item, 0) < quantity:
            raise ActionError("Seller lacks offered resources")
        seller.inventory[item] -= quantity
        offer_id = self.world.next_offer_id
        self.world.next_offer_id += 1
        self.world.offers[offer_id] = Offer(offer_id, seller_id, city, item, quantity, unit_price)
        self.world._emit("offer_posted", offer_id, seller_id, city, item, quantity, unit_price)
        self.world.assert_invariants()
        return offer_id

    def post_equipment_offer(self, initiator_id: str, seller_id: str, gear_id: int, unit_price: int) -> int:
        """A specific quality/durability-bearing item is escrowed by unique ID."""
        seller = self.world._account(seller_id)
        self.world._authorize(initiator_id, seller)
        city = self.world._at_city(seller)
        self.world._nonnegative(unit_price, "unit_price")
        if gear_id not in seller.gear_ids:
            raise ActionError("Seller does not own this equipment")
        seller.gear_ids.remove(gear_id)
        if isinstance(seller, Actor):
            for slot, equipped in list(seller.equipped.items()):
                if equipped == gear_id:
                    del seller.equipped[slot]
        item = self.world.gear[gear_id]
        offer_id = self.world.next_offer_id
        self.world.next_offer_id += 1
        self.world.offers[offer_id] = Offer(offer_id, seller_id, city, item.kind, 1, unit_price, gear_id)
        self.world._emit("equipment_offered", offer_id, seller_id, gear_id, item.quality, unit_price)
        self.world.assert_invariants()
        return offer_id

    def accept_offer(self, initiator_id: str, buyer_id: str, offer_id: int, quantity: int) -> None:
        buyer = self.world._account(buyer_id)
        self.world._authorize(initiator_id, buyer)
        offer = self.world.offers.get(offer_id)
        if offer is None:
            raise ActionError("Unknown or exhausted offer")
        self.world._positive(quantity, "quantity")
        if buyer_id == offer.seller_id or self.world._at_city(buyer) != offer.city:
            raise ActionError("Cannot accept your own offer or trade remotely")
        if (quantity > offer.quantity or (offer.gear_id is not None and quantity != 1)
                or not self.world._space_for(buyer, offer.item, quantity)):
            raise ActionError("Insufficient stock or carrying capacity")
        total = quantity * offer.unit_price
        if buyer.gold < total:
            raise ActionError("Buyer lacks gold")
        seller = self.world._account(offer.seller_id)
        transfer_gold(self.world, buyer, seller, total)
        if offer.gear_id is not None:
            buyer.gear_ids.append(offer.gear_id)
        else:
            self.world._add(buyer, offer.item, quantity)
        offer.quantity -= quantity
        if offer.quantity == 0:
            del self.world.offers[offer_id]
        self.world._emit("offer_filled", offer_id, buyer_id, quantity, total)
        self.world.assert_invariants()

    def cancel_offer(self, initiator_id: str, offer_id: int) -> None:
        offer = self.world.offers.get(offer_id)
        if offer is None:
            raise ActionError("Unknown offer")
        seller = self.world._account(offer.seller_id)
        self.world._authorize(initiator_id, seller)
        if self.world._at_city(seller) != offer.city:
            raise ActionError("Return to listing city to withdraw escrowed goods")
        if not self.world._space_for(seller, offer.item, offer.quantity):
            raise ActionError("Not enough space to reclaim goods")
        if offer.gear_id is not None:
            seller.gear_ids.append(offer.gear_id)
        else:
            self.world._add(seller, offer.item, offer.quantity)
        del self.world.offers[offer_id]
        self.world._emit("offer_canceled", offer_id)
        self.world.assert_invariants()

