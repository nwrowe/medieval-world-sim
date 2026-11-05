/* World, market, magic and property pages.
 * Pure markup generation over a read-only, on-demand UI context. No fetch,
 * event listeners or domain mutations live in this module.
 */
export function createWorldViews(ctx) {
  const { esc, pretty, dur, disabled, button, panel, heading,
    isBusy, progress, money } = ctx;

  const mapLocations = {
    crownreach: { x: 50, y: 47.6 },
    ironvale: { x: 33.3, y: 27.6 },
    greenhollow: { x: 71.1, y: 33.2 },
    emberfall: { x: 65.0, y: 69.4 },
    goldmeadow: { x: 30.6, y: 78.5 },
  };
  function worldMap() {
    const state = ctx.getState();
    const pending = ctx.getPending();
    const p = state.player;
    const destination = p.destination;
    // The underlying atlas remains a fixed image. Server-owned discovery
    // determines what can be seen; the player cannot reveal places by UI state.
    const fogHoles = state.cities.filter(city => city.discovered || city.is_current).map(city => {
      const point = mapLocations[city.id];
      return point ? '<circle cx="' + (point.x * 10) + '" cy="' +
        (point.y * 6.2) + '" r="145" fill="url(#atlas-clearing)"/>' : '';
    }).join('');
    const fog = '<svg class="atlas-fog" viewBox="0 0 1000 620" preserveAspectRatio="none" ' +
      'aria-hidden="true"><defs><radialGradient id="atlas-clearing">' +
      '<stop offset="0%" stop-color="black"/>' +
      '<stop offset="63%" stop-color="black"/>' +
      '<stop offset="100%" stop-color="white"/></radialGradient>' +
      '<mask id="atlas-discovery"><rect width="1000" height="620" fill="white"/>' +
      fogHoles + '</mask></defs><rect width="1000" height="620" ' +
      'fill="#26362e" opacity=".94" mask="url(#atlas-discovery)"/></svg>';
    const pins = state.cities.map(city => {
      const point = mapLocations[city.id];
      if (!point) return "";
      const current = city.id === p.city;
      const arriving = city.id === destination;
      const inactive = pending || Boolean(destination) || p.hp <= 0 ||
        p.defeated_until != null || current;
      return '<button class="map-pin map-' + esc(city.id) +
        (current ? ' is-here' : '') + (arriving ? ' is-destination' : '') +
        (!city.discovered && !current ? ' is-unexplored' : '') +
        '" type="button" data-ui="map-travel" data-target="' + esc(city.id) +
        '" title="' + esc(city.name) +
        (current ? " — you are here" : arriving ? " — destination" :
          " — " + dur(city.minutes) + " away, click to explore") +
        '"' + disabled(inactive) + '>' +
        '<span class="map-pin-light"></span><strong>' + esc(city.name.replace(" (capital)", "")) +
        '</strong>' + (current ? '<small>You are here</small>' :
        arriving ? '<small>Destination</small>' : '') + '</button>';
    }).join("");
    return '<section class="world-atlas" aria-label="Illustrated map of the Five Cities">' +
      '<div class="atlas-canvas"><img src="/world-map.svg" alt="Antique ink-drawn fantasy realm with mountains, rivers, forests and royal roads">' +
      fog + pins + '</div><div class="atlas-footer"><span>✦ The golden light marks your location</span>' +
      '<span>Uncharted places emerge when you reach them</span></div></section>';
  }

  function renderWorld() {
    const state = ctx.getState();
    const pending = ctx.getPending();
    const secureWorldClock = ctx.getSecureWorldClock();
    const p = state.player;
    const traveling = Boolean(p.destination);
    const defeated = p.hp <= 0 || p.defeated_until != null;
    const timeToArrival = traveling ? Math.max(1, p.arrival_minute - state.minute) : 0;
    const ready = !traveling && !defeated && state.minute >= p.ready_minute;
    const destinations = state.cities.filter(c => !c.is_current).map(city =>
      '<div class="mini-card"><div class="mini-card-top">' +
      '<div><div class="mini-card-title">' + esc(city.name) + '</div>' +
      '<div class="mini-card-sub">' + esc(dur(city.minutes)) +
      (city.discovered ? ' along the royal roads' : ' into uncharted territory') + '</div></div>' +
      '<span class="muted">◈</span></div>' +
      button(city.discovered ? "Travel" : "Explore", 'data-ui="travel" data-target="' + esc(city.id) + '"' +
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
      (secureWorldClock ?
        '<p class="small">Arrival is automatic as server time passes.</p>' :
        button("Complete journey", 'data-ui="advance" data-minutes="' + timeToArrival + '"' +
          disabled(pending))) + '</section>'
      : defeated ? '<div class="callout"><strong>Recovering</strong>Rest until your character ' +
        'has recovered before beginning another activity.</div>' : "";
    return heading("", "World Map", "A growing atlas of places you have visited. Venture beyond the familiar roads to lift the fog.") +
      worldMap() +
      '<div class="two-col"><div class="stack">' + journey +
      panel("Roads and unexplored settlements", "Travel to a location to add it to your personal atlas.",
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
      panel("Roads of the Five Cities", "Current road network",
        '<div class="route-map"><strong>✦ Crownreach</strong>' +
        state.cities.filter(city => city.id !== 'crownreach').map(city =>
          '<span>✦ ' + esc(city.discovered ? city.name : 'Unexplored road') + '</span>'
        ).join('') + '</div>' +
        '<p class="small">All roads presently lead through the royal capital. ' +
        'Travel times account for your current vehicle.</p>') +
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
    const state = ctx.getState();
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
    const state = ctx.getState();
    const mastered = Boolean(node.mastered) || nodes.some(other => other.tier > node.tier && other.unlocked);
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


  return { renderWorld, renderMarket, renderMagic, renderHome };
}
