import { createCharacterViews } from "/character-views.mjs";
import { createCommunityViews } from "/community-views.mjs";
import { createCityViews } from "/city-views.mjs";
import { createWorldViews } from "/world-views.mjs";

/* Oathmere — dependency-free responsive game client.
   Rendering is a read-only projection of server-authoritative world state.
   The browser never calculates gold, travel duration, spell success or ownership.
*/
(() => {
  "use strict";

  const root = document.getElementById("app");
  const globeIcon = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" ' +
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
    'stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/>' +
    '<path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>';
  const cityLinks = [
    { id: "inventory", icon: "◫", title: "Inventory" },
    { id: "home", icon: "⌂", title: "My Property" },
    { id: "magic", icon: "✧", title: "Magic" },
    { id: "guilds", icon: "⚑", title: "Guilds" },
    { id: "merits", icon: "✶", title: "Merits" },
    { id: "market", icon: "⚖", title: "Market" },
    { id: "job", icon: "▣", title: "Job" },
    { id: "warriors", icon: "⚔", title: "Warriors Guild" },
    { id: "mageguild", icon: "✦", title: "Mage Guild" },
    { id: "church", icon: "✝", title: "Church" },
    { id: "armory", icon: "⚒", title: "Armory", onlyCity: "crownreach" },
    { id: "track", icon: "♞", title: "Track" },
    { id: "training", icon: "✤", title: "University" },
    { id: "tavern", icon: "♜", title: "Tavern" },
    { id: "cityhall", icon: "♛", title: "City Hall" },
  ];
  const accountTabs = [
    { id: "character", icon: "♙", title: "Home" },
    { id: "equipment", icon: "⚔", title: "Equipment" },
    { id: "world", icon: globeIcon, title: "World" },
    { id: "chronicle", icon: "▤", title: "Chronicle" },
    { id: "people", icon: "⌕", title: "Search" },
  ];
  let state = null;
  let tab = "character";
  let levelCelebration = null;
  let presenceTimer = null;
  let lastUserActivity = Date.now();
  for (const name of ["pointerdown", "keydown", "touchstart"]) {
    document.addEventListener(name, () => {
      const wasIdle = Date.now() - lastUserActivity >= 5 * 60 * 1000;
      lastUserActivity = Date.now();
      if (wasIdle) publishPresence();
    }, { passive: true });
  }
  let school = "restoration";
  let latestPractice = null;
  let latestContract = null;
  let peopleQuery = "";
  let selectedCharacterId = null;
  let searchScope = "players";
  let chronicleCategory = "all";
  let chronicleQuery = "";
  let chatOpen = false;
  let chatChannelKey = "global";
  let chatDraft = "";
  let expandedUniversitySchool = null;
  let chatDirectTarget = null;
  let pending = false;
  let authNeeded = false;
  let offline = false;
  let selectedAttunements = new Set();
  let token = sessionStorage.getItem("medieval-world-token") || "";
  let multiMode = false;
  let inviteRequired = false;
  let secureWorldClock = false;
  let clockSyncedAt = Date.now();
  let csrfToken = "";
  let liveEvents = null;

  function esc(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function placeName(value) { return String(value || "").replace(/\s*\(capital\)/gi, ""); }
  function pretty(key) {
    return String(key || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
  }
  function money(value) { return Number(value).toLocaleString() + " g"; }
  function clock(minute) {
    const days = Math.floor(minute / 1440);
    const hh = String(Math.floor((minute % 1440) / 60)).padStart(2, "0");
    const mm = String(minute % 60).padStart(2, "0");
    return (days ? days + "d " : "") + hh + ":" + mm;
  }
  const easternFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", month: "short", day: "numeric",
    year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
  const headerClockFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hourCycle: "h23",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    month: "numeric", day: "numeric", year: "2-digit",
  });
  function easternNow() {
    const parts = Object.fromEntries(headerClockFormatter.formatToParts(new Date())
      .filter(part => part.type !== "literal").map(part => [part.type, part.value]));
    return parts.hour + ":" + parts.minute + ":" + parts.second + " - " +
      parts.month + "/" + parts.day + "/" + parts.year;
  }
  function eventTime(event) {
    if (!event.recorded_at) return "Earlier · timestamp unavailable";
    const date = new Date(event.recorded_at);
    return Number.isNaN(date.getTime()) ? "Earlier · timestamp unavailable" :
      easternFormatter.format(date);
  }
  function updateEasternClock() {
    const label = document.getElementById("eastern-clock");
    if (label) label.textContent = easternNow();
  }
  function dur(minutes) {
    const h = Math.floor(minutes / 60), m = minutes % 60;
    return h ? (h + "h " + (m ? m + "m" : "")) : m + "m";
  }
  function fullCountdown(seconds) {
    const value = Math.max(0, Math.ceil(Number(seconds) || 0));
    const hours = Math.floor(value / 3600);
    return String(hours).padStart(2, "0") + ":" +
      String(Math.floor((value % 3600) / 60)).padStart(2, "0") + ":" +
      String(value % 60).padStart(2, "0");
  }
  function timerSeconds(simSeconds) {
    const total = Math.max(0, Number(simSeconds) || 0);
    if (!secureWorldClock || !state || state.next_world_tick_seconds == null)
      return total;
    // State durations are integral world minutes. The server provides the
    // partial minute so hover timers can count down to the exact second.
    const partial = 60 - Number(state.next_world_tick_seconds);
    return Math.max(0, total - partial -
      Math.max(0, (Date.now() - clockSyncedAt) / 1000));
  }
  function timerAttrs(label, simSeconds) {
    const seconds = timerSeconds(simSeconds);
    const text = label + fullCountdown(seconds);
    const end = secureWorldClock && state && state.next_world_tick_seconds != null ?
      Date.now() + seconds * 1000 : 0;
    return ' data-hover-text="' + esc(text) + '" data-timer-label="' + esc(label) +
      '" data-timer-end="' + end + '" data-timer-fixed="' +
      (end ? "" : Math.ceil(seconds)) + '"';
  }
  function updateHoverTimers() {
    for (const item of document.querySelectorAll("[data-timer-label]")) {
      const seconds = Number(item.dataset.timerEnd) > 0 ?
        (Number(item.dataset.timerEnd) - Date.now()) / 1000 :
        Number(item.dataset.timerFixed);
      item.dataset.hoverText = item.dataset.timerLabel + fullCountdown(seconds);
    }
  }
  function simDuration(minutes) {
    const total = Math.max(0, Math.ceil(Number(minutes) || 0));
    const days = Math.floor(total / 1440);
    const hours = Math.floor((total % 1440) / 60);
    const mins = total % 60;
    return (days ? days + "d " : "") +
      (hours ? hours + "h " : "") +
      (mins || (!days && !hours) ? mins + "m" : "");
  }
  function isBusy() {
    return pending || !state || !state.started ||
      Boolean(state.player.destination) || state.player.hp <= 0 ||
      state.player.defeated_until != null || Boolean(state.duel);
  }
  function button(text, attrs = "", variant = "") {
    return '<button class="button ' + variant + '" ' + attrs + '>' + esc(text) + '</button>';
  }
  function disabled(flag) { return flag ? " disabled" : ""; }
  function chip(text) { return '<span class="pill">' + esc(text) + '</span>'; }
  function progress(value, max) {
    return '<progress class="meter" value="' +
      Math.max(0, Math.min(max, Number(value) || 0)) + '" max="' +
      Math.max(1, max) + '" aria-label="Skill progress"></progress>';
  }
  function panel(title, sub, body, extra = "") {
    return '<section class="panel"><div class="panel-head"><div><h3>' + esc(title) +
      '</h3>' + (sub ? '<p>' + esc(sub) + '</p>' : '') +
      '</div>' + extra + '</div>' + body + '</section>';
  }
  function notify(message, error = false) {
    let alert = document.querySelector(".alert");
    if (alert) alert.remove();
    alert = document.createElement("div");
    alert.className = "alert" + (error ? " error" : "");
    alert.setAttribute("role", "status");
    alert.textContent = message;
    document.body.appendChild(alert);
    setTimeout(() => { if (alert.isConnected) alert.remove(); }, 4300);
  }
  function nextId() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "web:" + Date.now() + ":" + Math.random().toString(36).slice(2);
  }

  async function request(url, body) {
    const headers = multiMode ? {} : { "X-Game-Token": token };
    if (multiMode && body !== undefined &&
        url !== "/api/auth/login" && url !== "/api/auth/register") {
      headers["X-CSRF-Token"] = csrfToken;
    }
    const options = { method: body === undefined ? "GET" : "POST", headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    let data;
    try { data = await response.json(); } catch { throw Error("The server sent an invalid response"); }
    if ((url === "/api/state" && data.next_world_tick_seconds !== undefined) ||
        (data.state && data.state.next_world_tick_seconds !== undefined)) {
      clockSyncedAt = Date.now();
    }
    if (response.status === 401) authNeeded = true;
    if (!response.ok) throw Error(data.error || "Request failed");
    authNeeded = false;
    offline = false;
    return data;
  }

  async function load() {
    try {
      const health = await request("/api/health");
      multiMode = health.mode === "multi-account-local";
      inviteRequired = Boolean(health.invite_required);
      secureWorldClock = multiMode && !Boolean(health.dev_fast_forward);
      if (multiMode) {
        const account = await request("/api/auth/session");
        csrfToken = account.csrf || "";
        if (!account.authenticated) {
          authNeeded = true;
          offline = false;
          state = null;
          render();
          return;
        }
      }
      state = await request("/api/state");
      tab = state.duel && state.duel.role !== "defender" ? "duel" : "character";
      syncAttunements();
      initializeReadMarkers();
      startLiveEvents();
      startPresence();
    } catch (error) {
      offline = !authNeeded;
      if (!authNeeded) notify(error.message, true);
    }
    render();
  }
  function syncAttunements() {
    if (state && state.started) selectedAttunements = new Set(state.player.attuned_paths);
  }
  async function send(path, body, success = "Action complete") {
    if (pending) return;
    pending = true;
    render();
    try {
      const result = await request(path, body);
      const oldLevel = state && state.started ? state.player.level : 1;
      const oldStats = state && state.started ? {
        hp: state.player.max_hp,
        strength: state.player.strength,
        defense: state.player.defense
      } : { hp: 0, strength: 0, defense: 0 };
      // A live event may arrive after a command commits but before its HTTP
      // response. Never overwrite a newer pushed state with an older result.
      state = (multiMode && state && result.state &&
               (state.activity_revision || 0) >
               (result.state.activity_revision || 0)) ?
        await request("/api/state") : result.state;
      if (state && state.started && state.player.level > oldLevel) {
        levelCelebration = { from: oldLevel, to: state.player.level,
          hp: state.player.max_hp - oldStats.hp,
          strength: state.player.strength - oldStats.strength,
          defense: state.player.defense - oldStats.defense };
      }
      syncAttunements();
      if (body && ["start_duel", "duel_turn", "flee_duel"].includes(body.action)) {
        tab = "duel";
      }
      if (body && body.action === "practice_magic" && result.result) {
        latestPractice = { ...result.result, nodeId: body.params.node_id };
        tab = "magic";
      }
      if (body && body.action === "complete_city_contract" && result.result) {
        latestContract = result.result;
      }
      if (body && body.action === "send_chat") chatDraft = "";
      if (body && body.action === "flee_duel" && result.result &&
          result.result.outcome === "ongoing") {
        success = "Escape failed — the opponent counterattacked. Choose your next move.";
      } else if (body && body.action === "flee_duel") {
        success = "Combat ended";
      }
       if (path === "/api/new") tab = "character";
      if (body && body.action === "race_horse") tab = "track";
      notify(body && body.action === "cast_spell" && result.result ?
        result.result.message : success);
    } catch (error) {
      notify(error.message, true);
    } finally {
      pending = false;
      render();
    }
  }
  function action(name, params, success) {
    return send("/api/action", { action: name, params, id: nextId() }, success);
  }
  function advance(minutes) {
    return send("/api/advance", multiMode ?
      { minutes: Number(minutes), id: nextId() } :
      { minutes: Number(minutes) }, "World time advanced");
  }

  function authPage() {
    if (multiMode) return '<div class="entry"><div class="entry-card">' +
      '<div class="entry-seal">✦</div><div class="eyebrow">Local multi-account world</div>' +
      '<h1>Welcome to Oathmere</h1>' +
      '<p>Each player has a private login and a separate character. ' +
      'This development server runs on your own computer.</p>' +
      '<form id="accountLoginForm" class="stack">' +
      '<label for="loginUsername">Username</label>' +
      '<input id="loginUsername" class="field" autocomplete="username" ' +
      'maxlength="24" required>' +
      '<label for="loginPassword">Password</label>' +
      '<input id="loginPassword" class="field" type="password" ' +
      'autocomplete="current-password" required>' +
      '<button class="button full gold" type="submit">Sign in</button></form>' +
      '<details class="account-register"><summary>Create an account</summary>' +
      '<form id="accountRegisterForm" class="stack">' +
      '<label for="registerUsername">Username</label>' +
      '<input id="registerUsername" class="field" autocomplete="username" ' +
      'minlength="3" maxlength="24" required>' +
      '<label for="registerCharacter">Character name</label>' +
      '<input id="registerCharacter" class="field" minlength="2" maxlength="28" required>' +
      (inviteRequired ?
      '<label for="registerInvite">Invitation code</label>' +
      '<input id="registerInvite" class="field" autocomplete="off" ' +
      'placeholder="One-time code from game operator" required>' : "") +
      '<label for="registerPassword">Password (12 characters minimum)</label>' +
      '<input id="registerPassword" class="field" type="password" ' +
      'autocomplete="new-password" minlength="12" maxlength="128" required>' +
      '<button class="button full" type="submit">Create character</button>' +
      '</form></details>' +
      '<p class="small">Development-only: local computer access. Do not expose this ' +
      'login server over the internet or ordinary LAN HTTP.</p>' +
      '</div></div>';
    return '<div class="entry"><div class="entry-card">' +
      '<div class="entry-seal">✦</div><div class="eyebrow">Private local world</div>' +
      '<h1>Enter the city gates</h1>' +
      '<p>This server requires the access code printed in its terminal. ' +
      'Only connect over your own trusted local network.</p>' +
      '<form id="accessForm"><label class="sr" for="access">Access code</label>' +
      '<input id="access" class="field" type="password" autocomplete="off" placeholder="Server access code" required>' +
      '<button class="button full" type="submit">Enter world</button></form></div></div>';
  }
  async function accountSubmit(url, body) {
    if (pending) return;
    pending = true;
    try {
      const outcome = await request(url, body);
      csrfToken = outcome.csrf || "";
      state = outcome.state;
      chatChannelKey = "global";
      chatDirectTarget = null;
      chatOpen = false;
      initializeReadMarkers();
      startLiveEvents();
      startPresence();
      authNeeded = false;
      offline = false;
      tab = "character";
      syncAttunements();
      notify(url.endsWith("register") ? "Character created" : "Signed in");
    } catch (error) {
      notify(error.message, true);
    } finally {
      pending = false;
      render();
    }
  }

  function newCharacterPage() {
    return '<div class="entry"><div class="entry-card">' +
      '<div class="entry-seal">✦</div><div class="eyebrow">Welcome, traveler</div>' +
      '<h1>Your story begins here.</h1>' +
      '<p>Five cities. Many ways to earn your fortune. Buy and sell goods, learn the arcane arts, ' +
      'and work toward a home of your own.</p>' +
      '<form id="newGameForm"><label class="sr" for="heroName">Character name</label>' +
      '<input class="field" id="heroName" maxlength="28" autocomplete="off" placeholder="Choose your character name" required>' +
      '<button class="button full gold" type="submit"' + disabled(pending) +
      '>Begin your adventure</button></form>' +
      '<p class="small">Starts in Goldmeadow with 240 gold. Your progress saves on this computer.</p>' +
      '</div></div>';
  }
  function offlinePage() {
    return '<div class="entry"><div class="entry-card"><div class="entry-seal">⌁</div>' +
      '<h1>World unavailable</h1><p>Could not reach the Python game server. ' +
      'Make sure it is running, then try again.</p>' +
      button("Reconnect", 'data-ui="reload"', "full") + '</div></div>';
  }

  function meterStat(label, value, max, kind, simSeconds) {
    const v = Number(value) || 0;
    const maximum = Math.max(1, Number(max) || 1);
    const hint = v >= maximum ? "Full" :
      simSeconds == null ? "No passive recovery available" : "Next increase in ";
    const timing = v < maximum && simSeconds != null ?
      timerAttrs(hint, simSeconds) : ' data-hover-text="' + esc(hint) + '"';
    return '<div class="vital vital-' + kind +
      '"' + timing + ' tabindex="0" aria-label="' +
      esc(label + ': ' + v + ' of ' + maximum + '. ' +
        (simSeconds == null ? hint : hint + fullCountdown(timerSeconds(simSeconds)))) + '">' +
      '<div class="vital-caption"><span class="vital-icon" aria-hidden="true">' +
      (kind === "health" ? "+" : kind === "stamina" ?
        '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
        'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="m13 2-9 12h8l-1 8 9-12h-8z"/></svg>' : "✦") +
      '</span><strong>' +
      v + '/' + maximum + '</strong></div>' +
      '<progress value="' + Math.max(0, Math.min(maximum, v)) +
      '" max="' + maximum + '" aria-label="' + esc(label) + '"></progress></div>';
  }
  function cooldownClock(minutes) {
    const total = Math.max(0, Number(minutes) || 0);
    return String(Math.floor(total / 60)).padStart(2, "0") + ":" +
      String(total % 60).padStart(2, "0");
  }
  function cooldownIcon(name) {
    const config = {
      job: { symbol: "▣", label: "Job" },
      food: { symbol: "♨", label: "Food" },
      potion: { symbol: "⚗", label: "Potion" },
    }[name];
    const data = state.player.cooldowns && state.player.cooldowns[name];
    const remaining = data ? data.remaining_minutes : 0;
    const max = data ? data.max_minutes : 1440;
    if (remaining <= 0) return "";
    const tip = config.label + " cooldown: ";
    return '<div class="cooldown-chip ' + (remaining >= max ? 'at-cap' : '') +
      '"' + timerAttrs(tip, remaining * 60) +
      ' tabindex="0" aria-label="' + esc(tip + fullCountdown(timerSeconds(remaining * 60))) +
      '"><span aria-hidden="true">' + config.symbol + '</span><strong>' +
      cooldownClock(remaining) + '</strong></div>';
  }
  function activityIcons() {
    if (!state || !state.started) return "";
    const items = ["job", "food", "potion"].map(cooldownIcon).join("");
    const p = state.player;
    const incoming = multiMode ? (state.trades || []).filter(t =>
      t.recipient === state.actor_id).length : 0;
    const trade = incoming ?
      '<button class="cooldown-chip activity-clickable activity-trade" type="button" ' +
      'data-ui="activity-trade" title="' + incoming + ' incoming trade offer(s)" ' +
      'aria-label="' + incoming + ' incoming trade offer(s)">' +
      '<span aria-hidden="true">⇄</span><strong>' + incoming + ' trade' +
      (incoming === 1 ? '' : 's') + '</strong></button>' : "";
    const tripMinutes = p.destination && Number.isFinite(p.arrival_minute) ?
      Math.max(0, p.arrival_minute - state.minute) : 0;
    const travel = p.destination ?
      '<button class="cooldown-chip activity-clickable" type="button" data-ui="activity-travel" ' +
      timerAttrs("Traveling to " + pretty(p.destination) + " · ", tripMinutes * 60) + ' ' +
      'aria-label="' + esc("Traveling to " + pretty(p.destination)) + '">' +
      '<span aria-hidden="true">♞</span><strong>' + esc(simDuration(tripMinutes)) +
      '</strong></button>' : "";
    const hall = state.training_hall || {};
    const current = hall.active;
    let university = "";
    if (current) {
      const school = (hall.schools || []).find(s => s.id === current.school);
      const course = school && school.courses[current.index];
      const label = "University: " + (school ? school.name : pretty(current.school)) +
        (course ? " · " + course.name : "") + " · ";
      university = '<button class="cooldown-chip activity-clickable" type="button" ' +
        'data-ui="activity-university"' +
        timerAttrs(label, current.remaining_minutes * 60) + ' aria-label="' +
        esc(label + fullCountdown(timerSeconds(current.remaining_minutes * 60))) +
        '"><span aria-hidden="true">✤</span><strong>' +
        Math.ceil(current.remaining_minutes / 1440) + 'd</strong></button>';
    }
    const defendant = state.duel;
    const hospitalMinutes = Math.max(0,
      Number(p.defeated_until || 0) - Number(state.minute || 0));
    const hospital = hospitalMinutes > 0 ?
      '<button type="button" class="cooldown-chip activity-clickable activity-hospital" ' +
      'data-ui="activity-hospital"' +
      timerAttrs("Hospitalized · ", hospitalMinutes * 60) +
      ' aria-label="Hospitalized">' +
      '<span aria-hidden="true">✚</span><strong>' +
      esc(simDuration(hospitalMinutes)) + '</strong></button>' : "";
    const defenderAlert = defendant && defendant.role === "defender" &&
      defendant.attack_started ?
      '<button class="cooldown-chip activity-clickable activity-combat" type="button" ' +
      'data-ui="activity-duel" title="' +
      esc("Under attack by " + state.duel.opponent_name +
        " · your character automatically counterattacks. Open to watch or flee.") +
      '" aria-label="Under attack · open combat">' +
      '<span aria-hidden="true">⚔</span><strong>Under attack</strong></button>' : "";
    return items + trade + travel + university + hospital + defenderAlert;
  }
  function navButton(entry, className = "") {
    return '<button type="button" class="nav-button ' + className +
      (tab === entry.id ? ' active' : '') +
      '" data-tab="' + esc(entry.id) + '" aria-current="' +
      (tab === entry.id ? 'page' : 'false') + '">' +
      '<span class="nav-icon" aria-hidden="true">' + entry.icon + '</span>' +
      '<span>' + esc(entry.title) + '</span></button>';
  }
  function shell() {
    const p = state.player;
    const location = state.cities.find(c => c.id === p.city);
    const place = p.destination ? ("En route to " + pretty(p.destination)) :
      (location ? placeName(location.name) : pretty(p.city));
    const renderers = {
      world: renderWorld, market: renderMarket,
      magic: renderMagic, home: renderHome, job: renderJob,
      inventory: renderInventory, training: renderTraining,
      character: renderCharacter, equipment: renderEquipment,
      chronicle: renderChronicle, warriors: renderWarriorsGuild,
      mageguild: renderMageGuild, tavern: renderTavern,
      cityhall: renderCityHall,
      church: renderChurch, people: renderPeople, armory: renderArmory,
      duel: renderDuel, track: renderTrack,
      profile: renderProfile,
      trade: renderTrade,
      guilds: renderGuilds, merits: renderMerits,
    };
    const view = state.duel && state.duel.role !== "defender" ?
      renderDuel : (renderers[tab] || renderWorld);
    const sidebar = cityLinks.filter(t => !t.onlyCity || t.onlyCity === p.city)
      .map(t => navButton(t)).join('');
    const topLinks = accountTabs.map(t => navButton(t, "account-button")).join('');
    return '<div class="shell">' +
      '<header class="topbar"><div class="topbar-inner">' +
      '<div class="brand"><div class="brand-mark">✦</div><span>OATHMERE</span></div>' +
      '<div class="statbar" aria-label="Character vitals">' +
      meterStat("Health", p.hp, p.max_hp, "health", p.health_next_sim_seconds) +
      meterStat("Stamina", p.stamina, p.max_stamina, "stamina", p.stamina_next_sim_seconds) +
      meterStat("Mana", p.mana, p.max_mana, "mana", p.mana_next_sim_seconds) +
      '<div class="gold-total"><strong>' +
      esc(money(p.gold)) + '</strong></div>' +
      '<div class="cooldown-strip activity-strip" aria-label="Active activities">' +
      activityIcons() + '</div></div>' +
      '<div class="top-actions">' +
      '<div class="world-time"><span>Oathmere time</span>' +
      '<strong id="eastern-clock">' + esc(easternNow()) + '</strong></div>' +
      '<nav class="account-nav" aria-label="Character menu">' + topLinks + '</nav>' +
      (multiMode ? '<button class="logout-link" type="button" data-ui="account-logout">' +
        'Sign out</button>' : '') +
      '</div></div></header>' +
      '<div class="workspace">' +
      '<aside class="sidebar" aria-label="Locations and services">' +

      '<div class="sidebar-place"><strong>' + esc(place) + '</strong></div>' +
      '<nav class="side-nav" aria-label="City locations">' + sidebar + '</nav>' +
      '</aside><div class="main-column">' +
      '<details class="mobile-nav"><summary>☷ &nbsp; Locations & services · ' +
      esc(place) + '</summary><nav aria-label="Mobile locations">' + sidebar +
      '</nav></details>' +
      '<main class="page" id="main-content">' + view() +
      '</main></div></div></div>';
  }

  function inventoryPanel() {
    const p = state.player;
    const inventory = Object.entries(p.inventory).filter(([, qty]) => qty > 0).sort();
    let body = inventory.length ? inventory.map(([item, qty]) => (
      '<div class="inventory-row"><span>' + esc(pretty(item)) +
      '</span><strong>× ' + qty + '</strong></div>'
    )).join("") : '<div class="empty">No items yet. Gather resources or visit a market.</div>';
    body += '<div class="divider"></div><div class="small">No fixed inventory limit in town. ' +
      'To travel, carry at most ' + p.cargo_limit +
      ' units, including equipment.</div>';
    return panel("Carried inventory", "Goods and resources", body, chip(p.cargo + " items"));
  }
  const chronicleCategories = ["Trade", "Combat", "Travel", "University",
    "Economy", "Equipment", "Magic", "Health", "Racing", "Property",
    "Guild", "Progression", "Other"];
  function chronicleEvents() {
    const query = chronicleQuery.trim().toLowerCase();
    return (state.events || []).filter(event =>
      (chronicleCategory === "all" || event.category === chronicleCategory) &&
      (!query || [event.text, event.kind, event.category].some(value =>
        String(value || "").toLowerCase().includes(query))));
  }
  function chronicleItems(events) {
    return events.length ? '<ul class="activity">' +
      events.map(e => '<li><span><span class="chronicle-tag">' +
        esc(e.category || "Other") + '</span> ' + esc(e.text) +
        '</span><time title="Simulation elapsed: ' + esc(clock(e.minute)) +
        '">' + esc(eventTime(e)) + '</time></li>').join("") +
      '</ul>' : '<p class="empty">No matching Chronicle events.</p>';
  }
  function activityPanel(showTitle = true) {
    const body = chronicleItems((state.events || []).slice(0, 12));
    return showTitle ? panel("Chronicle", "", body) :
      '<section class="panel chronicle-panel">' + body + '</section>';
  }
  // View modules receive a narrow interface rather than owning networking,
  // action execution or the mutable simulation state.
  const { renderWorld, renderMarket, renderMagic, renderHome } =
    createWorldViews({
      getState: () => state,
      getPending: () => pending,
      getSecureWorldClock: () => secureWorldClock,
      getSchool: () => school,
      setSchool: value => { school = value; },
      getLatestPractice: () => latestPractice,
      getSelectedAttunements: () => selectedAttunements,
      esc, pretty, dur, disabled, button, panel, heading, isBusy, progress, money,
    });

  function heading(kicker, title, subtitle) {
    // Page hierarchy: location is already in the sidebar; the page only needs a title.
    return '<div class="heading-row"><div><h2>' + esc(title) + '</h2>' +
      (subtitle ? '<p class="subheading">' + esc(subtitle) + '</p>' : '') +
      '</div></div>';
  }
  // Community presentation consumes scoped UI state, never network credentials
  // or mutable authoritative game objects.
  const { renderPeople, renderProfile, renderTrade, renderDuel } =
    createCommunityViews({
      getState: () => state,
      getPeopleQuery: () => peopleQuery,
      getSearchScope: () => searchScope,
      getMultiMode: () => multiMode,
      getSelectedCharacterId: () => selectedCharacterId,
      getPending: () => pending,
      esc, pretty, money, dur, button, disabled, isBusy, heading, panel,
      characterRow, progress, chip,
    });
  const { renderInventory, renderCharacter, renderEquipment, renderArmory } =
    createCharacterViews({
      getState: () => state,
      esc, pretty, clock, money, button, disabled, isBusy, heading, panel,
      characterRow,
    });
  function renderChronicle() {
    const options = ['<option value="all">All categories</option>'].concat(
      chronicleCategories.map(category => '<option value="' + esc(category) + '"' +
        (chronicleCategory === category ? " selected" : "") + '>' +
        esc(category) + '</option>')).join("");
    return heading("", "Chronicle", "") +
      '<section class="panel chronicle-panel">' +
      '<div class="chronicle-filters"><label for="chronicle-category">Event category</label>' +
      '<select id="chronicle-category" class="field">' + options + '</select>' +
      '<label for="chronicle-query">Search events</label>' +
      '<input id="chronicle-query" class="field" type="search" ' +
      'placeholder="Trade, combat, equipment…" maxlength="100" value="' +
      esc(chronicleQuery) + '"></div>' +
      '<div id="chronicle-list">' + chronicleItems(chronicleEvents()) + '</div>' +
      '</section>' +
      '<p class="small mt-13">New actions are recorded in Eastern time (24-hour clock). ' +
      'Older actions without saved timestamps are marked earlier. ' +
      (secureWorldClock ?
        'The multiplayer simulation follows server time.</p>' :
        'The simulation advances only when you take time-based actions.</p>');
  }
  function characterRow(label, value) {
    return '<div class="character-row"><span>' + esc(label) +
      '</span><strong>' + esc(value) + '</strong></div>';
  }
  const { renderWarriorsGuild, renderMageGuild, renderChurch, renderTrack,
    renderGuilds, renderMerits, renderCityHall, renderJob, renderTraining, renderTavern } =
    createCityViews({
      getState: () => state,
      getLatestContract: () => latestContract,
      getExpandedUniversitySchool: () => expandedUniversitySchool,
      getPending: () => pending,
      getSecureWorldClock: () => secureWorldClock,
      esc, pretty, money, dur, button, disabled, isBusy, heading, panel,
      characterRow, chip,
    });
  function levelUpOverlay() {
    if (!levelCelebration) return "";
    return '<div class="level-overlay" role="dialog" aria-modal="true" ' +
      'aria-labelledby="level-title"><div class="level-card">' +
      '<div class="level-sparks">✦ ✧ ✦</div>' +
      '<h2 id="level-title">LEVEL ' + levelCelebration.to + '!</h2>' +
      '<div class="level-gains"><span>+' +
      (levelCelebration.to - levelCelebration.from) + ' level</span>' +
      '<span>+' + levelCelebration.hp + ' Health Capacity</span>' +
      '<span>+' + levelCelebration.strength + ' Strength</span>' +
      '<span>+' + levelCelebration.defense + ' Defense</span></div>' +
      button("Continue", 'data-ui="dismiss-level"', "gold") +
      '</div></div>';
  }

  function chatReadKey(channel) {
    return "oathmere.read." + (state && state.actor_id || "hero") + "." + channel;
  }
  function readMarker(channel) {
    try {
      return Math.max(0, Number(localStorage.getItem(chatReadKey(channel))) || 0);
    } catch { return 0; }
  }
  function saveReadMarker(channel, id) {
    try {
      localStorage.setItem(chatReadKey(channel), String(Math.max(
        id, readMarker(channel))));
    } catch { /* Storage blocked: unread counts remain session-only. */ }
  }
  function initializeReadMarkers() {
    if (!multiMode || !state || !state.chat) return;
    for (const channel of state.chat.channels || []) {
      const key = chatReadKey(channel.key);
      try {
        if (localStorage.getItem(key) === null) {
          const newest = Math.max(0, ...(state.chat.messages || [])
            .filter(m => m.channel_key === channel.key).map(m => m.id));
          localStorage.setItem(key, String(newest));
        }
      } catch { /* Continue without durable read cursors. */ }
    }
  }
  function markChannelRead(channel) {
    if (!multiMode || !state || !state.chat || !channel ||
        document.visibilityState === "hidden") return;
    const newest = Math.max(0, ...(state.chat.messages || [])
      .filter(m => m.channel_key === channel).map(m => m.id));
    saveReadMarker(channel, newest);
  }
  function unreadCount() {
    if (!multiMode || !state || !state.chat) return 0;
    return (state.chat.messages || []).filter(message =>
      message.sender !== state.actor_id &&
      message.id > readMarker(message.channel_key)).length;
  }
  async function publishPresence() {
    if (!multiMode || !csrfToken || !state || !state.started) return;
    try {
      await request("/api/presence", {
        visible: document.visibilityState === "visible" &&
          Date.now() - lastUserActivity < 5 * 60 * 1000
      });
    } catch { /* The connection can be interrupted; the next ping retries. */ }
  }
  function startPresence() {
    if (!multiMode || presenceTimer) return;
    publishPresence();
    presenceTimer = setInterval(publishPresence, 25000);
  }
  function stopPresence() {
    if (presenceTimer) clearInterval(presenceTimer);
    presenceTimer = null;
  }
  document.addEventListener("visibilitychange", publishPresence);

  function stopLiveEvents() {
    if (liveEvents) {
      liveEvents.close();
      liveEvents = null;
    }
  }
  function startLiveEvents() {
    if (!multiMode || !state || !state.started ||
        typeof EventSource === "undefined" || liveEvents) return;
    const stream = new EventSource("/api/events");
    liveEvents = stream;
    const receiveActivity = event => {
      if (stream !== liveEvents || !state || !state.started) return;
      let update;
      try { update = JSON.parse(event.data); } catch { return; }
      if (update.actor_id !== state.actor_id ||
          update.revision < (state.activity_revision || 0)) return;
      state.activity_revision = update.revision;
      if ("chat" in update) state.chat = update.chat;
      if ("trades" in update) state.trades = update.trades;
      if ("minute" in update) state.minute = update.minute;
      if ("next_world_tick_seconds" in update) {
        state.next_world_tick_seconds = update.next_world_tick_seconds;
        clockSyncedAt = Date.now();
      }
      if ("duel" in update) state.duel = update.duel;
      if ("last_duel" in update) state.last_duel = update.last_duel;
      if (state.training_hall) state.training_hall.active = update.course_active;
      if (Array.isArray(update.users)) state.users = update.users;
      if (Array.isArray(update.events)) state.events = update.events;
      if (update.player_status) {
        Object.assign(state.player, update.player_status);
      }
      if (chatOpen) markChannelRead(chatChannelKey);
      refreshLiveSurfaces();
    };
    stream.addEventListener("activity", receiveActivity);
    stream.addEventListener("activity-delta", receiveActivity);
    // EventSource reconnects automatically and sends the session cookie.
    // This stream intentionally has no client-controlled actor identifier.
  }
  function refreshLiveSurfaces() {
    if (!state || !state.started) return;
    const strip = document.querySelector(".activity-strip");
    if (strip) strip.innerHTML = activityIcons();
    // Pushed clock ticks also change the health, stamina and mana values.
    const p = state.player;
    for (const [kind, label, value, maximum, next] of [
      ["health", "Health", p.hp, p.max_hp, p.health_next_sim_seconds],
      ["stamina", "Stamina", p.stamina, p.max_stamina, p.stamina_next_sim_seconds],
      ["mana", "Mana", p.mana, p.max_mana, p.mana_next_sim_seconds],
    ]) {
      const old = document.querySelector(".vital-" + kind);
      if (old) old.outerHTML = meterStat(label, value, maximum, kind, next);
    }
    const dock = document.querySelector(".chat-dock");
    if (dock) {
      const fragment = document.createElement("div");
      fragment.innerHTML = chatDock();
      const fresh = fragment.querySelector(".chat-dock");
      if (fresh) {
        const oldToggle = dock.querySelector(".chat-toggle");
        const newToggle = fresh.querySelector(".chat-toggle");
        if (oldToggle && newToggle) oldToggle.innerHTML = newToggle.innerHTML;
        if (chatOpen) {
          for (const selector of [".chat-channels", ".chat-history"]) {
            const old = dock.querySelector(selector);
            const next = fresh.querySelector(selector);
            if (!old || !next || old.innerHTML === next.innerHTML) continue;
            const atBottom = old.scrollHeight - old.scrollTop - old.clientHeight < 32;
            old.innerHTML = next.innerHTML;
            if (selector === ".chat-history" && atBottom) old.scrollTop = old.scrollHeight;
          }
        }
      }
    }
    if (tab === "duel" || (state.duel && state.duel.role === "attacker")) {
      const content = document.getElementById("main-content");
      if (content) content.innerHTML = renderDuel();
    }
    if (tab === "people") {
      // Replace just the search results, preserving a search being typed.
      const matches = document.querySelector(".search-matches");
      if (matches) {
        const temp = document.createElement("div");
        temp.innerHTML = renderPeople();
        const latest = temp.querySelector(".search-matches");
        if (latest && matches.innerHTML !== latest.innerHTML)
          matches.innerHTML = latest.innerHTML;
      }
    } else if (tab === "profile") {
      const content = document.getElementById("main-content");
      if (content) content.innerHTML = renderProfile();
    } else if (tab === "chronicle") {
      const list = document.getElementById("chronicle-list");
      if (list) list.innerHTML = chronicleItems(chronicleEvents());
    }
    if (tab === "trade") {
      const current = document.getElementById("trade-offers-list");
      if (current) {
        const frame = document.createElement("div");
        frame.innerHTML = renderTrade();
        const next = frame.querySelector("#trade-offers-list");
        if (next && current.innerHTML !== next.innerHTML)
          current.innerHTML = next.innerHTML;
      }
    }
    const header = document.querySelector(".statbar");
    if (header) {
      const fresh = [
        meterStat("Health", state.player.hp, state.player.max_hp,
                  "health", state.player.health_next_sim_seconds),
        meterStat("Stamina", state.player.stamina, state.player.max_stamina,
                  "stamina", state.player.stamina_next_sim_seconds),
        meterStat("Mana", state.player.mana, state.player.max_mana,
                  "mana", state.player.mana_next_sim_seconds)
      ];
      const oldVitals = header.querySelectorAll(".vital");
      oldVitals.forEach((node, i) => {
        if (fresh[i] && node.outerHTML !== fresh[i]) node.outerHTML = fresh[i];
      });
      const moneyLabel = header.querySelector(".gold-total strong");
      if (moneyLabel) moneyLabel.textContent = money(state.player.gold);
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && chatOpen) {
      markChannelRead(chatChannelKey);
      refreshLiveSurfaces();
    }
  });

  function chatDock() {
    if (!state || !state.started) return "";
    const chat = state.chat || { channels: [], messages: [] };
    const available = chat.channels.slice();
    if (multiMode && chatDirectTarget &&
        !available.some(x => x.key === "direct:" + chatDirectTarget)) {
      const user = (state.users || []).find(x => x.id === chatDirectTarget);
      if (user && user.kind === "human") {
        available.push({ key: "direct:" + chatDirectTarget, kind: "direct",
                         target: chatDirectTarget, label: user.name });
      }
    }
    const selected = available.find(x => x.key === chatChannelKey) ||
      available[0] || { key: "global", kind: "global", target: "", label: "Global" };
    const posts = (chat.messages || []).filter(x => x.channel_key === selected.key);
    const channels = available.map(channel =>
      button(channel.label, 'data-ui="chat-channel" data-key="' + esc(channel.key) +
        '" aria-pressed="' + (selected.key === channel.key) + '"',
        selected.key === channel.key ? "secondary" : "ghost")).join('');
    return '<aside class="chat-dock ' + (chatOpen ? "is-open" : "") +
      '" aria-label="Chat">' +
      '<div class="chat-dock-actions"><button type="button" class="chat-toggle" data-ui="chat-toggle" ' +
      'aria-expanded="' + chatOpen + '">' +
      '<span aria-hidden="true">✉</span> Chat ' +
      (unreadCount() ? '<span class="chat-unread" aria-label="' +
        unreadCount() + ' unread chat messages">' + Math.min(99, unreadCount()) +
        (unreadCount() > 99 ? '+' : '') + '</span>' : '') +
      (chatOpen ? '⌄' : '⌃') + '</button>' +
      '<button class="chat-game-refresh" type="button" data-ui="refresh-game" ' +
      'title="Refresh the entire game state" aria-label="Refresh game state">' +
      '↻</button></div>' +
      (chatOpen ? '<div class="chat-content">' +
        '<div class="chat-channels">' + channels + '</div>' +
        '<p class="chat-preview-notice">' + (multiMode ?
          'Live local chat · Unread messages appear beside the Chat tab.' :
          'Local preview: only one human account is connected. ' +
          'Live player-to-player chat requires separate authenticated accounts.') +
        '</p>' +
        '<div class="chat-history" aria-live="polite">' +
        (posts.length ? posts.map(post =>
          '<div class="chat-post"><strong>' +
          esc(post.sender_name ||
              (post.sender === (state.actor_id || "hero") ? state.name : post.sender)) +
          '</strong><p>' + esc(post.body) +
          '</p></div>').join('') :
          '<p class="small">No messages in this channel yet.</p>') +
        '</div>' +
        '<form id="chatComposeForm" class="chat-compose">' +
        '<label class="sr-only" for="chat-text">Chat message</label>' +
        '<input id="chat-text" class="field" maxlength="400" ' +
        'placeholder="Write a message" autocomplete="off" value="' +
        esc(chatDraft) + '"' + disabled(pending) + '>' +
        '<button type="submit" class="button secondary" ' +
        (pending || !chatDraft.trim() ? 'disabled' : '') + '>Send</button>' +
        '</form></div>' : '') +
      '</aside>';
  }

  function render() {
    if (authNeeded) root.innerHTML = authPage();
    else if (offline) root.innerHTML = offlinePage();
    else if (state && !state.started) root.innerHTML = newCharacterPage();
    else if (state && state.started) root.innerHTML = shell() +
      chatDock() + levelUpOverlay();
    else root.innerHTML = '<main class="startup"><div class="loader-ring"></div>' +
      '<p>Opening the city gates…</p></main>';
  }

  root.addEventListener("submit", async event => {
    if (event.target.id === "newGameForm") {
      event.preventDefault();
      const name = document.getElementById("heroName").value.trim();
      if (name) await send("/api/new", { name }, "Welcome to the Five Cities!");
    } else if (event.target.id === "accessForm") {
      event.preventDefault();
      token = document.getElementById("access").value.trim();
      sessionStorage.setItem("medieval-world-token", token);
      await load();
    } else if (event.target.id === "accountLoginForm") {
      event.preventDefault();
      await accountSubmit("/api/auth/login", {
        username: document.getElementById("loginUsername").value.trim(),
        password: document.getElementById("loginPassword").value
      });
    } else if (event.target.id === "accountRegisterForm") {
      event.preventDefault();
      await accountSubmit("/api/auth/register", {
        username: document.getElementById("registerUsername").value.trim(),
        display_name: document.getElementById("registerCharacter").value.trim(),
        password: document.getElementById("registerPassword").value,
        ...(inviteRequired ? {
          invite: document.getElementById("registerInvite").value.trim()
        } : {})
      });
    } else if (event.target.id === "tradeOfferForm") {
      event.preventDefault();
      const field = id => document.getElementById(id).value;
      const integer = id => Number(field(id));
      const offerGold = integer("trade-offer-gold");
      const requestGold = integer("trade-request-gold");
      const offerQuantity = integer("trade-offer-quantity");
      const requestQuantity = integer("trade-request-quantity");
      const requestedGear = integer("trade-request-gear");
      if (![offerGold, requestGold, offerQuantity, requestQuantity, requestedGear]
          .every(n => Number.isSafeInteger(n) && n >= 0)) {
        notify("Trade quantities must be nonnegative whole numbers", true);
        return;
      }
      const offerItem = field("trade-offer-item");
      const requestItem = field("trade-request-item");
      if ((offerItem && !offerQuantity) || (!offerItem && offerQuantity) ||
          (requestItem && !requestQuantity) || (!requestItem && requestQuantity)) {
        notify("Choose an item and a quantity together", true);
        return;
      }
      const offerGear = field("trade-offer-gear");
      const offer = {
        gold: offerGold,
        items: offerItem ? [{ item: offerItem, quantity: offerQuantity }] : [],
        gear_ids: offerGear ? [Number(offerGear)] : []
      };
      const request = {
        gold: requestGold,
        items: requestItem ? [{ item: requestItem, quantity: requestQuantity }] : [],
        gear_ids: requestedGear ? [requestedGear] : []
      };
      if (!offer.gold && !offer.items.length && !offer.gear_ids.length &&
          !request.gold && !request.items.length && !request.gear_ids.length) {
        notify("A trade cannot be empty", true);
        return;
      }
      await action("propose_trade", {
        recipient_id: field("trade-recipient"), offer, request
      }, "Offer sent and your assets placed in escrow");
    } else if (event.target.id === "chatComposeForm") {
      event.preventDefault();
      let channel = (state.chat.channels || []).find(x => x.key === chatChannelKey);
      if (!channel && multiMode && chatDirectTarget &&
          chatChannelKey === "direct:" + chatDirectTarget) {
        const recipient = (state.users || []).find(person =>
          person.id === chatDirectTarget && person.kind === "human" &&
          person.id !== state.actor_id);
        if (recipient) channel = { kind: "direct", target: recipient.id };
      }
      // Never silently fall back to Global when a private channel is missing:
      // a message addressed to a person must not be broadcast accidentally.
      if (!channel && chatChannelKey === "global") {
        channel = (state.chat.channels || []).find(x => x.kind === "global");
      }
      if (channel && chatDraft.trim() && !pending) {
        await action("send_chat", {
          kind: channel.kind, target: channel.target, message: chatDraft.trim()
        }, "Message posted to local chat");
      }
    }
  });

  root.addEventListener("input", event => {
    if (event.target.id === "chronicle-query") {
      chronicleQuery = event.target.value;
      const list = document.getElementById("chronicle-list");
      if (list) list.innerHTML = chronicleItems(chronicleEvents());
      return;
    }
    if (event.target.id === "chat-text") {
      chatDraft = event.target.value;
      const submit = event.target.closest("form").querySelector('button[type="submit"]');
      if (submit) submit.disabled = !chatDraft.trim() || pending;
    }
  });

  root.addEventListener("change", event => {
    if (event.target.id === "chronicle-category") {
      chronicleCategory = event.target.value;
      const list = document.getElementById("chronicle-list");
      if (list) list.innerHTML = chronicleItems(chronicleEvents());
      return;
    }
    const path = event.target.getAttribute("data-attune");
    if (!path) return;
    if (event.target.checked) selectedAttunements.add(path);
    else selectedAttunements.delete(path);
  });

  root.addEventListener("click", event => {
    const summary = event.target.closest(".university-school > summary");
    if (summary) {
      const details = summary.parentElement;
      expandedUniversitySchool = details.open ? null : details.dataset.university;
      return;
    }
    const element = event.target.closest("button");
    if (!element || pending || element.disabled) return;
    if (element.dataset.tab) {
      tab = element.dataset.tab;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (element.dataset.school && !element.dataset.ui) {
      school = element.dataset.school;
      render();
      return;
    }
    const ui = element.dataset.ui;
    const item = element.dataset.item;
    const node = element.dataset.node;
    switch (ui) {
      case "account-logout":
        (async () => {
          try {
            await request("/api/auth/logout", {});
            stopLiveEvents();
            stopPresence();
            state = null;
            csrfToken = "";
            authNeeded = true;
            notify("Signed out");
            render();
          } catch (error) {
            notify(error.message, true);
          }
        })(); break;
      case "chat-toggle":
        chatOpen = !chatOpen;
        if (chatOpen) markChannelRead(chatChannelKey);
        render(); break;
      case "chat-channel":
        if (chatChannelKey !== element.dataset.key) chatDraft = "";
        chatChannelKey = element.dataset.key;
        markChannelRead(chatChannelKey);
        render(); break;
      case "refresh-game":
        (async () => {
          if (pending) return;
          try {
            const fresh = await request("/api/state");
            if (!multiMode || !state || !state.activity_revision ||
                (fresh.activity_revision || 0) >= state.activity_revision) {
              state = fresh;
            }
            syncAttunements();
            render();
            notify("Game state refreshed");
          } catch (error) {
            notify(error.message, true);
          }
        })(); break;
      case "chat-refresh":
        (async () => {
          try {
            state = await request("/api/state");
            render();
          } catch (error) { notify(error.message, true); }
        })(); break;
      case "profile-open":
        selectedCharacterId = element.dataset.character;
        tab = "profile";
        render();
        window.scrollTo({ top: 0, behavior: "smooth" });
        break;
      case "profile-chat":
        if (multiMode) {
          chatDirectTarget = element.dataset.character;
          if (chatChannelKey !== "direct:" + chatDirectTarget) chatDraft = "";
          chatChannelKey = "direct:" + chatDirectTarget;
          chatOpen = true;
          markChannelRead(chatChannelKey);
          render();
        } else {
          notify("Direct chat needs authenticated multiplayer accounts. NPCs cannot receive DMs.", true);
        }
        break;
      case "profile-trade":
        if (multiMode) {
          selectedCharacterId = element.dataset.character;
          tab = "trade";
          render();
        } else {
          notify("Player-to-player trading requires individual accounts.", true);
        }
        break;
      case "dismiss-level":
        levelCelebration = null; render(); break;
      case "guild-found": {
        const input = document.getElementById("guild-name");
        const name = input && input.value.trim();
        if (!name || name.length < 3) {
          notify('Enter a guild name of at least 3 characters', true); break;
        }
        action("found_guild", { name }, "Guild founded"); break;
      }
      case "guild-leave": action("leave_guild", {}, "Left your guild"); break;
      case "merit-claim":
        action("claim_merit", { achievement: element.dataset.achievement }, "Merit earned"); break;
      case "merit-buy":
        action("buy_merit_upgrade", { perk: element.dataset.perk }, "Permanent improvement unlocked"); break;
      case "church-heal":
        action("church_heal", {}, "The church restores your health"); break;
      case "activity-trade":
        tab = "trade"; render(); break;
      case "activity-duel":
        tab = "duel"; render(); break;
      case "activity-hospital":
        tab = "character"; render(); break;
      case "activity-travel":
        tab = "world"; render(); break;
      case "activity-university":
        tab = "training";
        if (state.training_hall && state.training_hall.active)
          expandedUniversitySchool = state.training_hall.active.school;
        render(); break;
      case "course-enroll":
        action("enroll_course_choice", {
          school: element.dataset.school, index: Number(element.dataset.index)
        }, "Course enrollment confirmed"); break;
      case "horse-buy":
        action("buy_racehorse", { breed: element.dataset.breed }, "Racehorse purchased"); break;
      case "horse-race":
        action("race_horse", { breed: element.dataset.breed }, "Race completed"); break;
      case "reload": load(); break;
      case "travel":
      case "map-travel":
        action("travel", { destination: element.dataset.target }, "Journey started"); break;
      case "gather": action("gather", { item, quantity: Number(element.dataset.qty) },
        "Resources added to your inventory"); break;
      case "advance": advance(Number(element.dataset.minutes)); break;
      case "buy":
      case "sell": {
        const quantity = Number(document.getElementById("qty-" + item).value);
        if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > 20) {
          notify("Select a whole quantity between 1 and 20", true);
          return;
        }
        action(ui === "buy" ? "regional_buy" : "regional_sell",
          { item, quantity }, ui === "buy" ? "Goods purchased" : "Goods sold");
        break;
      }
      case "store":
      case "retrieve": {
        const id = (ui === "store" ? "store-" : "retrieve-") + item;
        const input = document.getElementById(id);
        const quantity = Number(input && input.value);
        if (!Number.isSafeInteger(quantity) || quantity <= 0) {
          notify("Enter a positive whole quantity", true); return;
        }
        action(ui === "store" ? "store_goods" : "retrieve_goods",
          { item, quantity }, ui === "store" ? "Goods stored" : "Goods retrieved");
        break;
      }
      case "consume":
        action("consume", { item }, pretty(item) + " used"); break;
      case "contract": action("complete_city_contract",
        { contract_id: element.dataset.contract }, "Contract completed"); break;
      case "practice": action("practice_magic", { node_id: node }, "Practice completed"); break;
      case "find-people":
        peopleQuery = document.getElementById("people-query").value.trim();
        render(); break;
      case "search-type":
        peopleQuery = document.getElementById("people-query").value.trim();
        searchScope = element.dataset.scope === "market" ? "market" : "players";
        render(); break;
      case "trade-refresh":
        (async () => {
          try { state = await request("/api/state"); render(); }
          catch (error) { notify(error.message, true); }
        })(); break;
      case "trade-accept":
        action("accept_trade", {
          trade_id: Number(element.dataset.tradeId),
          terms_hash: element.dataset.termsHash
        }, "Trade completed"); break;
      case "trade-close":
        action("close_trade", { trade_id: Number(element.dataset.tradeId) },
          "Trade closed; escrow returned to maker"); break;
      case "player-attack":
        action("start_duel", { defender_id: element.dataset.player },
          "Challenge begun · choose your combat move"); break;
      case "duel-swing":
        action("duel_turn", { move: element.dataset.move, node_id: "" },
          "Attack resolved"); break;
      case "duel-strike":
        action("duel_turn", { move: "strike", node_id: "" }, "Strike resolved"); break;
      case "duel-guard":
        action("duel_turn", { move: "guard", node_id: "" }, "Guard resolved"); break;
      case "duel-cast":
        action("duel_turn", { move: "cast", node_id: node }, "Spell cast"); break;
      case "duel-flee":
        action("flee_duel", {}, "You escaped the duel"); break;
      case "field-cast":
        action("cast_spell", { node_id: node }, "Spell cast"); break;
      case "study-restoration":
        school = "restoration"; tab = "magic"; render(); break;
      case "unlock": action("unlock_magic", { node_id: node }, "New magical ability unlocked"); break;
      case "apply-attune":
        if (selectedAttunements.size > 2) {
          notify("Only two advanced specializations can be active", true);
          return;
        }
        action("attune_magic", { paths: Array.from(selectedAttunements) },
          "Magical specializations updated");
        break;
      case "buy-home": action("buy_home", { tier: element.dataset.tier }, "New home purchased"); break;
      case "upgrade-home": action("upgrade_home", { tier: element.dataset.tier }, "Home upgraded"); break;
      case "build-facility": action("build_home_facility",
        { facility: element.dataset.facility }, "Facility constructed"); break;
      case "buy-vehicle": action("buy_vehicle",
        { vehicle: element.dataset.vehicle }, "Vehicle purchased"); break;
      case "select-vehicle": action("select_vehicle",
        { vehicle: element.dataset.vehicle || null }, "Travel option changed"); break;
      case "buy-starter": action("buy_starter_gear",
        { kind: element.dataset.kind }, "New equipment purchased"); break;
      case "equip": action("equip",
        { gear_id: Number(element.dataset.gearId) }, "Equipment updated"); break;
      case "unequip": action("unequip",
        { slot: element.dataset.slot }, "Equipment removed"); break;
      default: break;
    }
  });

  load();
  setInterval(() => {
    updateEasternClock();
    updateHoverTimers();
  }, 1000);
})();
