# Autonomous NPC economy — 30 simulated days

**Scenario:** 50 autonomous NPCs, five cities, four staffed capital companies, seed 42, six simulated hours between NPC decisions, 30 days total. These are reproducible results from GitHub Actions on the `feat/stochastic-npc-economy` branch (November 2, 2026). The model is an experiment, not a balanced game economy.

## Observed outcomes

| Metric | Result |
|---|---:|
| NPCs / simulated days / decision ticks | 50 / 30 / 120 |
| Market transactions | 232 |
| Gold transacted across markets | 4,207 |
| Raw resource units gathered | 648 |
| Staffed production shifts | 155 |
| Crafted pieces of equipment | 36 |
| Equipment purchases | 8 |
| NPC combat attacks | 6 |
| Gold before / after | 5,400 / 5,400 |
| Invalid action proposals | 0 |
| Idle decisions | 4,663 |

### Business liquidity

Four companies each started with 430 gold invested by their NPC owner. After 30 days their remaining **cash** was:

| Company | Gold remaining |
|---|---:|
| Steelworks | 2 |
| Forge | 23 |
| Tannery | 0 |
| Leatherworking | 1 |

These are *cash balances, not profits*. Unsold equipment, intermediate goods, escrowed inventory, and other assets have not been marked to market. A company with no cash may own unsold products. Its challenge is **liquidity**, not necessarily negative net worth.

## Interpretation

The NPC engine accomplished its immediate objective: independent decisions produced intercity travel, extraction, genuine resource transactions, company-funded shifts, crafting, equipment purchases, and combat. There was no script telling a buyer to purchase a particular batch of ore, coal, steel, or armor.

The economy is **not self-sustaining yet**. The population generated 36 crafted equipment pieces but purchased only eight, so manufacturers had insufficient end-customer demand. Three companies ended nearly or completely out of cash, despite accounting conservation. By design, no automatic subsidy was introduced to conceal this failure.

This prototype does not yet charge citizens for food or housing, establish repair and replacement demand, provide regular funded bounties, or give company owners a sophisticated liquidity-preserving budget. Its rule-based policies optimize bounded local opportunities, not mathematically optimal long-term profit.

## Next experiments

1. Add consumption sinks and real buyer needs (food, lodging, item condition, tools) with the same wallet accounting.
2. Give companies spending limits based on cash runway and expected sales; measure inventory turnover.
3. Compare demand/production/shortage curves over multiple seeds (e.g. 11, 42, 73).
4. Only then test a *contextual bandit* selecting pricing and production decisions based on realized profit; compare to the fixed stochastic rule baseline.

Run the experiment:

```bash
python -m medieval_world_sim.agents.demo --npcs 50 --days 30 --seed 42 --json
```

The extended 30-day scenario is also exercised in CI. Unlike a constant-output mock, it will reveal future changes in sales, production, and market volume.
