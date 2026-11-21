/* Headless browser-page contract checks. Run with node tests/test_browser_views.mjs.
 * The page module accepts data and formatting callbacks, not DOM or game actions.
 */
import assert from "node:assert/strict";
import { createWorldViews } from "../src/medieval_world_sim/web/static/world-views.mjs";
import { travelJustArrived, activeCourseEnded } from
  "../src/medieval_world_sim/web/static/live-transitions.mjs";
import { readFileSync } from "node:fs";

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
  getMapZoom: () => 2.5,
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
assert.match(views.renderWorld(), /<h2>Map<\/h2>/);
assert.match(views.renderMarket(), /Market/);
assert.match(views.renderMagic(), /Magic/);
assert.match(views.renderHome(), /Property/);
assert.doesNotMatch(views.renderHome(), /Invest in your future/);
// Mutable state is read fresh on every render; there must be no stale snapshot.
state = { ...state, gatherable: { grain: 2 },
  world_map: {
    width: 3, height: 3, relief: Array(9).fill(1), roads: [],
    tiles: [{i: 1, biome: "forest", elevation_m: 120, visible: true,
             sites: [{name: "Old Ruin"}]}],
    towns: [{id:"riverwatch",name:"Riverwatch",x:2,y:1}],
    position: [0,0], sight_radius: 2, explored_percent: 3.2,
    steps: [{x:1,y:0,minutes:4,label:"Old Ruin"},
            {x:2,y:1,minutes:12,label:"Riverwatch"}],
  }
};
const map = views.renderWorld();
assert.match(map, /<h2>Map<\/h2>/);
assert.match(map, /map-key-city/);
assert.match(map, /map-key-poi/);
assert.match(map, /Hotlist · 1 discovered destinations/);
assert.match(map, /Est. 12m/);
assert.match(map, /data-ui="explore-hex" data-x="2" data-y="1"/);
assert.match(map, /survey-site-marker map-destination/);
assert.match(map, /survey-city-marker map-destination/);
assert.match(map, /pointer-events="all"/);
assert.doesNotMatch(map, /Roads and destinations|Gather nearby resources|Time and recovery|Return to a settlement for commerce/i);
assert.doesNotMatch(map, /Exploration and Awareness|A growing atlas/i);
assert.doesNotMatch(map, /Click any highlighted land hex|Journeys use the cost/);
assert.doesNotMatch(map, /grain/);
// The final travel push transitions destination to null. The browser must
// make exactly one final private-map fetch rather than stopping at the prior hex.
assert.equal(travelJustArrived("crownreach", null), true);
assert.equal(travelJustArrived(null, null), false);
assert.equal(travelJustArrived("crownreach", "crownreach"), false);
assert.equal(activeCourseEnded({school:"rhetoric",index:0}, null), true);
assert.equal(activeCourseEnded({school:"rhetoric",index:0},
  {school:"rhetoric",index:0,remaining_minutes:5}), false);
assert.equal(activeCourseEnded(null, null), false);
assert.equal(activeCourseEnded({school:"rhetoric",index:0},
  {school:"rhetoric",index:1}), true);
const appSource = readFileSync(
  new URL("../src/medieval_world_sim/web/static/app.js", import.meta.url), "utf8");
const indexSource = readFileSync(
  new URL("../src/medieval_world_sim/web/static/index.html", import.meta.url), "utf8");
const stylesSource = readFileSync(
  new URL("../src/medieval_world_sim/web/static/styles.css", import.meta.url), "utf8");
assert.match(appSource, /mapTravelSettlePending = true/);
assert.match(appSource, /!state\.player\.destination && !mapTravelSettlePending/);
assert.match(appSource, /universityNeedsRefresh = true/);
assert.match(appSource, /refreshFinishedUniversityCourse\(\)/);
assert.match(appSource, /data-encounter-id/);
assert.match(appSource, /chronicleOpenEncounters\.has/);
assert.match(appSource, /chronicleVisibleCount = 50/);
assert.match(appSource, /chronicle-more/);
assert.match(indexSource, /<title>Oathmere<\/title>/);
assert.doesNotMatch(indexSource, /The Five Cities/);
assert.match(stylesSource, /\.profile-magic-panel \{ margin-top:18px/);
assert.match(stylesSource, /\.chat-dock \{[^\n]+width:210px/);
assert.match(stylesSource, /\.chat-game-refresh:first-child/);
assert.match(appSource, /<label for="registerUsername">Email Address<\/label>/);
assert.match(appSource, /<label for="loginUsername">Email Address<\/label>/);
assert.match(appSource, /type="email" autocomplete="email"/);
assert.match(appSource, /dropped into an unfamiliar location/);
assert.match(appSource, /setInterval\(checkServerConnection, 5000\)/);
assert.match(appSource, /cache: "no-store", signal: controller.signal/);
assert.match(appSource, /function markServerDisconnected\(\)/);
assert.match(appSource, /stopLiveEvents\(\);\s*stopPresence\(\);\s*render\(\)/);
assert.match(appSource, /if \(offline\) root.innerHTML = offlinePage\(\)/);
assert.match(appSource, /if \(offline\) await load\(true\)/);
assert.match(appSource, /<h1>Server disconnected<\/h1>/);
assert.doesNotMatch(appSource, /Try reconnecting|Oathmere cannot reach the game server/);
assert.match(appSource, /passwordToggle\("loginPassword"\)/);
assert.match(appSource, /passwordToggle\("registerPassword"\)/);
assert.match(appSource, /passwordToggle\("access"\)/);
assert.match(appSource, /case "toggle-password":/);
assert.match(appSource, /data-activity-key="hospital"/);
assert.match(appSource, /compactWallTime\(timerSeconds\(hospitalMinutes \* 60\)\)/);
assert.match(stylesSource, /\.merits-columns \{display:grid;grid-template-columns:repeat\(2/);
assert.match(stylesSource, /:root\[data-theme="dark"\] \.entry-card h1/);
assert.match(stylesSource, /:root\[data-theme="dark"\] \.character-name-link:hover/);
assert.match(stylesSource, /:root\[data-theme="dark"\] \.side-nav \.nav-button:disabled/);
assert.doesNotMatch(appSource, /Your account is registered/);
assert.doesNotMatch(appSource, /Level ' \+ spec\.trait_level \+ ' trait/);
assert.doesNotMatch(appSource, /<legend>Choose your lineage<\/legend>/);
const characterSource = readFileSync(
  new URL("../src/medieval_world_sim/web/static/character-views.mjs", import.meta.url),
  "utf8");
assert.match(characterSource, /characterRow\("Age", p\.age_days/);
assert.doesNotMatch(characterSource, /World age \(shared\)/);
assert.doesNotMatch(characterSource, /characterRow\("Birthright"/);
console.log("Browser page module smoke tests passed");
