/* Pure view-module checks; no DOM, network or browser globals required. */
import assert from "node:assert/strict";
import { createCommunityViews } from "../src/medieval_world_sim/web/static/community-views.mjs";
import { createCityViews } from "../src/medieval_world_sim/web/static/city-views.mjs";
import { createCharacterViews } from "../src/medieval_world_sim/web/static/character-views.mjs";
import { createWorldViews } from "../src/medieval_world_sim/web/static/world-views.mjs";

let query = "", scope = "players", selected = "player:bob", travelIntent = null;
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
assert.match(community.renderPeople(), />Attack<\/button>/);
assert.doesNotMatch(community.renderPeople(), /Attack · no entry cost/);
const profile = community.renderProfile();
assert.match(profile, /Bob/);
assert.doesNotMatch(profile, /Back to Search|personal finances are private|<h2>Bob<\/h2>/);
state.users.push({
  id: "npc:test", name: "Town Guard", kind: "npc", city: "crownreach",
  hp: 24, max_hp: 24, level: 2, can_attack: true,
  recovering_minutes: 0
});
selected = "npc:test";
assert.match(community.renderProfile(),
  /This is a computer-controlled adventurer\. Direct messaging and trade is disabled/);
selected = "player:bob";
assert.match(community.renderTrade(), /Propose a trade/);
assert.match(community.renderDuel(), /No active duel/);
query = "nonexistent";
assert.doesNotMatch(community.renderPeople(), /profile-open.*Bob/);
const cityNames = [
  "renderMercenaryJobs", "renderChurch", "renderTrack",
  "renderGuilds", "renderMerits", "renderCityHall", "renderJob",
  "renderTraining", "renderTavern"
];
for (const name of cityNames) {
  assert.equal(typeof city[name], "function", name);
  assert.ok(city[name]().length > 35, name + " must render meaningful markup");
}
state = { ...state, player: { ...state.player, work: {
  ...state.player.work, manual: 57 } } };
state = { ...state, merits: {
  balance: 1, total_earned: 1,
  achievements: [{ id: "first_steps", name: "First Steps",
    description: "Create your character", award: 1,
    eligible: false, claimed: true }],
  upgrades: [{ id: "roadcraft", name: "Roadcraft", cost: 2,
    description: "Shorter journeys", owned: false }]
} };
const meritPage = city.renderMerits();
assert.match(meritPage, /Your merit ledger|First Steps/);
assert.doesNotMatch(meritPage, /<h2>Merits<\/h2>|Honor your milestones|Merits are earned once|\+1 merit/);
assert.match(city.renderJob(), /Manual:57/);
assert.match(city.renderJob(), /Occupation/);
assert.doesNotMatch(city.renderJob(), /Available Work|Complete contract/);
state = { ...state, contracts: ["warriors", "mageguild", "job"].map((venue, i) => ({
  id: "test" + i, title: "Contract " + venue, description: "Help the city",
  venue, reward: 10, cooldown_minutes: 60, stamina: 0, mana: 0,
  cooldown_available: true, can_pay: true, has_material: true
})) };
const hired = city.renderMercenaryJobs();
for (const name of ["Warrior contracts", "Mage contracts", "Merchant contracts",
  "Contract warriors", "Contract mageguild", "Contract job"]) {
  assert.match(hired, new RegExp(name));
}
// Character pages include inventory, public character attributes, and gear UI.
// They must use fresh state projections instead of caching player inventories.
state = { ...state, name: "Alice", net_worth_estimate: 200,
  housing: { tier: null, city: null }, equipped: {}, gear: [],
  equipment_catalog: [], player: { ...state.player,
    max_stamina: 100, max_mana: 100, cargo: 0, cargo_limit: 12,
    stored_here: {}, storage_cities: {}, consumables: [], cooldowns: {},
    school_xp: { restoration: 0 }, insight: 0, level: 1, level_xp: 0,
    combat_xp: 0, strength: 1, defense: 1,
    work: { ...state.player.work, experience: {} } } };
const character = createCharacterViews({
  ...helpers, clock: minute => String(minute),
  getState: () => state
});
for (const name of ["renderInventory", "renderCharacter", "renderEquipment", "renderArmory"]) {
  assert.equal(typeof character[name], "function", name);
  assert.ok(character[name]().length > 35, name + " must render meaningful markup");
}
assert.match(character.renderInventory(), /Inventory/);
assert.match(character.renderEquipment(), /Equipped Gear/);
state = { ...state, player: { ...state.player, inventory: { grain: 3 } } };
assert.match(character.renderInventory(), /3 carried/);
const world = createWorldViews({
  ...helpers, getState: () => state, getPending: () => false,
  getSecureWorldClock: () => true,
  getTravelIntent: () => travelIntent,
  getSchool: () => "restoration", setSchool: () => {},
  getSelectedAttunements: () => new Set(),
  getLatestPractice: () => null
});
const novice = {
  node_id: "restoration.soothe_wounds", title: "Soothe wounds",
  school: "restoration", tier: 1, role: "healing",
  prerequisites: [], school_xp: 80, required_xp: 0,
  insight_cost: 0, mana_cost: 8, unlocked: true,
  eligible: false, active: true, mastered: true,
  can_practice: false, castable: true
};
state = { ...state, cities: [
    { id: "crownreach", name: "Crownreach",
      is_current: true, discovered: true, minutes: 0 },
    { id: "ironvale", name: "Ironvale",
      is_current: false, discovered: true, minutes: 90 }
  ], gatherable: {},
  magic_schools: ["restoration"], magic_nodes: [novice],
  player: { ...state.player, attuned_paths: [],
    school_xp: { restoration: 80 }, mana: 100,
    cargo: 14, cargo_limit: 12 } };
