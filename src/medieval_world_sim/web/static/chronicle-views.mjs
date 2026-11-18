/* Pure, presentation-only grouping for durable combat encounter projections.
 * Incoming events are newest first. Never mutate the journal-derived actions.
 */
export function groupCombatChronicle(events) {
  const grouped = new Map();
  const result = [];
  for (const event of events || []) {
    if (event.encounter_id == null || event.kind === "combat_encounter") {
      result.push(event);
      continue;
    }
    const key = String(event.encounter_id);
    let entry = grouped.get(key);
    if (!entry) {
      entry = {
        id: "encounter-" + key, kind: "combat_encounter",
        category: "Combat", minute: event.minute,
        recorded_at: event.recorded_at,
        text: String(event.encounter_attacker || "Unknown adventurer") +
          " attacked " + String(event.encounter_defender || "Unknown adventurer") +
          " · " + String(event.encounter_outcome || "In progress"),
        actions: [],
      };
      grouped.set(key, entry);
      result.push(entry);
    }
    entry.actions.push(event);
  }
  for (const entry of grouped.values()) entry.actions.reverse();
  return result;
}
