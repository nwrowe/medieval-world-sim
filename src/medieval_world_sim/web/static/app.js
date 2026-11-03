/* Medieval World — dependency-free responsive game client.
   Rendering is a read-only projection of server-authoritative world state.
   The browser never calculates gold, travel duration, spell success or ownership.
*/
(() => {
  "use strict";

  const root = document.getElementById("app");
  const tabs = [
    { id: "world", icon: "⚑", title: "Explore" },
    { id: "market", icon: "⚖", title: "Market" },
    { id: "magic", icon: "✧", title: "Magic" },
    { id: "home", icon: "⌂", title: "Property" },
  ];
  let state = null;
  let tab = "world";
  let school = "restoration";
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
    const day = Math.floor(minute / 1440) + 1;
    const hh = String(Math.floor(minute % 1440 / 60)).padStart(2, "0");
    const mm = String(minute % 60).padStart(2, "0");
    return "Day " + day + " · " + hh + ":" + mm;
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
    return '<div class="progress"><span style="width:' +
      (max > 0 ? Math.max(0, Math.min(100, Math.round(value / max * 100))) : 0) +
      '%"></span></div>';
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

  function stat(label, value, extra = "") {
    return '<div class="stat ' + extra + '"><small>' + esc(label) + '</small><strong>' +
      esc(value) + '</strong></div>';
  }
  function shell() {
    const p = state.player;
    const location = state.cities.find(c => c.id === p.city);
    const place = p.destination ? ("En route to " + pretty(p.destination)) :
      (location ? location.name : pretty(p.city));
    const tabsHTML = tabs.map(t => '<button class="tab ' + (tab === t.id ? "active" : "") +
      '" data-tab="' + t.id + '" aria-current="' + (tab === t.id ? "page" : "false") +
      '"><span class="tab-icon">' + t.icon + '</span>' + t.title + '</button>').join("");
    const navHTML = tabs.map(t => '<button class="' + (tab === t.id ? "active" : "") +
      '" data-tab="' + t.id + '" aria-label="' + t.title + '"><span>' + t.icon +
      '</span>' + t.title + '</button>').join("");
    const view = {
      world: renderWorld,
      market: renderMarket,
      magic: renderMagic,
      home: renderHome,
    }[tab];
    return '<div class="shell">' +
      '<header class="topbar"><div class="topbar-inner"><div class="brand">' +
      '<div class="brand-mark">✦</div> MEDIEVAL WORLD</div><div class="world-time">' +
      'THE FIVE CITIES<strong>' + esc(clock(state.minute)) + '</strong></div></div>' +
      '<nav class="tabs" aria-label="Main navigation">' + tabsHTML + '</nav></header>' +
      '<div class="hero"><div class="hero-inner">' +
      '<span class="eyebrow">A living world awaits</span><h1>' + esc(state.name) + '</h1>' +
      '<p class="hero-desc">' + esc(place) +
      ' · Explore the world, build your fortune, and master the arcane.</p>' +
      '<span class="hero-badge">✧ &nbsp; Level ' + p.level +
      ' Adventurer · ' + (p.destination ? "Traveling" : "Ready") + '</span>' +
      '<div class="statbar">' +
      stat("Gold", money(p.gold), "gold") + stat("Health", p.hp + " / " + p.max_hp) +
      stat("Stamina", p.stamina + " / " + p.max_stamina) +
      stat("Mana", p.mana + " / " + p.max_mana) +
      stat("Pack", p.cargo + " / " + p.cargo_limit) + '</div></div></div>' +
      '<main class="page">' + view() + '</main>' +
      '<nav class="bottom-nav" aria-label="Mobile navigation">' + navHTML + '</nav></div>';
  }

  function inventoryPanel() {
    const p = state.player;
    const inventory = Object.entries(p.inventory).filter(([, qty]) => qty > 0).sort();
    let body = inventory.length ? inventory.map(([item, qty]) => (
      '<div class="inventory-row"><span>' + esc(pretty(item)) +
      '</span><strong>× ' + qty + '</strong></div>'
    )).join("") : '<div class="empty">Your pack is empty. Gather resources to start trading.</div>';
    body += '<div class="divider"></div><div class="small">Local capacity: 20 units. ' +
      'Travel capacity: ' + p.cargo_limit + ' units. Equipped gear also takes space.</div>';
    return panel("Your pack", "Items and cargo", body, chip(p.cargo + " items"));
  }
  function activityPanel() {
    let body = state.events.length ? '<ul class="activity">' +
      state.events.map(e => '<li><span>' + esc(e.text) +
      '</span><time>' + esc(clock(e.minute)) + '</time></li>').join("") +
      '</ul>' : '<p class="empty">The chronicle begins with your first action.</p>';
    return panel("Chronicle", "Your most recent actions", body);
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
      const quantity = Math.min(2, available, 20 - p.cargo);
      return '<div class="resource-chip"><div><strong>' + esc(pretty(item)) +
        '</strong><div class="small">' + available + ' nearby</div></div>' +
        button(quantity > 0 ? "Gather " + quantity : "Full", 'data-ui="gather" data-item="' +
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
    return '<div class="heading-row"><div><div class="section-kicker">The open road</div>' +
      '<h2>Explore the realm</h2><p class="subheading">Travel, harvest, and discover new trade routes.</p>' +
      '</div>' + chip(clock(state.minute)) + '</div>' +
      '<div class="two-col"><div class="stack">' + journey +
      panel("Choose your destination", "All routes connect through the royal capital.",
        '<div class="card-grid">' + destinations + '</div>') +
      panel("Gather nearby resources", "Collect resources to sell locally or take to another city.",
        '<div class="resource-list">' + gathering + '</div>' +
        (!ready && !traveling ? '<p class="small" style="margin-top:12px">Gathering cooldown: ' +
          Math.max(0, p.ready_minute - state.minute) + ' minutes remaining.</p>' : "")) +
      panel("Time and recovery", "World time advances when you choose to rest or travel.",
        '<div class="button-group">' +
        button("Rest 1 hour", 'data-ui="advance" data-minutes="60"' + disabled(pending), "secondary") +
        button("Pass 6 hours", 'data-ui="advance" data-minutes="360"' + disabled(pending), "ghost") +
        button("Next day", 'data-ui="advance" data-minutes="1440"' + disabled(pending), "ghost") +
        '</div><p class="small" style="margin-top:12px">Stamina and mana recover with time. ' +
        'The world does not run in real time yet.</p>') +
      '</div><aside class="stack">' + inventoryPanel() + activityPanel() +
      '</aside></div>';
  }

  function renderMarket() {
    const p = state.player;
    const unavailable = isBusy();
    const cards = state.quotes.map(quote => {
      const owned = p.inventory[quote.item] || 0;
      const maxBuy = Math.min(quote.sell_capacity, Math.floor(p.gold / quote.player_buy_price),
        Math.max(0, 20 - p.cargo));
      const maxSell = Math.min(quote.buy_capacity, owned,
        Math.floor(quote.city_gold / quote.player_sell_price));
      return '<div class="market-card"><div class="mini-card-top">' +
        '<h3>' + esc(pretty(quote.item)) + '</h3>' +
        '<span class="inventory-pill">Owned: ' + owned + '</span></div>' +
        '<p class="small" style="margin:0">Merchant stock: ' + quote.stock +
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
        '</div><p class="small" style="margin:0">Available: buy up to ' +
        maxBuy + ', sell up to ' + maxSell + '</p></div>';
    }).join("");
    return '<div class="heading-row"><div><div class="section-kicker">Commerce & opportunity</div>' +
      '<h2>Regional marketplace</h2><p class="subheading">Buying prices differ by city. ' +
      'Carry goods where merchants pay more.</p></div>' + chip(money(p.gold)) + '</div>' +
      '<div class="callout" style="margin-bottom:20px"><strong>Merchant trading</strong>' +
      'Every sale is paid with the city’s existing gold and every purchase uses physical stock. ' +
      'Travel to the producing cities to buy low, then sell at a higher bid elsewhere. ' +
      'Daily limits and availability apply.</div>' +
      '<div class="market-grid">' + cards + '</div>';
  }

  function renderMagic() {
    const p = state.player;
    if (!state.magic_schools.includes(school)) school = state.magic_schools[0];
    const schools = state.magic_schools.map(s =>
      '<button data-school="' + esc(s) + '" class="' + (s === school ? "active" : "") +
      '">' + esc(pretty(s)) + '</button>').join("");
    const nodes = state.magic_nodes.filter(n => n.school === school);
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
    return '<div class="heading-row"><div><div class="section-kicker">The arcane arts</div>' +
      '<h2>Magic progression</h2><p class="subheading">Practice each school independently. ' +
      'Insight unlocks advanced skills.</p></div>' + chip(p.insight + " Insight") + '</div>' +
      '<div class="two-col"><div class="stack">' +
      panel(pretty(school) + " school", "Unlock prerequisites, spend mana, and advance your skill.",
        '<div class="school-tabs">' + schools + '</div>' +
        '<div class="callout" style="margin-bottom:14px"><strong>Practice-only prototype</strong>' +
        'Skills currently award XP, not paid contracts or spell effects. Those features will use ' +
        'this progression tree later.</div>' +
        '<div class="magic-track">' + list + '</div>') +
      '</div><aside class="stack">' +
      panel("Your arcane studies", "Mana regenerates as world time advances.",
        '<div class="mini-card-top"><strong>Mana</strong><strong>' + p.mana +
        ' / ' + p.max_mana + '</strong></div>' + progress(p.mana, p.max_mana) +
        '<div class="divider"></div><div class="mini-card-top"><strong>School experience</strong>' +
        '<strong>' + (p.school_xp[school] || 0) + ' XP</strong></div>' +
        progress(p.school_xp[school] || 0, 350) +
        '<p class="small" style="margin:13px 0 0">Basic practice eventually stops granting XP. ' +
        'Higher-tier studies unlock additional progression.</p>') +
      panel("Active specializations", "Select at most two advanced branches. Changing your ' +
        'selection has a six-hour in-game cooldown.",
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
        '<p class="small" style="margin:0">Roads: ' + v.road_time_percent +
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
    return '<div class="heading-row"><div><div class="section-kicker">A place to call your own</div>' +
      '<h2>Homes & transportation</h2><p class="subheading">Upgrade your home, train more ' +
      'efficiently, and travel faster.</p></div>' + chip(money(p.gold)) + '</div>' +
      (h.tier ? '<div class="home-banner" style="margin-bottom:20px">' +
        '<small>Your home · ' + esc(pretty(h.city)) + '</small>' +
        '<h3>' + esc(pretty(h.tier)) + '</h3>' +
        '<p>+' + h.training_bonus_pct + '% local training XP · ' +
        (h.active_vehicle ? esc(pretty(h.active_vehicle)) + ' ready' : "Traveling on foot") +
        '</p></div>' :
        '<div class="callout" style="margin-bottom:20px"><strong>Invest in your future</strong>' +
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
          '<div style="margin-top:13px">' + button("Park and walk",
            'data-ui="select-vehicle" data-vehicle=""' + disabled(!atHome), "ghost") +
          '</div>' : "")) +
      '</div>';
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
      case "travel": action("travel", { destination: element.dataset.target }, "Journey started"); break;
      case "gather": action("gather", { item, quantity: Number(element.dataset.qty) },
        "Resources added to your pack"); break;
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
      default: break;
    }
  });

  load();
})();
