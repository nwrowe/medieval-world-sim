/* Character search, profiles, person-to-person trade, and duel presentation.
 * All views are projections of caller-provided state. No credentials,
 * network traffic, trading decisions or authoritative mutations live here.
 */
export function createCommunityViews(ctx) {
  const { esc, pretty, money, dur, button, disabled, isBusy,
    heading, panel, characterRow, progress, chip } = ctx;

  function presenceBadge(value) {
    const status = ["active", "away", "offline"].includes(value) ? value : "offline";
    return '<span class="player-presence ' + status + '" title="' +
      esc("Player is " + status) + '" aria-label="' +
      esc("Player is " + status) + '"><span class="presence-dot"></span>' +
      (status[0].toUpperCase() + status.slice(1)) + '</span>';
  }
  function renderPeople() {
    const state = ctx.getState();
    const peopleQuery = ctx.getPeopleQuery();
    const searchScope = ctx.getSearchScope();
    const multiMode = ctx.getMultiMode();
    const query = peopleQuery.trim().toLowerCase();
    const players = (state.users || []).filter(person =>
      person.city === state.player.city && !person.destination &&
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
          (multiMode && person.kind === "human" ?
            presenceBadge(person.presence) : "") +
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
    const state = ctx.getState();
    const selectedCharacterId = ctx.getSelectedCharacterId();
    const multiMode = ctx.getMultiMode();
    const pending = ctx.getPending();
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
      '<h3>' + esc(person.name) +
      (multiMode && !isNpc ? presenceBadge(person.presence) : "") + '</h3>' +
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
    const state = ctx.getState();
    const multiMode = ctx.getMultiMode();
    const selectedCharacterId = ctx.getSelectedCharacterId();
    const pending = ctx.getPending();
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
    const state = ctx.getState();
    const pending = ctx.getPending();
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
          button("Flee · 50% chance", 'data-ui="duel-flee" title="Uses one round. A failed escape invites an automatic counterattack."' +
            disabled(pending), "ghost")) :
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
        button("Flee · 50% chance", 'data-ui="duel-flee" title="Uses one round. A failed escape invites an automatic counterattack."' +
            disabled(pending), "ghost") +
        '</div><h4>Combat magic</h4>' +
        '<div class="combat-actions">' +
        (casts || '<p class="small">Unlock spells on the Magic page to use them here.</p>') +
        '</div>' + (duel.pending_ward ? chip("Prepared ward: " +
          duel.pending_ward + " damage") : ""))) +
      panel("Round-by-round chronicle", "", logs);
  }

  return { renderPeople, renderProfile, renderTrade, renderDuel };
}
