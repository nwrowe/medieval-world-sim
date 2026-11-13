/* World, market, magic and property pages.
 * Pure markup generation over a read-only, on-demand UI context. No fetch,
 * event listeners or domain mutations live in this module.
 */
export function createWorldViews(ctx) {
  const { esc, pretty, dur, disabled, button, panel, heading,
    isBusy, progress, money } = ctx;


  const sqrt3 = Math.sqrt(3);
  const radius = 8;
  const travelTime = minutes => ctx.getState().dev_travel_seconds ?
    Math.max(0, minutes) + "s" : dur(minutes);
  const biomeColors = {
    ocean: "#799eae", lake: "#83b1bd", grassland: "#b4c889",
    forest: "#628d68", rainforest: "#426b56", taiga: "#749282",
    hills: "#a9a183", mountain: "#938b7d", alpine: "#ded6c4",
    tundra: "#b4c0b5", desert: "#d1bd89", steppe: "#c0bd8f",
    wetland: "#7d9e8a"
  };
  const reliefColors = ["#87999e", "#959c96", "#8a918d", "#858783", "#96948e"];
  function hexCenter(x, y) {
    return [sqrt3 * radius * (x + (y % 2) * .5 + .5),
      radius * (1 + y * 1.5)];
  }
  function points(x, y) {
    const [cx,cy] = hexCenter(x,y);
    return Array.from({length:6},(_,i) => {
      const angle = -Math.PI / 2 + i * Math.PI / 3;
      return (cx + radius * Math.cos(angle)).toFixed(1) + "," +
        (cy + radius * Math.sin(angle)).toFixed(1);
    }).join(" ");
  }
  function worldMap() {
    const state = ctx.getState();
    const atlas = state.world_map;
    if (!atlas) return '<p class="small">The map has not been surveyed.</p>';
    const width = Math.ceil(sqrt3 * radius * (atlas.width + .5));
    const height = Math.ceil(radius * (1.5 * (atlas.height - 1) + 2));
    const tiles = new Map(atlas.tiles.map(t => [t.i,t]));
    const nearbySteps = new Map((atlas.steps || []).map(step =>
      [step.y * atlas.width + step.x, step]));
    const canStep = !state.player.destination && state.player.hp > 0 &&
      state.player.defeated_until == null && !isBusy();
    const hexes = Array.from(atlas.relief, (tier,index) => {
      const x = index % atlas.width, y = Math.floor(index / atlas.width);
      const tile = tiles.get(index);
      const fill = tile ? (biomeColors[tile.biome] || "#abb08f") :
        (reliefColors[Number(tier)] || reliefColors[1]);
      const faded = tile && !tile.visible;
      const caption = tile ? "Hex " + x + "," + y + " — " +
        tile.biome + ", " + tile.elevation_m + " m" :
        "Unexplored terrain";
      const mount = Number(tier) >= 3 ?
        '<path d="M-5 3 L-1 -5 L2 -1 L4 -4 L7 3" fill="none" stroke="' +
        (tile ? "#57584b" : "#737674") + '" stroke-width=".85" opacity=".6"/>' : "";
      const [cx,cy] = hexCenter(x,y);
      const step = canStep && nearbySteps.has(index);
      const attrs = step ? ' data-ui="explore-hex" data-x="' + x +
        '" data-y="' + y + '" tabindex="0" role="button" ' +
        'aria-label="Travel to hex ' + x + ', ' + y + '"' : '';
      return '<g><polygon class="' + (step ? 'hex-step-target' : '') +
        '" points="' + points(x,y) + '" fill="' + fill + '"' + attrs +
        (faded ? ' opacity=".67"' : "") + ' stroke="#e5ddc9" stroke-opacity=".34"' +
        ' stroke-width=".65"><title>' + esc(caption) + '</title></polygon>' +
        (mount ? '<g transform="translate(' + cx.toFixed(1) + ' ' + cy.toFixed(1) +
          ')" pointer-events="none">' + mount + '</g>' : '') + '</g>';
    }).join("");
    const roadlines = atlas.roads.map(pair => {
      const [a,b] = pair;
      const ac = hexCenter(a % atlas.width, Math.floor(a / atlas.width));
      const bc = hexCenter(b % atlas.width, Math.floor(b / atlas.width));
      return '<path d="M' + ac.map(z=>z.toFixed(1)).join(",") + 'L' +
        bc.map(z=>z.toFixed(1)).join(",") + '" />';
    }).join("");
    const sites = atlas.tiles.filter(t=>t.sites && t.sites.length).map(tile => {
      const x = tile.i % atlas.width, y = Math.floor(tile.i / atlas.width);
      const [cx,cy] = hexCenter(x, y);
      const active = canStep && nearbySteps.has(tile.i);
      const attrs = active ? ' data-ui="explore-hex" data-x="' + x +
        '" data-y="' + y + '" role="button" tabindex="0"' : '';
      return '<g class="survey-site-marker' + (active ? ' map-destination' : '') +
        '"' + attrs + '><circle cx="' + cx.toFixed(1) + '" cy="' +
        cy.toFixed(1) + '" r="7" fill="transparent"/>' +
        '<path d="M' + cx.toFixed(1) + ',' + (cy-3.8).toFixed(1) +
        ' l3.8,3.8 l-3.8,3.8 l-3.8,-3.8 z" fill="#83607c" ' +
        'stroke="#e7cf9d" stroke-width="1.1"/><title>' +
        esc(tile.sites.map(site=>site.name).join(", ")) + '</title></g>';
    }).join("");
    const towns = atlas.towns.map(city=>{
      const [x,y] = hexCenter(city.x, city.y);
      const active = canStep && nearbySteps.has(city.y * atlas.width + city.x);
      const attrs = active ? ' data-ui="explore-hex" data-x="' + city.x +
        '" data-y="' + city.y + '" role="button" tabindex="0"' : '';
      return '<g class="survey-city-marker' + (active ? ' map-destination' : '') +
        '"' + attrs + '><circle cx="' + x.toFixed(1) +
        '" cy="' + y.toFixed(1) + '" r="6" fill="#d6b26c" ' +
        'stroke="#483a2d" stroke-width="1.5"/>' +
        '<text x="' + (x+7).toFixed(1) + '" y="' + (y-6).toFixed(1) +
        '" fill="#2d382d" stroke="#e7debb" stroke-width="2" paint-order="stroke"' +
        ' font-family="Georgia,serif" font-size="11">' +
        esc(city.name) + '</text><title>' + esc(city.name) + '</title></g>';
    }).join("");
    const [px,py] = hexCenter(atlas.position[0], atlas.position[1]);
    const zoom = ctx.getMapZoom();
    const svg = '<svg class="terrain-atlas-svg" viewBox="0 0 ' + width + ' ' + height +
      '" width="' + Math.round(width * zoom) + '" height="' +
      Math.round(height * zoom) +
      '" aria-label="Explored hex map with unknown terrain shown in gray">' +
      '<g class="survey-hexes">' + hexes + '</g>' +
      '<g class="survey-roads" fill="none" stroke="#67503a" stroke-width="1.9" ' +
      'stroke-linecap="round" pointer-events="none">' + roadlines + '</g>' +
      '<g class="survey-sites">' + sites + '</g>' +
      '<g class="survey-towns">' + towns + '</g>' +
      '<circle class="survey-player" cx="' + px.toFixed(1) + '" cy="' +
      py.toFixed(1) + '" r="5.5" fill="#fff1ab" stroke="#384d40" stroke-width="2.4">' +
      '<title>Your current position</title></circle></svg>';
    return '<section class="terrain-atlas" aria-label="Oathmere hex exploration map">' +
      '<div class="terrain-map-toolbar">' +
      '<span>Map zoom</span>' +
      button("−", 'data-ui="map-zoom-out" aria-label="Zoom out"'
        + disabled(zoom <= 1), "secondary") +
      '<strong>' + Math.round(zoom * 100) + '%</strong>' +
      button("+", 'data-ui="map-zoom-in" aria-label="Zoom in"'
        + disabled(zoom >= 4), "secondary") +
      button("Center", 'data-ui="map-center"', "secondary") +
      '</div><div class="terrain-map-scroll">' + svg + '</div>' +
      '<div class="terrain-atlas-legend"><span>■ Full color: in sight</span>' +
      '<span>■ Muted color: explored</span><span>■ Gray: uncharted</span>' +
      '<span>Vision radius: ' + atlas.sight_radius + ' hexes</span>' +
      '<span>Explored: ' + Number(atlas.explored_percent).toFixed(1) +
      '%</span><span>' + (atlas.in_wilderness ? 'Exploring wilderness' :
        'In a settlement') + '</span></div>' +
      '<p class="small terrain-map-hint">Click any highlighted land hex within ' +
      'sight, or a previously discovered city or location anywhere on the map. ' +
      'Journeys use the cost of each terrain hex crossed. ' +
      'Return to a town to use markets and other city services.</p></section>';
  }
  function renderHexConfirmation() {
    const state = ctx.getState();
    const target = ctx.getHexIntent();
    if (!state || !target || !state.world_map || state.player.destination) return "";
    const step = (state.world_map.steps || []).find(t =>
      t.x === target.x && t.y === target.y);
    if (!step) return "";
    return '<div class="travel-confirm-overlay" role="presentation">' +
      '<section class="travel-confirm-card" role="dialog" aria-modal="true" ' +
      'aria-labelledby="hex-travel-title" aria-describedby="hex-travel-description">' +
      '<div class="section-kicker">Explore the wilderness</div>' +
      '<h2 id="hex-travel-title">Travel to ' + esc(step.label) + '?</h2>' +
      '<p id="hex-travel-description">Estimated travel time: <strong>' +
      esc(travelTime(step.minutes)) + '</strong>. Every hex along the journey ' +
      'will be explored as you cross it.</p>' +
      '<div class="travel-confirm-actions">' +
      button("Cancel", 'data-ui="hex-travel-cancel"', "secondary") +
      button("Begin journey", 'data-ui="hex-travel-confirm"', "gold") +
      '</div></section></div>';
  }
  function renderTravelConfirmation() {
    const state = ctx.getState();
    const target = ctx.getTravelIntent();
    if (!state || !target) return "";
    const city = state.cities.find(place => place.id === target);
    const p = state.player;
    if (!city || city.is_current || p.destination) return "";
    const blocked = isBusy() || p.cargo > p.cargo_limit;
    const title = city.discovered ? city.name : "Uncharted settlement";
    return '<div class="travel-confirm-overlay" role="presentation">' +
      '<section class="travel-confirm-card" role="dialog" aria-modal="true" ' +
      'aria-labelledby="travel-confirm-title" aria-describedby="travel-confirm-description">' +
      '<div class="section-kicker">Royal roads</div>' +
      '<h2 id="travel-confirm-title">Travel to ' + esc(title) + '?</h2>' +
      '<p id="travel-confirm-description">Estimated journey: <strong>' +
      esc(travelTime(city.minutes)) + '</strong>. You cannot trade, gather, or train while traveling.</p>' +
      '<p class="small">Road cargo: ' + p.cargo + ' / ' + p.cargo_limit +
      (blocked ? ' · Travel is currently unavailable.' : '') + '</p>' +
      '<div class="travel-confirm-actions">' +
      button("Cancel", 'data-ui="travel-cancel"', "secondary") +
      button("Begin journey", 'data-ui="travel-confirm" data-target="' +
        esc(city.id) + '"' + disabled(blocked), "gold") +
      '</div></section></div>';
  }

  function renderWorld() {
    const state = ctx.getState();
    const pending = ctx.getPending();
    const secureWorldClock = ctx.getSecureWorldClock();
    const p = state.player;
    const traveling = Boolean(p.destination);
    const inWilderness = Boolean(state.world_map && state.world_map.in_wilderness);

    const defeated = p.hp <= 0 || p.defeated_until != null;
    const timeToArrival = traveling ? Math.max(1, p.arrival_minute - state.minute) : 0;
    const ready = !traveling && !defeated && state.minute >= p.ready_minute;
    const destinations = state.cities.filter(c => !c.is_current).map(city =>
      '<div class="mini-card"><div class="mini-card-top">' +
      '<div><div class="mini-card-title">' + esc(city.name) + '</div>' +
      '<div class="mini-card-sub">' + esc(travelTime(city.minutes)) +
      (city.discovered ? ' along the royal roads' : ' into uncharted territory') + '</div></div>' +
      '<span class="muted">◈</span></div>' +
      button(city.discovered ? "Travel" : "Explore", 'data-ui="travel" data-target="' + esc(city.id) + '"' +
        disabled(isBusy() || inWilderness || p.cargo > p.cargo_limit), "full secondary") + '</div>'
    ).join("");
    const gathering = Object.entries(state.gatherable).map(([item, available]) => {
      const quantity = Math.min(2, available);
      return '<div class="resource-chip"><div><strong>' + esc(pretty(item)) +
        '</strong><div class="small">' + available + ' nearby</div></div>' +
        button(quantity > 0 ? "Gather " + quantity : "Unavailable", 'data-ui="gather" data-item="' +
          esc(item) + '" data-qty="' + quantity + '"' +
          disabled(!ready || quantity < 1 || pending), "s secondary") + '</div>';
    }).join("") || '<p class="small">No gatherable natural resources remain here; visit a different region.</p>';
    const journey = traveling ?
      '<section class="journey"><div class="section-kicker">Journey in progress</div>' +
      '<h3>' + (p.hex_target ? 'Exploring hex ' + p.hex_target.join(", ") :
        'Road to ' + esc(pretty(p.destination))) + '</h3>' +
      '<p>' + esc(travelTime(timeToArrival)) + ' until arrival. Your purchases and abilities ' +
      'are paused while traveling.</p>' +
      (secureWorldClock ?
        '<p class="small">Arrival is automatic as server time passes.</p>' :
        button("Complete journey", 'data-ui="advance" data-minutes="' + timeToArrival + '"' +
          disabled(pending))) + '</section>'
      : defeated ? '<div class="callout"><strong>Recovering</strong>Rest until your character ' +
        'has recovered before beginning another activity.</div>' : "";
    return heading("", "World Map", "A growing atlas of places you have visited. Venture beyond the familiar roads to lift the fog.") +
      worldMap() +
      (inWilderness ? '<div class="callout"><strong>Wilderness</strong>' +
        'Explore adjacent hexes or return to a settlement for trade, crafting ' +
        'and other town services.</div>' : '') +
      (p.cargo > p.cargo_limit ?
        '<div class="callout"><strong>Travel cargo exceeded</strong>You have ' +
        p.cargo + ' of ' + p.cargo_limit + ' road cargo units. ' +
        'Store extra goods in the city inventory before departure; city storage is unlimited.</div>' : '') +
      '<div class="two-col"><div class="stack">' + journey +
      panel("Roads and destinations", "Follow connected roads to reveal new settlements and terrain.",
        '<div class="card-grid">' + destinations + '</div>') +
      panel("Gather nearby resources", "Collect resources to sell locally or take to another city.",
        '<div class="resource-list">' + gathering + '</div>' +
        (!ready && !traveling ? '<p class="small mt-12">Gathering cooldown: ' +
          Math.max(0, p.ready_minute - state.minute) + ' minutes remaining.</p>' : "")) +
      panel("Time and recovery",
        secureWorldClock ? "World time follows the server clock." :
          "World time advances when you choose to rest or travel.",
        secureWorldClock ?
          '<p>Travel, cooldowns, stamina and mana progress automatically with real time.</p>' :
          '<div class="button-group">' +
          button("Rest 1 hour", 'data-ui="advance" data-minutes="60"' + disabled(pending), "secondary") +
          button("Pass 6 hours", 'data-ui="advance" data-minutes="360"' + disabled(pending), "ghost") +
          button("Next day", 'data-ui="advance" data-minutes="1440"' + disabled(pending), "ghost") +
          '</div><p class="small mt-12">Stamina and mana recover with simulated time.</p>') +
      '</div><aside class="stack">' +
      panel("Exploration and Awareness", "Your discovered map is permanent",
        '<p class="small">The world shows gray elevation relief beyond your sight. ' +
        'Travel opens new hexes along the whole route, and your discoveries stay mapped. ' +
        'Purchase Awareness I and II in Merits to expand your radius from 2 to 3 and 4.</p>' +
        '<p class="small">You can travel to mapped cities or explore the next uncharted ' +
        'road exit. Undiscovered ruins and natural resources are not transmitted ' +
        'to your browser.</p>') +
      '</aside></div>';
  }

  function sellOnlyGoods() {
    const state = ctx.getState();
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
    const state = ctx.getState();
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

  // Visual 100/100 means the SERVER's practice ceiling for that tier,
  // not the earlier eligibility threshold for the next unlock.
  const tierThresholds = [0, 80, 180, 420, 1000];
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
    const state = ctx.getState();
    const node = state.magic_nodes.find(x => x.node_id === outcome.nodeId);
    const schoolName = node ? node.school : outcome.nodeId.split(".")[0];
    const scene = practiceScenes[schoolName] || practiceScenes.divination;
    return '<section class="practice-report" role="status" aria-live="polite">' +
      '<div class="section-kicker">Latest practice · ' + esc(pretty(schoolName)) + '</div>' +
      '<h3>' + esc(node ? node.title : pretty(outcome.nodeId.split(".").pop())) +
      (outcome.success ? ' · Success' : ' · Unsuccessful attempt') + '</h3>' +
      '<p>' + esc(scene.setting + ' ' + (outcome.success ? scene.success : scene.failure)) +
      '</p></section>';
  }

  const schoolIcons = {
    restoration: "✚", divination: "☽", enchantment: "ᚱ",
    warding: "⛨", elemental: "✹", alchemy: "⚗",
  };
  const schoolDescriptions = {
    restoration: "Restoration channels life-giving energy to mend wounds and ease suffering. Skilled healers can return battered adventurers to the road.",
    divination: "Divination studies hidden patterns and possible futures. Its practitioners uncover useful knowledge and eventually improve their journeys.",
    enchantment: "Enchantment binds magical runes to everyday objects. As your skill deepens, you can repair and strengthen the equipment you carry.",
    warding: "Warding shapes protective barriers against danger. Master the art to prepare defenses before a difficult encounter.",
    elemental: "Elemental magic harnesses the forces of fire and matter. Learn to shape energy and turn raw materials into useful resources.",
    alchemy: "Alchemy blends herbs, reagents, and magical techniques into useful preparations. Experienced alchemists can brew remedies from gathered ingredients.",
  };
  function spellRow(node, nodes, p) {
    const state = ctx.getState();
    const mastered = Boolean(node.mastered);
    // Training is limited by the character's mana and the server's mastery
    // rules, never by a separate waiting timer.
    const needed = node.prerequisites.filter(id =>
      !state.magic_nodes.some(n => n.node_id === id && n.unlocked) &&
      id !== "arcane_fundamentals");
    const earlierComplete = node.tier <= 1 ||
      (p.school_xp[node.school] || 0) >= tierThresholds[node.tier - 1];
    const status = node.unlocked ? (
      !node.active ? "Attunement required" :
      node.castable ? "Mastered · Castable" : "Studying · Cast at 100/100") :
      node.eligible ? "Ready to unlock" :
      !earlierComplete ? "Master previous tier to 100/100" :
      needed.length ? "Requires earlier spell" : "Requires Insight";
    let control;
    if (node.unlocked) {
      control = button(mastered ? "Mastered" : "Practice · " + node.mana_cost + " mana",
        'data-ui="practice" data-node="' + esc(node.node_id) + '"' +
        disabled(!node.can_practice || isBusy() || p.mana < node.mana_cost),
        mastered ? "ghost" : "secondary");
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
      esc(status) + '</span></div>' +
      '</div><div class="spell-action">' + control + '</div></div>';
  }
  function renderMagic() {
    const state = ctx.getState();
    const selectedAttunements = ctx.getSelectedAttunements();
    const latestPractice = ctx.getLatestPractice();
    let school = ctx.getSchool();
    const p = state.player;
    if (!state.magic_schools.includes(school)) {
      school = state.magic_schools[0];
      ctx.setSchool(school);
    }
    const all = state.magic_nodes;
    const nodes = all.filter(n => n.school === school);
    const schoolXp = p.school_xp[school] || 0;
    const mastery = masteryTrack(schoolXp);
    const schools = state.magic_schools.map(name => {
      const xp = p.school_xp[name] || 0;
      const track = masteryTrack(xp);
      const learned = all.filter(n => n.school === name && n.castable).length;
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
      '</strong></div>' +
      '<div class="magic-context-stat">✧ ' + p.insight + ' Insight</div></div>' +
      '<p class="magic-school-description">' +
      esc(schoolDescriptions[school] || "") + '</p>' +
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
    const state = ctx.getState();
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


  return { renderWorld, renderTravelConfirmation, renderHexConfirmation,
    renderMarket, renderMagic, renderHome };
}
