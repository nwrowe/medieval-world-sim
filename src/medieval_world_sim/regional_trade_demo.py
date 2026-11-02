"""An honest three-unit arbitrage route with real gold, stock and travel."""
from .core.engine import WorldEngine
from .core.entities import Actor
from .catalog import CAPITAL


def main() -> None:
    world = WorldEngine([Actor("merchant", "human", city="ironvale", gold=100)])
    first_gold = world.actors["merchant"].gold
    beginning = world.total_gold
    local = world.regional_quote("ironvale", "iron_ore")
    destination = world.regional_quote(CAPITAL, "iron_ore")
    quantity = 3
    print(f"Ironvale: buy iron ore for {local.player_buy_price}g per unit.")
    print(f"Crownreach: sell iron ore for {destination.player_sell_price}g per unit.")
    spent = world.execute("merchant", "regional_buy", {
        "item": "iron_ore", "quantity": quantity
    }, "buy-ironvale")
    minutes = world.execute("merchant", "travel", {
        "destination": CAPITAL
    }, "depart-ironvale")
    world.advance(minutes)
    earned = world.execute("merchant", "regional_sell", {
        "item": "iron_ore", "quantity": quantity
    }, "sell-crownreach")
    world.assert_invariants()
    print(f"Travel: {minutes} minutes carrying {quantity} units (limit 12).")
    print(f"Spent: {spent}g | Received: {earned}g | Gross trade profit: {earned - spent}g")
    print(f"Merchant wallet: {first_gold}g -> {world.actors['merchant'].gold}g")
    print(f"Gold conserved: {world.total_gold == beginning}")


if __name__ == "__main__":
    main()
