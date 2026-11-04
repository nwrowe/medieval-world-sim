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
  let csrfToken = "";
  let liveEvents = null;
  let presenceTimer = null;

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
  function easternNow() { return easternFormatter.format(new Date()); }
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
      Boolean(state.player.destination) || state.player.hp <= 0 || Boolean(state.duel);
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

  async function request(url, body, keepalive = false) {
    const headers = multiMode ? {} : { "X-Game-Token": token };
    if (multiMode && body !== undefined &&
        url !== "/api/auth/login" && url !== "/api/auth/register") {
      headers["X-CSRF-Token"] = csrfToken;
    }
    const options = { method: body === undefined ? "GET" : "POST", headers,
      keepalive };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    let data;
    try { data = await response.json(); } catch { throw Error("The server sent an invalid response"); }
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
      tab = state.duel ? "duel" : "character";
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
    const oldStats = state && state.started ? {
      level: state.player.level, hp: state.player.max_hp,
      strength: state.player.strength, defense: state.player.defense
    } : null;
    pending = true;
    render();
    try {
      const result = await request(path, body);
      const oldLevel = oldStats ? oldStats.level : 1;
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
    let hint = "Full";
    if (v < maximum) hint = simSeconds == null ?
      "No passive recovery available" :
      "Next increase in " + simSeconds +
      " simulated seconds — use Rest or advance world time";
    return '<div class="vital vital-' + kind +
      '" title="' + esc(hint) + '" tabindex="0" aria-label="' +
      esc(label + ': ' + v + ' of ' + maximum + '. ' + hint) + '">' +
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
    const tip = config.label + " cooldown: " + cooldownClock(remaining) +
      " simulated time remaining. Advances with game time.";
    return '<div class="cooldown-chip ' + (remaining >= max ? 'at-cap' : '') +
      '" title="' + esc(tip) + '" tabindex="0" aria-label="' + esc(tip) +
      '"><span aria-hidden="true">' + config.symbol + '</span><strong>' +
      cooldownClock(remaining) + '</strong></div>';
  }
  function activityIcons() {
    if (!state || !state.started) return "";
    const items = ["job", "food", "potion"].map(cooldownIcon).join("");
    const p = state.player;
    const hospitalMinutes = Number.isFinite(p.defeated_until) ?
      Math.max(0, p.defeated_until - state.minute) : 0;
    const hospital = p.hp <= 0 && hospitalMinutes > 0 ?
      '<button class="cooldown-chip activity-clickable activity-hospital" ' +
      'type="button" data-ui="activity-hospital" title="' +
      esc("Hospitalized: " + simDuration(hospitalMinutes) +
        " of simulated time remaining") +
      '" aria-label="' + esc("Hospitalized: " + simDuration(hospitalMinutes)) +
      '"><span aria-hidden="true">✚</span><strong>' +
      esc(simDuration(hospitalMinutes)) + '</strong></button>' : "";
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
      'title="' + esc("Traveling to " + pretty(p.destination) + " · " +
        simDuration(tripMinutes) + " of simulated time remaining") + '" ' +
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
        (course ? " · " + course.name : "") + " · " +
        simDuration(current.remaining_minutes) + " simulated time remaining";
      university = '<button class="cooldown-chip activity-clickable" type="button" ' +
        'data-ui="activity-university" title="' + esc(label) + '" aria-label="' +
        esc(label) + '"><span aria-hidden="true">✤</span><strong>' +
        Math.ceil(current.remaining_minutes / 1440) + 'd</strong></button>';
    }
    const defenderAlert = state.duel && state.duel.role === "defender" &&
      state.duel.round > 0 ?
      '<button class="cooldown-chip activity-clickable activity-combat" type="button" ' +
      'data-ui="activity-duel" title="' +
      esc("Under attack by " + state.duel.opponent_name +
        " · your character automatically counterattacks. Open to watch or flee.") +
      '" aria-label="Under attack · open combat">' +
      '<span aria-hidden="true">⚔</span><strong>Under attack</strong></button>' : "";
    return hospital + items + trade + travel + university + defenderAlert;
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
  const mapLocations = {
    crownreach: { x: 50, y: 47.6 },
    ironvale: { x: 33.3, y: 27.6 },
    greenhollow: { x: 71.1, y: 33.2 },
    emberfall: { x: 65.0, y: 69.4 },
    goldmeadow: { x: 30.6, y: 78.5 },
  };
  function worldMap() {
    const p = state.player;
    const destination = p.destination;
    const pins = state.cities.map(city => {
      const point = mapLocations[city.id];
      if (!point) return "";
      const current = city.id === p.city;
      const arriving = city.id === destination;
      const inactive = pending || Boolean(destination) || p.hp <= 0 || current;
      return '<button class="map-pin map-' + esc(city.id) +
        (current ? ' is-here' : '') + (arriving ? ' is-destination' : '') +
        '" type="button" data-ui="map-travel" data-target="' + esc(city.id) +
        '" title="' + esc(city.name) +
        (current ? " — you are here" : arriving ? " — destination" :
          " — " + dur(city.minutes) + " away, click to travel") +
        '"' + disabled(inactive) + '>' +
        '<span class="map-pin-light"></span><strong>' + esc(city.name.replace(" (capital)", "")) +
        '</strong>' + (current ? '<small>You are here</small>' :
        arriving ? '<small>Destination</small>' : '') + '</button>';
    }).join("");
    return '<section class="world-atlas" aria-label="Illustrated map of the Five Cities">' +
      '<div class="atlas-canvas"><img src="/world-map.svg" alt="Antique ink-drawn fantasy realm with mountains, rivers, forests and royal roads">' +
      pins + '</div><div class="atlas-footer"><span>✦ Blue lights mark the cities</span>' +
      '<span>Click a city to begin traveling · Your location glows gold</span></div></section>';
  }

  function renderWorld() {
    const p = state.player;
    const traveling = Boolean(p.destination);
    const defeated = p.hp <= 0;
    const timeToArrival = traveling ? Math.max(1, p.arrival_minute - state.minute) : 0;
    const ready = !traveling && !defeated && state.minute >= p.ready_minute;
    const destinations = state.cities.filter(c => !c.is_current).map(city =>
      '<div class="mini-card"><div class="mini-card-top">' +
      '<div><div class="mini-card-title">' + esc(city.name) + '</div>' +
      '<div class="mini-card-sub">' + esc(dur(city.minutes)) + ' by your current route</div></div>' +
      '<span class="muted">◈</span></div>' +
      button("Travel", 'data-ui="travel" data-target="' + esc(city.id) + '"' +
        disabled(isBusy()), "full secondary") + '</div>'
    ).join("");
    const gathering = Object.entries(state.gatherable).map(([item, available]) => {
      const quantity = Math.min(2, available);
      return '<div class="resource-chip"><div><strong>' + esc(pretty(item)) +
        '</strong><div class="small">' + available + ' nearby</div></div>' +
        button(quantity > 0 ? "Gather " + quantity : "Unavailable", 'data-ui="gather" data-item="' +
          esc(item) + '" data-qty="' + quantity + '"' +
          disabled(!ready || quantity < 1 || pending), "s secondary") + '</div>';
    }).join("") || '<p class="small">The capital has no natural resource deposits. ' +
      'Visit the surrounding cities to gather materials.</p>';
    const journey = traveling ?
      '<section class="journey"><div class="section-kicker">Journey in progress</div>' +
      '<h3>Road to ' + esc(pretty(p.destination)) + '</h3>' +
      '<p>' + esc(dur(timeToArrival)) + ' until arrival. Your purchases and abilities ' +
      'are paused while traveling.</p>' +
      button("Complete journey", 'data-ui="advance" data-minutes="' + timeToArrival + '"' +
        disabled(pending)) + '</section>'
      : defeated ? '<div class="callout"><strong>Recovering</strong>Rest until your character ' +
        'has recovered before beginning another activity.</div>' : "";
    return heading("", "World Map", "") +
      worldMap() +
      '<div class="two-col"><div class="stack">' + journey +
      panel("Choose your destination", "All routes connect through the royal capital.",
        '<div class="card-grid">' + destinations + '</div>') +
      panel("Gather nearby resources", "Collect resources to sell locally or take to another city.",
        '<div class="resource-list">' + gathering + '</div>' +
        (!ready && !traveling ? '<p class="small mt-12">Gathering cooldown: ' +
          Math.max(0, p.ready_minute - state.minute) + ' minutes remaining.</p>' : "")) +
      panel("Time and recovery", "World time advances when you choose to rest or travel.",
        '<div class="button-group">' +
        button("Rest 1 hour", 'data-ui="advance" data-minutes="60"' + disabled(pending), "secondary") +
        button("Pass 6 hours", 'data-ui="advance" data-minutes="360"' + disabled(pending), "ghost") +
        button("Next day", 'data-ui="advance" data-minutes="1440"' + disabled(pending), "ghost") +
        '</div><p class="small mt-12">Stamina and mana recover with time. ' +
        'The world does not run in real time yet.</p>') +
      '</div><aside class="stack">' +
      panel("Roads of the Five Cities", "Current road network",
        '<div class="route-map"><strong>✦ Crownreach</strong>' +
        '<span>↙ Goldmeadow</span><span>↖ Ironvale</span>' +
        '<span>↗ Greenhollow</span><span>↘ Emberfall</span></div>' +
        '<p class="small">All roads presently lead through the royal capital. ' +
        'Travel times account for your current vehicle.</p>') +
      '</aside></div>';
  }

  function sellOnlyGoods() {
    const p = state.player;
    const stock = state.quotes.filter(quote =>
      !quote.locally_produced && quote.stock === 0 &&
      (p.inventory[quote.item] || 0) > 0);
    if (!stock.length) return "";
    const rows = stock.map(q => {
      const owned = p.inventory[q.item] || 0;
      const amount = Math.min(owned, q.buy_capacity,
        Math.floor(q.city_gold / q.player_sell_price));
      return '<div class="inventory-row"><span>' + esc(pretty(q.item)) +
        ' · owned ' + owned + ' · ' + q.player_sell_price + 'g each</span>' +
        '<label class="sr" for="qty-' + esc(q.item) + '">Quantity</label>' +
        '<input class="qty" id="qty-' + esc(q.item) +
        '" type="number" min="1" max="20" value="1">' +
        button("Sell", 'data-ui="sell" data-item="' + esc(q.item) + '"' +
        disabled(!amount || isBusy()), "s secondary") + '</div>';
    }).join("");
    return panel("Sell carried imports", "Goods this city does not normally produce", rows);
  }

  function renderMarket() {
    const p = state.player;
    const unavailable = isBusy();
    const localQuotes = state.quotes.filter(quote => quote.locally_produced || quote.stock > 0);
    const cards = localQuotes.map(quote => {
      const owned = p.inventory[quote.item] || 0;
      const maxBuy = Math.min(quote.sell_capacity, Math.floor(p.gold / quote.player_buy_price));
      const maxSell = Math.min(quote.buy_capacity, owned,
        Math.floor(quote.city_gold / quote.player_sell_price));
      return '<div class="market-card"><div class="mini-card-top">' +
        '<h3>' + esc(pretty(quote.item)) + '</h3>' +
        '<span class="inventory-pill">Owned: ' + owned + '</span></div>' +
        '<p class="small m-0">Stock: ' + quote.stock + '</p>' +
        '<div class="prices"><div><small>Buy for</small><strong>' + quote.player_buy_price +
        'g</strong></div><div class="sell"><small>Sell for</small><strong>' +
        quote.player_sell_price + 'g</strong></div></div>' +
        '<div class="trade-actions">' +
        '<label class="sr" for="qty-' + esc(quote.item) + '">Quantity</label>' +
        '<input class="qty" id="qty-' + esc(quote.item) +
        '" type="number" min="1" max="20" value="1" inputmode="numeric">' +
        button("Buy", 'data-ui="buy" data-item="' + esc(quote.item) + '"' +
          disabled(unavailable || !maxBuy), "secondary") +
        button("Sell", 'data-ui="sell" data-item="' + esc(quote.item) + '"' +
          disabled(unavailable || !maxSell), "") +
        '</div><p class="small m-0">Available: ' +
        quote.sell_capacity + '</p></div>';
    }).join("");
    return heading("", "Market", "") +
      '<div class="market-grid">' +
      (cards || '<p class="empty">No goods are stocked here yet. Sell locally acquired ' +
      'materials to the merchants to seed the marketplace.</p>') + '</div>' +
      '<div class="mt-13">' + sellOnlyGoods() + '</div>';
  }

  // Mastery tracks are a visual representation of existing school XP,
  // not a new economy, skill cap, unlock gate, or 400-level grind.
  const tierThresholds = [0, 30, 120, 350, 1000];
  function masteryTrack(xp) {
    const idx = tierThresholds.findIndex((limit, i) =>
      i < tierThresholds.length - 1 && xp < tierThresholds[i + 1]);
    const tier = idx < 0 ? 4 : idx + 1;
    const floor = tierThresholds[tier - 1];
    const ceiling = tierThresholds[tier];
    const rank = Math.min(100, Math.floor((xp - floor) / (ceiling - floor) * 100));
    return { tier, rank, floor, ceiling };
  }
  const practiceScenes = {
    restoration: {
      setting: "In the chapel infirmary, you place your hands above a patient's bandaged arm and guide a thread of warmth into the wounded flesh.",
      success: "The ache softens under your touch. An attending healer nods and quietly asks you to return for further study.",
      failure: "The warmth disperses before it settles. The healer shows you where your focus faltered.",
    },
    divination: {
      setting: "In the archive tower, you lay a handful of old coins beneath a candle and search their shifting shadows for a pattern.",
      success: "For one clear instant, the pattern holds. You record what you saw before it fades.",
      failure: "The shadows scatter into unrelated shapes. You mark the mistake and try to understand it.",
    },
    enchantment: {
      setting: "At a workbench, you carefully trace a rune into a fragment of iron, testing whether the line will hold a spell.",
      success: "The rune catches a steady light. Your tutor examines the finished mark with approval.",
      failure: "The mark flickers and fades. You reshape the line and note how the metal resisted.",
    },
    warding: {
      setting: "You stand inside a chalk circle and attempt to weave a thin protective veil across its boundary.",
      success: "The air grows firm as glass. For a moment, the ward withstands your tutor's test.",
      failure: "The veil parts under the slightest touch. You study the weak point before resetting the circle.",
    },
    elemental: {
      setting: "Beside a forge, you draw a measured breath and coax a spark to dance across your palms without burning your skin.",
      success: "The spark rises into a controlled flame. The smith watches its shape before returning to his work.",
      failure: "The spark flares too quickly and dies. You learn again the difference between power and control.",
    },
    alchemy: {
      setting: "Over a narrow brass burner, you measure crushed herbs into a clear flask and wait for the mixture to change.",
      success: "The liquid settles into the expected hue. You carefully label the preparation for your records.",
      failure: "An unexpected precipitate forms. You empty the flask and write down the failed proportion.",
    },
  };
  function practiceStory(outcome) {
    const node = state.magic_nodes.find(x => x.node_id === outcome.nodeId);
    const schoolName = node ? node.school : outcome.nodeId.split(".")[0];
    const scene = practiceScenes[schoolName] || practiceScenes.divination;
    return '<section class="practice-report" role="status" aria-live="polite">' +
      '<div class="section-kicker">Latest practice · ' + esc(pretty(schoolName)) + '</div>' +
      '<h3>' + esc(node ? node.title : pretty(outcome.nodeId.split(".").pop())) +
      (outcome.success ? ' · Success' : ' · Unsuccessful attempt') + '</h3>' +
      '<p>' + esc(scene.setting + ' ' + (outcome.success ? scene.success : scene.failure)) + '</p>' +
      '<div class="practice-rewards"><span>' + (outcome.xp_gained > 0 ? '+' : '') +
      outcome.xp_gained + ' XP</span><span>−' + outcome.mana_spent + ' mana</span>' +
      (outcome.insight_gained ? '<span>+' + outcome.insight_gained + ' Insight</span>' : '') +
      '<span>' + outcome.roll + ' rolled / ' + outcome.chance + '% success chance</span></div>' +
      '<p class="practice-note">Practice has no wage. Future guild and church contracts ' +
      'will pay real gold only when their objectives are completed.</p></section>';
  }

  const schoolIcons = {
    restoration: "✚", divination: "☽", enchantment: "ᚱ",
    warding: "⛨", elemental: "✹", alchemy: "⚗",
  };
  const schoolRoles = {
    restoration: "Healing", divination: "Sight & travel",
    enchantment: "Gear & runes", warding: "Protection",
    elemental: "Fire & combat", alchemy: "Potions",
  };
  function spellRow(node, nodes, p) {
    const higherUnlocked = nodes.some(other => other.tier > node.tier && other.unlocked);
    const needsXp = Math.max(0, node.required_xp - (p.school_xp[node.school] || 0));
    const needed = node.prerequisites.filter(id =>
      !state.magic_nodes.some(n => n.node_id === id && n.unlocked) &&
      id !== "arcane_fundamentals");
    const status = node.unlocked ? (node.active ? "Learned" : "Attunement required") :
      node.eligible ? "Ready to unlock" :
      needsXp ? needsXp + " XP needed" : needed.length ? "Requires earlier spell" :
      "Requires Insight";
    let control;
    if (node.unlocked) {
      control = button(higherUnlocked ? "Mastered" : "Practice · " + node.mana_cost + " mana",
        'data-ui="practice" data-node="' + esc(node.node_id) + '"' +
        disabled(higherUnlocked || !node.active || isBusy() || p.mana < node.mana_cost),
        higherUnlocked ? "ghost" : "secondary") +
        button("Cast · " + node.mana_cost + " mana",
          'data-ui="field-cast" data-node="' + esc(node.node_id) + '"' +
          disabled(!node.active || isBusy() || p.mana < node.mana_cost), "gold");
    } else {
      control = button(node.eligible ?
        "Unlock · " + node.insight_cost + " Insight" : "Locked",
        'data-ui="unlock" data-node="' + esc(node.node_id) + '"' +
        disabled(!node.eligible || isBusy()), node.eligible ? "gold" : "ghost");
    }
    return '<div class="spell-row ' + (node.unlocked ? 'is-learned' : 'is-locked') +
      '"><span class="spell-symbol" aria-hidden="true">' +
      (node.unlocked ? "✧" : "◇") + '</span><div class="spell-description">' +
      '<h4>' + esc(node.title) + '</h4>' +
      '<div class="spell-meta"><span class="' +
      (node.unlocked ? "spell-status learned" : "spell-status") + '">' +
      esc(status) + '</span><span>' + esc(pretty(node.role)) +
      ' · usable spell</span></div>' +
      '</div><div class="spell-action">' + control + '</div></div>';
  }
  function renderMagic() {
    const p = state.player;
    if (!state.magic_schools.includes(school)) school = state.magic_schools[0];
    const all = state.magic_nodes;
    const nodes = all.filter(n => n.school === school);
    const schoolXp = p.school_xp[school] || 0;
    const mastery = masteryTrack(schoolXp);
    const schools = state.magic_schools.map(name => {
      const xp = p.school_xp[name] || 0;
      const track = masteryTrack(xp);
      const learned = all.filter(n => n.school === name && n.unlocked).length;
      return '<button type="button" data-school="' + esc(name) +
        '" class="school-tile ' + (name === school ? 'selected' : '') +
        '" aria-pressed="' + (name === school) + '">' +
        '<div class="school-tile-heading"><span class="school-glyph" aria-hidden="true">' +
        (schoolIcons[name] || '✧') + '</span><strong>' + esc(pretty(name)) +
        '</strong></div><div class="school-tile-metrics"><span>Tier ' +
        track.tier + ' · ' + learned + '/6 spells</span><strong>' +
        track.rank + '/100</strong></div>' +
        progress(track.rank, 100) + '</button>';
    }).join('');
    const tiers = [1,2,3,4].map(tier => {
      const floor = tierThresholds[tier - 1], ceiling = tierThresholds[tier];
      const rank = Math.min(100, Math.max(0,
        Math.floor((schoolXp - floor) / (ceiling - floor) * 100)));
      const tierNodes = nodes.filter(n => n.tier === tier);
      return '<section class="spell-tier-block"><div class="spell-tier-heading">' +
        '<span class="tier-index">Tier ' + tier + '</span>' +
        '<span>' + (tier === 1 ? 'Foundations' : tier === 2 ?
          'Discipline' : tier === 3 ? 'Specialization' : 'Mastery') + '</span>' +
        '<div class="tier-inline-meter">' + progress(rank, 100) +
        '</div><strong>' + (schoolXp >= ceiling ? 100 : rank) +
        '/100</strong></div><div class="spell-rows">' +
        tierNodes.map(n => spellRow(n, nodes, p)).join('') +
        '</div></section>';
    }).join('');
    const specialist = all.filter(n => n.tier === 3 && n.unlocked);
    const attune = specialist.length ? specialist.map(n =>
      '<label class="attune-option"><input type="checkbox" data-attune="' +
      esc(n.node_id) + '"' + (selectedAttunements.has(n.node_id) ? " checked" : "") +
      '><span>' + esc(n.title) + ' <small>' + esc(pretty(n.school)) +
      '</small></span></label>').join('') :
      '<p class="small">Tier III branches appear here once learned.</p>';
    return heading("", "Magic", "") +
      '<div class="school-overview" aria-label="Magic schools">' + schools + '</div>' +
      '<div class="magic-context"><div><strong>' + esc(pretty(school)) +
      '</strong><span>' + esc(schoolRoles[school]) +
      ' · ' + schoolXp + ' XP</span></div>' +
      '<div class="magic-context-stat">✧ ' + p.insight + ' Insight</div></div>' +
      '<div class="magic-flow"><span>Practice</span><span aria-hidden="true">›</span>' +
      '<span>Unlock spells</span><span aria-hidden="true">›</span>' +
      '<span>Cast in the world or combat</span></div>' +
      (latestPractice ? practiceStory(latestPractice) : '') +
      '<div class="magic-layout"><section class="magic-progression" ' +
      'aria-label="Spell progression">' + tiers + '</section>' +
      '<aside class="magic-specialization">' +
      panel("Specializations", "",
        '<div class="mini-card-top"><span>Active paths</span><strong>' +
        p.attuned_paths.length + ' / 2</strong></div>' +
        attune + button("Apply", 'data-ui="apply-attune"' +
          disabled(isBusy() || !specialist.length), "full secondary") +
        '<p class="small mt-13">Changing paths has a 6-hour in-game cooldown.</p>') +
      '</aside></div>';
  }

  function renderHome() {
    const p = state.player, h = state.housing;
    const atHome = h.city && h.city === p.city && !isBusy();
    const ownedIdx = h.tier ? state.homes.findIndex(x => x.id === h.tier) : -1;
    const homes = state.homes.map((home, i) => {
      const cost = ownedIdx < 0 ? home.price :
        i > ownedIdx ? home.price - state.homes[ownedIdx].price : 0;
      const can = !isBusy() && (ownedIdx < 0 || (i > ownedIdx && atHome)) && p.gold >= cost;
      return '<div class="mini-card ' + (i === ownedIdx ? "active" : "") + '">' +
        '<div class="mini-card-top"><div class="mini-card-title">' + esc(home.name) +
        '</div><span class="amount">+' + home.training_bonus_pct + '% XP</span></div>' +
        '<div class="small">' + esc(money(home.price)) + ' total property value</div>' +
        button(ownedIdx === i ? "Owned" : ownedIdx > i ? "Lower tier" :
          (ownedIdx === -1 ? "Buy · " : "Upgrade · ") + money(cost),
          'data-ui="' + (ownedIdx === -1 ? "buy-home" : "upgrade-home") +
          '" data-tier="' + esc(home.id) + '"' + disabled(!can),
          "full " + (i === ownedIdx ? "secondary" : "")) + '</div>';
    }).join("");
    const facilities = state.facilities.map(f =>
      '<div class="mini-card"><div class="mini-card-top"><div class="mini-card-title">' +
      esc(f.name) + '</div><span class="price">' + money(f.price) + '</span></div>' +
      '<div class="small">Requires home Tier ' + f.min_home_tier + '</div>' +
      button(h.facilities.includes(f.id) ? "Built" : "Build facility",
        'data-ui="build-facility" data-facility="' + esc(f.id) + '"' +
        disabled(h.facilities.includes(f.id) || !atHome || ownedIdx + 1 < f.min_home_tier ||
          p.gold < f.price), "full secondary") + '</div>'
    ).join("");
    const vehicles = state.vehicles.map(v => {
      const owns = h.vehicles.includes(v.id), active = h.active_vehicle === v.id;
      return '<div class="mini-card"><div class="mini-card-top"><div class="mini-card-title">' +
        esc(v.name) + '</div><span class="price">' + money(v.price) + '</span></div>' +
        '<p class="small m-0">Roads: ' + v.road_time_percent +
        '% of walking time · ' + v.travel_cargo_limit +
        ' cargo units<br>Requires ' + esc(pretty(v.facility)) + '</p>' +
        (owns ? button(active ? "Park vehicle" : "Use vehicle",
          'data-ui="select-vehicle" data-vehicle="' +
          (active ? "" : esc(v.id)) + '"' + disabled(!atHome),
          "full " + (active ? "secondary" : "")) :
          button("Buy " + v.name, 'data-ui="buy-vehicle" data-vehicle="' +
            esc(v.id) + '"' + disabled(!atHome || !h.facilities.includes(v.facility) ||
              p.gold < v.price), "full secondary")) + '</div>';
    }).join("");
    return heading("", "Property", "") +
      (h.tier ? '<div class="home-banner mb-20">' +
        '<small>Your home · ' + esc(pretty(h.city)) + '</small>' +
        '<h3>' + esc(pretty(h.tier)) + '</h3>' +
        '<p>+' + h.training_bonus_pct + '% local training XP · ' +
        (h.active_vehicle ? esc(pretty(h.active_vehicle)) + ' ready' : "Traveling on foot") +
        '</p></div>' :
        '<div class="callout mb-20"><strong>Invest in your future</strong>' +
        'Your first home unlocks a permanent local training bonus as you upgrade it. ' +
        'It also gives you somewhere to build transport facilities.</div>') +
      '<div class="stack">' +
      panel("Property tiers", "Home upgrades pay only the price difference.",
        '<div class="house-tiers">' + homes + '</div>') +
      panel("Property improvements", "Facilities must be constructed in your home city.",
        '<div class="card-grid">' + facilities + '</div>') +
      panel("Vehicles", "Purchase vehicles and select one while visiting your home.",
        '<div class="card-grid">' + vehicles + '</div>' +
        (h.active_vehicle ?
          '<div class="mt-13">' + button("Park and walk",
            'data-ui="select-vehicle" data-vehicle=""' + disabled(!atHome), "ghost") +
          '</div>' : "")) +
      '</div>';
  }

  function heading(kicker, title, subtitle) {
    // Page hierarchy: location is already in the sidebar; the page only needs a title.
    return '<div class="heading-row"><div><h2>' + esc(title) + '</h2>' +
      (subtitle ? '<p class="subheading">' + esc(subtitle) + '</p>' : '') +
      '</div></div>';
  }
  function presenceIndicator(person) {
    if (!multiMode || person.kind !== "human") return "";
    const status = ["active", "away"].includes(person.presence) ?
      person.presence : "offline";
    return ' <span class="presence-indicator presence-' + status +
      '" title="' + esc(status[0].toUpperCase() + status.slice(1)) +
      '" aria-label="' + esc("Player is " + status) + '">' +
      '<span class="presence-dot" aria-hidden="true"></span>' +
      esc(status[0].toUpperCase() + status.slice(1)) + '</span>';
  }
  function renderPeople() {
    const query = peopleQuery.trim().toLowerCase();
    const players = (state.users || []).filter(person =>
      !state.player.destination && !person.traveling &&
      person.city === state.player.city &&
      person.name.toLowerCase().includes(query));
    const market = (state.quotes || []).filter(quote =>
      (quote.locally_produced || quote.stock > 0) &&
      pretty(quote.item).toLowerCase().includes(query));
    const rows = searchScope === "players" ?
      players.map(person => {
        const self = person.id === (state.actor_id || "hero");
        const recovering = person.recovering_minutes > 0;
        const text = self ? "Your character" :
          recovering ? "Hospitalized" : person.can_attack ? "Attack · no entry cost" :
          person.kind === "human" ? "View profile" : "Out of reach";
        const profileOnly = person.kind === "human" && !self && !person.can_attack;
        return '<div class="equipment-item"><div><h3>' +
          '<button type="button" class="character-name-link" data-ui="profile-open" ' +
          'data-character="' + esc(person.id) + '">' + esc(person.name) + '</button>' +
          presenceIndicator(person) +
          '</h3><p>' + esc(pretty(person.city)) + ' · Level ' + person.level +
          ' · ' + (self ? 'You' : person.kind === "npc" ?
            'NPC adventurer' : 'Player') + ' · HP ' +
          person.hp + '/' + person.max_hp +
          (recovering ? ' · Recovering ' + dur(person.recovering_minutes) : '') +
          '</p></div>' +
          button(text, (profileOnly ?
            'data-ui="profile-open" data-character="' + esc(person.id) + '"' :
            'data-ui="player-attack" data-player="' + esc(person.id) + '"') +
            disabled((!profileOnly && !person.can_attack) || isBusy()), "secondary") +
          '</div>';
      }).join('') :
      (state.world_items || []).filter(item =>
        pretty(item.id).toLowerCase().includes(query)).map(item => {
        const low = item.lowest_buy, high = item.highest_sell;
        return '<div class="equipment-item search-price"><div><h3>' +
          esc(pretty(item.id)) + '</h3><p>' + esc(item.category) + '</p>' +
          '<p><strong>Lowest buy:</strong> ' +
          (low ? esc(money(low.price) + ' · ' + pretty(low.city)) : 'No current vendor') +
          '</p><p><strong>Highest sell:</strong> ' +
          (high ? esc(money(high.price) + ' · ' + pretty(high.city)) : 'No current buy quote') +
          '</p><p class="small">Player-trade value: not established</p></div>' +
          (low && low.city === state.player.city && item.category === 'Resource' ?
            button('Market', 'data-tab="market"', "secondary") :
            low && item.category === 'Equipment' && state.player.city === 'crownreach' ?
            button('Armory', 'data-tab="armory"', "secondary") : '') +
          '</div>';
      }).join('');
    const hint = searchScope === "players" ? (multiMode ?
      'Both players and NPCs use the same turn-based combat. Defenders ' +
      'automatically counterattack each move; player duels draw after ten rounds. ' :
      'These are persistent computer-controlled adventurers, not connected players. ') +
      'To attack, be in the same city. Starting a duel costs no stamina; ' +
      'each offensive swing costs stamina. Victory takes 5% ' +
      'of the defeated character’s carried gold.' :
      'All known goods and equipment are listed. Buy and sell prices are live NPC merchant quotes ' +
      'when the merchant can currently trade; unavailable routes show no quote. ' +
      'Crafted goods have no guaranteed city merchant, and player-trade values are not yet tracked.';
    return heading("", "Search", "") +
      '<section class="panel search-results-panel">' +
      '<div class="search-panel">' +
      '<label for="people-query">Find</label>' +
      '<div class="search-type" role="group" aria-label="Search category">' +
      button("Characters", 'data-ui="search-type" data-scope="players" aria-pressed="' +
        (searchScope === "players") + '"', searchScope === "players" ? "secondary" : "ghost") +
      button("Items", 'data-ui="search-type" data-scope="market" aria-pressed="' +
        (searchScope === "market") + '"', searchScope === "market" ? "secondary" : "ghost") +
      '</div><div class="button-group"><input id="people-query" class="field" ' +
      'type="search" maxlength="64" placeholder="' +
      (searchScope === "players" ? "Character name" : "Item name") +
      '" value="' + esc(peopleQuery) + '">' +
      button("Search", 'data-ui="find-people"', "secondary") +
      '</div></div><div class="search-matches">' +
      (rows || '<p class="empty">No matches.</p>') +
      '<p class="small mt-13">' + esc(hint) + '</p>' +
      '</div></section>';
  }

  function renderProfile() {
    const person = (state.users || []).find(user => user.id === selectedCharacterId);
    if (!person) return heading("", "Character unavailable", "") +
      panel("Search for characters", "", button("Back to Search", 'data-tab="people"', "secondary"));
    const self = person.id === (state.actor_id || "hero");
    const isNpc = person.kind === "npc";
    const reachable = !self && person.can_attack;
    const recovering = Number(person.recovering_minutes) > 0;
    return heading("", esc(person.name), "") +
      '<div class="profile-grid"><section class="panel character-public-profile">' +
      '<div class="section-kicker">' +
      (isNpc ? 'NPC adventurer' : self ? 'Your character' : 'Player adventurer') +
      '</div>' +
      '<h3>' + esc(person.name) + presenceIndicator(person) + '</h3>' +
      characterRow("Level", person.level) +
      characterRow("Health", person.hp + " / " + person.max_hp) +
      characterRow("Location", pretty(person.city)) +
      characterRow("Status", recovering ?
        "Recovering (" + dur(person.recovering_minutes) + ")" :
        person.hp > 0 ? "Active" : "Defeated") +
      '<p class="small">Equipment, combat attributes, inventory and personal finances are private.</p>' +
      '</section>' +
      panel("Interactions", "",
        '<div class="button-group">' +
        button("Attack", 'data-ui="player-attack" data-player="' + esc(person.id) + '"' +
          disabled(!reachable || pending || isBusy()), "gold") +
        button("Chat", 'data-ui="profile-chat" data-character="' + esc(person.id) + '"' +
          disabled(self || (multiMode && isNpc)), "secondary") +
        button("Trade", 'data-ui="profile-trade" data-character="' + esc(person.id) + '"' +
          disabled(self || (multiMode && isNpc)), "secondary") +
        '</div><p class="small">' + (isNpc ?
          'This is a computer-controlled adventurer. Direct messaging and person-to-person trade ' +
          'will require the upcoming authenticated multiplayer service.' :
          (self ? 'You are viewing your own public profile.' :
           (multiMode ? 'Player duels use the same weapon, spell, and stamina choices as NPC battles. ' +
            'Defenders automatically counterattack; the fight ends on defeat, retreat, or a ten-round draw.' :
            'Messaging and trading with players requires authenticated multiplayer accounts.'))) + '</p>' +
        button("Back to Search", 'data-tab="people"', "ghost")) +
      '</div>';
  }

  function tradeAssetSummary(bundle, gear) {
    const parts = [];
    if (bundle.gold) parts.push(bundle.gold + " gold");
    for (const line of bundle.items || []) {
      parts.push(line.quantity + " × " + pretty(line.item));
    }
    for (const item of gear || []) {
      parts.push(pretty(item.kind) + " #" + item.id +
        " (quality " + item.quality + ", durability " + item.durability + ")");
    }
    return parts.length ? parts.map(esc).join(" · ") : "Nothing";
  }

  function renderTrade() {
    if (!multiMode) return heading("", "Trade", "") +
      panel("Unavailable", "Requires authenticated multiplayer accounts", "");
    const me = state.actor_id;
    const partners = (state.users || []).filter(person =>
      person.kind === "human" && person.id !== me);
    const partner = partners.find(p => p.id === selectedCharacterId) || partners[0];
    const incoming = state.trades || [];
    const partnerOptions = partners.map(person =>
      '<option value="' + esc(person.id) + '"' +
      (partner && partner.id === person.id ? ' selected' : '') + '>' +
      esc(person.name + " · " + pretty(person.city)) + '</option>').join('');
    const offeredItems = Object.entries(state.player.inventory || {})
      .filter(pair => pair[1] > 0)
      .map(([name, quantity]) => '<option value="' + esc(name) + '">' +
        esc(pretty(name) + " · owned " + quantity) + '</option>').join('');
    const requestedItems = (state.world_items || [])
      .filter(item => item.category !== "Equipment")
      .map(item => '<option value="' + esc(item.id) + '">' +
        esc(pretty(item.id)) + '</option>').join('');
    const equippedGear = (state.gear || []).map(item =>
      '<option value="' + item.id + '">' +
      esc(pretty(item.kind) + " #" + item.id + " · Q" + item.quality +
        " · durability " + item.durability) + '</option>').join('');
    const form = partners.length ?
      '<form id="tradeOfferForm" class="trade-compose">' +
      '<label for="trade-recipient">Trade with</label>' +
      '<select id="trade-recipient" class="field">' + partnerOptions + '</select>' +
      '<div class="trade-terms"><fieldset><legend>You offer</legend>' +
      '<label for="trade-offer-gold">Gold</label>' +
      '<input id="trade-offer-gold" class="field" type="number" min="0" ' +
      'max="1000000000000" step="1" value="0">' +
      '<label for="trade-offer-item">Item</label>' +
      '<select id="trade-offer-item" class="field"><option value="">None</option>' +
      offeredItems + '</select>' +
      '<label for="trade-offer-quantity">Quantity</label>' +
      '<input id="trade-offer-quantity" class="field" type="number" min="0" ' +
      'max="100000" step="1" value="0">' +
      '<label for="trade-offer-gear">Equipment</label>' +
      '<select id="trade-offer-gear" class="field"><option value="">None</option>' +
      equippedGear + '</select></fieldset>' +
      '<fieldset><legend>You request</legend>' +
      '<label for="trade-request-gold">Gold</label>' +
      '<input id="trade-request-gold" class="field" type="number" min="0" ' +
      'max="1000000000000" step="1" value="0">' +
      '<label for="trade-request-item">Item</label>' +
      '<select id="trade-request-item" class="field"><option value="">None</option>' +
      requestedItems + '</select>' +
      '<label for="trade-request-quantity">Quantity</label>' +
      '<input id="trade-request-quantity" class="field" type="number" min="0" ' +
      'max="100000" step="1" value="0">' +
      '<label for="trade-request-gear">Specific equipment ID (optional)</label>' +
      '<input id="trade-request-gear" class="field" type="number" min="0" ' +
      'step="1" value="0"></fieldset></div>' +
      '<p class="small">Both players must be in the same city. Your offered assets ' +
      'are held in escrow until the other player accepts, or either player cancels. ' +
      'The terms cannot be edited after sending.</p>' +
      '<button class="button gold" type="submit">Send trade offer</button>' +
      '</form>' : '<p class="small">Another human account must register to trade.</p>';
    const existing = incoming.map(trade => {
      const mine = trade.maker === me;
      const headline = mine ?
        "To " + trade.recipient_name : "From " + trade.maker_name;
      const controls = mine ? button("Cancel offer",
        'data-ui="trade-close" data-trade-id="' + trade.id + '"' +
        disabled(pending || isBusy()), "secondary") :
        button("Accept exact terms",
          'data-ui="trade-accept" data-trade-id="' + trade.id +
          '" data-terms-hash="' + esc(trade.terms_hash) + '"' +
          disabled(pending || isBusy()), "gold") +
        button("Decline", 'data-ui="trade-close" data-trade-id="' + trade.id +
          '"' + disabled(pending || isBusy()), "secondary");
      return panel("Trade #" + trade.id + " · " + headline,
        "City: " + pretty(trade.city),
        '<div class="trade-asset-details"><p><strong>' +
        esc(trade.maker_name) + " offers:</strong> " +
        tradeAssetSummary(trade.offer, trade.offer_gear) +
        '</p><p><strong>' + esc(trade.recipient_name) + " provides:</strong> " +
        tradeAssetSummary(trade.request, trade.request_gear) + '</p></div>' +
        '<div class="button-group">' + controls + '</div>');
    }).join('');
    return heading("", "Trade", "") +
      '<div class="stack">' +
      panel("Propose a trade", "Gold, goods and equipment", form) +
      panel("Open offers", "Review the exact assets before acceptance",
        '<div id="trade-offers-list">' +
        (existing || '<p class="small">No pending offers.</p>') + '</div>') +
      '</div>';
  }

  function renderDuel() {
    const duel = state.duel;
    const p = state.player;
    if (!duel) {
      const result = state.last_duel;
      const title = result ? (
        result.outcome === "won" ? "Victory" :
        result.outcome === "lost" ? "Hospitalized" :
        result.outcome === "draw" ? "Draw" :
        result.outcome === "opponent_fled" ? "Opponent retreated" : "Retreated"
      ) : "No active duel";
      const opponent = result && (state.users || []).find(u => u.id === result.opponent_id);
      const text = result ? (result.outcome === "won" ?
        'You claimed ' + money(result.gold) + ' from ' +
        (opponent ? opponent.name : "your opponent") + '.' :
        result.outcome === "lost" ? 'Your opponent took ' + money(result.gold) +
        '. Recovery: ' + dur(Math.max(0, (p.defeated_until || 0) - state.minute)) + '.' :
        result.outcome === "draw" ? 'Both fighters survived ten rounds. No loot or hospitalization.' :
        result.outcome === "opponent_fled" ? 'Your opponent withdrew. No loot or hospitalization.' :
        'You escaped without loot or hospitalization.') : 'Search for someone to fight.';
      const logs = result ? result.log.map(line => '<li>' + esc(line) + '</li>').join('') : '';
      return heading("", title, text) +
        panel("Battle report", result ? result.rounds + " rounds · " +
          result.xp + " combat XP" : "", '<ol class="combat-log">' + logs + '</ol>' +
          button("Return to Search", 'data-tab="people"', "secondary"));
    }
    const defending = duel.role === "defender";
    const learned = state.magic_nodes.filter(n => n.unlocked && n.active && n.tier > 0);
    const mainSwing = (state.combat_moves || []).find(m => m.move === "strike");
    const casts = learned.map(n => {
      const meleeMagic = n.school === "enchantment" || n.school === "divination";
      const swingCost = mainSwing ? mainSwing.stamina : 1;
      const magicStamina = state.magic_stamina_cost + (meleeMagic ? swingCost : 0);
      const extra = ' + ' + magicStamina + ' stamina';
      return button(n.title + ' · ' + n.mana_cost + ' mana' + extra,
        'data-ui="duel-cast" data-node="' + esc(n.node_id) + '"' +
        disabled(pending || p.mana < n.mana_cost ||
          p.stamina < magicStamina), "secondary");
    }).join('');
    const logs = duel.log.length ?
      '<ol class="combat-log">' + duel.log.map(line => '<li>' + esc(line) +
      '</li>').join('') + '</ol>' :
      '<p class="small">You have the initiative. Choose your opening move.</p>';
    return heading("", "Combat · " + duel.opponent_name,
      (defending ? "Defending automatically · " : "Choose your move · ") +
      "Round " + (duel.round + 1) +
      (duel.max_rounds ? " of " + duel.max_rounds : "") +
      " · the encounter is saved after every round") +
      '<div class="combat-vitals">' +
      panel(state.name, "Your health", progress(p.hp, p.max_hp) +
        '<p>' + p.hp + ' / ' + p.max_hp + ' HP · ' + p.stamina +
        ' / ' + p.max_stamina + ' stamina · ' + p.mana + ' mana</p>') +
      panel(duel.opponent_name, "Enemy health", progress(duel.opponent_hp, duel.opponent_max_hp) +
        '<p>' + duel.opponent_hp + ' / ' + duel.opponent_max_hp + ' HP</p>') +
      '</div>' +
      (defending ?
        panel("Automatic defense",
          "Your character counterattacks every attacking move without spending stamina.",
          '<p>Your opponent controls the offensive turns. You can watch the battle ' +
          'or flee at any time; you do not need to respond manually.</p>' +
          button("Flee", 'data-ui="duel-flee"' + disabled(pending), "ghost")) :
      panel("Choose your move", "Attack stamina is paid once per swing. Defensive counterstrikes cost none.",
        '<div class="combat-actions">' +
        (state.combat_moves || []).map(option =>
          button(option.label + ' · ' + option.stamina + ' stamina',
            'data-ui="duel-swing" data-move="' + option.move + '"' +
            disabled(pending || !option.available),
            option.move === "strike" ? "gold" : "secondary")).join('') +
        button("Guard · " + state.guard_stamina_cost + " stamina",
          'data-ui="duel-guard"' + disabled(pending ||
            p.stamina < state.guard_stamina_cost), "secondary") +
        button("Flee", 'data-ui="duel-flee"' + disabled(pending), "ghost") +
        '</div><h4>Combat magic</h4>' +
        '<div class="combat-actions">' +
        (casts || '<p class="small">Unlock spells on the Magic page to use them here.</p>') +
        '</div>' + (duel.pending_ward ? chip("Prepared ward: " +
          duel.pending_ward + " damage") : ""))) +
      panel("Round-by-round chronicle", "", logs);
  }
  function renderInventory() {
    const p = state.player;
    const stash = p.stored_here || {};
    const carried = Object.entries(p.inventory).filter(([, qty]) => qty > 0).sort();
    const stored = Object.entries(stash).filter(([, qty]) => qty > 0).sort();
    const carryRows = carried.map(([item, qty]) => {
      const consumable = (p.consumables || []).find(c => c.item === item);
      const track = consumable && p.cooldowns && p.cooldowns[consumable.channel];
      const canUse = consumable && track &&
        track.remaining_minutes + consumable.cooldown_minutes <= track.max_minutes &&
        (consumable.channel === "food" ?
          (p.hp < p.max_hp || p.stamina < p.max_stamina || p.hunger > 0) :
          p.hp < p.max_hp);
      return '<div class="stash-row"><div><strong>' + esc(pretty(item)) +
      '</strong><p>' + qty + ' carried</p></div>' +
      (consumable ? button("Use", 'data-ui="consume" data-item="' +
        esc(item) + '"' + disabled(!canUse || isBusy()), "s secondary") : '') +
      '<label class="sr" for="store-' + esc(item) + '">Store quantity</label>' +
      '<input class="qty" id="store-' + esc(item) +
      '" type="number" min="1" max="' + qty + '" value="1">' +
      button("Store", 'data-ui="store" data-item="' + esc(item) + '"' +
        disabled(isBusy()), "s secondary") + '</div>';
    }).join("") ||
      '<p class="empty">No carried goods yet. Visit the market or gather resources.</p>';
    const stashRows = stored.map(([item, qty]) =>
      '<div class="stash-row"><div><strong>' + esc(pretty(item)) +
      '</strong><p>' + qty + ' in this city</p></div>' +
      '<label class="sr" for="retrieve-' + esc(item) + '">Retrieve quantity</label>' +
      '<input class="qty" id="retrieve-' + esc(item) +
      '" type="number" min="1" max="' + qty + '" value="1">' +
      button("Retrieve", 'data-ui="retrieve" data-item="' + esc(item) + '"' +
        disabled(isBusy()), "s secondary") + '</div>').join("") ||
      '<p class="empty">Nothing stored in this city.</p>';
    const stores = Object.entries(p.storage_cities || {}).filter(([, count]) => count > 0)
      .map(([city, count]) => characterRow(pretty(city), count + " items")).join("");
    return heading("", "Inventory", "") +
      '<div class="callout mb-20"><strong>Carrying ' + p.cargo + ' items · Road limit ' +
      p.cargo_limit + '</strong>Your carried inventory has no fixed city limit. ' +
      'Store goods locally before traveling if your carried load exceeds ' +
      'your road capacity. Stored goods stay in their city until you return.</div>' +
      '<div class="two-col"><div class="stack">' +
      panel("Carried goods", "Choose what to take on the road", carryRows) +
      panel("City storage", "Available in " + pretty(p.city), stashRows) +
      '</div><aside class="stack">' +
      panel("Your stored goods", "Inventory in other settlements",
        stores || '<p class="small">You have no city-stored goods.</p>') +
      panel("Equipment & vehicles", "Equipment also uses road cargo capacity",
        '<p class="small">Owned equipment is currently always carried. ' +
        'The horse and carriage increase your road limit.</p>' +
        button("Equipment", 'data-tab="equipment"', "secondary") + ' ' +
        button("Property", 'data-tab="home"', "ghost")) +
      '</aside></div>';
  }
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
      'The game simulation still advances only when you take time-based actions.</p>';
  }
  function characterRow(label, value) {
    return '<div class="character-row"><span>' + esc(label) +
      '</span><strong>' + esc(value) + '</strong></div>';
  }
  function renderCharacter() {
    const p = state.player, w = p.work;
    const xpNext = 10 * p.level * p.level;
    const study = Object.entries(p.school_xp).map(([key, xp]) =>
      characterRow(pretty(key) + " magic", xp + " XP")).join('');
    const career = Object.entries(w.experience).map(([key, xp]) =>
      characterRow(pretty(key), xp + " XP")).join('');
    const homeName = state.housing.tier ? pretty(state.housing.tier) +
      " · " + pretty(state.housing.city) : "No residence";
    return '<div class="profile-hero"><h3>' + esc(state.name) +
      '</h3><p class="home-lore">Under the stone arches of Crownreach, merchants whisper about Goldmeadow’s silent bell. ' +
      'Couriers report missing caravans and a sealed royal ledger in the capital. ' +
      'Your journey begins here with little more than a purse and the chance to make a name in Oathmere.</p>' +
      '<p class="home-lore"><strong>Your first steps:</strong> earn coin in the Market, ' +
      'seek work at the Guild, study an art of magic, or test your strength against a local challenger. ' +
      'Whatever lies behind the silence of the bell, the cities will need capable hands.</p></div>' +
      '<div class="profile-grid">' +
      panel("Character State", "",
        characterRow("Level", p.level) +
        characterRow("Experience toward next level", p.level_xp + " / " + xpNext) +
        characterRow("Health", p.hp + " / " + p.max_hp) +
        characterRow("Stamina", p.stamina + " / " + p.max_stamina) +
        characterRow("Mana", p.mana + " / " + p.max_mana) +
        characterRow("Days played (simulated)", state.days_played) +
        characterRow("Elapsed world time", clock(state.minute))) +
      panel("Combat Attributes", "",
        characterRow("Strength", p.strength) +
        characterRow("Defense", p.defense) +
        characterRow("Combat experience", p.combat_xp + " XP")) +
      panel("Work Attributes", "",
        characterRow("Manual", w.manual) +
        characterRow("Intelligence", w.intelligence) +
        characterRow("Endurance", w.endurance) +
        characterRow("Completed shifts", w.shifts) +
        (career || '<p class="small">No occupational experience yet.</p>')) +
      panel("Assets", "",
        characterRow("Gold", money(p.gold)) +
        characterRow("Estimated net worth", money(state.net_worth_estimate)) +
        characterRow("Residence", homeName) +
        characterRow("Insight", p.insight) +
        (study || '<p class="small">No magical studies yet.</p>')) +
      '</div>';
  }
  function equipmentMannequin(owned, equipped) {
    const kind = slot => {
      const item = owned.find(x => x.id === equipped[slot]);
      return item ? item.kind : "";
    };
    // Original SVG mannequin: equipment is placed over a neutral silhouette.
    const armor = kind("body"), weapon = kind("weapon"), shield = kind("offhand");
    const dagger = kind("secondary"), helm = kind("helm"), boots = kind("boots");
    const greaves = kind("greaves"), gloves = kind("gloves");
    return '<div class="equipment-figure" role="img" aria-label="' +
      esc('Character wearing ' +
        [armor, weapon, shield, dagger, helm, boots, greaves, gloves].filter(Boolean).join(', ')) + '">' +
      '<svg viewBox="0 0 240 270" aria-hidden="true">' +
      '<ellipse cx="120" cy="259" rx="66" ry="8" fill="#d7d0bf"/>' +
      '<path d="M93 165 L147 165 L144 240 L122 240 L119 198 L115 240 L95 240 Z" fill="#636c60"/>' +
      '<path d="M83 84 L157 84 L151 174 L89 174 Z" fill="' +
      (armor === 'plate_armor' ? '#87939a' : armor === 'leather_armor' ? '#8e613e' : '#9a8c6f') + '"/>' +
      '<rect x="56" y="92" width="24" height="86" rx="11" fill="#a58b6b"/>' +
      '<rect x="160" y="92" width="24" height="86" rx="11" fill="#a58b6b"/>' +
      '<circle cx="120" cy="52" r="29" fill="#c3a17a"/>' +
      '<path d="M92 46 Q120 0 148 46 L142 35 L98 35 Z" fill="#574639"/>' +
      (armor ? '<path d="M83 86 L157 86 L151 166 L89 166Z" fill="none" stroke="#dcc59d" stroke-width="5"/>' : '') +
      (shield ? '<path d="M173 119 L211 129 L204 193 L182 213 L162 193 L158 130Z" fill="#637e79" stroke="#d5bd83" stroke-width="5"/>' : '') +
      (weapon ? '<path d="M49 76 L45 205" stroke="#707c83" stroke-width="8"/>' +
        '<path d="M27 176 L67 176" stroke="#9c7d42" stroke-width="8"/>' : '') +
      (helm ? '<path d="M91 43 Q120 4 149 43 L150 58 L139 47 L101 47 L90 58Z" fill="#8e9796" stroke="#d9c99e" stroke-width="3"/>' : '') +
      (gloves ? '<rect x="54" y="157" width="28" height="22" rx="5" fill="#8a9696"/>' +
        '<rect x="158" y="157" width="28" height="22" rx="5" fill="#8a9696"/>' : '') +
      (greaves ? '<path d="M96 189 L112 189 L110 232 L95 232Z" fill="#8a9696"/>' +
        '<path d="M126 189 L142 189 L144 232 L129 232Z" fill="#8a9696"/>' : '') +
      (boots ? '<path d="M94 229 L112 229 L110 246 L78 246Z" fill="#5c5b52"/>' +
        '<path d="M129 229 L144 229 L163 246 L128 246Z" fill="#5c5b52"/>' : '') +
      (dagger ? '<path d="M192 112 L189 179" stroke="#8d9ea5" stroke-width="5"/>' +
        '<path d="M176 165 L202 165" stroke="#91683d" stroke-width="5"/>' : '') +
      '</svg><p>' + esc([armor, weapon, shield, dagger, helm, boots, greaves, gloves]
        .filter(Boolean).map(pretty).join(' · ') ||
        'Unarmored adventurer') + '</p></div>';
  }

  function renderEquipment() {
    const p = state.player;
    const owned = state.gear || [];
    const equipped = state.equipped || {};
    const slots = ["weapon", "secondary", "offhand", "helm", "body",
      "gloves", "greaves", "boots", "tool"];
    const slotRows = slots.map(slot => {
      const id = equipped[slot];
      const gear = owned.find(g => g.id === id);
      return '<div class="equipment-slot"><div><small>' + esc(pretty(slot)) +
        '</small><strong>' + (gear ? esc(pretty(gear.kind)) + " #" + gear.id :
          "Empty") + '</strong></div>' +
        (gear ? button("Unequip", 'data-ui="unequip" data-slot="' + esc(slot) + '"' +
          disabled(isBusy()), "s ghost") : '') + '</div>';
    }).join('');
    const gearRows = owned.map(gear => {
      const inUse = equipped[gear.slot] === gear.id;
      return '<div class="equipment-item"><div><h3>' + esc(pretty(gear.kind)) +
        ' · #' + gear.id + '</h3><p>Slot: ' + esc(pretty(gear.slot)) +
        ' · Quality ' + gear.quality + ' · Durability ' + gear.durability +
        '/' + gear.max_durability +
        ' · Attack +' + gear.attack + ' · Defense +' + gear.defense +
        '</p></div>' +
        button(inUse ? "Equipped" : "Equip", 'data-ui="equip" data-gear-id="' +
          gear.id + '"' + disabled(inUse || isBusy()), "s secondary") + '</div>';
    }).join('') || '<p class="empty">You own no equipment yet. Starter gear is sold at Crownreach.</p>';
    return heading("", "Equipment", "") +
      '<div class="profile-grid">' +
      panel("Equipped Gear", "", equipmentMannequin(owned, equipped) + slotRows) +
      panel("Owned Equipment", "", gearRows) +
      '</div>';
  }
  function renderArmory() {
    const p = state.player;
    const inCapital = p.city === "crownreach" && !p.destination;
    const catalog = (state.equipment_catalog || []).map(item =>
      '<div class="inventory-row"><span><strong>' + esc(pretty(item.kind)) +
      '</strong><small class="armory-spec">' + esc(pretty(item.slot)) +
      ' · Attack +' + item.attack + ' · Defense +' + item.defense +
      ' · Durability ' + item.durability + ' · Quality ' + item.quality +
      ' · Swing ' + (item.kind === "dagger" ? "2" : item.kind === "sword" ? "5" :
        item.kind === "axe" ? "7" : item.kind === "bow" ? "4" : "—") + ' stamina' +
      '</small></span>' +
      button("Buy · " + money(item.price),
        'data-ui="buy-starter" data-kind="' + esc(item.kind) + '"' +
        disabled(!inCapital || isBusy() || p.gold < item.price),
        "s secondary") + '</div>').join('');
    return heading("", "Armory & Blacksmith", "") +
      (inCapital ?
        panel("Available Equipment", "", catalog) :
        panel("No armory here", "",
          '<p class="small">Starter equipment is currently sold only in Crownreach.</p>' +
          button("World Map", 'data-tab="world"', "secondary")));
  }
  function futurePage(kicker, title, narrative, next, label, nested = false) {
    return (nested ? "" : heading("", title, "")) +
      '<section class="story-panel"><div class="section-kicker">Coming chapter</div>' +
      '<h3>' + esc(title) + '</h3><p>' + esc(narrative) + '</p>' +
      '<p class="small">This location is planned. It cannot yet award gold, XP, ' +
      'contracts, or equipment.</p>' + button(label, 'data-tab="' + esc(next) + '"',
        "secondary") + '</section>';
  }
  const contractScenes = {
    warrior_patrol: "You take your position along the weathered city wall. By the end of your patrol, the guard captain signs your report and orders your wage paid from the city treasury.",
    mage_copywork: "Beneath the guild's high windows, you copy protective sigils until your fingertips ache. The archivist checks your script, then pays you from the guild's civic stipend.",
    church_supplies: "You bring a bundle of herbs to the infirmary. The sisters inventory it for their patients and offer a modest payment from the city's charitable allowance.",
    labor_shift: "You join the porters hauling grain and supplies through the market yard. After the last cart is loaded, the foreman counts out your wages.",
  };
  function contractBoard(venue) {
    const p = state.player;
    const offers = (state.contracts || []).filter(contract => contract.venue === venue);
    const items = offers.map(contract => {
      const can = !isBusy() && contract.cooldown_available &&
        contract.can_pay && contract.has_material &&
        p.stamina >= contract.stamina && p.mana >= contract.mana;
      const costs = [contract.stamina ? contract.stamina + ' stamina' : null,
        contract.mana ? contract.mana + ' mana' : null,
        contract.material ? '1 ' + pretty(contract.material) : null].filter(Boolean);
      return '<div class="contract-card"><div><h3>' + esc(contract.title) + '</h3>' +
        '<p>' + esc(contract.description) + '</p>' +
        '<div class="contract-terms"><span>+' + contract.reward + ' gold</span>' +
        '<span>' + esc(costs.length ? costs.join(' · ') : 'No item cost') + '</span>' +
        '<span>+' + contract.cooldown_minutes + 'm Job cooldown</span></div>' +
        (!contract.can_pay ? '<p class="small">The city cannot currently fund this offer.</p>' :
         !contract.has_material ? '<p class="small">You need ' + esc(pretty(contract.material)) + '.</p>' :
         !contract.cooldown_available ?
           '<p class="small">Job cooldown limit: 24h. Pass game time to work again.</p>' : '') +
        '</div>' +
        button("Complete contract", 'data-ui="contract" data-contract="' +
          esc(contract.id) + '"' + disabled(!can), "secondary") + '</div>';
    }).join("");
    let report = "";
    if (latestContract && offers.some(c => c.id === latestContract.contract_id)) {
      const scene = contractScenes[latestContract.contract_id] || "You finish your work and receive payment.";
      report = '<div class="practice-report" role="status"><h3>Contract completed</h3>' +
        '<p>' + esc(scene) + '</p><div class="practice-rewards"><span>+' +
        latestContract.reward + ' gold</span><span>+' + latestContract.xp_gained +
        ' XP</span></div></div>';
    }
    return report + panel("Available Work", "",
      items || '<p class="empty">No contracts are posted here.</p>');
  }
  function renderWarriorsGuild() {
    return heading("", "Warriors Guild", "") +
      '<section class="story-panel"><h3>Duty at the western gate</h3>' +
      '<p>The watch captain glances at your gear. "A sharp eye is worth as much as a blade. ' +
      'There is honest coin in keeping these streets safe."</p></section>' +
      contractBoard("warriors") +
      '<p class="small mt-13">Patrols train combat experience. Bounties and actual NPC battles are future missions.</p>';
  }
  function renderMageGuild() {
    return heading("", "Mage Guild", "") +
      '<section class="story-panel"><h3>The keeper of the archives</h3>' +
      '<p>The archivist slides a sheaf of wards across the table. "Our copies never finish themselves. ' +
      'Work well and there is a modest stipend."</p>' +
      button("Study magic", 'data-tab="magic"', "secondary") + '</section>' +
      contractBoard("mageguild");
  }
  function renderChurch() {
    const service = state.church || {};
    const missing = state.player.max_hp - state.player.hp;
    return heading("", "Church of the Hearth", "") +
      '<section class="story-panel"><h3>The candlelit nave</h3>' +
      '<p>The sisters keep a lamp lit for travelers returning injured from the roads. ' +
      '"We turn away no prayer," says the matron, "but herbs and bandages cost coin."</p>' +
      '<p>Full recovery: ' + money(service.price || 20) + '. ' +
      'One treatment per simulated day. No job, potion, or other cooldown is added.</p>' +
      (service.used_today ? '<p class="small">You have received your treatment today.</p>' : '') +
      button("Receive healing · " + money(service.price || 20),
        'data-ui="church-heal"' + disabled(!service.available ||
        state.player.gold < service.price || isBusy()), "gold") +
      '<p class="small">Your wounds: ' + missing + ' HP missing.</p></section>' +
      contractBoard("church");
  }
  function renderTrack() {
    const track = state.track || {}, p = state.player;
    const horses = (track.horses || []).map(h => {
      const eligible = !isBusy() && p.stamina >= track.race_cost &&
        p.gold >= track.entry_fee && !track.cooldown_remaining;
      return '<div class="mini-card"><div class="mini-card-title">♞ ' +
        esc(h.name) + '</div><div class="mini-card-sub">Speed ' + h.speed +
        ' · Endurance ' + h.stamina + ' · ' +
        (h.owned ? 'In your stable' : money(h.price)) + '</div>' +
        (h.owned ?
          button('Race · ' + money(track.entry_fee),
            'data-ui="horse-race" data-breed="' + esc(h.id) + '"' +
            disabled(!eligible), "gold") :
          button('Buy · ' + money(h.price),
            'data-ui="horse-buy" data-breed="' + esc(h.id) + '"' +
            disabled(isBusy() || p.gold < h.price), "secondary")) +
        '</div>';
    }).join('');
    const last = track.last_result;
    return heading("", "The Track",
      "Breed, train and race horses against a field of local riders.") +
      '<section class="story-panel"><h3>The Five Cities Circuit</h3>' +
      '<p>In Oathmere, a rider is judged as much by the patience of their mount as ' +
      'the courage of their hand. At the city track, novice jockeys race for ' +
      'coin and honor beneath the pennants of the five roads.</p>' +
      '<p>Riding experience: <strong>' + (track.riding_xp || 0) +
      ' XP</strong> · Entry ' + money(track.entry_fee || 10) +
      ' · ' + (track.race_cost || 15) + ' stamina · ' +
      'Winner receives 30 gold.</p>' +
      (track.cooldown_remaining ? '<p>Next race in ' +
        dur(track.cooldown_remaining) + ' simulated time.</p>' : '') +
      '</section>' + panel("Your stable & horse market",
        "Buy horses permanently; their speed and endurance determine race performance.",
        '<div class="card-grid">' + horses + '</div>') +
      (last ? panel("Latest race", "",
        '<p><strong>' + esc(pretty(last.breed)) + ' placed #' + last.placing +
        '</strong> · Your score ' + last.score + ' · Opponents ' +
        last.rival_scores.join(' / ') + '</p>' +
        '<p>+' + last.xp + ' riding XP · Prize ' + money(last.prize) + '</p>') : '');
  }
  function renderGuilds() {
    const info = state.guilds || {}, own = info.my_guild, rules = info.rules || {};
    const directory = (info.directory || []).map(g =>
      '<div class="equipment-item"><div><h3>' + esc(g.name) +
      '</h3><p>' + g.members + ' members</p></div></div>').join('');
    let myGuild = '';
    if (own) {
      const roster = Object.entries(own.members).map(([id, role]) =>
        '<div class="inventory-row"><span>' + esc(id === 'hero' ? state.name : id) +
        '</span>' + chip(pretty(role)) + '</div>').join('');
      myGuild = panel(own.name, 'Your ' + pretty(own.role) + ' role',
        '<div class="resource-list">' +
        chip('Rating ' + own.rating) + chip('Wins ' + own.wins) +
        chip('Losses ' + own.losses) + '</div>' +
        '<h4>Members</h4>' + roster +
        '<p class="small">Invitations, officer appointments and membership ' +
        'permissions exist in the engine. A multi-account server is required ' +
        'to make guild recruitment useful across real players.</p>' +
        button('Leave guild', 'data-ui="guild-leave"' + disabled(isBusy() ||
        Object.keys(own.members).length > 1 && own.role === 'leader'), 'ghost'));
    } else {
      myGuild = panel('Found your guild',
        'Choose a banner name and pay a one-time 100 gold charter fee.',
        '<div class="button-group"><input class="field" id="guild-name" maxlength="40" ' +
        'placeholder="Guild name (3–40 characters)" aria-label="Guild name">' +
        button('Found Guild · ' + money(info.founding_cost || 100),
          'data-ui="guild-found"' + disabled(isBusy() ||
          state.player.gold < (info.founding_cost || 100)), 'gold') + '</div>');
    }
    return heading('', 'Guilds', 'Build a banner, gather allies, and prepare for the ranked-war era.') +
      '<div class="stack">' + myGuild +
      panel('The Guild Hall', 'Existing banners', directory ||
        '<p class="small">No guilds have been founded yet.</p>') +
      panel('Ranked wars — framework', 'The system is designed, but matchmaking and war attacks are not enabled.',
        '<p>Two guilds will face a ' + (rules.notice_minutes / 60) +
        '-hour preparation period followed by at most ' +
        (rules.duration_minutes / 60) + ' hours of competition.</p>' +
        '<div class="resource-list">' + chip('Cumulative War Score') +
        chip('Roster lock') + chip('No outside interference') +
        chip('Surrender available') + '</div>' +
        '<p class="small">Score targets will scale with roster size. ' +
        'Participation, performance, and victory each contribute to rewards. ' +
        'The Elo-based matchmaker, fortifications and reward payments are future work.</p>') +
      '</div>';
  }
  function renderMerits() {
    const info = state.merits || {};
    const feats = (info.achievements || []).map(f =>
      '<div class="equipment-item"><div><h3>' + esc(f.name) +
      '</h3><p>' + esc(f.description) + ' · +' + f.award +
      ' merit</p></div>' +
      (f.claimed ? chip('Claimed') :
        button(f.eligible ? 'Claim merit' : 'Locked',
          'data-ui="merit-claim" data-achievement="' + esc(f.id) + '"' +
          disabled(!f.eligible || isBusy()), f.eligible ? 'gold' : 'ghost')) +
      '</div>').join('');
    const upgrades = (info.upgrades || []).map(perk =>
      '<div class="equipment-item"><div><h3>' + esc(perk.name) +
      '</h3><p>' + esc(perk.description) + '</p></div>' +
      (perk.owned ? chip('Owned') :
        button('Buy · ' + perk.cost + ' merits',
          'data-ui="merit-buy" data-perk="' + esc(perk.id) + '"' +
          disabled(info.balance < perk.cost || isBusy()), 'secondary')) +
      '</div>').join('');
    return heading('', 'Merits', 'Honor your milestones and shape a lasting character.') +
      '<div class="stack">' +
      panel('Your merit ledger', 'Merits are earned once per achievement, not repeatedly farmed.',
        '<div class="resource-list">' + chip('Available: ' + (info.balance || 0)) +
        chip('Lifetime earned: ' + (info.total_earned || 0)) + '</div>') +
      panel('Achievements', 'Complete goals throughout Oathmere.', feats) +
      panel('Permanent improvements', 'Spend earned merits on carefully bounded advantages.', upgrades) +
      '</div>';
  }
  function renderCityHall() {
    return futurePage("", "City Hall",
      "A clerk maintains the city's merchant ledgers, civic obligations and contracts. You can now earn wages at the guilds and employment hall.",
      "job", "Find work");
  }
  function renderJob() {
    const w = state.player.work;
    return heading("", "Job", "") +
      '<div class="two-col"><div class="stack">' +
      contractBoard("job") +
      '</div><aside class="stack">' +
      panel("Work Stats", "",
        characterRow("Manual", w.manual) +
        characterRow("Intelligence", w.intelligence) +
        characterRow("Endurance", w.endurance) +
        characterRow("Shifts completed", w.shifts)) +
      '</aside></div>';
  }
  function renderTraining() {
    const hall = state.training_hall || { schools: [], active: null };
    const studies = hall.active;
    const studying = studies ?
      '<p class="small university-progress">Studying ' +
      esc(pretty(studies.school)) + ' · Course ' + (studies.index + 1) +
      ' · ' + Math.max(1, Math.ceil(studies.remaining_minutes / 1440)) +
      ' simulated days remaining</p>' : '';
    const tiles = hall.schools.map(school => {
      const courses = school.courses.map((course, index) => {
        const fee = Number(course.tuition);
        const blocked = pending || isBusy() || state.player.gold < fee || !course.available;
        const action = course.completed ? chip("Completed") :
          course.active ? chip("In progress") :
          button("Enroll · " + money(fee),
            'data-ui="course-enroll" data-school="' + esc(school.id) +
            '" data-index="' + index + '"' + disabled(blocked), "secondary");
        return '<div class="university-course"><div><strong>' +
          esc(course.name) + '</strong><small>' + course.days +
          ' days · +' + course.stat_bonus + ' ' + esc(pretty(school.stat)) +
          ' · Tuition ' + money(fee) + '</small></div>' + action + '</div>';
      }).join('');
      return '<details class="university-school" data-university="' +
        esc(school.id) + '"' +
        (expandedUniversitySchool === school.id ? ' open' : '') +
        '><summary><span><strong>' +
        esc(school.name) + '</strong><small>' +
        school.completed + ' of ' + school.total + ' courses completed</small></span>' +
        '<span class="university-expand" aria-hidden="true">⌄</span></summary>' +
        '<div class="university-school-body">' +
        '<p class="small">Graduation: 1 merit' +
        (school.capstone_perk ? ' · +' + school.capstone_perk.bonus +
          ' ' + esc(pretty(school.capstone_perk.stat)) : '') +
        (school.martial_perk ? ' · +' + school.martial_perk.bonus +
          ' ' + esc(pretty(school.martial_perk.stat)) : '') +
        '</p>' +
        courses + '</div></details>';
    }).join('');
    return heading("", "University", "") + studying +
      '<div class="university-grid">' + tiles + '</div>';
  }
  function renderTavern() {
    return heading("A place to rest", "Wayfarer's Tavern",
      "Take shelter, listen to rumors, or advance the simulation.") +
      '<section class="story-panel"><div class="section-kicker">The common room</div>' +
      '<h3>A seat by the hearth</h3><p>The innkeeper nods toward an empty bench. ' +
      'Around you, travelers discuss the roads and the promise of work in distant cities.</p>' +
      '<p class="small">Resting advances simulated world time and restores resources. ' +
      'The clock in the header continues to show real Eastern time.</p>' +
      '<div class="button-group">' +
      button("Rest 1 hour", 'data-ui="advance" data-minutes="60"' + disabled(pending), "secondary") +
      button("Pass 6 hours", 'data-ui="advance" data-minutes="360"' + disabled(pending), "ghost") +
      '</div></section>';
  }

  function levelUpOverlay() {
    if (!levelCelebration) return "";
    return '<div class="level-overlay" role="dialog" aria-modal="true" ' +
      'aria-labelledby="level-title"><div class="level-card">' +
      '<div class="level-sparks">✦ ✧ ✦</div>' +
      '<h2 id="level-title">LEVEL ' + levelCelebration.to + '!</h2>' +
      '<div class="level-gains"><span>+' + (levelCelebration.to - levelCelebration.from) +
      ((levelCelebration.to - levelCelebration.from) === 1 ? ' level' : ' levels') +
      '</span><span>+' + levelCelebration.hp + ' Health Capacity' +
      '</span><span>+' + levelCelebration.strength + ' Strength' +
      '</span><span>+' + levelCelebration.defense + ' Defense</span></div>' +
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
    stream.addEventListener("activity", event => {
      if (stream !== liveEvents || !state || !state.started) return;
      let update;
      try { update = JSON.parse(event.data); } catch { return; }
      if (update.actor_id !== state.actor_id ||
          update.revision < (state.activity_revision || 0)) return;
      state.activity_revision = update.revision;
      state.chat = update.chat;
      state.trades = update.trades;
      state.minute = update.minute;
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
    });
    // EventSource reconnects automatically and sends the session cookie.
    // This stream intentionally has no client-controlled actor identifier.
  }
  function refreshLiveSurfaces() {
    if (!state || !state.started) return;
    const strip = document.querySelector(".activity-strip");
    if (strip) strip.innerHTML = activityIcons();
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
        password: document.getElementById("registerPassword").value
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
  setInterval(updateEasternClock, 15000);
})();
