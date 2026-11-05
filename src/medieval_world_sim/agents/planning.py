"""Opt-in whole-route logistics for the offline Optimizer playtester.

The planner only proposes commands. WorldEngine executes and validates them.
No private city stock, mutation privileges, or model output are involved.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..catalog import CAPITAL, CITIES
from ..systems.regional_trade import BASE_LOCAL_ASK
from .observation import NPCView


@dataclass(frozen=True)
class RouteOption:
    name: str
    params: dict[str, object]
    score: float
    projected_profit: int = 0


def route_candidates(view: NPCView) -> tuple[RouteOption, ...]:
    """Select only feasible, projected profitable *cross-city* trades.

    The capital quote is public and reflects the current bid, quota and
    treasury. Source-city stock is only observed when physically present.
    Forecasts are not guarantees; changed prices or depleted budgets can
    postpone or prevent liquidation.
    """
    load = sum(view.stock(k) for k, _ in view.inventory) + len(view.gear)
    capacity = max(0, view.travel_cargo_limit - load)
    if capacity == 0 or view.gold < 5:
        return ()
    proposals: list[RouteOption] = []
    if view.city == CAPITAL:
        for city, spec in CITIES.items():
            if city == CAPITAL:
                continue
            choices = []
            for item in spec.deposits:
                bid = view.regional_quote(item, capital=True)
                estimated_cost = BASE_LOCAL_ASK[item] + 1  # conservative empty-stock premium
                if bid is None or bid.player_sell_price <= estimated_cost:
                    continue
                quantity = min(4, capacity, view.gold // estimated_cost,
                               bid.buy_capacity,
                               bid.city_gold // bid.player_sell_price)
                if quantity:
                    projected = quantity * (bid.player_sell_price - estimated_cost)
                    choices.append((projected, item))
            if choices:
                projected, _ = max(choices)
                proposals.append(RouteOption(
                    "travel", {"destination": city},
                    min(20.0, 15 + projected / 5), projected))
    else:
        for quote in view.regional_quotes:
            if quote.item not in CITIES[view.city].deposits:
                continue  # Purchasing imports locally is rarely good arbitrage.
            bid = view.regional_quote(quote.item, capital=True)
            if bid is None or bid.player_sell_price <= quote.player_buy_price:
                continue
            quantity = min(4, capacity, view.gold // quote.player_buy_price,
                           quote.sell_capacity, bid.buy_capacity,
                           bid.city_gold // bid.player_sell_price)
            if quantity > 0:
                projected = quantity * (bid.player_sell_price - quote.player_buy_price)
                proposals.append(RouteOption(
                    "regional_buy", {"item": quote.item, "quantity": quantity},
                    min(23.0, 16 + projected / 4), projected))
    return tuple(sorted(proposals,
                        key=lambda option: (-option.projected_profit,
                                            str(option.params))))


def deliver_route(view: NPCView, plan) -> RouteOption | None:
    """Continue a committed route without allowing a local buy/sell loop."""
    if plan is None or plan.remaining <= 0:
        return None
    if view.stock(plan.item) < plan.remaining:
        # Missing stock should be visible as a stalled objective, not silently
        # replaced by an unrelated or unjustified transaction.
        return None
    if view.city != plan.destination:
        load = sum(q for _, q in view.inventory) + len(view.gear)
        if load <= view.travel_cargo_limit:
            return RouteOption("travel", {"destination": plan.destination}, 100)
        return None
    bid = view.regional_quote(plan.item)
    if bid is None or bid.player_sell_price <= 0:
        return None
    quantity = min(plan.remaining, bid.buy_capacity,
                   bid.city_gold // bid.player_sell_price)
    if quantity <= 0:
        return None
    return RouteOption("regional_sell", {"item": plan.item, "quantity": quantity}, 100)


def recover_route(view: NPCView, plan) -> RouteOption | None:
    """Bounded fallback for a funded route whose destination has dried up.

    Never pretend to have sold cargo. Try one other importer after three days,
    then locally store unliquidated cargo after seven days, preserving ownership
    and cost-basis diagnostics instead of trapping the agent indefinitely.
    """
    if plan is None or view.stock(plan.item) < plan.remaining:
        return None
    age = view.minute - plan.start_minute
    if age >= 7 * 1440:
        return RouteOption("store_goods", {
            "item": plan.item, "quantity": plan.remaining}, 99)
    if (age < 3 * 1440 or plan.recovery_attempts
            or view.city != CAPITAL or plan.destination != CAPITAL):
        return None
    # The other city's bid is an estimate, not a promised sale. No private
    # treasury balances or inaccessible inventory are observed remotely.
    alternatives = [city for city, spec in sorted(CITIES.items())
                    if city not in (CAPITAL, plan.source)
                    and plan.item not in spec.deposits]
    if not alternatives:
        return None
    return RouteOption("travel", {"destination": alternatives[0]}, 98)
