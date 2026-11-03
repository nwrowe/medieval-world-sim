/* Medieval World — dependency-free responsive game client.
   Rendering is a read-only projection of server-authoritative world state.
   The browser never calculates gold, travel duration, spell success or ownership.
*/
(() => {
  "use strict";

  const root = document.getElementById("app");
  const tabs = [
    { id: "city", icon: "⌘", title: "City Map" },
    { id: "world", icon: "⚑", title: "World Map" },
    { id: "market", icon: "⚖", title: "Market" },
    { id: "magic", icon: "✧", title: "Magic" },
    { id: "home", icon: "⌂", title: "Property" },
    { id: "job", icon: "▣", title: "Job" },
    { id: "inventory", icon: "◫", title: "Inventory" },
    { id: "training", icon: "✤", title: "Training Hall" },
  ];
  const accountTabs = [
    { id: "character", icon: "♙", title: "Home" },
    { id: "equipment", icon: "⚔", title: "Equipment" },
    { id: "chronicle", icon: "▤", title: "Chronicle" },
    { id: "people", icon: "⌕", title: "Players" },
  ];
  const cityLore = {
    goldmeadow: {
      title: "Where the road begins",
      opening: "Morning bells drift across the grain fields of Goldmeadow. The gates stand open, traders argue over their loads, and a notice board promises honest pay to anyone brave enough to seek it.",
      district: "Market lanes and farmsteads",
    },
    crownreach: {
      title: "Under the royal banners",
      opening: "The capital's stone gates open onto busy merchant streets. Armor rings from the smiths' quarter, and messengers hurry toward the guild halls with sealed contracts.",
      district: "Royal market and guild quarter",
    },
    ironvale: {
      title: "Where iron meets ambition",
      opening: "Mine carts creak below Ironvale's steep walls. The forge smoke never settles, and a traveler can earn a name here as quickly as a wage.",
      district: "The foundries and northern gates",
    },
    emberfall: {
      title: "A city of fire and stone",
      opening: "Orange light spills from Emberfall's furnaces long after sunset. Quarrymen and merchants share stories of dangerous roads beyond the city walls.",
      district: "The quarry district",
    },
    greenhollow: {
      title: "Between forest and stone",
      opening: "In Greenhollow, timber wagons roll beneath ancient trees. Herbalists barter at the crossroads and the old paths invite both curiosity and caution.",
      district: "Forest markets and herbal gardens",
    },
  };
  let state = null;
  let tab = "city";
  let school = "restoration";
  let latestPractice = null;
  let latestContract = null;
  let peopleQuery = "";
  let pending = false;
  let authNeeded = false;
  let offline = false;
  let selectedAttunements = new Set();
  let token = sessionStorage.getItem("medieval-world-token") || "";

  function esc(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
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
  function isBusy() {
    return pending || !state || !state.started ||
      Boolean(state.player.destination) || state.player.hp <= 0;
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
      '</h3><p>' + esc(sub) + '</p></div>' + extra + '</div>' + body + '</section>';
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
    const headers = { "X-Game-Token": token };
    const options = { method: body === undefined ? "GET" : "POST", headers };
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
      state = await request("/api/state");
      syncAttunements();
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
      state = result.state;
      syncAttunements();
      if (body && body.action === "practice_magic" && result.result) {
        latestPractice = { ...result.result, nodeId: body.params.node_id };
        tab = "magic";
      }
      if (body && body.action === "complete_city_contract" && result.result) {
        latestContract = result.result;
      }
      notify(success);
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
    return send("/api/advance", { minutes: Number(minutes) }, "World time advanced");
  }

  function authPage() {
    return '<div class="entry"><div class="entry-card">' +
      '<div class="entry-seal">✦</div><div class="eyebrow">Private local world</div>' +
      '<h1>Enter the city gates</h1>' +
      '<p>This server requires the access code printed in its terminal. ' +
      'Only connect over your own trusted local network.</p>' +
      '<form id="accessForm"><label class="sr" for="access">Access code</label>' +
      '<input id="access" class="field" type="password" autocomplete="off" placeholder="Server access code" required>' +
      '<button class="button full" type="submit">Enter world</button></form></div></div>';
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
      '<div class="vital-caption"><span>' + esc(label) + '</span><strong>' +
      v + '/' + maximum + '</strong></div>' +
      '<progress value="' + Math.max(0, Math.min(maximum, v)) +
      '" max="' + maximum + '" aria-label="' + esc(label) + '"></progress></div>';
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
      (location ? location.name : pretty(p.city));
    const renderers = {
      city: renderCity, world: renderWorld, market: renderMarket,
      magic: renderMagic, home: renderHome, job: renderJob,
      inventory: renderInventory, training: renderTraining,
      character: renderCharacter, equipment: renderEquipment,
      chronicle: renderChronicle, warriors: renderWarriorsGuild,
      mageguild: renderMageGuild, tavern: renderTavern,
      healer: renderHealer, cityhall: renderCityHall,
      church: renderChurch, people: renderPeople,
    };
    const view = renderers[tab] || renderCity;
    const sidebar = tabs.map(t => navButton(t)).join('');
    const topLinks = accountTabs.map(t => navButton(t, "account-button")).join('');
    return '<div class="shell">' +
      '<header class="topbar"><div class="topbar-inner">' +
      '<div class="brand"><div class="brand-mark">✦</div><span>MEDIEVAL WORLD</span></div>' +
      '<div class="statbar" aria-label="Character vitals">' +
      meterStat("Health", p.hp, p.max_hp, "health", p.health_next_sim_seconds) +
      meterStat("Stamina", p.stamina, p.max_stamina, "stamina", p.stamina_next_sim_seconds) +
      meterStat("Mana", p.mana, p.max_mana, "mana", p.mana_next_sim_seconds) +
      '<div class="gold-total"><small>Gold</small><strong>' +
      esc(money(p.gold)) + '</strong></div></div>' +
      '<div class="top-actions">' +
      '<div class="world-time"><span>Medieval World time</span>' +
      '<strong id="eastern-clock">' + esc(easternNow()) + '</strong></div>' +
      '<nav class="account-nav" aria-label="Character menu">' + topLinks + '</nav>' +
      '</div></div></header>' +
      '<div class="workspace">' +
      '<aside class="sidebar" aria-label="Locations and services">' +
      '<div class="sidebar-place"><small>Current location</small><strong>' +
      esc(place) + '</strong><span>' + (p.destination ? "On the road" : "Inside the city walls") +
      '</span></div><div class="sidebar-label">Places & services</div>' +
      '<nav class="side-nav" aria-label="Location navigation">' + sidebar + '</nav>' +
      '<div class="sidebar-foot">One world, five cities. Your choices make the story.</div>' +
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
  function activityPanel() {
    let body = state.events.length ? '<ul class="activity">' +
      state.events.map(e => '<li><span>' + esc(e.text) +
      '</span><time title="Simulation elapsed: ' + esc(clock(e.minute)) +
      '">' + esc(eventTime(e)) + '</time></li>').join("") +
      '</ul>' : '<p class="empty">The chronicle begins with your first action.</p>';
    return panel("Chronicle", "Your most recent actions", body);
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
        '<p class="small m-0">Merchant stock: ' + quote.stock +
        ' · City gold: ' + money(quote.city_gold) + '</p>' +
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
        '</div><p class="small m-0">Available: buy up to ' +
        maxBuy + ', sell up to ' + maxSell + '</p></div>';
    }).join("");
    return heading("", "Market", "Trade using the current city's real stock and gold.") +
      '<div class="callout mb-20"><strong>Local market · ' + p.cargo +
      ' carried · Road limit ' + p.cargo_limit + '</strong>' +
      'You can own any quantity of goods in a city. Travel requires loading no more ' +
      'than your vehicle can carry. The city pays from its existing gold and ' +
      'merchants only sell real stock.</div>' +
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

  function renderMagic() {
    const p = state.player;
    if (!state.magic_schools.includes(school)) school = state.magic_schools[0];
    const schools = state.magic_schools.map(s =>
      '<button data-school="' + esc(s) + '" class="' + (s === school ? "active" : "") +
      '">' + esc(pretty(s)) + '</button>').join("");
    const nodes = state.magic_nodes.filter(n => n.school === school);
    const schoolXp = p.school_xp[school] || 0;
    const mastery = masteryTrack(schoolXp);
    const tierBoxes = [1,2,3,4].map(tier => {
      const floor = tierThresholds[tier - 1], ceiling = tierThresholds[tier];
      const rank = Math.min(100, Math.max(0,
        Math.floor((schoolXp - floor) / (ceiling - floor) * 100)));
      return '<div class="tier-box ' + (tier === mastery.tier ? 'active' : '') +
        '"><small>Tier ' + tier + '</small><strong>' +
        (schoolXp >= ceiling ? '100' : rank) + '/100</strong>' +
        progress(Math.max(0, rank), 100) + '</div>';
    }).join("");
    const list = nodes.map(node => {
      const canUse = !isBusy();
      let controls = "";
      if (node.unlocked) {
        controls = button("Practice · " + node.mana_cost + " mana",
          'data-ui="practice" data-node="' + esc(node.node_id) + '"' +
          disabled(!canUse || !node.active || p.mana < node.mana_cost),
          node.active ? "" : "ghost");
      } else {
        controls = button(node.eligible ? "Unlock" : "Locked",
          'data-ui="unlock" data-node="' + esc(node.node_id) + '"' +
          disabled(!canUse || !node.eligible), node.eligible ? "gold" : "ghost");
      }
      return '<div class="magic-node ' + (!node.unlocked ? "locked" : "") + '">' +
        '<div><span class="tier">Tier ' + node.tier +
        (node.active ? ' · Active' : node.unlocked ? ' · Learned' : ' · Locked') +
        '</span><h3>' + esc(node.title) + '</h3><p>' + esc(pretty(node.role)) +
        ' · ' + node.required_xp + ' school XP · ' + node.insight_cost + ' Insight' +
        (node.prerequisites.length ? '<br>Requires: ' +
          esc(node.prerequisites.map(id => pretty(id.split(".").pop())).join(", ")) : '') +
        '</p></div>' + controls + '</div>';
    }).join("");
    const specialist = state.magic_nodes.filter(n => n.tier === 3 && n.unlocked);
    const checkboxes = specialist.length ? specialist.map(n =>
      '<div class="specialist"><label><input type="checkbox" data-attune="' +
      esc(n.node_id) + '"' + (selectedAttunements.has(n.node_id) ? " checked" : "") +
      '><div><strong>' + esc(n.title) + '</strong>' +
      '<div class="small">' + esc(pretty(n.school)) + ' · also enables its Tier IV mastery</div>' +
      '</div></label></div>').join("") :
      '<p class="small">Unlock Tier III skills to choose your two active specializations.</p>';
    return heading("", "Magic Progression", "") +
      '<div class="school-banner"><div><small>ARCANE DISCIPLINE</small><h3>' +
      esc(pretty(school)) + '</h3><p>Progress through four tiers of study. ' +
      'Unlocking a spell also requires Insight and prerequisite knowledge.</p></div>' +
      '<div class="insight-badge">' + p.insight + ' Insight</div></div>' +
      '<div class="school-tabs">' + schools + '</div>' +
      '<div class="tier-track">' + tierBoxes + '</div>' +
      (latestPractice ? practiceStory(latestPractice) : '') +
      '<div class="two-col"><div class="stack">' +
      panel("Study & abilities", "Your unlocked spells, branches and prerequisites",
        '<div class="magic-track">' + list + '</div>') +
      '</div><aside class="stack">' +
      panel("Your studies", "Existing school progression",
        characterRow("Mana", p.mana + " / " + p.max_mana) +
        characterRow("School experience", schoolXp + " XP") +
        characterRow("Mastery progress", "Tier " + mastery.tier + " · " +
          mastery.rank + "/100") +
        '<p class="small mt-13">The 100-step tier meters summarize existing XP; ' +
        'they do not add new levels or change unlock conditions. Basic practice ' +
        'eventually stops granting experience, so more advanced spells matter.</p>') +
      panel("Active specializations", "Select at most two advanced branches. Changing your " +
        "selection has a six-hour in-game cooldown.",
        '<p class="small">Active: ' + p.attuned_paths.length + ' / 2</p>' +
        checkboxes + button("Apply specializations",
          'data-ui="apply-attune"' + disabled(isBusy() || !specialist.length),
          "full secondary")) + '</aside></div>';
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
  function cityLocation(icon, title, description, target, badge = "") {
    return '<div class="location-card"><span class="location-icon">' + icon + '</span>' +
      '<div><h3>' + esc(title) + '</h3><p>' + esc(description) + '</p>' +
      (badge ? '<span class="location-badge">' + esc(badge) + '</span>' : '') +
      '</div>' + button("Enter", 'data-tab="' + esc(target) + '"', "s secondary") + '</div>';
  }
  function renderCity() {
    const p = state.player;
    const lore = cityLore[p.city] || cityLore.goldmeadow;
    const city = state.cities.find(c => c.id === p.city);
    const name = city ? city.name : pretty(p.city);
    const locations = [
      cityLocation("⚖", "Marketplace", "Buy and sell goods using the local city's real gold and stock.", "market", "Open"),
      cityLocation("⚔", "Warriors Guild", "Future: earn coin through escorted caravans, patrols, and bounty contracts.", "warriors", "Contracts planned"),
      cityLocation("✧", "Mage Guild", "Study six schools today. Arcane commissions and investigations are planned.", "mageguild", "Studies open"),
      cityLocation("⚒", "Armory & Blacksmith", "Manage your weapons and armor. Crownreach stocks basic equipment.", "equipment", "Equipment open"),
      cityLocation("✚", "Healer\'s Sanctuary", "Future: treatment, healing provisions, and restorative services.", "healer", "Healing planned"),
      cityLocation("✝", "Church of the Hearth", "A chapel for reflection and future restorative service and charity contracts.", "church", "Services planned"),
      cityLocation("♛", "City Hall", "Future: civic standing, records, permits, and city affairs.", "cityhall", "Civic features planned"),
      cityLocation("▣", "Employment Hall", "Browse jobs, employers, and eventually shift-based work.", "job", "Jobs planned"),
      cityLocation("✤", "Training Hall", "Future: long-term discipline, scholarship, and stat training.", "training", "Training planned"),
      cityLocation("⌂", "Homes & Stables", "Purchase a residence, improve it, and select faster travel.", "home", "Open"),
      cityLocation("♜", "The Wayfarer's Tavern", "Rest to recover stamina and mana and let world time pass.", "tavern", "Open"),
      cityLocation("⚑", "The City Gates", "Leave the walls to gather resources or choose a road to another city.", "world", "Open"),
    ].join('');
    return heading("", "City Map", "") +
      '<section class="story-panel"><div class="section-kicker">Chapter I · A stranger at the gate</div>' +
      '<h3>' + esc(lore.title) + '</h3><p>' + esc(lore.opening) + '</p>' +
      '<p>You have a name, ' + esc(money(p.gold)) +
      ', and few obligations. The city offers many doors; which one will you open?</p>' +
      '<small>Story introduction · Narrative quests and choices are planned, not yet active.</small></section>' +
      panel("Streets & districts", lore.district,
        '<div class="location-grid">' + locations + '</div>');
  }
  function renderPeople() {
    const users = (state.users || []).filter(person =>
      person.name.toLowerCase().includes(peopleQuery.toLowerCase()));
    const cards = users.map(person =>
      '<div class="equipment-item"><div><h3>' + esc(person.name) +
      '</h3><p>' + esc(pretty(person.city)) + ' · Level ' + person.level +
      (person.id === "hero" ? ' · You' : '') + '</p></div>' +
      button(person.id === "hero" ? "Your character" : "Attack",
        'data-ui="player-attack" data-player="' + esc(person.id) + '"' +
        disabled(person.id === "hero" || !state.multiplayer || isBusy()),
        "secondary") + '</div>').join("") || '<p class="empty">No matching players.</p>';
    return heading("", "Find Players", "") +
      '<div class="search-panel"><label for="people-query">Search player names</label>' +
      '<div class="button-group"><input id="people-query" class="field" ' +
      'type="search" maxlength="28" placeholder="Character name" value="' +
      esc(peopleQuery) + '">' +
      button("Search", 'data-ui="find-people"', "secondary") + '</div></div>' +
      panel("Player directory", "Current server accounts", cards) +
      '<p class="small mt-13">This server currently hosts one shared single-player character. ' +
      'The player directory is genuine, but PvP will require persistent separate ' +
      'user accounts, authenticated sessions and multiplayer combat. ' +
      'No attack is possible against yourself.</p>';
  }

  function renderInventory() {
    return heading("Belongings", "Inventory",
      "Own any amount in town; road travel has a cargo limit.") +
      '<div class="two-col"><div class="stack">' + inventoryPanel() +
      '</div><aside class="stack">' +
      panel("Trading & travel", "Inventory and vehicle limits",
        '<p class="small">Carried goods have quantity and occupy inventory capacity. ' +
        'A horse or carriage can increase your travel limit.</p>' +
        button("Visit Market", 'data-tab="market"', "secondary") + ' ' +
        button("Equipment", 'data-tab="equipment"', "ghost")) +
      '</aside></div>';
  }
  function renderChronicle() {
    return heading("", "Chronicle", "") +
      activityPanel() +
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
    return '<div class="profile-hero"><div><small>ADVENTURER</small><h3>' + esc(state.name) +
      '</h3><p>Level ' + p.level + ' · ' + esc(pretty(p.city)) + '</p></div>' +
      '<div><small>Estimated net worth</small><strong>' +
      esc(money(state.net_worth_estimate)) + '</strong></div></div>' +
      '<div class="profile-grid">' +
      panel("Life & progress", "Current character state",
        characterRow("Level", p.level) +
        characterRow("Experience toward next level", p.level_xp + " / " + xpNext) +
        characterRow("Health", p.hp + " / " + p.max_hp) +
        characterRow("Stamina", p.stamina + " / " + p.max_stamina) +
        characterRow("Mana", p.mana + " / " + p.max_mana) +
        characterRow("Days played (simulated)", state.days_played) +
        characterRow("Elapsed world time", clock(state.minute))) +
      panel("Combat attributes", "Base fighter progression",
        characterRow("Strength", p.strength) +
        characterRow("Defense", p.defense) +
        characterRow("Combat experience", p.combat_xp + " XP") +
        button("Equipment", 'data-tab="equipment"', "secondary mt-13")) +
      panel("Work attributes", "Experience from employment and future training",
        characterRow("Manual", w.manual) +
        characterRow("Intelligence", w.intelligence) +
        characterRow("Endurance", w.endurance) +
        characterRow("Completed shifts", w.shifts) +
        (career || '<p class="small">No occupational experience yet.</p>') +
        button("Job", 'data-tab="job"', "secondary mt-13")) +
      panel("Assets & studies", "Personal wealth and growth",
        characterRow("Gold", money(p.gold)) +
        characterRow("Estimated net worth", money(state.net_worth_estimate)) +
        characterRow("Residence", homeName) +
        characterRow("Insight", p.insight) +
        (study || '<p class="small">You have yet to practice magic.</p>') +
        '<p class="small mt-13">Net worth estimates held assets; it is not liquid gold. ' +
        'Raw goods use local resale bids, and equipment uses appraised value.</p>') +
      '</div>';
  }
  function renderEquipment() {
    const p = state.player;
    const owned = state.gear || [];
    const equipped = state.equipped || {};
    const slots = ["weapon", "offhand", "body", "tool"];
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
    const inCapital = p.city === "crownreach" && !p.destination;
    const catalog = (state.equipment_catalog || []).map(item =>
      '<div class="inventory-row"><span>' + esc(pretty(item.kind)) +
      ' · ' + esc(pretty(item.slot)) + '</span>' +
      button("Buy · " + money(item.price),
        'data-ui="buy-starter" data-kind="' + esc(item.kind) + '"' +
        disabled(!inCapital || isBusy() || p.gold < item.price),
        "s secondary") + '</div>').join('');
    return heading("Armory", "Equipment",
      "Manage your character's real combat gear and active slots.") +
      '<div class="two-col"><div class="stack">' +
      panel("Equipped gear", "Active slots", slotRows) +
      panel("Owned equipment", "Switch equipment when in a city", gearRows) +
      '</div><aside class="stack">' +
      panel("Crownreach armory", "Basic equipment is sold only in the capital",
        '<p class="small">' + (inCapital ? "Starter stock is available." :
          "Travel to Crownreach to purchase starter equipment.") + '</p>' +
        catalog) +
      '</aside></div>';
  }
  function futurePage(kicker, title, narrative, next, label, nested = false) {
    return (nested ? "" : heading("", title, "")) +
      '<section class="story-panel"><div class="section-kicker">Coming chapter</div>' +
      '<h3>' + esc(title) + '</h3><p>' + esc(narrative) + '</p>' +
      '<p class="small">This location is planned. It cannot yet award gold, XP, ' +
      'contracts, or equipment.</p>' + button(label, 'data-tab="' + esc(next) + '"',
        "secondary") + '</section>';
  }
  function renderWarriorsGuild() {
    return futurePage("Guild quarter", "Warriors Guild",
      "The hall smells of worn leather and oiled steel. A contract board stands behind the steward: caravan escort, city patrol, and bounty work will eventually offer paid combat missions.",
      "equipment", "Prepare equipment");
  }
  function renderMageGuild() {
    return heading("Guild quarter", "Mage Guild", "Scholarship, spellcraft and future commissions.") +
      '<section class="story-panel"><div class="section-kicker">The six schools</div>' +
      '<h3>The keeper of the archives</h3><p>The archmage studies your arrival without surprise. ' +
      'There is room for another apprentice, but first there are six disciplines to learn.</p>' +
      '<p class="small">School study is available now. Paid magical contracts and spell effects ' +
      'are planned for later.</p>' +
      button("Study magic", 'data-tab="magic"', "secondary") + '</section>';
  }
  function renderHealer() {
    return futurePage("The temple district", "Healer's Sanctuary",
      "Beneath a quiet stone arch, healers tend weary travelers. Treatment, restorative remedies, and related costs will eventually be real simulation systems.",
      "city", "Return to City Map");
  }
  function renderChurch() {
    return heading("", "Church of the Hearth", "") +
      '<section class="story-panel"><h3>The candlelit nave</h3>' +
      '<p>Quiet footsteps echo beneath the stone arches. Healers and petitioners ' +
      'gather here, asking aid and sharing news from the roads. A novice invites ' +
      'you to study the arts of restoration.</p>' +
      '<p class="small">Church services, charitable assignments, and paid healing ' +
      'contracts are planned. No gold is earned merely by visiting.</p>' +
      button("Study restoration", 'data-ui="study-restoration"', "secondary") + '</section>';
  }
  function renderCityHall() {
    return futurePage("The civic quarter", "City Hall",
      "A clerk maintains ledgers of the city's merchants, residents and obligations. Permits, civic reputation, and faction affairs may someday be managed here.",
      "city", "Return to City Map");
  }
  function renderJob() {
    const w = state.player.work;
    return heading("The city's livelihoods", "Job",
      "Employment, wages and long-term professions.") +
      '<div class="two-col"><div class="stack">' +
      futurePage("Employment Hall", "Contracts & employers",
        "Merchants seek porters, the foundries need laborers, and inns always need hands. A future jobs board will show real employers, wages, shift requirements and experience.",
        "city", "Return to City Map", true) +
      '</div><aside class="stack">' +
      panel("Your work record", "Authoritative work attributes",
        characterRow("Manual", w.manual) +
        characterRow("Intelligence", w.intelligence) +
        characterRow("Endurance", w.endurance) +
        characterRow("Shifts completed", w.shifts)) +
      '</aside></div>';
  }
  function renderTraining() {
    const w = state.player.work;
    return heading("Learning for a lifetime", "Training Hall",
      "Planned courses will improve work and combat attributes over time.") +
      '<div class="two-col"><div class="stack">' +
      futurePage("The old university", "Training & scholarship",
        "A hall for tutors, scholars and veteran soldiers. Future courses will take time and money, with clear progression rules and different paths for intellect, labor and warfare.",
        "magic", "Practice magic now", true) +
      '</div><aside class="stack">' +
      panel("Current disciplines", "Baseline work attributes",
        characterRow("Manual", w.manual) +
        characterRow("Intelligence", w.intelligence) +
        characterRow("Endurance", w.endurance)) +
      '</aside></div>';
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

  function render() {
    if (authNeeded) root.innerHTML = authPage();
    else if (offline) root.innerHTML = offlinePage();
    else if (state && !state.started) root.innerHTML = newCharacterPage();
    else if (state && state.started) root.innerHTML = shell();
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
    }
  });

  root.addEventListener("change", event => {
    const path = event.target.getAttribute("data-attune");
    if (!path) return;
    if (event.target.checked) selectedAttunements.add(path);
    else selectedAttunements.delete(path);
  });

  root.addEventListener("click", event => {
    const element = event.target.closest("button");
    if (!element || pending || element.disabled) return;
    if (element.dataset.tab) {
      tab = element.dataset.tab;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (element.dataset.school) {
      school = element.dataset.school;
      render();
      return;
    }
    const ui = element.dataset.ui;
    const item = element.dataset.item;
    const node = element.dataset.node;
    switch (ui) {
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
      case "practice": action("practice_magic", { node_id: node }, "Practice completed"); break;
      case "find-people":
        peopleQuery = document.getElementById("people-query").value.trim();
        render(); break;
      case "player-attack":
        notify("PvP requires multiple authenticated accounts; only this character exists.", true); break;
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
