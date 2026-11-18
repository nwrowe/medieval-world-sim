/* Detect the two server transitions that invalidate private projections.
 * Live activity updates intentionally do not send map tiles or full courses.
 * Refreshing the authoritative snapshot only at these boundaries keeps the
 * map responsive without re-requesting expensive route quotes each tick.
 */
export function travelJustArrived(previousDestination, nextDestination) {
  return Boolean(previousDestination) && !nextDestination;
}

export function activeCourseEnded(previous, next) {
  return Boolean(previous) && (!next ||
    previous.school !== next.school || previous.index !== next.index);
}
