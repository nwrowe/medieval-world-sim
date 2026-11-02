# Next milestone: Magic as a multi-activity progression system

**Status:** Planned, not yet implemented. This is a design target for the next slice after regional trading.

The goal is the open-ended progression and income variety of a crime-like activity system, but with fantasy **magic schools** that also have genuine utility elsewhere in the game. It must not be a separate minigame disconnected from crafting, markets, travel, and combat.

## Basic progression model

Every character begins with **100 maximum mana** (separate from stamina, life and employment stats). Mana replenishes over simulated time. Character expertise is **per magical discipline**, not a single universal magic score. Each attempted magical activity consumes mana; meaningful successful activity grants skill experience, with bounded practice credit on failure. Learning allows access to higher-tier spells.

The initial prototype should use deterministic seeded rolls driven by spell difficulty, school skill, and a small luck term. Success chance should improve gradually, with a floor/ceiling and safeguards against unlimited practice XP and guaranteed money.

Suggested discipline tracks:

| School | Low-tier activity | Earn gold how? | Utility elsewhere |
|---|---|---|---|
| Restoration | Cleanse water / mend small injuries | Paid medical contracts or direct patient payment | Heal allies, reduce recovery duration |
| Enchantment | Minor equipment imbuement | Enchant customer gear for a fee | Boost gear efficiency, wear resistance |
| Divination | Identify materials, read omens | Funded caravan forecasts, identification | Reveal trade demand, improve scouting |
| Warding | Secure a store or caravan | Guard contracts | Protect traders, improve defense |
| Elemental | Kindle furnaces, manage fires | Paid forge/sawmill work | Combat spells, faster production |
| Alchemy | Purify reagents | Sell actual potions made with real ingredients | Potions, resistances and recovery |

A new player can specialize without mandatory combat; medical, merchant and artisan play all benefit from spells. Experience should not automatically pay coins: magic work earns income only when a funded beneficiary purchases a service or finished product.

## Mechanics to implement in small PRs

1. **Mana and schools:** a composed \`MagicState\` on Actor, validated mana spending, passive regeneration, school XP and tier gating, deterministic seeded probability/ability rolls. Avoid direct state mutations by NPCs.
2. **Daily magical jobs:** city-funded requests with real budget, action cooldowns, school XP, and conservative pay caps. A few simple tasks per school suffice to test engagement; a failed job consumes mana but does not trigger a payout.
3. **Useful spells:** restoration reduces injuries (subject to defeating/revive rules), enchanting consumes materials and modifies real gear, divination exposes limited market information, wards improve caravan safety; combat magic uses the same attack checks and cannot circumvent combat stamina/defeat rules.
4. **NPC policies and testing:** add novice mage and specialized service NPCs, test economic conservation, mana/XP abuse, skill growth, spell effect caps, chance distributions and long-run balance across seeded 30/90-day runs.

## Balancing and safety criteria

- Mana regenerates on its own clock, separately from physical stamina, and doesn't provide free gold.
- Every paid spell has an **existing payer** (patient, company, city or contract escrow) and an explicit cap/limit; no spammable city payouts.
- A spell cannot retroactively bypass completed travel, bank money, consume nonexistent materials, or mutate a target without the authoritative world rules.
- The best magical careers should be viable alternatives to trading, business ownership and combat, not strictly better than all of them.
- Random failures should create some variety but must never silently erase someone else's equipment or funds.
