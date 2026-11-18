/* Small pure helpers shared by the live activity strip and its browser tests.
 * The authoritative server supplies simulator-minute cooldown values.
 */
export function scaledTimerSeconds(simSeconds, secondsPerMinute,
                                   nextWorldTickSeconds, sinceSnapshotSeconds) {
  const total = Math.max(0, Number(simSeconds) || 0);
  const scale = secondsPerMinute === 1 ? 1 : 60;
  const whole = total * scale / 60;
  if (nextWorldTickSeconds == null) return whole;
  const untilTick = Math.max(0, Math.min(scale, Number(nextWorldTickSeconds) || 0));
  const elapsed = Math.max(0, Number(sinceSnapshotSeconds) || 0);
  return Math.max(0, whole - (scale - untilTick) - elapsed);
}

export function totalUnspentMerits(merits = {}) {
  const balance = Math.max(0, Number(merits.balance) || 0);
  const unclaimed = (merits.achievements || [])
    .filter(feat => feat.eligible && !feat.claimed)
    .reduce((sum, feat) => {
      const award = Number(feat.award);
      return sum + (Number.isSafeInteger(award) && award > 0 ? award : 1);
    }, 0);
  return balance + unclaimed;
}
