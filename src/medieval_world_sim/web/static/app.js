import { createCharacterViews } from "/character-views.mjs";
import { createCommunityViews } from "/community-views.mjs";
import { createCityViews } from "/city-views.mjs";
import { createWorldViews } from "/world-views.mjs";
import { createWildernessViews } from "/wilderness-views.mjs";
import { createEconomyViews } from "/economy-views.mjs";
import { createEconomyActions } from "/economy-actions.mjs";
import { groupCombatChronicle } from "/chronicle-views.mjs";
import { travelJustArrived, activeCourseEnded } from "/live-transitions.mjs";
import { scaledTimerSeconds, totalUnspentMerits } from "/activity-state.mjs";

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
    { id: "merits", icon: "✶", title: "Renown" },
    { id: "market", icon: "⚖", title: "Market" },
    { id: "companies", icon: "⚒", title: "Companies", onlyCity: "crownreach" },
    { id: "job", icon: "▣", title: "Occupation" },
    { id: "mercenary", icon: "⚔", title: "Mercenary Jobs" },
    { id: "church", icon: "✝", title: "Church" },
    { id: "armory", icon: "⚒", title: "Armory", onlyCity: "crownreach" },
    { id: "harbor", icon: "⚓", title: "Harbor", onlyCity: "crownreach" },
    { id: "track", icon: "♞", title: "Track" },
    { id: "training", icon: "✤", title: "University" },
    { id: "tavern", icon: "♜", title: "Tavern" },
    { id: "cityhall", icon: "♛", title: "Quests" },
  ];
  const accountTabs = [
    { id: "character", icon: "♙", title: "Home" },
    { id: "equipment", icon: "⚔", title: "Equipment" },
    { id: "world", icon: globeIcon, title: "Map" },
    { id: "chronicle", icon: "▤", title: "Chronicle" },
    { id: "letters", icon: "✉", title: "Letters" },
    { id: "people", icon: "⌕", title: "Search" },
  ];
  let state = null;
  let duelPreviewTarget = null;
  let lineageCatalog = [];
  let tab = "character";
  const pageHistory = [];
  const THEME_KEY = "oathmere.appearance.theme";
  // Keep the established light appearance unless the user chooses otherwise.
  let themePreference = "light";
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (["light", "dark"].includes(saved)) themePreference = saved;
  } catch { /* Private browsing can disable local storage. */ }
  function applyTheme() {
    document.documentElement.dataset.theme = themePreference;
  }
  applyTheme();
  function combatNavigationLocked() {
    return Boolean(state && state.duel && state.duel.attack_started);
  }
  function navigateTo(nextTab) {
    if (combatNavigationLocked() && nextTab !== "duel") return;
    if (nextTab !== "duel") duelPreviewTarget = null;
    if (nextTab !== tab) {
      pageHistory.push(tab);
      if (pageHistory.length > 25) pageHistory.shift();
      tab = nextTab;
    }
  }
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
  let introActor = null;
  let travelIntent = null;
  let hexIntent = null;
  let guildLeaveIntent = null;
  let confirmationIntent = null;
  let companySection = "overview";
  function requestConfirmation({title, description, button, command, params, success}) {
    confirmationIntent = {title, description, button, command, params, success};
    render();
  }
  let mapZoom = 2.5;
  let forceMapCenter = false;
  let mapPollBusy = false;
  let lastMapPollAt = 0;
  // Private map tiles are absent from live updates. Fetch one final map when
  // travel completes, even though the player's destination is now null.
  let mapTravelSettlePending = false;
  let universityNeedsRefresh = false;
  let universityRefreshBusy = false;
  let peopleQuery = "";
  let selectedCharacterId = null;
  let searchScope = "players";
  let armoryCategory = "weapons";
  let chronicleCategory = "all";
  let chronicleQuery = "";
  let chronicleVisibleCount = 50;
  const chronicleOpenEncounters = new Set();
  let renderedChronicleEvents = null;
  let renderedChronicleFilterKey = "";
  let chatOpen = false;
  let chatChannelKey = "global";
  let chatDraft = "";
  let expandedUniversitySchool = null;
  let chatDirectTarget = null;
  let pending = false;
  let authNeeded = false;
  let offline = false;
  let loadingWorld = false;
  let probingServer = false;
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
  function compactWallTime(seconds) {
    const count = Math.max(0, Math.ceil(Number(seconds) || 0));
    if (count >= 86400) return Math.ceil(count / 86400) + "d";
    if (count >= 3600) {
      const hours = Math.floor(count / 3600);
      const mins = Math.ceil((count % 3600) / 60);
      return hours + "h" + (mins ? " " + mins + "m" : "");
    }
    return count >= 60 ? Math.ceil(count / 60) + "m" : count + "s";
  }
  function timerEndMs(simSeconds) {
    if (!secureWorldClock || !state || state.next_world_tick_seconds == null)
      return 0;
    // Use one wall-clock deadline anchored to the authoritative snapshot.
    // Never subtract elapsed time once here and again while rebuilding chips.
    const secondsPerMinute = state.dev_travel_seconds ? 1 : 60;
    return clockSyncedAt + 1000 * scaledTimerSeconds(
      simSeconds, secondsPerMinute, state.next_world_tick_seconds, 0);
  }
  function timerSeconds(simSeconds) {
    const end = timerEndMs(simSeconds);
    if (end) return Math.max(0, (end - Date.now()) / 1000);
    const secondsPerMinute = state && state.dev_travel_seconds ? 1 : 60;
    return scaledTimerSeconds(simSeconds, secondsPerMinute, null, 0);
  }
  function timerAttrs(label, simSeconds, seconds = timerSeconds(simSeconds)) {
    const text = label + fullCountdown(seconds);
    const end = timerEndMs(simSeconds);
    return ' data-hover-text="' + esc(text) + '" data-timer-label="' + esc(label) +
      '" data-timer-end="' + end + '" data-timer-fixed="' +
      (end ? "" : Math.ceil(seconds)) + '"';
  }
  function updateHoverTimers() {
    for (const item of document.querySelectorAll("[data-timer-label]")) {
      const seconds = Number(item.dataset.timerEnd) > 0 ?
        (Number(item.dataset.timerEnd) - Date.now()) / 1000 :
        Number(item.dataset.timerFixed);
      const remaining = fullCountdown(seconds);
      item.dataset.hoverText = item.dataset.timerLabel + remaining;
      const readout = item.querySelector("[data-timer-display]");
      if (readout) readout.textContent = remaining;
      if (readout && ["university", "hospital"].includes(item.dataset.activityKey))
        readout.textContent = compactWallTime(seconds);
      if (seconds <= 0 && item.dataset.activityKey === "civic-shift") {
        item.remove();
        if (state) state.active_contract = null;
        continue;
      }
      if (item.hasAttribute("data-university-countdown")) {
        item.textContent = remaining + " remaining";
        if (Number(item.dataset.timerEnd) > 0 && state) {
          const panel = item.closest(".university-progress");
          const meter = panel && panel.querySelector(".university-progress-meter");
          const percent = panel && panel.querySelector(".university-progress-percent");
          if (meter) {
            const total = Number(meter.dataset.totalMinutes) || 0;
            const scale = state.dev_travel_seconds ? 1 : 60;
            if (total > 0) {
              const elapsed = Math.max(0, Math.min(total,
                total - Math.max(0, seconds) / scale));
              meter.value = elapsed;
              if (percent)
                percent.textContent = Math.floor(elapsed * 100 / total) + "% complete";
            }
          }
        }
      }
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

  function markServerDisconnected() {
    if (offline) return;
    offline = true;
    // A disconnected client must not keep stale menus or controls visible.
    stopLiveEvents();
    stopPresence();
    render();
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
    let response;
    try {
      response = await fetch(url, options);
    } catch {
      markServerDisconnected();
      throw Error("The game server is unavailable");
    }
    let data;
    try { data = await response.json(); } catch { throw Error("The server sent an invalid response"); }
    if ((url === "/api/state" && data.next_world_tick_seconds !== undefined) ||
        (data.state && data.state.next_world_tick_seconds !== undefined)) {
      clockSyncedAt = Date.now();
    }
    if (response.status === 401) authNeeded = true;
    if (!response.ok) throw Error(data.error || "Request failed");
    authNeeded = false;
    return data;
  }

  async function load(preservePage = false) {
    if (loadingWorld) return;
    loadingWorld = true;
    try {
      const health = await request("/api/health");
      multiMode = health.mode === "multi-account-local";
      inviteRequired = Boolean(health.invite_required);
      lineageCatalog = Array.isArray(health.lineages) ? health.lineages : [];
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
      if (!preservePage)
        tab = state.duel && state.duel.role !== "defender" ? "duel" : "character";
      offline = false;
      syncAttunements();
      initializeReadMarkers();
      startLiveEvents();
      startPresence();
    } catch (error) {
      if (!authNeeded) {
        markServerDisconnected();
        if (!preservePage) notify(error.message, true);
      }
    } finally {
      loadingWorld = false;
      render();
    }
  }

  async function checkServerConnection() {
    // Check the live server rather than trusting the browser's "online" flag.
    // One small request every five seconds detects shut-down servers even
    // when a tab is idle and the last game screen is still in memory.
    if (probingServer || loadingWorld || (!state && !offline && !authNeeded)) return;
    probingServer = true;
    const controller = new AbortController();
    const limit = setTimeout(() => controller.abort(), 3500);
    try {
      const response = await fetch("/api/health", {
        cache: "no-store", signal: controller.signal
      });
      if (!response.ok || (await response.json()).ok !== true)
        throw Error("Server health check failed");
      if (offline) await load(true);
    } catch {
      markServerDisconnected();
    } finally {
      clearTimeout(limit);
      probingServer = false;
    }
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
        defense: state.player.defense,
        mana: state.player.max_mana
      } : { hp: 0, strength: 0, defense: 0, mana: 0 };
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
          defense: state.player.defense - oldStats.defense,
          mana: state.player.max_mana - oldStats.mana };
      }
      syncAttunements();
      // Action responses already carry full map and University projections.
      mapTravelSettlePending = false;
      universityNeedsRefresh = false;
      if (body && ["start_duel", "engage_duel", "duel_turn", "flee_duel"].includes(body.action)) {
        tab = "duel";
        if (body.action === "engage_duel") duelPreviewTarget = null;
      }
      if (body && body.action === "practice_magic" && result.result) {
        latestPractice = { ...result.result, nodeId: body.params.node_id };
        tab = "magic";
      }
      if (body && body.action === "start_city_contract" && result.result) {
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

  function lineagePicker() {
    return '<fieldset class="lineage-fieldset" aria-label="Lineage options">' +
      '<div class="lineage-grid">' + lineageCatalog.map(spec =>
        '<label class="lineage-option"><input type="radio" name="lineage" value="' +
        esc(spec.id) + '" required>' +
        '<span class="lineage-option-body"><strong>' + esc(spec.title) +
        '</strong><small>' + esc(spec.description) + '</small>' +
        '<span class="lineage-stats">Work: +' + spec.work[0] + ' Manual · +' +
        spec.work[1] + ' Intellect · +' + spec.work[2] + ' Endurance</span>' +
        '<span class="lineage-stats">Combat: +' + spec.attack + ' Attack / +' +
        spec.defense + ' Defense</span>' +
        '<span class="lineage-trait">' +
        esc(spec.trait) + ': ' + esc(spec.trait_description) +
        '</span></span></label>').join('') + '</div></fieldset>';
  }

  function introKey(actorId) { return "oathmere.welcome." + actorId; }
  function pendingIntroduction() {
    if (!state || !state.actor_id) return false;
    if (introActor === state.actor_id) return true;
    try { return localStorage.getItem(introKey(state.actor_id)) === "pending"; }
    catch { return false; }
  }
  function markIntroductionPending() {
    if (!state || !state.actor_id) return;
    introActor = state.actor_id;
    try { localStorage.setItem(introKey(state.actor_id), "pending"); }
    catch { /* Keep the welcome step in this page session. */ }
  }
  function completeIntroduction() {
    if (!state || !state.actor_id) return;
    if (introActor === state.actor_id) introActor = null;
    try { localStorage.removeItem(introKey(state.actor_id)); }
    catch { /* The button still opens the city interface. */ }
  }
  function lineagePromptPage() {
    return '<div class="entry"><div class="entry-card lineage-entry">' +
      '<div class="entry-seal">✦</div><h1>Choose your lineage</h1>' +
      '<p>Before entering Oathmere, choose the lineage that will shape your character.</p>' +
      '<form id="lineageChoiceForm">' + lineagePicker() +
      '<button class="button full gold" type="submit">Confirm lineage</button></form>' +
      '</div></div>';
  }
  function introductionPage() {
    return '<div class="entry"><div class="entry-card">' +
      '<div class="entry-seal">✦</div><div class="eyebrow">Your story begins</div>' +
      '<h1>Welcome to Oathmere</h1>' +
      '<p>You are dropped into an unfamiliar location with a small amount of gold ' +
      'and only the clothes on your back. Nobody here knows your name or what ' +
      'you might become. Across Oathmere lie unfamiliar roads, hidden places, ' +
      'and countless opportunities to shape your own story.</p>' +
      button("Enter Oathmere", 'data-ui="enter-oathmere"', "full gold") +
      '</div></div>';
  }

  function passwordToggle(target) {
    return '<button type="button" class="password-toggle" data-ui="toggle-password" ' +
      'data-password-for="' + target + '" aria-label="Show password" ' +
      'title="Show password" aria-pressed="false">' +
      '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" ' +
      'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M2.4 12s3.5-6 9.6-6 9.6 6 9.6 6-3.5 6-9.6 6-9.6-6z"/>' +
      '<circle cx="12" cy="12" r="2.8"/>' +
      '<path class="password-eye-slash" d="M3 3 21 21"/></svg></button>';
  }

  function authPage() {
    if (multiMode) return '<div class="entry"><div class="entry-card">' +
      '<div class="entry-seal">✦</div><div class="eyebrow">Local multi-account world</div>' +
      '<h1>Welcome to Oathmere</h1>' +
      '<p>Each player has a private login and a separate character. ' +
      'This development server runs on your own computer.</p>' +
      '<form id="accountLoginForm" class="stack">' +
      '<label for="loginUsername">Email Address</label>' +
      '<input id="loginUsername" class="field" type="text" inputmode="email" autocomplete="username" ' +
      'maxlength="254" required>' +
      '<label for="loginPassword">Password</label>' +
      '<div class="password-input-wrap">' +
      '<input id="loginPassword" class="field" type="password" ' +
      'autocomplete="current-password" required>' +
      passwordToggle("loginPassword") + '</div>' +
      '<button class="button full gold" type="submit">Sign in</button></form>' +
      '<details class="account-register"><summary>Create an account</summary>' +
      '<form id="accountRegisterForm" class="stack">' +
      '<label for="registerUsername">Email Address</label>' +
      '<input id="registerUsername" class="field" type="email" autocomplete="email" ' +
      'maxlength="254" required>' +
      '<label for="registerCharacter">Character name</label>' +
      '<input id="registerCharacter" class="field" minlength="2" maxlength="28" required>' +
      (inviteRequired ?
      '<label for="registerInvite">Invitation code</label>' +
      '<input id="registerInvite" class="field" autocomplete="off" ' +
      'placeholder="One-time code from game operator" required>' : "") +
      '<label for="registerPassword">Password (12 characters minimum)</label>' +
      '<div class="password-input-wrap">' +
      '<input id="registerPassword" class="field" type="password" ' +
      'autocomplete="new-password" minlength="12" maxlength="128" required>' +
      passwordToggle("registerPassword") + '</div>' +
      '<button class="button full" type="submit">Register account</button>' +
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
      '<div class="password-input-wrap">' +
      '<input id="access" class="field" type="password" autocomplete="off" placeholder="Server access code" required>' +
      passwordToggle("access") + '</div>' +
      '<button class="button full" type="submit">Enter world</button></form></div></div>';
  }
  async function accountSubmit(url, body) {
    if (pending) return;
    pending = true;
    try {
      const outcome = await request(url, body);
      csrfToken = outcome.csrf || "";
      state = outcome.state;
      if (url.endsWith("/register")) markIntroductionPending();
      pageHistory.length = 0;
      tab = "character";
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
    return '<div class="entry"><div class="entry-card lineage-entry">' +
      '<div class="entry-seal">✦</div><div class="eyebrow">Welcome, traveler</div>' +
      '<h1>Your story begins in Oathmere.</h1>' +
      '<p>Enter an unfamiliar world as an unknown traveler. Choose your lineage, ' +
      'then discover where the roads lead.</p>' +
      '<form id="newGameForm"><label for="heroName">Character name</label>' +
      '<input class="field" id="heroName" maxlength="28" autocomplete="off" placeholder="Choose your character name" required>' +
      lineagePicker() +
      '<button class="button full gold" type="submit"' + disabled(pending) +
      '>Begin your adventure</button></form>' +
      '<p class="small">Begin with 240 gold. Unexplored places remain hidden on your map.</p>' +
      '</div></div>';
  }
  function refreshVital(old, label, value, maximum, kind, next) {
    if (!old) return;
    // Preserve the hovered/focused DOM node across each world tick. Replacing
    // it with outerHTML dismisses the CSS tooltip and causes flashing.
    const wrapper = document.createElement("div");
    wrapper.innerHTML = meterStat(label, value, maximum, kind, next);
    const fresh = wrapper.firstElementChild;
    if (!fresh) return;
    old.setAttribute("aria-label", fresh.getAttribute("aria-label"));
    for (const key of ["hoverText", "timerLabel", "timerEnd", "timerFixed"]) {
      if (key in fresh.dataset) old.dataset[key] = fresh.dataset[key];
      else delete old.dataset[key];
    }
    const oldText = old.querySelector(".vital-caption strong");
    const newText = fresh.querySelector(".vital-caption strong");
    if (oldText && newText) oldText.textContent = newText.textContent;
    const oldProgress = old.querySelector("progress");
    const newProgress = fresh.querySelector("progress");
    if (oldProgress && newProgress) {
      oldProgress.max = newProgress.max;
      oldProgress.value = newProgress.value;
    }
  }
  function offlinePage() {
    return '<div class="entry" role="alert"><div class="entry-card">' +
      '<div class="entry-seal">⌁</div><h1>Server disconnected</h1>' +
      '<p>Gameplay is temporarily unavailable. The client will reconnect ' +
      'automatically when the server returns.</p></div></div>';
  }

  function meterStat(label, value, max, kind, simSeconds) {
    const v = Number(value) || 0;
    const maximum = Math.max(1, Number(max) || 1);
    const hint = v >= maximum ? label + ": Full" :
      simSeconds == null ? label + ": No passive recovery available" :
      label + ": Next increase in ";
    const timing = v < maximum && simSeconds != null ?
      timerAttrs(hint, simSeconds) : ' data-hover-text="' + esc(hint) + '"';
    return '<div class="vital vital-' + kind +
      '"' + timing + ' tabindex="0" aria-label="' +
      esc(label + ': ' + v + ' of ' + maximum + '. ' +
        (v >= maximum || simSeconds == null ? hint :
          hint + fullCountdown(timerSeconds(simSeconds)))) + '">' +
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
    const seconds = timerSeconds(remaining * 60);
    const time = fullCountdown(seconds);
    return '<div class="cooldown-chip ' + (remaining >= max ? 'at-cap' : '') +
      '" data-activity-key="cooldown-' + name + '"' +
      timerAttrs(tip, remaining * 60, seconds) +
      ' tabindex="0" aria-label="' + esc(tip + time) +
      '"><span aria-hidden="true">' + config.symbol + '</span><strong data-timer-display>' +
      time + '</strong></div>';
  }
  function activityIcons() {
    if (!state || !state.started) return "";
    const items = ["job", "food", "potion"].map(cooldownIcon).join("");
    const p = state.player;
    const incoming = multiMode ? (state.trades || []).filter(t =>
      t.recipient === state.actor_id).length : 0;
    const trade = incoming ?
      '<button class="cooldown-chip activity-clickable activity-trade" type="button" ' +
      'data-activity-key="trade" data-ui="activity-trade" title="' + incoming + ' incoming trade offer(s)" ' +
      'aria-label="' + incoming + ' incoming trade offer(s)">' +
      '<span aria-hidden="true">⇄</span><strong>' + incoming + ' trade' +
      (incoming === 1 ? '' : 's') + '</strong></button>' : "";
    const merits = state.merits || {};
    // Claiming transfers points from eligible achievements to balance:
    // it must not make the notification count go down and back up.
    const available = totalUnspentMerits(merits);
    const meritAlert = available > 0 ?
      '<button class="cooldown-chip activity-clickable" type="button" ' +
      'data-activity-key="merits" data-ui="activity-merits" data-hover-text="' +
      esc(available + ' Renown available') +
      '" aria-label="' + esc(available + ' Renown available') + '">' +
      '<span aria-hidden="true">✶</span><strong>' +
      available + ' Renown' +
      '</strong></button>' : "";
    const lettersCount = (state.economy?.job_offers || []).length;
    const letters = lettersCount ?
      '<button class="cooldown-chip activity-clickable" type="button" ' +
      'data-activity-key="letters" data-ui="activity-letters" ' +
      'data-hover-text="' + lettersCount + ' employment letter' +
      (lettersCount === 1 ? '' : 's') + '" aria-label="Employment letters">' +
      '<span aria-hidden="true">✉</span><strong>' +
      lettersCount + ' letter' + (lettersCount === 1 ? '' : 's') + '</strong></button>' : "";
    const tripMinutes = p.destination && Number.isFinite(p.arrival_minute) ?
      Math.max(0, p.arrival_minute - state.minute) : 0;
    const travel = p.destination ?
      '<button class="cooldown-chip activity-clickable" type="button" data-activity-key="travel" data-ui="activity-travel" ' +
      timerAttrs("Traveling to " + (p.hex_target ? "hex (" + p.hex_target.join(",") + ")" : pretty(p.destination)) + " · ", tripMinutes * 60) + ' ' +
      'aria-label="' + esc("Traveling to " + (p.hex_target ? "hex " + p.hex_target.join(", ") : pretty(p.destination))) + '">' +
      '<span aria-hidden="true">♞</span><strong>' + esc(state.dev_travel_seconds ? tripMinutes + "s" : simDuration(tripMinutes)) +
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
        'data-activity-key="university" data-ui="activity-university"' +
        timerAttrs(label, current.remaining_minutes * 60) + ' aria-label="' +
        esc(label + fullCountdown(timerSeconds(current.remaining_minutes * 60))) +
        '"><span aria-hidden="true">✤</span><strong data-timer-display>' +
        compactWallTime(timerSeconds(current.remaining_minutes * 60)) +
        '</strong></button>';
    }
    const defendant = state.duel;
    const hospitalMinutes = Math.max(0,
      Number(p.defeated_until || 0) - Number(state.minute || 0));
    const hospital = hospitalMinutes > 0 ?
      '<button type="button" class="cooldown-chip activity-clickable activity-hospital" ' +
      'data-activity-key="hospital" data-ui="activity-hospital"' +
      timerAttrs("Hospitalized · ", hospitalMinutes * 60) +
      ' aria-label="Hospitalized">' +
      '<span aria-hidden="true">✚</span><strong data-timer-display>' +
      compactWallTime(timerSeconds(hospitalMinutes * 60)) +
      '</strong></button>' : "";
    const defenderAlert = defendant && defendant.role === "defender" &&
      defendant.attack_started ?
      '<button class="cooldown-chip activity-clickable activity-combat" type="button" ' +
      'data-activity-key="combat" data-ui="activity-duel" title="' +
      esc("Under attack by " + state.duel.opponent_name +
        " · your character automatically counterattacks. Open to watch or flee.") +
      '" aria-label="Under attack · open combat">' +
      '<span aria-hidden="true">⚔</span><strong>Under attack</strong></button>' : "";
    const roomRemaining = state.tavern?.room_boost_remaining || 0;
    const room = roomRemaining > 0 ?
      '<button class="cooldown-chip activity-clickable" type="button" ' +
      'data-activity-key="tavern-room" data-ui="activity-tavern"' +
      timerAttrs("Room recovery bonus · ", roomRemaining * 60) +
      ' aria-label="Double recovery active"><span aria-hidden="true">♜</span>' +
      '<strong data-timer-display>' +
      fullCountdown(timerSeconds(roomRemaining * 60)) + '</strong></button>' : "";
    const activeShift = state.active_contract;
    const shift = activeShift ? '<button class="cooldown-chip activity-clickable" ' +
      'type="button" data-activity-key="civic-shift" data-ui="activity-mercenary"' +
      timerAttrs("Mercenary job · ", activeShift.remaining_minutes * 60) +
      '><span aria-hidden="true">▣</span><strong data-timer-display>' +
      fullCountdown(timerSeconds(activeShift.remaining_minutes * 60)) +
      '</strong></button>' : "";
    return items + room + shift + meritAlert + letters + trade + travel + university + hospital + defenderAlert;
  }
  function navButton(entry, className = "") {
    const locked = combatNavigationLocked();
    return '<button type="button" class="nav-button ' + className +
      (tab === entry.id ? ' active' : '') +
      (locked ? ' combat-nav-locked' : '') +
      '" data-tab="' + esc(entry.id) + '"' + disabled(locked) +
      ' aria-current="' + (tab === entry.id ? 'page' : 'false') + '">' +
      '<span class="nav-icon" aria-hidden="true">' + entry.icon + '</span>' +
      '<span>' + esc(entry.title) + '</span></button>';
  }
  function shell() {
    const p = state.player;
    const location = (state.cities || []).find(c => c.id === p.city);
    const goalCity = (state.cities || []).find(c => c.id === p.destination);
    const inWilderness = Boolean(state.world_map?.in_wilderness);
    const place = p.destination ?
      (p.hex_target ? "Exploring the wilderness" :
        "En route to " + (goalCity ? goalCity.name : pretty(p.destination))) :
      inWilderness ? "Wilderness" :
      location ? location.name : pretty(p.city);
    const renderers = {
      world: () => renderWorld() + renderWilderness(),
      market: () => renderMarket() + renderStalls(),
      magic: renderMagic, home: renderHome,
      companies: renderCompanies, job: renderEmployment, letters: renderLetters,
      inventory: renderInventory, training: renderTraining,
      character: renderCharacter, equipment: renderEquipment,
      chronicle: renderChronicle, mercenary: renderMercenaryJobs,
      tavern: renderTavern,
      cityhall: renderCityHall, harbor: renderHarbor,
      church: renderChurch, people: renderPeople, armory: renderArmory,
      duel: renderDuel, track: renderTrack,
      profile: renderProfile,
      trade: renderTrade,
      guilds: renderGuilds, merits: renderMerits,
      settings: renderSettings,
    };
    const view = state.duel && state.duel.role !== "defender" ?
      renderDuel : (renderers[tab] || renderWorld);
    const remoteLinks = new Set(["inventory","magic","guilds","merits"]);
    const sidebar = cityLinks.filter(t =>
      (!t.onlyCity || t.onlyCity === p.city) &&
      (!p.destination && !inWilderness || remoteLinks.has(t.id)))
      .map(t => navButton(t)).join('');
    const topLinks = accountTabs.map(t => navButton(t, "account-button")).join('');
    return '<div class="shell">' +
      '<header class="topbar"><div class="topbar-inner">' +
      '<div class="brand"><div class="brand-mark">✦</div><span>OATHMERE</span></div>' +
      '<div class="statbar" aria-label="Character vitals">' +
      meterStat("Life", p.hp, p.max_hp, "health", p.health_next_sim_seconds) +
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
      '<div class="account-utility">' +
      '<button class="settings-shortcut' + (tab === "settings" ? " active" : "") +
      '" type="button" data-ui="settings-open"' +
      disabled(combatNavigationLocked()) +
      ' aria-label="Open Settings" data-hover-text="Settings" aria-current="' +
      (tab === "settings" ? "page" : "false") + '">' +
      '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round">' +
      '<path d="M4 6h16M4 12h16M4 18h16"/></svg></button>' +
      (multiMode ? '<button class="logout-link" type="button" data-ui="account-logout">' +
        'Sign out</button>' : '') + '</div>' +
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
    return groupCombatChronicle(state.events || []).filter(event =>
      (chronicleCategory === "all" || event.category === chronicleCategory) &&
      (!query || [event.text, event.kind, event.category,
        ...(event.actions || []).map(action => action.text)].some(value =>
        String(value || "").toLowerCase().includes(query))));
  }
  function chronicleItems(events) {
    const rows = groupCombatChronicle(events);
    return rows.length ? '<ul class="activity">' +
      rows.map(e => e.kind === "combat_encounter" ?
        '<li class="activity-encounter"><details data-encounter-id="' +
        esc(e.id) + '"' + (chronicleOpenEncounters.has(String(e.id)) ? ' open' : '') +
        '><summary><span class="encounter-title">' +
        '<span><span class="chronicle-tag">Combat</span> ' + esc(e.text) +
        '</span><small class="encounter-disclosure"><span class="encounter-chevron" ' +
        'aria-hidden="true">▸</span> ' + e.actions.length + ' actions · ' +
        '<span class="when-closed">Click to expand</span>' +
        '<span class="when-open">Click to collapse</span></small></span>' +
        '<time title="Simulation elapsed: ' + esc(clock(e.minute)) +
        '">' + esc(eventTime(e)) + '</time></summary>' +
        '<ol class="encounter-rounds">' + e.actions.map(action =>
          '<li><span>' + esc(action.text) + '</span><time>' +
          esc(eventTime(action)) + '</time></li>').join("") +
        '</ol></details></li>' :
        '<li><span><span class="chronicle-tag">' +
        esc(e.category || "Other") + '</span> ' + esc(e.text) +
        '</span><time title="Simulation elapsed: ' + esc(clock(e.minute)) +
        '">' + esc(eventTime(e)) + '</time></li>').join("") +
      '</ul>' : '<p class="empty">No matching Chronicle events.</p>';
  }
  function chronicleResults() {
    const matches = chronicleEvents();
    const shown = Math.min(chronicleVisibleCount, matches.length);
    return '<p class="chronicle-count">Showing ' + shown + ' of ' +
      matches.length + ' matching entries · Search covers the 500 most recent ' +
      'events in this view</p>' +
      chronicleItems(matches.slice(0, shown)) +
      (shown < matches.length ? button("Show 50 more",
        'data-ui="chronicle-more"', "secondary") : '');
  }
  function rememberChronicleExpansion(container) {
    for (const details of container.querySelectorAll("details[data-encounter-id]")) {
      const key = details.dataset.encounterId;
      if (details.open) chronicleOpenEncounters.add(key);
      else chronicleOpenEncounters.delete(key);
    }
  }
  function chronicleFilterKey() {
    return chronicleCategory + "\u0000" + chronicleQuery + "\u0000" +
      chronicleVisibleCount;
  }
  function refreshChronicleList() {
    const list = document.getElementById("chronicle-list");
    if (!list || (renderedChronicleEvents === state.events &&
                  renderedChronicleFilterKey === chronicleFilterKey())) return;
    rememberChronicleExpansion(list);
    list.innerHTML = chronicleResults();
    renderedChronicleEvents = state.events;
    renderedChronicleFilterKey = chronicleFilterKey();
  }
  function activityPanel(showTitle = true) {
    const body = chronicleItems((state.events || []).slice(0, 12));
    return showTitle ? panel("Chronicle", "", body) :
      '<section class="panel chronicle-panel">' + body + '</section>';
  }
  // View modules receive a narrow interface rather than owning networking,
  // action execution or the mutable simulation state.
  const { renderWorld, renderTravelConfirmation, renderHexConfirmation,
    renderMarket, renderMagic, renderHome } =
    createWorldViews({
      getState: () => state,
      getPending: () => pending,
      getSecureWorldClock: () => secureWorldClock,
      getSchool: () => school,
      setSchool: value => { school = value; },
      getLatestPractice: () => latestPractice,
      getTravelIntent: () => travelIntent,
      getHexIntent: () => hexIntent,
      getMapZoom: () => mapZoom,
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
      getDuelPreviewTarget: () => duelPreviewTarget,
      getMultiMode: () => multiMode,
      getSelectedCharacterId: () => selectedCharacterId,
      getPending: () => pending,
      esc, pretty, money, dur, button, disabled, isBusy, heading, panel,
      characterRow, progress, chip,
    });
  const { renderInventory, renderCharacter, renderEquipment, renderArmory } =
    createCharacterViews({
      getState: () => state,
      getArmoryCategory: () => armoryCategory,
      esc, pretty, clock, money, button, disabled, isBusy, heading, panel,
      characterRow,
    });
  function renderSettings() {
    const appearance = ["light", "dark"].map(value =>
      button(value === "light" ? "Light" : "Dark",
        'type="button" data-ui="settings-theme" data-value="' + value +
        '" aria-pressed="' + (themePreference === value) + '"',
        themePreference === value ? "secondary settings-choice active" :
          "secondary settings-choice")).join("");
    const accountNote = multiMode ?
      "Your password and account data remain in the local Oathmere server." :
      "This world is using the local single-player preview.";
    const clockMode = state.dev_travel_seconds ?
      "Accelerated testing · one world minute per real second" :
      "Normal world clock";
    return heading("", "Settings", "") +
      '<div class="settings-grid">' +
      panel("Appearance", "Saved locally in this browser",
        '<div class="settings-choices" role="group" aria-label="Color theme">' +
        appearance + '</div>') +
      panel("Email & notifications", "Not yet connected",
        '<p class="small">Planned: verified email address, notification categories, ' +
        'delivery preferences and opt-out controls. No email is currently sent ' +
        'or collected by these settings.</p>' +
        '<span class="settings-future">Future configuration</span>') +
      panel("Account & security", "Local development",
        '<p class="small">' + esc(accountNote) + '</p>' +
        '<p class="small">Future: change password, manage signed-in sessions ' +
        'and review account security. Sign out remains available above.</p>') +
      panel("World & gameplay", "Current session",
        '<div class="settings-info"><span>World clock</span><strong>' +
        esc(clockMode) + '</strong></div>' +
        '<p class="small">Future: accessibility, sound and game notifications. ' +
        'Changing world simulation settings requires server-side controls.</p>') +
      '</div>';
  }
  function renderChronicle() {
    renderedChronicleEvents = state.events;
    renderedChronicleFilterKey = chronicleFilterKey();
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
      '<div id="chronicle-list">' + chronicleResults() + '</div>' +
      '</section>';
  }
  function characterRow(label, value) {
    return '<div class="character-row"><span>' + esc(label) +
      '</span><strong>' + esc(value) + '</strong></div>';
  }
  const { renderMercenaryJobs, renderChurch, renderTrack, renderHarbor,
    renderGuilds, renderMerits, renderCityHall, renderJob, renderTraining, renderTavern } =
    createCityViews({
      getState: () => state,
      getLatestContract: () => latestContract,
      getExpandedUniversitySchool: () => expandedUniversitySchool,
      getPending: () => pending,
      getSecureWorldClock: () => secureWorldClock,
      timerAttrs, timerText: seconds => fullCountdown(timerSeconds(seconds)),
      esc, pretty, money, dur, button, disabled, isBusy, heading, panel,
      characterRow, chip,
    });
  const { renderWilderness, handleWildernessClick } = createWildernessViews({
    getState: () => state, action, render, isBusy,
    esc, pretty, button, disabled, panel,
  });
  // Economy page rendering and action dispatch own no networking or mutable
  // server state. The main coordinator only supplies its established callbacks.
  const { renderCompanies, renderEmployment, renderStalls, renderLetters } =
    createEconomyViews({
      getState: () => state,
      getCompanySection: () => companySection,
      esc, pretty, money, button, disabled, isBusy, heading, panel, timerAttrs, fullCountdown, timerSeconds,
    });
  const { handleEconomyClick } = createEconomyActions({
    getRoot: () => root, getState: () => state, action, notify,
    confirmAction: requestConfirmation,
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
      '<span>+' + levelCelebration.defense + ' Defense</span>' +
      (levelCelebration.mana > 0 ? '<span>+' + levelCelebration.mana +
        ' Mana Capacity</span>' : '') + '</div>' +
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
      if (Array.isArray(update.employment_offers) && state.economy)
        state.economy.job_offers = update.employment_offers;
      if ("active_contract" in update) state.active_contract = update.active_contract;
      if ("minute" in update) state.minute = update.minute;
      if ("next_world_tick_seconds" in update) {
        state.next_world_tick_seconds = update.next_world_tick_seconds;
        clockSyncedAt = Date.now();
      }
      if ("duel" in update) state.duel = update.duel;
      if ("last_duel" in update) state.last_duel = update.last_duel;
      if ("course_active" in update && state.training_hall) {
        const priorCourse = state.training_hall.active;
        const nextCourse = update.course_active;
        // The stream omits completed/available flags for every school.
        // Re-read authoritative enrollment options when a course completes.
        if (activeCourseEnded(priorCourse, nextCourse))
          universityNeedsRefresh = true;
        state.training_hall.active = nextCourse;
      }
      if (Array.isArray(update.users)) state.users = update.users;
      if (Array.isArray(update.presence_updates) && Array.isArray(state.users)) {
        const presenceById = new Map(update.presence_updates.map(item =>
          [item.id, item.presence]));
        state.users = state.users.map(user => presenceById.has(user.id) ?
          { ...user, presence: presenceById.get(user.id) } : user);
      }
      if (Array.isArray(update.events)) state.events = update.events;
      if (update.player_status) {
        const wasTraveling = Boolean(state.player.destination);
        Object.assign(state.player, update.player_status);
        if (travelJustArrived(wasTraveling, state.player.destination))
          mapTravelSettlePending = true;
      }
      if (chatOpen) markChannelRead(chatChannelKey);
      refreshLiveSurfaces();
    };
    stream.addEventListener("activity", receiveActivity);
    stream.addEventListener("activity-delta", receiveActivity);
    stream.addEventListener("error", () => {
      // A dropped stream may be a brief SSE failure rather than a server
      // outage. Verify the health endpoint before blocking the client.
      if (stream === liveEvents) checkServerConnection();
    });
    // EventSource reconnects automatically and sends the session cookie.
    // This stream intentionally has no client-controlled actor identifier.
  }
  function refreshActivityStrip(strip) {
    // Preserve unchanged chip nodes across every SSE update. Replacing
    // innerHTML even with identical markup dismisses hovered CSS tooltips.
    const fragment = document.createElement("div");
    fragment.innerHTML = activityIcons();
    const desired = Array.from(fragment.children);
    const wanted = new Set(desired.map(node => node.dataset.activityKey));
    for (const old of Array.from(strip.children)) {
      if (!wanted.has(old.dataset.activityKey)) old.remove();
    }
    const existing = new Map(Array.from(strip.children).map(node =>
      [node.dataset.activityKey, node]));
    desired.forEach((fresh, index) => {
      const key = fresh.dataset.activityKey;
      let old = existing.get(key);
      if (!old || old.tagName !== fresh.tagName) {
        if (old) old.remove();
        strip.insertBefore(fresh, strip.children[index] || null);
        existing.set(key, fresh);
        return;
      }
      if (strip.children[index] !== old)
        strip.insertBefore(old, strip.children[index] || null);
      for (const attr of Array.from(old.attributes)) {
        if (!fresh.hasAttribute(attr.name)) old.removeAttribute(attr.name);
      }
      for (const attr of Array.from(fresh.attributes)) {
        if (old.getAttribute(attr.name) !== attr.value)
          old.setAttribute(attr.name, attr.value);
      }
      const oldIcon = old.querySelector("span");
      const freshIcon = fresh.querySelector("span");
      if (oldIcon && freshIcon && oldIcon.innerHTML !== freshIcon.innerHTML)
        oldIcon.innerHTML = freshIcon.innerHTML;
      const readout = old.querySelector("strong");
      const nextReadout = fresh.querySelector("strong");
      if (readout && nextReadout && readout.textContent !== nextReadout.textContent)
        readout.textContent = nextReadout.textContent;
    });
  }
  function refreshPeopleSearch() {
    // Only refresh the result/suggestion containers. The input DOM stays in
    // place, so characters appear as you type without losing keyboard focus.
    const results = document.querySelector(".search-matches");
    const suggestions = document.getElementById("people-suggestions");
    if (!results && !suggestions) return;
    const temp = document.createElement("div");
    temp.innerHTML = renderPeople();
    const nextResults = temp.querySelector(".search-matches");
    const nextSuggestions = temp.querySelector("#people-suggestions");
    if (results && nextResults && results.innerHTML !== nextResults.innerHTML)
      results.innerHTML = nextResults.innerHTML;
    if (suggestions && nextSuggestions) {
      if (suggestions.innerHTML !== nextSuggestions.innerHTML)
        suggestions.innerHTML = nextSuggestions.innerHTML;
      suggestions.hidden = nextSuggestions.hidden;
    }
  }
  function refreshLiveSurfaces() {
    if (!state || !state.started) return;
    const strip = document.querySelector(".activity-strip");
    if (strip) refreshActivityStrip(strip);
    // Pushed clock ticks also change the health, stamina and mana values.
    const p = state.player;
    for (const [kind, label, value, maximum, next] of [
      ["health", "Life", p.hp, p.max_hp, p.health_next_sim_seconds],
      ["stamina", "Stamina", p.stamina, p.max_stamina, p.stamina_next_sim_seconds],
      ["mana", "Mana", p.mana, p.max_mana, p.mana_next_sim_seconds],
    ]) {
      refreshVital(document.querySelector(".vital-" + kind),
                   label, value, maximum, kind, next);
    }
    // Re-anchor the University page to the same server clock as its badge
    // without replacing the opened school details or its progress meter.
    if (tab === "training") {
      const timer = document.querySelector(".university-countdown");
      const current = state.training_hall && state.training_hall.active;
      if (timer && current) {
        const simSeconds = current.remaining_minutes * 60;
        const end = timerEndMs(simSeconds);
        timer.dataset.timerEnd = String(end);
        timer.dataset.timerFixed = end ? "" : String(Math.ceil(timerSeconds(simSeconds)));
      }
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
      refreshPeopleSearch();
    } else if (tab === "profile") {
      const content = document.getElementById("main-content");
      if (content) content.innerHTML = renderProfile();
    } else if (tab === "chronicle") {
      refreshChronicleList();
    }
    if (tab === "letters") {
      const content = document.getElementById("main-content");
      if (content) content.innerHTML = renderLetters();
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
      refreshVital(header.querySelector(".vital-health"), "Life",
                   state.player.hp, state.player.max_hp, "health",
                   state.player.health_next_sim_seconds);
      refreshVital(header.querySelector(".vital-stamina"), "Stamina",
                   state.player.stamina, state.player.max_stamina, "stamina",
                   state.player.stamina_next_sim_seconds);
      refreshVital(header.querySelector(".vital-mana"), "Mana",
                   state.player.mana, state.player.max_mana, "mana",
                   state.player.mana_next_sim_seconds);
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
      '<div class="chat-dock-actions"><button type="button" class="chat-game-refresh" ' +
      'data-ui="page-back" title="Back to previous page" aria-label="Back to previous page"' +
      disabled(!pageHistory.length || combatNavigationLocked()) + '>‹</button>' +
      '<button type="button" class="chat-toggle" data-ui="chat-toggle" ' +
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

  function gameConfirmation() {
    const choice = confirmationIntent;
    if (!choice) return "";
    return '<div class="travel-confirm-overlay" role="presentation">' +
      '<section class="travel-confirm-card" role="dialog" aria-modal="true" ' +
      'aria-labelledby="game-confirm-title" aria-describedby="game-confirm-description">' +
      '<h2 id="game-confirm-title">' + esc(choice.title) + '</h2>' +
      '<p id="game-confirm-description">' + esc(choice.description) + '</p>' +
      '<div class="travel-confirm-actions">' +
      button("Cancel", 'data-ui="game-confirm-cancel"', "secondary") +
      button(choice.button, 'data-ui="game-confirm-accept"', "gold") +
      '</div></section></div>';
  }
  function guildLeaveConfirmation() {
    const own = state && state.guilds && state.guilds.my_guild;
    if (!guildLeaveIntent || !own) return "";
    const lastMember = Object.keys(own.members).length === 1;
    return '<div class="travel-confirm-overlay" role="presentation">' +
      '<section class="travel-confirm-card" role="dialog" aria-modal="true" ' +
      'aria-labelledby="guild-leave-title" aria-describedby="guild-leave-description">' +
      '<h2 id="guild-leave-title">' +
      (lastMember ? 'Dissolve ' + esc(own.name) + '?' : 'Leave ' + esc(own.name) + '?') +
      '</h2><p id="guild-leave-description">' +
      (lastMember ? 'You are the last member. Leaving will permanently dissolve ' +
        'the guild and all its accumulated progress. Are you sure?' :
        'Are you sure you want to leave this guild?') +
      '</p><div class="travel-confirm-actions">' +
      button("Cancel", 'data-ui="guild-leave-cancel"', "secondary") +
      button(lastMember ? "Dissolve guild" : "Leave guild",
        'data-ui="guild-leave-confirm"', "gold") +
      '</div></section></div>';
  }
  let lastMapHex = null;
  function render() {
    // Preserve native <details> expansion before a full shell replacement.
    rememberChronicleExpansion(root);
    const previous = root.querySelector(".terrain-map-scroll");
    const oldScroll = previous ? [previous.scrollLeft, previous.scrollTop] : null;
    if (offline) root.innerHTML = offlinePage();
    else if (authNeeded) root.innerHTML = authPage();
    else if (state && !state.started) root.innerHTML = newCharacterPage();
    else if (state && state.started && !state.player.lineage_selected)
      root.innerHTML = lineagePromptPage();
    else if (state && state.started && pendingIntroduction())
      root.innerHTML = introductionPage();
    else if (state && state.started) root.innerHTML = shell() +
      chatDock() + levelUpOverlay() +
      (tab === "world" ? renderTravelConfirmation() + renderHexConfirmation() : "") +
      guildLeaveConfirmation() + gameConfirmation();
    else root.innerHTML = '<main class="startup"><div class="loader-ring"></div>' +
      '<p>Opening the city gates…</p></main>';
    const map = root.querySelector(".terrain-map-scroll");
    if (map && state && state.world_map) {
      const hex = state.world_map.position.join(",");
      if (!oldScroll || hex !== lastMapHex || forceMapCenter) {
        forceMapCenter = false;
        const marker = map.querySelector(".survey-player");
        if (marker) {
          const frame = map.getBoundingClientRect();
          const point = marker.getBoundingClientRect();
          map.scrollLeft += point.left + point.width / 2 - frame.left - frame.width / 2;
          map.scrollTop += point.top + point.height / 2 - frame.top - frame.height / 2;
        }
        lastMapHex = hex;
      } else if (oldScroll) {
        map.scrollLeft = oldScroll[0];
        map.scrollTop = oldScroll[1];
      }
    }
  }

  root.addEventListener("submit", async event => {
    if (event.target.id === "newGameForm") {
      event.preventDefault();
      const name = document.getElementById("heroName").value.trim();
      const lineage = new FormData(event.target).get("lineage");
      if (name && lineage) await send("/api/new", { name, lineage }, "Welcome to Oathmere!");
    } else if (event.target.id === "lineageChoiceForm") {
      event.preventDefault();
      const lineage = new FormData(event.target).get("lineage");
      if (lineage) await action("choose_lineage", { lineage }, "Your lineage is now part of your story");
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

  // Native details state is independent of server push cadence. Remember
  // expanded encounters across Chronicle refreshes and full-page renders.
  root.addEventListener("toggle", event => {
    const details = event.target;
    if (!details.matches || !details.matches("details[data-encounter-id]") ||
        !root.contains(details)) return;
    const key = details.dataset.encounterId;
    if (details.open) chronicleOpenEncounters.add(key);
    else chronicleOpenEncounters.delete(key);
    if (chronicleOpenEncounters.size > 100)
      chronicleOpenEncounters.delete(chronicleOpenEncounters.values().next().value);
  }, true);

  root.addEventListener("input", event => {
    if (event.target.id === "guild-name") {
      event.target.setCustomValidity("");
      return;
    }
    if (event.target.id === "people-query") {
      peopleQuery = event.target.value;
      refreshPeopleSearch();
      return;
    }
    if (event.target.id === "chronicle-query") {
      chronicleQuery = event.target.value;
      chronicleVisibleCount = 50;
      refreshChronicleList();
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
      chronicleVisibleCount = 50;
      refreshChronicleList();
      return;
    }
    const path = event.target.getAttribute("data-attune");
    if (!path) return;
    if (event.target.checked) selectedAttunements.add(path);
    else selectedAttunements.delete(path);
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && confirmationIntent) {
      event.preventDefault();
      confirmationIntent = null;
      render();
      return;
    }
    if (event.key === "Escape" && (travelIntent || hexIntent)) {
      event.preventDefault();
      travelIntent = null;
      hexIntent = null;
      render();
    }
  });

  root.addEventListener("input", event => {
    if (event.target.id !== "occupation-company-search") return;
    const term = event.target.value.trim().toLowerCase();
    for (const row of root.querySelectorAll("[data-company-search]")) {
      row.hidden = !row.dataset.companySearch.includes(term);
    }
  });
  root.addEventListener("click", event => {
    const summary = event.target.closest(".university-school > summary");
    if (summary) {
      const details = summary.parentElement;
      const opening = !details.open;
      for (const other of root.querySelectorAll(".university-school")) {
        if (other !== details) other.open = false;
      }
      expandedUniversitySchool = opening ? details.dataset.university : null;
      return;
    }
    const element = event.target.closest("button, [data-ui=\"explore-hex\"]");
    if (!element || pending || element.disabled ||
        (offline && element.dataset.ui !== "reload")) return;
    if (element.dataset.tab) {
      navigateTo(element.dataset.tab);
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (element.dataset.school && !element.dataset.ui) {
      school = element.dataset.school;
      render();
      return;
    }
    if (handleEconomyClick(element) || handleWildernessClick(element)) return;
    const ui = element.dataset.ui;
    const item = element.dataset.item;
    const node = element.dataset.node;
    switch (ui) {
      case "game-confirm-cancel":
        confirmationIntent = null; render(); break;
      case "game-confirm-accept": {
        const choice = confirmationIntent;
        confirmationIntent = null;
        if (choice) action(choice.command, choice.params, choice.success);
        break;
      }
      case "activity-tavern":
        navigateTo("tavern"); render(); break;
      case "activity-mercenary":
        navigateTo("mercenary"); render(); break;
      case "company-section":
        companySection = element.dataset.section || "overview";
        render(); break;
      case "enter-oathmere":
        completeIntroduction();
        tab = "character";
        render();
        break;
      case "settings-open":
        navigateTo("settings");
        render();
        break;
      case "settings-theme": {
        const value = element.dataset.value;
        if (!["light", "dark"].includes(value)) break;
        themePreference = value;
        try { localStorage.setItem(THEME_KEY, value); }
        catch { /* A blocked preference store must not prevent theme use. */ }
        applyTheme();
        render();
        break;
      }
      case "account-logout":
        (async () => {
          try {
            await request("/api/auth/logout", {});
            stopLiveEvents();
            stopPresence();
            state = null;
            csrfToken = "";
            pageHistory.length = 0;
            selectedCharacterId = null;
            authNeeded = true;
            notify("Signed out");
            render();
          } catch (error) {
            notify(error.message, true);
          }
        })(); break;
      case "chronicle-more": {
        chronicleVisibleCount += 50;
        refreshChronicleList();
        break;
      }
      case "page-back":
        if (pageHistory.length) {
          tab = pageHistory.pop();
          render();
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
        break;
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
        navigateTo("profile");
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
          navigateTo("trade");
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
        if (!name || name.length < 3 || name.length > 40) {
          if (input) {
            input.setCustomValidity("Guild name must contain 3–40 characters.");
            input.reportValidity();
          }
          notify("Guild name must contain 3–40 characters.", true);
          break;
        }
        input.setCustomValidity("");
        action("found_guild", { name }, "Guild founded"); break;
      }
      case "guild-join":
        action("join_guild", { guild_id: element.dataset.guild }, "Joined guild");
        break;
      case "guild-invite": {
        const selected = document.getElementById("guild-invite-target")?.value;
        if (selected) action("invite_guild", {candidate_id: selected}, "Invitation sent");
        break;
      }
      case "guild-role":
        action("set_guild_role", {member_id: element.dataset.member,
          role: element.dataset.role}, "Guild role updated");
        break;
      case "guild-right":
        action("set_guild_right", {member_id: element.dataset.member,
          right: element.dataset.right, enabled: element.dataset.enabled === "true"},
          "Member permission updated");
        break;
      case "guild-enlist":
        action("enlist_guild_war", {enabled: element.dataset.enabled === "true"},
          "Weekly war enrollment updated");
        break;
      case "war-practice":
        action("start_war_practice", {}, "Practice war started");
        break;
      case "war-join":
        action("join_warfront", {}, "Entered Banner Clash warfront");
        break;
      case "war-leave":
        requestConfirmation({
          title: "Leave the battlefield?",
          description: "Leaving while opponents can contest the field concedes one hit.",
          button: "Leave battlefield", command: "leave_warfront",
          params: {}, success: "Left warfront"
        });
        break;
      case "war-attack":
        tab = "duel";
        action("engage_duel", {defender_id: element.dataset.target, move: "strike"},
          "War attack");
        break;
      case "war-assist":
        action("assist_war_attack", {attacker_id: element.dataset.attacker},
          "Joined group attack");
        break;
      case "war-dressing":
        action("use_field_dressing", {}, "Field dressing applied");
        break;
      case "war-restore":
        action("cast_war_restoration", {target_id: element.dataset.target},
          "Teammate restored");
        break;
      case "war-milestone":
        requestConfirmation({
          title: "Activate " + element.dataset.power.replaceAll("_", " ") + "?",
          description: "Each war milestone ability can be used only once per war.",
          button: "Activate ability", command: "activate_war_milestone",
          params: {power: element.dataset.power}, success: "Milestone activated"
        });
        break;
      case "guild-leave":
        if (state.guilds?.my_guild) {
          const guild = state.guilds.my_guild;
          guildLeaveIntent = {id: guild.id, lastMember: Object.keys(guild.members).length === 1};
        }
        render(); break;
      case "guild-leave-cancel":
        guildLeaveIntent = null;
        render(); break;
      case "guild-leave-confirm": {
        const confirmation = guildLeaveIntent;
        if (!confirmation) break;
        guildLeaveIntent = null;
        (async () => {
          try {
            const fresh = await request("/api/state");
            state = fresh;
            const guild = fresh.guilds?.my_guild;
            if (!guild || guild.id !== confirmation.id ||
                (Object.keys(guild.members).length === 1) !== confirmation.lastMember) {
              notify("Your guild membership changed; review before leaving.", true);
              render();
              return;
            }
            await action("leave_guild", {}, "Left your guild");
          } catch (error) { notify(error.message, true); render(); }
        })();
        break;
      }
      case "merit-claim":
        action("claim_merit", { achievement: element.dataset.achievement }, "Renown earned"); break;
      case "merit-buy":
        action("buy_merit_upgrade", { perk: element.dataset.perk }, "Permanent improvement unlocked"); break;
      case "church-heal":
        action("church_heal", {}, "The church restores your health"); break;
      case "tavern-room": {
        const t = state?.tavern;
        if (!t?.room_available) break;
        requestConfirmation({
          title: "Rent a room?",
          description: "Pay " + t.room_price + " gold to double Life, Stamina and Mana recovery for 30 game minutes. Available again after 24 game hours.",
          button: "Rent room", command: "rent_tavern_room",
          params: {}, success: "Room rented; recovery doubled"
        });
        break;
      }
      case "tavern-mead":
        if (!state?.tavern?.mead_available) break;
        action("buy_tavern_mead", {}, "Mead purchased"); break;
      case "activity-trade":
        tab = "trade"; render(); break;
      case "activity-duel":
        tab = "duel"; render(); break;
      case "activity-hospital":
        tab = "character"; render(); break;
      case "activity-letters":
        navigateTo("letters");
        render();
        break;
      case "activity-merits":
        navigateTo("merits");
        render();
        break;
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
      case "toggle-password": {
        const id = element.dataset.passwordFor;
        if (!["loginPassword", "registerPassword", "access"].includes(id)) break;
        const input = document.getElementById(id);
        if (!input) break;
        const visible = input.type === "password";
        input.type = visible ? "text" : "password";
        element.setAttribute("aria-pressed", String(visible));
        element.setAttribute("aria-label", visible ? "Hide password" : "Show password");
        element.title = visible ? "Hide password" : "Show password";
        element.classList.toggle("password-visible", visible);
        break;
      }
      case "explore-hex": {
        const x = Number(element.dataset.x), y = Number(element.dataset.y);
        if (isBusy() || !(state.world_map.steps || []).some(t =>
          t.x === x && t.y === y)) break;
        hexIntent = { x, y };
        render();
        const cancel = root.querySelector('[data-ui="hex-travel-cancel"]');
        if (cancel) cancel.focus();
        break;
      }
      case "hex-travel-cancel": hexIntent = null; render(); break;
      case "hex-travel-confirm": {
        const destination = hexIntent;
        if (!destination || isBusy() || !(state.world_map.steps || []).some(t =>
          t.x === destination.x && t.y === destination.y)) {
          hexIntent = null;
          render();
          break;
        }
        hexIntent = null;
        action("explore_hex", destination, "Hex journey started");
        break;
      }
      case "map-zoom-in":
        mapZoom = Math.min(4, Math.round((mapZoom + .5) * 10) / 10);
        forceMapCenter = true; render(); break;
      case "map-zoom-out":
        mapZoom = Math.max(1, Math.round((mapZoom - .5) * 10) / 10);
        forceMapCenter = true; render(); break;
      case "map-center": forceMapCenter = true; render(); break;
      case "travel":
      case "map-travel": {
        const city = state.cities.find(c => c.id === element.dataset.target);
        if (!city || city.is_current || isBusy() ||
            state.player.cargo > state.player.cargo_limit) {
          notify("Travel is unavailable from your current state", true);
          break;
        }
        travelIntent = city.id;
        tab = "world";
        render();
        const cancel = root.querySelector('[data-ui="travel-cancel"]');
        if (cancel) cancel.focus();
        break;
      }
      case "travel-cancel":
        travelIntent = null;
        render();
        break;
      case "travel-confirm": {
        const destination = travelIntent;
        const city = state.cities.find(c => c.id === destination);
        if (!city || city.is_current || destination !== element.dataset.target ||
            isBusy() || state.player.cargo > state.player.cargo_limit) {
          travelIntent = null;
          render();
          notify("Journey details changed; select your destination again", true);
          break;
        }
        travelIntent = null;
        action("travel", { destination }, "Journey started");
        break;
      }
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
      case "retrieve":
      case "discard": {
        const id = (ui === "retrieve" ? "retrieve-" : "store-") + item;
        const input = document.getElementById(id);
        const quantity = Number(input && input.value);
        if (!Number.isSafeInteger(quantity) || quantity <= 0) {
          notify("Enter a positive whole quantity", true); return;
        }
        if (ui === "discard") requestConfirmation({
          title: "Discard goods?",
          description: "Permanently discard " + quantity + " " + pretty(item) + "? This cannot be undone.",
          button: "Discard", command: "discard_goods",
          params: {item, quantity}, success: "Goods discarded"
        });
        else action(ui === "store" ? "store_goods" : "retrieve_goods",
          {item, quantity}, ui === "store" ? "Goods stored" : "Goods retrieved");
        break;
      }
      case "discard-gear": {
        const gearId = Number(element.dataset.gearId);
        if (!Number.isSafeInteger(gearId) || gearId <= 0) break;
        requestConfirmation({
          title: "Discard equipment?", description: "Permanently destroy this piece of equipment? This cannot be undone.",
          button: "Discard", command: "discard_gear",
          params: {gear_id: gearId}, success: "Equipment discarded"
        });
        break;
      }
      case "store-gear":
      case "retrieve-gear": {
        const gearId = Number(element.dataset.gearId);
        if (!Number.isSafeInteger(gearId) || gearId <= 0) {
          notify("Invalid equipment", true); break;
        }
        action(ui === "store-gear" ? "store_gear" : "retrieve_gear",
          { gear_id: gearId },
          ui === "store-gear" ? "Equipment stored" : "Equipment retrieved");
        break;
      }
      case "consume":
        action("consume", { item }, pretty(item) + " used"); break;
      case "contract": action("start_city_contract",
        { contract_id: element.dataset.contract }, "Job initiated"); break;
      case "practice": action("practice_magic", { node_id: node }, "Practice completed"); break;
      case "find-people":
        peopleQuery = document.getElementById("people-query").value.trim();
        render(); break;
      case "search-type":
        peopleQuery = document.getElementById("people-query").value.trim();
        searchScope = element.dataset.scope === "market" ? "market" : "players";
        render(); break;
      case "armory-tab":
        if (["weapons", "armor", "tools"].includes(element.dataset.category)) {
          armoryCategory = element.dataset.category;
          render();
        }
        break;
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
      case "player-attack": {
        if (combatNavigationLocked()) break;
        const target = (state.users || []).find(person =>
          person.id === element.dataset.player && person.can_attack);
        if (!target) { notify("The target is no longer available", true); break; }
        duelPreviewTarget = target.id;
        navigateTo("duel");
        render();
        break;
      }
      case "duel-engage": {
        const target = duelPreviewTarget;
        if (!target || combatNavigationLocked()) break;
        action("engage_duel", { defender_id: target, move: element.dataset.move },
          "Attack resolved");
        break;
      }
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

  async function refreshTravelMap() {
    // Push updates intentionally omit the per-character private map. Fetch
    // only during a visible active journey, not on every background tick.
    if (!state || !state.started ||
        (!state.player.destination && !mapTravelSettlePending) ||
        tab !== "world" || pending || mapPollBusy || offline || authNeeded)
      return;
    const now = Date.now();
    const cadence = state.dev_travel_seconds ? 950 : 2500;
    if (now - lastMapPollAt < cadence) return;
    lastMapPollAt = now;
    mapPollBusy = true;
    try {
      const latest = await request("/api/state");
      if (!state || pending || tab !== "world" || !latest.started) return;
      // Full state replacement is required here: the streamed activity delta
      // never includes private hex discovery, tile data, or trip position.
      if ((latest.activity_revision || 0) >= (state.activity_revision || 0)) {
        state = latest;
        mapTravelSettlePending = false;
        // Keep the persistent topbar DOM and hovered vital tooltip alive.
        // Only repaint the World panel and its scrollable map.
        refreshLiveSurfaces();
        const content = document.getElementById("main-content");
        if (content) {
          const previous = content.querySelector(".terrain-map-scroll");
          const left = previous ? previous.scrollLeft : 0;
          const top = previous ? previous.scrollTop : 0;
          content.innerHTML = renderWorld() + renderWilderness();
          const updated = content.querySelector(".terrain-map-scroll");
          if (updated) {
            const hex = latest.world_map.position.join(",");
            if (hex !== lastMapHex) {
              const player = updated.querySelector(".survey-player");
              if (player) {
                const frame = updated.getBoundingClientRect();
                const point = player.getBoundingClientRect();
                updated.scrollLeft += point.left + point.width / 2 -
                  frame.left - frame.width / 2;
                updated.scrollTop += point.top + point.height / 2 -
                  frame.top - frame.height / 2;
              }
              lastMapHex = hex;
            } else {
              updated.scrollLeft = left;
              updated.scrollTop = top;
            }
          }
        }
      }
    } catch (error) {
      // Transient network failures should not erase an already working map.
    } finally {
      mapPollBusy = false;
    }
  }
  async function refreshFinishedUniversityCourse() {
    if (!universityNeedsRefresh || universityRefreshBusy || pending ||
        !state || !state.started || offline || authNeeded) return;
    universityRefreshBusy = true;
    try {
      const fresh = await request("/api/state");
      if (!state || pending || !fresh.started) return;
      if ((fresh.activity_revision || 0) >= (state.activity_revision || 0)) {
        state = fresh;
        universityNeedsRefresh = false;
        if (tab === "training") render();
        else refreshLiveSurfaces();
      }
    } catch (error) {
      // Keep the refresh flag so a temporary network failure is retried.
    } finally {
      universityRefreshBusy = false;
    }
  }
  document.addEventListener("keydown", event => {
    const hex = event.target.closest('[data-ui="explore-hex"]');
    if (hex && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      hex.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    }
  });
  load();
  setInterval(checkServerConnection, 5000);
  window.addEventListener("online", checkServerConnection);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") checkServerConnection();
  });
  setInterval(() => {
    updateEasternClock();
    updateHoverTimers();
    refreshTravelMap();
    refreshFinishedUniversityCourse();
  }, 1000);
})();
