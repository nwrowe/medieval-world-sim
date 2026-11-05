/* Headless browser-page contract checks. Run with node tests/test_browser_views.mjs.
 * The page module accepts data and formatting callbacks, not DOM or game actions.
 */
import assert from "node:assert/strict";
import { createWorldViews } from "../src/medieval_world_sim/web/static/world-views.mjs";

let school = "restoration";
let state = {
  minute: 0,
  cities: [{ id: "crownreach", name: "Crownreach", is_current: true, minutes: 0 }],
  gatherable: {},
  quotes: [],
  magic_schools: ["restoration"],
  magic_nodes: [],
  housing: { city: null, tier: null, facilities: [], vehicles: [], active_vehicle: null },
  homes: [], facilities: [], vehicles: [],
  player: {
    hp: 24, max_hp: 24, defeated_until: null, city: "crownreach",
    destination: null, ready_minute: 0, inventory: {}, gold: 240,
    mana: 100, insight: 0, school_xp: { restoration: 0 }, attuned_paths: [],
  },
};
const views = createWorldViews({
  getState: () => state,
  getPending: () => false,
  getSecureWorldClock: () => true,
  getSchool: () => school,
  setSchool: value => { school = value; },
  getLatestPractice: () => null,
  getSelectedAttunements: () => new Set(),
  esc: v => String(v),
  pretty: v => String(v),
  dur: v => String(v) + "m",
  disabled: flag => flag ? " disabled" : "",
  button: (text, attributes = "") => "<button " + attributes + ">" + text + "</button>",
  panel: (_title, _subtitle, body) => "<section>" + body + "</section>",
  heading: (_kicker, title) => "<h2>" + title + "</h2>",
  isBusy: () => false,
  progress: (v, max) => "<progress max='" + max + "' value='" + v + "'></progress>",
  money: v => String(v) + "g",
});
for (const name of ["renderWorld", "renderMarket", "renderMagic", "renderHome"]) {
  assert.equal(typeof views[name], "function", name + " must be exposed");
  assert.ok(views[name]().length > 50, name + " must render");
}
assert.match(views.renderWorld(), /World Map/);
assert.match(views.renderMarket(), /Market/);
assert.match(views.renderMagic(), /Magic/);
assert.match(views.renderHome(), /Property/);
// Mutable state is read fresh on every render; there must be no stale snapshot.
state = { ...state, gatherable: { grain: 2 } };
assert.match(views.renderWorld(), /grain/);
console.log("Browser page module smoke tests passed");
