# Two Autonomous NPC Playtesters and Observer/Critic Layer

This opt-in, isolated simulation runs **two test avatars** using actual
WorldEngine rules in the existing 5-city economy. The ordinary population
remains lightweight and deterministic. These avatars are controlled by a
rules-based utility policy and are not connected to real user accounts.

## Three separate responsibilities

1. **Action selection:** Read-only observations → needs (health, hunger,
   fatigue, finances, curiosity) → profession/persona candidates → utility
   scores modified by personality, bounded recent memory, Gaussian RNG →
   a validated `WorldEngine.execute(actor_id, action, params, request_id)`.
2. **Learning:** A bounded, 48-decision trace per character learns action-family
   payoffs and repeated failure penalties. It cannot change stats, money,
   inventory, combat calculations or permissions. This is a small EMA, not RL.
3. **Criticism:** A special observer uses **only** a 30-record summarized event
   window, recent action counts and a few player-visible facts. By default
   a deterministic local critic produces evidence-linked scores and warnings.
   The optional LLM critic runs *after* game actions, never inside them.

Separating these roles means a model cannot grant gold, choose combat targets,
bypass restrictions or impersonate player credentials. The two critic avatars
use standard playable-actor rules only **inside the throwaway offline test**
and are never auto-enrolled into the multiplayer SQLite server.

## Explorer versus Optimizer

| Agent | Favors | Question answered |
|---|---|---|
| Explorer | Uncharted cities, magic, variety, study | Do systems invite discovery? |
| Optimizer | Reliable civic income, profitable regional trade, equipment | Are there dominant tactics or dead ends? |

Both can travel, work city contracts, gather, buy/sell with the funded city
merchant, purchase/equip starter gear and enroll in university courses.
Explorer also prioritizes spell training, unlocking nodes and occasional
combat with designated simulator adventurers. Actions still fail if ordinary
engine rules reject them. Public multiplayer NPCs are not yet autonomously
ticked: this is **simulation harness integration first**, not background
server AI.

## Run and compare

No third-party packages or external API credentials are needed:

```bash
python -m medieval_world_sim.agents.demo --npcs 28 --days 8 --seed 42 --playtest --reflect-every 30 --report-file playtest-feedback.json
python -m medieval_world_sim.agents.demo --npcs 28 --days 8 --seed 43 --playtest --json
```

The `--npcs` flag counts *ordinary* NPCs. `--playtest` adds exactly two
avatars, each starting at level 1 with 240 gold in Crownreach. The
`--reflect-every` interval counts meaningful attempted actions; major
events may also trigger reflection after at least five new decisions.
The runner produces final reflections at session end. World advancement is
still the configured accelerated step, not an always-running hosted service.

### Objective-based trade planning and richer diagnostics

The **Optimizer** now treats regional arbitrage as a committed objective:
buy raw material at its source city, travel to Crownreach, then sell into
the capital's *currently funded* merchant demand. It never deliberately
buys and immediately resells the same cargo locally. A route is completed
only when the goods have been sold; the learning signal is **realized
revenue minus actual purchase cost**. On partial sales or depleted city
budgets, the optimizer retains its cargo objective and can perform local
work while waiting for a funded sale.

The source city still needs stock; arrival and market conditions can change.
Profitable plans aren't guarantees of profit. Outstanding inventory is
labeled an *unsettled position*, not a realized financial loss.

Observers now track estimated inventory value at **published capital bids**
(excludes equipment and ignores stock quotas and available funds), work/magic/
combat XP, equipment acquired, education completed, level progression,
completed trade cycles and real route profitability. This is a diagnostic
mark only, **not withdrawable gold or an exact net-worth figure**.

Critic findings now distinguish: failed local buy-sell loops, losing
long-distance routes, ongoing unsold cargo, character-level stagnation,
rejected commands and truly new discoveries since the previous reflection.
The 0–10 ratings remain **proxies**, with explicit caveats: command acceptance
does not establish UI clarity, social engagement is not measured, and
action diversity is not necessarily an interesting decision.

For a reproducible multi-seed summary with per-seed evidence, run:

```bash
python -m medieval_world_sim.agents.compare --seeds 10 --days 30 --npcs 28 --first-seed 42 --report-file npc-compare.json
```

The command is intentionally opt-in; ten 30-day simulations can take
substantial computation time. Use `--seeds 3 --days 4` to get a quick
smoke test. Each run is independent and starts the two test avatars at
level one, without any paid model calls.

### Opt-in LLM reflections (network, credentials, cost)

To send the limited *test telemetry* (NOT real account secrets) to an external
model, explicitly provide a model and API key:

```bash
export OPENAI_API_KEY="YOUR_KEY"
python -m medieval_world_sim.agents.demo --npcs 28 --days 8 --seed 42 --playtest --llm-model YOUR_SUPPORTED_MODEL --report-file playtest-feedback.json
```

