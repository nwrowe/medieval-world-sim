# First Baseline Experiment

**Reproduce:** `python -m medieval_world_sim --citizens 200 --days 30 --seed 42`

**Model:** single settlement; 80 farmers, 40 woodcutters, 40 miners, 20 blacksmiths, 20 guards. Fixed prices; no taxes or money creation; finite treasury starts at 5,000 gold. Every citizen starts with 30 gold and 3 food. Routine NPCs follow scripted economic rules, not LLMs.

| Day | Treasury | Gini (citizen gold) | Hungry citizens that day | Total food inventory |
|---:|---:|---:|---:|---:|
| 0 | 5,000 | 0.000 | 0 | 600 |
| 6 | 3,240 | 0.202 | 0 | 1,320 |
| 12 | 1,200 | 0.308 | 0 | 2,040 |
| 18 | 2 | 0.422 | 0 | 2,760 |
| 24 | 2 | 0.495 | 37 | 3,660 |
| 30 | 2 | 0.554 | 47 | 4,644 |

## Observation

The treasury exhausts its purchasing power, withdrawing guard wages and sword demand. Citizen wealth inequality rises. Despite aggregate food stocks increasing, a growing number of citizens cannot obtain food because they lack gold. This is **not evidence about real-world or player behavior**; it is a deliberately simple demonstration of why circulation, distribution, production incentives, and rules for fiscal inflows/outflows all matter.

## Next experiments

- Vary treasury starting gold and government outflows.
- Add taxes, tariffs, minting rules and explicit resource/money sinks as separately audited events.
- Introduce price formation and shopping alternatives, then measure shortage vs. affordability.
- Compare rule agents with bounded goal-driven agent behaviors.
- Add scenarios where a human player changes supply, prices, or productive capacity.

The results here represent one seed and one toy set of parameters, not a balanced economy or business forecast.
