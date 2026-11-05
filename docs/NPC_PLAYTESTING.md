# Two Autonomous NPC Playtesters and Observer/Critic Layer

This opt-in, isolated simulation runs **two test avatars** using actual
WorldEngine rules in the existing 5-city economy. The ordinary population
remains lightweight and deterministic. These avatars are controlled by a
rules-based utility policy and are not connected to real user accounts.

## Three separate responsibilities

1. **Action selection:** Read-only observations → needs (health, hunger,
   fatigue, finances, curiosity) → profession/persona candidates → utility
   scores modified by personality, bounded recent memory, Gaussian RNG →
   a validated \`WorldEngine.execute(actor_id, action, params, request_id)\`.
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

\`\`\`bash
python -m medieval_world_sim.agents.demo --npcs 28 --days 8 --seed 42 --playtest --reflect-every 30 --report-file playtest-feedback.json
python -m medieval_world_sim.agents.demo --npcs 28 --days 8 --seed 43 --playtest --json
\`\`\`

The \`--npcs\` flag counts *ordinary* NPCs. \`--playtest\` adds exactly two
avatars, each starting at level 1 with 240 gold in Crownreach. The
\`--reflect-every\` interval counts meaningful attempted actions; major
events may also trigger reflection after at least five new decisions.
The runner produces final reflections at session end. World advancement is
still the configured accelerated step, not an always-running hosted service.

### Opt-in LLM reflections (network, credentials, cost)

To send the limited *test telemetry* (NOT real account secrets) to an external
model, explicitly provide a model and API key:

\`\`\`bash
export OPENAI_API_KEY="YOUR_KEY"
python -m medieval_world_sim.agents.demo --npcs 28 --days 8 --seed 42 --playtest --llm-model YOUR_SUPPORTED_MODEL --report-file playtest-feedback.json
\`\`\`

This optional connector uses a fixed HTTPS endpoint, a short timeout, a
bounded JSON response and a strictly validated structured schema. It can
incur model-usage charges. Model availability and model-specific parameter
support must be confirmed before using a real provider. Network/API errors
fall back to local telemetry and are reported as \`critic_errors\`. No
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
