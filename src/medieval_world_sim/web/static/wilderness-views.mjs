/* Terrain-based wilderness activities.
 * Only uses current-hex server projections. All state changes go through
 * authenticated actions with server-side stamina, location and roll checks.
 */
export function createWildernessViews(ctx) {
  const { esc, pretty, button, disabled, panel, isBusy } = ctx;
  let bypassedSite = null;
  const costFor = (w, qty) => Number((w.gather_cost || {})[String(qty)]) || (1 + qty * 2);

  function renderWilderness() {
    const state = ctx.getState();
    const area = state?.wilderness;
    if (!area || state.player.destination) {
      bypassedSite = null;
      return "";
    }
    const busy = isBusy();
    const resources = (area.resources || []).map(r => {
      const enough = r.available > 0 && !busy;
      return '<div class="wilderness-row">' +
        '<div><strong>' + esc(pretty(r.item)) + '</strong>' +
        '<p class="small">Local potential: ' + r.potential +
        '/100 · Available: ' + r.available + '</p></div>' +
        '<div class="wilderness-buttons">' +
        button("Gather 1 · " + costFor(area, 1) + " stamina",
          'type="button" data-wilderness="gather" data-item="' + esc(r.item) +
          '" data-quantity="1"' +
          disabled(!enough || area.stamina < costFor(area, 1)), "secondary") +
        button("Gather 2 · " + costFor(area, 2) + " stamina",
          'type="button" data-wilderness="gather" data-item="' + esc(r.item) +
          '" data-quantity="2"' +
          disabled(!enough || r.available < 2 || area.stamina < costFor(area, 2)),
          "secondary") + '</div></div>';
    }).join("");
    const siteCards = (area.sites || []).map(site => {
      const prior = site.resolved;
      if (bypassedSite === site.id && !prior) {
        return '<div class="wilderness-site">' +
          '<h4>' + esc(site.name) + '</h4>' +
          '<p class="small">You passed by without spending stamina. ' +
          'Choose another hex on the map to continue traveling.</p>' +
          button("Reconsider this site",
            'type="button" data-wilderness="reconsider" data-site-id="' +
            esc(site.id) + '"', "ghost") + '</div>';
      }
      const result = prior ?
        '<p class="wilderness-resolution"><strong>Already investigated:</strong> ' +
        esc(pretty(prior.approach)) + ' — ' +
        (prior.success ? 'success' : 'no find') +
        (prior.quantity ? ' · +' + prior.quantity + ' ' +
          esc(pretty(prior.item)) : '') +
        (prior.damage ? ' · -' + prior.damage + ' health' : '') +
        '. This site cannot be rerolled by this character.</p>' : "";
      const actions = !prior ? (site.choices || []).map(opt =>
        button(opt.label + " · " + opt.stamina + " stamina · " +
          opt.chance + "% success",
          'type="button" data-wilderness="investigate" data-site-id="' +
          esc(site.id) + '" data-approach="' + esc(opt.id) + '"' +
          disabled(!opt.available || busy), "secondary")
      ).join("") +
        button("Go around · free",
          'type="button" data-wilderness="bypass" data-site-id="' +
          esc(site.id) + '"', "ghost") : "";
      return '<div class="wilderness-site"><div class="section-kicker">' +
        esc(pretty(site.kind)) + ' · Danger ' + site.danger + '/10</div>' +
        '<h4>' + esc(site.name) + '</h4><p>' + esc(site.clue) + '</p>' +
        result +
        (actions ? '<div class="wilderness-buttons">' + actions + '</div>' : "") +
        '<p class="small">One investigation per character. Any failed attempt ' +
        'still consumes stamina; exploring deeper can cause minor injuries.</p>' +
        '</div>';
    }).join("");
    return panel("Wilderness · " + pretty(area.biome),
      esc(pretty(area.geology)) + ' · ' + area.elevation_m + ' m' +
      (area.river ? ' · River corridor' : '') + ' · ' +
      area.stamina + ' stamina available',
      '<p class="small">These resources come from the actual terrain and geology ' +
      'under this hex. Gathering uses stamina; stock slowly replenishes each day.</p>' +
      (resources || '<p class="small">This terrain has no harvestable material.</p>') +
      (siteCards ? '<h3 class="wilderness-sites-title">Places to investigate</h3>' +
        siteCards : '<p class="small">No special site on this hex. Keep surveying the map.</p>'));
  }

  function handleWildernessClick(element) {
    const kind = element?.dataset?.wilderness;
    if (!kind) return false;
    const state = ctx.getState();
    if (!state || !state.wilderness || state.player.destination) return true;
    const siteId = element.dataset.siteId;
    if (kind === "bypass" || kind === "reconsider") {
      bypassedSite = kind === "bypass" ? siteId : null;
      ctx.render();
      return true;
    }
    if (isBusy()) return true;
    if (kind === "gather") {
      const quantity = Number(element.dataset.quantity);
      const item = element.dataset.item;
      if (![1, 2].includes(quantity) ||
          !(state.wilderness.resources || []).some(r => r.item === item)) return true;
      ctx.action("wilderness_gather", {item, quantity}, "Resources harvested");
      return true;
    }
    if (kind === "investigate") {
      const site = (state.wilderness.sites || []).find(s => s.id === siteId);
      if (!site || site.resolved ||
          !(site.choices || []).some(a => a.id === element.dataset.approach)) return true;
      ctx.action("investigate_site", {
        site_id: siteId, approach: element.dataset.approach,
      }, "Site investigation completed");
      return true;
    }
    return false;
  }

  return { renderWilderness, handleWildernessClick };
}
