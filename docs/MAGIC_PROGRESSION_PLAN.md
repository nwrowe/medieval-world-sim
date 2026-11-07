# Six-school magic progression — implemented tree architecture

**Status:** The six-school skill-tree catalog, actor mana/skill state, progression commands, deterministic practice and attunement rules are implemented on the \`feat/six-school-magic-progression\` branch. **Paid jobs, world spell effects, magic NPC occupations, and economic balance have NOT been implemented.** This release supplies their stable domain foundation.

## Progression concept

Each actor has a separate \`MagicState\`: 100 starting/max mana, experience for each school, available Insight, total Insight earned, unlocked node IDs, a count of casting attempts, up to two concurrently attuned specialist branches, and an attunement-switch timestamp. It is independent of combat XP, stamina and working attributes.

The single common root, \`arcane_fundamentals\`, is known by all new characters. All six schools can be studied by the same character; early entry nodes are free to unlock. A character unlocks an individual node only after learning its prerequisites, mastering the previous tier to 100/100 and spending sufficient Insight (Tier I starts unlocked for study at no Insight cost). **No early permanent class choice.**

| Tier | Role | Previous tier must reach | Insight to unlock | Mana for practice |
|---|---|---:|---:|---:|
| I | Novice practice | None | 0 | 8 |
| II | Applied skill | Tier I 100/100 (80 school XP) | 1 | 15 |
| III | Specialization (choose branches) | Tier II 100/100 (180 school XP) | 2 | 25 |
| IV | Advanced mastery | Tier III 100/100 (420 school XP) | 3 | 40 |

**Insight** is earned globally, one point for every 50 total magical XP across schools. Unlocking spends Insight but doesn't consume school XP. Practicing an eligible unlocked node grants school-specific XP, with skill-dependent, seeded success and small failure credit. Practice becomes trivial and stops granting XP beyond per-tier caps (Tier I 80, II 180, III 420, IV 1000); this encourages progression. **Current practice pacing:** each practice attempt costs mana and gives one base school XP (with applicable housing/lineage bonuses). Failed attempts still teach basic lessons. There is **no separate timed practice cooldown**; players may train repeatedly whenever they have sufficient mana. The UI's tier meter reaches **100/100 at its actual practice ceiling**, at exactly the mastery prerequisite for the next tier: for example, Tier I ends at 80 school XP and Soothe Wounds then becomes untrainable; Field Healing can then be unlocked using earned Insight. Spell casting is distinct from practice and is not disabled by training mastery. Older journal actions retain their historic XP/cooldown and unlock-threshold rules on replay.

**Mana** replenishes +1 per 10 simulated minutes, whether time is advanced in one big chunk or several smaller chunks. It replenishes independently of stamina. Practicing consumes mana regardless of success. This is a prototype balance; numbers are content constants that can be adjusted after gameplay testing.

## Full six-school tree

All schools have a novice node → applied node → **two tier-three specializations**, each with a distinct tier-four mastery. These are *node names and future integration hooks*; they are **not yet functional effects**.

| School | Novice | Applied skill | Tier III A → Tier IV A | Tier III B → Tier IV B |
|---|---|---|---|---|
| Restoration | Soothe Wounds | Field Healing | Revival Arts → Master Healer | Battle Medic → Combat Restoration |
| Divination | Read Omens | Trade Appraisal | Merchant Foresight → Oracle | Pathfinder → Wayfinder |
| Enchantment | Etch a Rune | Tool Improvement | Smith's Runes → Runemaster | Combat Imbuement → Battle Enchanter |
| Warding | Minor Shield | Ward Goods | Caravan Protector → Grand Warden | Combat Defender → Aegis Master |
| Elemental | Kindle Flame | Furnace Assistance | Crafting Fire → Forge Elementalist | Battle Magic → Stormcaller |
| Alchemy | Purify Reagents | Potion Enhancement | Apothecary's Art → Master Alchemist | Resistance Elixirs → Elixir Sage |

The immutable \`content/magic_tree.py\` registry provides one entry per node, including \`id\`, school, title, tier, prerequisite IDs, effect-domain role, XP gate, Insight cost, mana cost and difficulty. Content validation prevents broken prerequisites and missing branches when loaded.

### Two concurrent active specializations

Characters can **eventually learn all branches**. Learning a Tier III branch or its Tier IV mastery does not automatically activate its advanced abilities. The character selects at most **two unlocked Tier III paths**, across all six schools, via \`attune_magic\`. Tier IV uses the corresponding Tier III attunement. Reattuning has a six-hour simulated-time cooldown; acquired skills remain learned, not discarded.

Tier I and II nodes remain available without attunement. This preserves long-term completionist progression while differentiating active builds.

## Authoritative API

The shared player/NPC command allowlist now includes:
- \`unlock_magic\` with \`node_id\`: purchase an eligible node using Insight.
- \`practice_magic\` with \`node_id\`: pay mana, roll deterministic chance, earn school XP and possibly Insight; returns a detached result.
- \`attune_magic\` with \`paths\`: switch the active Tier III specializations, with cooldown.
- \`world.magic_tree(actor_id, school=None)\`: return detached read-only \`MagicNodeStatus\` records with the requirements, eligibility and active state for later UI integration.

All mutating operations use \`WorldEngine.execute\` identity binding, idempotent action IDs, atomic rollback, typed world events, and engine invariants. Casting is disabled while traveling or defeated. Practice rolls are a cryptographic hash of the world seed, actor ID, node ID, actor's attempt count and world minute, making results deterministic and resistant to accidentally repeating the same random result at one timestamp.

\`\`\`bash
python -m medieval_world_sim --scenario magic
python -m unittest discover -s tests -v
\`\`\`

## Scope boundaries / next work

The \`practice_magic\` command is **training only**. It does not heal anyone, affect combat stats, increase merchant payouts, alter gear, grant items or mint gold. A combat or commercial spell must later be a separate validated action handler that checks ownership, target consent/eligibility, material input, attunement, mana, cooldowns and payer funds. Such an effect handler may reuse the catalog's \`role\` field and progression checks, but should never bypass current combat, trade, travel or accounting rules.

Recommended next implementations: funded magical service contracts; bounded Restoration healing; useful Divination market information; reagent-consuming Enchantment; then Warding, Elemental and Alchemy effects. This intentionally separates **tree architecture** from economically sensitive gameplay effects, as requested.

Cross-school abilities (e.g. Divination+Warding Safe Passage) are a *future extension*. They are not in this initial 37-node registry; explicit cross-school prerequisites will need deliberate catalog schema adjustments and balancing.
