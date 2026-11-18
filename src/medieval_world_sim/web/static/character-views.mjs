/* Private player's character, inventory, equipment and capital armory pages.
 * All mutations remain in the authenticated server and app.js action handlers.
 */
export function createCharacterViews(ctx) {
  const { esc, pretty, clock, money, button, disabled, isBusy, heading,
    panel, characterRow } = ctx;

  function renderInventory() {
    const state = ctx.getState();
    const p = state.player;
    const atCity = !p.destination && !state.world_map?.in_wilderness;
    const stash = atCity ? (p.stored_here || {}) : {};
    const carried = Object.entries(p.inventory).filter(([, qty]) => qty > 0).sort();
    const stored = Object.entries(stash).filter(([, qty]) => qty > 0).sort();
    const carryRows = carried.map(([item, qty]) => {
      const consumable = (p.consumables || []).find(c => c.item === item);
      const track = consumable && p.cooldowns && p.cooldowns[consumable.channel];
      const canUse = consumable && track &&
        track.remaining_minutes + consumable.cooldown_minutes <= track.max_minutes &&
        (consumable.channel === "food" ?
          (p.hp < p.max_hp || p.stamina < p.max_stamina || p.hunger > 0) :
          consumable.item === "mana_tonic" ? p.mana < p.max_mana :
          p.hp < p.max_hp);
      return '<div class="stash-row"><div><strong>' + esc(pretty(item)) +
      '</strong><p>' + qty + ' carried</p></div>' +
      (consumable ? button("Use", 'data-ui="consume" data-item="' +
        esc(item) + '"' + disabled(!canUse || isBusy()), "s secondary") : '') +
      '<label class="sr" for="store-' + esc(item) + '">Quantity</label>' +
      '<input class="qty" id="store-' + esc(item) +
      '" type="number" min="1" max="' + qty + '" value="1">' +
      (atCity ? button("Store", 'data-ui="store" data-item="' + esc(item) + '"' +
        disabled(isBusy()), "s secondary") : '') +
      button("Discard", 'data-ui="discard" data-item="' + esc(item) + '"' +
        disabled(isBusy() || !!p.destination), "s ghost") + '</div>';
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
    return heading("", "Inventory", "") + '<div class="stack">' +
      panel("Carried goods", "", carryRows) +
      panel("Stored Goods", atCity ? "Available in " + pretty(p.city) : "",
        atCity ? stashRows : '<p class="empty">Storage is unavailable outside a city.</p>') +
      '</div>';
  }

  function homeMagicPanel(state) {
    const p = state.player;
    // Show unlocked spells being studied; only tier-mastered spells can cast.
    // the same authenticated field-cast action handles all Home casts.
    const learned = (state.magic_nodes || []).filter(
      node => node.tier > 0 && node.unlocked);
    const spells = learned.length ? '<div class="home-spell-list">' +
      learned.map(node => {
        const usable = node.castable && !p.destination &&
          p.mana >= node.mana_cost && !isBusy();
        const note = !node.active ? pretty(node.school) + ' · Attunement required' :
          !node.castable ? pretty(node.school) + ' · Reach 100/100 to cast' :
          pretty(node.school) + ' · ' + node.mana_cost + ' mana';
        return '<div class="home-spell"><div class="home-spell-description">' +
          '<strong>' + esc(node.title) + '</strong><small>' + esc(note) +
          '</small></div>' +
          button("Cast", 'data-ui="field-cast" data-node="' + esc(node.node_id) +
            '"' + disabled(!usable), "secondary") +
          '</div>';
      }).join('') + '</div>' :
      '<p class="small">You have not learned any spells yet. Visit Magic to begin studying.</p>' +
      button("Study magic", 'data-tab="magic"', "secondary");
    return panel("Magic", "Train spells to 100/100 before casting; casting costs mana.", spells);
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
    const lineage = (state.lineage_options || []).find(x => x.id === p.lineage);
    return '<div class="profile-grid">' +
      panel("Character State", "",
        characterRow("Name", state.name) +
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
      '</div><div class="profile-magic-panel">' + homeMagicPanel(state) + '</div>';
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
        '<div class="button-group">' +
        button(inUse ? "Equipped" : "Equip", 'data-ui="equip" data-gear-id="' +
          gear.id + '"' + disabled(inUse || isBusy()), "s secondary") +
        button("Store", 'data-ui="store-gear" data-gear-id="' +
          gear.id + '"' + disabled(inUse || isBusy()), "s ghost") +
        button("Discard", 'data-ui="discard-gear" data-gear-id="' +
          gear.id + '"' + disabled(isBusy() || !!p.destination), "s ghost") +
        '</div></div>';
    }).join('') || '<p class="empty">You own no equipment yet. Starter gear is sold at Crownreach.</p>';
    const storedGear = (state.stored_gear_here || []).map(gear =>
      '<div class="equipment-item"><div><h3>' +
      esc(pretty(gear.kind)) + ' · #' + gear.id + '</h3><p>Quality ' +
      gear.quality + ' · Durability ' + gear.durability +
      ' · Stored in ' + esc(pretty(p.city)) + '</p></div>' +
      button("Retrieve", 'data-ui="retrieve-gear" data-gear-id="' +
        gear.id + '"' + disabled(isBusy()), "s secondary") + '</div>').join('') ||
      '<p class="small">No equipment stored in this city.</p>';
    const otherStores = Object.entries(p.stored_gear_cities || {})
      .filter(([city, count]) => city !== p.city && count > 0)
      .map(([city, count]) => esc(pretty(city)) + ': ' + count).join(' · ');
    return heading("", "Equipment", "") +
      '<div class="profile-grid">' +
      panel("Equipped Gear", "", equipmentMannequin(owned, equipped) + slotRows) +
      panel("Owned Equipment", "Only carried equipment counts against your road cargo limit.", gearRows) +
      '</div><div class="equipment-storage-panel">' +
      panel("Stored Equipment", "Unlimited in Crownreach and other settlements; retrieve it in the same city.", storedGear +
        (otherStores ? '<p class="small">Other city armories: ' + otherStores + '</p>' : '')) +
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
