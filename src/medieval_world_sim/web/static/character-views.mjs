/* Private player's character, inventory, equipment and capital armory pages.
 * All mutations remain in the authenticated server and app.js action handlers.
 */
export function createCharacterViews(ctx) {
  const { esc, pretty, clock, money, button, disabled, isBusy, heading,
    panel, characterRow } = ctx;

  function renderInventory() {
    const state = ctx.getState();
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

  function renderCharacter() {
    const state = ctx.getState();
    const p = state.player, w = p.work;
    const xpNext = 10 * p.level * p.level;
    const study = Object.entries(p.school_xp).map(([key, xp]) =>
      characterRow(pretty(key) + " magic", xp + " XP")).join('');
    const career = Object.entries(w.experience).map(([key, xp]) =>
      characterRow(pretty(key), xp + " XP")).join('');
    const homeName = state.housing.tier ? pretty(state.housing.tier) +
      " · " + pretty(state.housing.city) : "No residence";
    const places = {
      crownreach: ["The Royal Capital", "Stone towers rise above crowded markets and the clamor of the royal forge.",
        "Every road begins here. Beyond the gates, much of the realm remains uncharted."],
      ironvale: ["The Iron Hills", "The ring of hammers echoes across the mountain roads.",
        "Ore and skilled hands sustain the workshops of the realm."],
      emberfall: ["The Ashen Crossing", "Dark stone and coal fires mark the road through the southern highlands.",
        "Caravans bring fuel and stories from the far roads."],
      greenhollow: ["The Elderwood Frontier", "Deep woodland shelters herb-gatherers, hunters and ancient pathways.",
        "The forest rewards observant travelers."],
      goldmeadow: ["The Southern Granary", "Fields and wind-worn barns stretch toward the southern horizon.",
        "Grain and livestock feed the cities beyond."],
    };
    const scene = places[p.city] || ["The Five Cities", "A place to begin.", "The world awaits."];
    const explored = (p.discovered_cities || []).length;
    const lineage = (state.lineage_options || []).find(x => x.id === p.lineage);
    return '<div class="profile-hero home-hero"><div class="home-hero-content">' +
      '<small>' + esc(scene[0]) + ' · ' + esc(lineage ? lineage.name : "Traveler") + '</small>' +
      '<h3>' + esc(state.name) + '</h3>' +
      '<p class="home-scene">' + esc(scene[1]) + '</p>' +
      '<p class="home-scene-note">' + esc(scene[2]) + '</p>' +
      '<div class="home-hero-foot"><span>✦ ' + explored + ' of ' +
      state.cities.length + ' cities charted</span>' +
      '<span>Level ' + p.level + ' · ' + esc(scene[0]) + '</span></div></div>' +
      '<div class="home-hero-crest" aria-hidden="true">✦</div></div>' +
      '<div class="profile-grid">' +
      panel("Character State", "",
        characterRow("Level", p.level) +
        characterRow("Lineage", lineage ? lineage.name : "Unchosen") +
        characterRow("Experience toward next level", p.level_xp + " / " + xpNext) +
        characterRow("Health", p.hp + " / " + p.max_hp) +
        characterRow("Stamina", p.stamina + " / " + p.max_stamina) +
        characterRow("Mana", p.mana + " / " + p.max_mana) +
        characterRow("World age (shared)", clock(state.minute))) +
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
      panel("Lineage & Trait", "",
        characterRow("Birthright", lineage ? lineage.name : "Unchosen") +
        characterRow("Unique trait", lineage ? lineage.trait : "None") +
        characterRow("Trait status", p.lineage_trait_unlocked ? "Unlocked" :
          "Unlocks at level 3") +
        (lineage ? '<p class="small">' + esc(lineage.trait_description) + '</p>' : '')) +
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
    const state = ctx.getState();
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
    const state = ctx.getState();
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

  return { renderInventory, renderCharacter, renderEquipment, renderArmory };
}