This optional connector uses a fixed HTTPS endpoint, a short timeout, a
bounded JSON response and a strictly validated structured schema, with at most 12 external
reflections per agent per run. It can incur model-usage charges. Model availability and model-specific parameter
support must be confirmed before using a real provider. Network/API errors
fall back to local telemetry and are reported as `critic_errors`. No
automatic model calls occur without this explicit option.

### What a structured result means

Each reflection includes 0–10 *proxy* scores for progression, clarity,
meaningful decisions, repetition (higher means less repetitive) and
social opportunities. Issues have categories:

- Bug
- UX issue
- Balance concern
- Exploit candidate
- Boredom signal
- Emergent story

Each includes concrete supporting telemetry, confidence, and a tentative
follow-up experiment. LLM suggestions are labeled unverified hypotheses.
The report also aggregates issue codes observed by *both* playtesters.
Keep the results in versioned JSON files when comparing seeds or releases.

## Follow-up: smarter NPC decisions and capital storage

**Magic mastery.** The server now emits `mastered` and `can_practice`
for each magic node. Both the UI practice button and autonomous NPC action
proposals use these server-owned flags. At a tier's training XP ceiling, or
after a higher tier in the school is learned, practice is disabled and
rejected; learned spells remain available for *casting* as before. The
existing replay migration for historical magic commands remains intact.

**City inventory and roads.** Both humans and NPCs can hold an unlimited
number of ordinary goods in any city, and can stash unlimited goods in
Crownreach or another settlement. An *outbound road departure* still checks
the total cargo count against the selected vehicle's capacity. Only
carried goods and carried equipment count; stashed items stay in their
respective city. Unequipped armor/weapons can now be deposited into and
retrieved from local city armories. Each storage command checks account
ownership; the asset ledger, invariant checker and checkpoints include
stored gear. Equipment must be retrieved before it can be traded or equipped.
A large armory does not enlarge road capacity.

**Economic policies.** Ordinary haulers already used funded source/capital
price comparisons; they now also remember actual paid quantities and costs
(including offers from NPC gatherers) and hold goods if the destination bid
would produce a known loss. Their realized profit, losing cycles and pending
shipments are reported separately. Gatherers sell material they produce and
companies pay workers/make items: those roles have different business risks.
Explorer and Optimizer both use committed multi-city trade routes; they
do not propose an untracked source-city buy and immediate local resale.
When a destination bid stays unavailable, the agent may try one alternative
importer after three days, or store unsold goods locally after seven days.
A stored position is **not** counted as a profitable completed route and its
unrecovered cost remains visible in report telemetry.

**Combat incentives.** Ordinary adventurers now buy starter arms when
available and consider fighting same-city, alive simulated NPC opponents
frequently enough to train combat. The Explorer and Optimizer can also test
combat while keeping distinct progression/trading priorities. All combat
passes through the real engine and its HP, stamina, defeat-recovery and
**maximum 10-gold NPC-attack loot** enforcement. Playtesters and human
accounts are not exposed as automatic combat victims. No combat action is
issued by the optional LLM critic. The rules-based **ordinary** NPC roles
(gatherers, haulers and adventurers) are now integrated with the local
multiplayer server's committed world-time advances. The special
Explorer/Optimizer playtesters remain **offline only** and do not control
live characters. See [local multiplayer](MULTIPLAYER_LOCAL_DEVELOPMENT.md).

**Evidence and score limitations.** Multi-seed reports now include cash gained
per simulated day, trade profit per day, combat strikes/victories/loot,
pending stored trade positions and the fraction of decisions aligned with
each playtester's assigned goals (`goal_action_pct`). These are telemetry
proxies, not measurements of player fun. A local buy-sell loss now requires
a matching resource, city, purchase/sale quantity and same visit to avoid
false alarms from partial sales and legitimate intercity trade.

## Limitations and next steps

- An LLM is a critic, not a substitute for genuine new-player feedback.
  High-level clarity scores are *telemetry-derived proxies*, not measured
  player confusion. A quiet action stream does not prove an exploitable bug.
- The simulation is a sandbox economy, not a saveable player account. The
  latest 48 action traces and latest 24 reflections per observer are bounded
  in memory. CLI JSON export persists reports for offline comparison.
- The present world has no true dungeons or cooperative party expeditions,
  so testers cannot assess those mechanics yet. Social opportunity scores
  are a deliberately low baseline, not a quantitative social study.
- The existing server's named NPCs remain scheduled as static actors in
  the web world. Moving autonomous decisions into production demands secure
  server-side scheduling, per-NPC action budgets, restart-safe memory and
  persistence, transaction safety, and replay integration; do not run the
  offline loop against the live multiplayer world without that work.
- Compare multiple seeds, player behavior and actual human playtests before
  changing balance based on model commentary.
