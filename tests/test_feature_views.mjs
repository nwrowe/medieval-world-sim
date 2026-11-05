/* Pure view-module checks; no DOM, network or browser globals required. */
import assert from "node:assert/strict";
import { createCommunityViews } from "../src/medieval_world_sim/web/static/community-views.mjs";
import { createCityViews } from "../src/medieval_world_sim/web/static/city-views.mjs";

let query = "", scope = "players", selected = "player:bob";
let state = {
  name: "Alice", minute: 0, actor_id: "player:alice", multiplayer: true,
  users: [
    { id: "player:alice", name: "Alice", kind: "human", city: "crownreach",
      hp: 24, max_hp: 24, level: 1, can_attack: false, recovering_minutes: 0 },
    { id: "player:bob", name: "Bob", kind: "human", city: "crownreach",
      hp: 20, max_hp: 24, level: 2, can_attack: true, recovering_minutes: 0,
      presence: "active" },
  ],
  quotes: [], world_items: [], trades: [], gear: [], duel: null, last_duel: null,
  combat_moves: [], magic_nodes: [], contracts: [], guilds: {
    my_guild: null, directory: [], rules: { notice_minutes: 1440, duration_minutes: 1440 }
  },
  merits: { balance: 0, total_earned: 0, achievements: [], upgrades: [] },
  church: { price: 20, available: false }, track: { horses: [], race_cost: 15, entry_fee: 10 },
  training_hall: { active: null, schools: [] },
  player: {
    city: "crownreach", gold: 200, hp: 24, max_hp: 24, stamina: 100,
    max_stamina: 100, mana: 100, inventory: {}, work: {
      manual: 0, intelligence: 0, endurance: 0, shifts: 0
    }
  }
};
const helpers = {
  esc: value => String(value),
  pretty: value => String(value),
  money: value => Number(value) + "g",
  dur: value => String(value) + "m",
  button: (label, attrs = "") => "<button " + attrs + ">" + label + "</button>",
  disabled: flag => flag ? " disabled" : "",
  isBusy: () => false,
  heading: (_kicker, title) => "<h2>" + title + "</h2>",
  panel: (title, _description, content) => "<section><h3>" + title + "</h3>" + content + "</section>",
  characterRow: (label, value) => "<div>" + label + ":" + value + "</div>",
  progress: (value, max) => "<progress value='" + value + "' max='" + max + "'></progress>",
  chip: label => "<span>" + label + "</span>"
};
const community = createCommunityViews({
  ...helpers, getState: () => state, getPeopleQuery: () => query,
  getSearchScope: () => scope, getMultiMode: () => true,
  getSelectedCharacterId: () => selected, getPending: () => false
});
const city = createCityViews({
  ...helpers, getState: () => state, getLatestContract: () => null,
  getExpandedUniversitySchool: () => null, getPending: () => false,
  getSecureWorldClock: () => true
});
for (const name of ["renderPeople", "renderProfile", "renderTrade", "renderDuel"]) {
  assert.equal(typeof community[name], "function");
  assert.ok(community[name]().length > 35, name + " must render meaningful markup");
}
assert.match(community.renderPeople(), /Bob/);
assert.match(community.renderProfile(), /Bob/);
assert.match(community.renderTrade(), /Propose a trade/);
assert.match(community.renderDuel(), /No active duel/);
query = "nonexistent";
assert.doesNotMatch(community.renderPeople(), /profile-open.*Bob/);
const cityNames = [
  "renderWarriorsGuild", "renderMageGuild", "renderChurch", "renderTrack",
  "renderGuilds", "renderMerits", "renderCityHall", "renderJob",
  "renderTraining", "renderTavern"
];
for (const name of cityNames) {
  assert.equal(typeof city[name], "function", name);
  assert.ok(city[name]().length > 35, name + " must render meaningful markup");
}
state = { ...state, player: { ...state.player, work: {
  ...state.player.work, manual: 57 } } };
assert.match(city.renderJob(), /Manual:57/);
console.log("Community and city view modules passed smoke tests");