const mastered = world.renderMagic();
assert.match(mastered, /Mastered/);
assert.match(mastered, /data-ui="practice"[^>]+disabled/);
assert.doesNotMatch(mastered, /data-ui="field-cast"/);
assert.match(mastered, /data-ui="practice"/);
assert.match(world.renderWorld(), /Travel cargo exceeded/);
travelIntent = "ironvale";
let modal = world.renderTravelConfirmation();
assert.match(modal, /Travel to Ironvale/);
assert.match(modal, /Estimated journey: <strong>90m<\/strong>/);
assert.match(modal, /data-ui="travel-cancel"/);
assert.match(modal, /data-ui="travel-confirm" data-target="ironvale" disabled/);
state = { ...state, player: { ...state.player, cargo: 2 },
  stored_gear_here: [{ id: 94, kind: "sword", quality: 10,
    durability: 20, slot: "weapon" }] };
assert.match(character.renderEquipment(), /data-ui="retrieve-gear"/);
modal = world.renderTravelConfirmation();
assert.match(modal, /data-ui="travel-confirm" data-target="ironvale"/);
assert.doesNotMatch(modal, /data-ui="travel-confirm" data-target="ironvale" disabled/);
travelIntent = null;
assert.equal(world.renderTravelConfirmation(), "");
// The displayed 100/100 threshold must match the authoritative 80-XP cap.
state = { ...state, player: { ...state.player,
  school_xp: { restoration: 30 } },
  magic_nodes: [{ ...novice, mastered: false, can_practice: true,
    practice_ready_minute: 0, school_xp: 30 }] };
const magicPage = world.renderMagic();
assert.match(magicPage, /37\/100/);
assert.match(magicPage, /Restoration channels life-giving energy/);
assert.doesNotMatch(magicPage, /Practice using mana|gradual XP|usable spell|XP needed/);
state = { ...state, magic_nodes: [
  { ...novice, mastered: false, can_practice: true,
    school_xp: 30, castable: false },
  { ...novice, node_id: "restoration.field_healing", title: "Field Healing",
    tier: 2, unlocked: false, active: false, mastered: false,
    eligible: false, insight_cost: 1, required_xp: 30,
    prerequisites: ["restoration.soothe_wounds"] }
] };
assert.match(world.renderMagic(), /Master previous tier to 100\/100/);
assert.doesNotMatch(world.renderMagic(), /XP needed/);
state = { ...state, minute: 0, magic_nodes: [{
  ...novice, mastered: false, can_practice: true,
  practice_ready_minute: 120, school_xp: 30
}] };
const manaOnly = world.renderMagic();
assert.match(manaOnly, /Practice · 8 mana/);
assert.doesNotMatch(manaOnly, /ready in 120m/);
assert.doesNotMatch(manaOnly, /data-ui="practice"[^>]+disabled/);
state = { ...state, player: { ...state.player, mana: 2 } };
assert.match(world.renderMagic(), /data-ui="practice"[^>]+disabled/);
// Casting belongs to the Home screen, not the Magic training screen.
state = { ...state, player: { ...state.player, mana: 100, hp: 18,
    work: { ...state.player.work, experience: {} }, discovered_cities: ["crownreach"],
    lineage: "human", lineage_trait_unlocked: false, level: 1,
    level_xp: 0, combat_xp: 0, strength: 1, defense: 1 },
  magic_nodes: [{ ...novice, unlocked: true, active: true, castable: true },
    { ...novice, node_id: "warding.shelter", title: "Shelter",
      school: "warding", active: false, castable: false, mana_cost: 10 }] };
let homeMagic = character.renderCharacter();
assert.match(homeMagic, /<h3>Magic<\/h3>/);
assert.match(homeMagic, /data-ui="field-cast" data-node="restoration.soothe_wounds"/);
assert.match(homeMagic, /data-ui="field-cast" data-node="warding.shelter" disabled/);
assert.doesNotMatch(world.renderMagic(), /data-ui="field-cast"/);
state = { ...state, magic_nodes: [
  { ...novice, unlocked: true, active: true, castable: false, mastered: false }
] };
const studying = character.renderCharacter();
assert.match(studying, /Reach 100\/100 to cast/);
assert.match(studying, /data-ui="field-cast" data-node="restoration.soothe_wounds" disabled/);
state = { ...state, magic_nodes: [{ ...novice, castable: true }] };
state = { ...state, player: { ...state.player, mana: 0 } };
homeMagic = character.renderCharacter();
assert.match(homeMagic, /data-ui="field-cast" data-node="restoration.soothe_wounds" disabled/);
state = { ...state, player: { ...state.player, mana: 100 },
  magic_nodes: [novice] };
const practiceContext = createWorldViews({
  ...helpers, getState: () => state, getPending: () => false,
  getSecureWorldClock: () => true, getTravelIntent: () => null,
  getSchool: () => "restoration", setSchool: () => {},
  getSelectedAttunements: () => new Set(),
  getLatestPractice: () => ({
    nodeId: "restoration.soothe_wounds", success: true,
    xp_gained: 1, mana_spent: 8, roll: 7, chance: 95,
    insight_gained: 0
  })
});
const practiceResult = practiceContext.renderMagic();
assert.match(practiceResult, /In the chapel infirmary/);
assert.doesNotMatch(practiceResult, /practice-rewards|practice-note|\+1 XP|−8 mana|rolled \/|Practice has no wage/);
console.log("Community, city, magic and storage view modules passed smoke tests");
