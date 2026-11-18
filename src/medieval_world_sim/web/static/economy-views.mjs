/* Player economy: company ownership, jobs and local escrowed listings.
 * Pure presentation. It never authenticates, transfers assets or changes state.
 */
export function createEconomyViews(ctx) {
  const { esc, pretty, money, button, disabled, heading, panel, isBusy } = ctx;
  const options = (items, value = "id", label = "name") => items.map(item =>
    '<option value="' + esc(item[value]) + '">' + esc(item[label] || pretty(item[value])) +
    '</option>').join("");
  const input = (field, value = 1, min = 0) =>
    '<input class="field" data-econ-field="' + esc(field) +
    '" type="number" min="' + min + '" step="1" value="' + value + '">';
  const choose = (field, opts) =>
    '<select class="field" data-econ-field="' + esc(field) + '">' + opts + '</select>';
  const doButton = (name, title, attrs = "") =>
    button(title, 'type="button" data-econ="' + name + '" ' + attrs +
      disabled(isBusy()), "secondary");
  const line = (label, value) =>
    '<div class="character-row"><span>' + esc(label) + '</span><strong>' +
    esc(value) + '</strong></div>';
  const tags = (values) => Object.entries(values || {}).filter(([, n]) => n > 0)
    .map(([key, amount]) => esc(pretty(key)) + ' ×' + amount).join(" · ") || "None";

  function renderCompanies() {
    const state = ctx.getState();
    const econ = state.economy || {};
    const owned = econ.owned || [];
    const industries = econ.industries || [];
    const canStart = owned.length < 3 && !isBusy() &&
      state.player.city === "crownreach";
    const industryOptions = industries.map(x =>
      '<option value="' + esc(x.id) + '">' + esc(pretty(x.id)) +
      ' · ' + esc(tags(x.inputs)) + ' → ' + esc(tags(x.outputs)) + '</option>').join("");
    const intro = panel("Found a company", "Businesses operate in Crownreach. Owners fund payroll and stock materials.",
      '<div class="economy-controls economy-four">' +
      '<label>Company ID (3–32 lowercase characters)' +
      '<input id="economy-new-id" class="field" maxlength="32" placeholder="river_bakery"></label>' +
      '<label>Trade' + choose("industry", industryOptions) + '</label>' +
      '<label>Initial funding' + input("investment", 120, 1) + '</label>' +
      doButton("company-found", "Found company", disabled(!canStart)) + '</div>' +
      '<p class="small">You may own up to three companies. Capital and inventory are conserved.</p>');
    const cards = owned.map(company => {
      const cid = esc(company.id);
      const recipe = industries.find(x => x.id === company.industry) || {};
      const staff = company.employees.map(worker =>
        '<div class="economy-staff" data-econ-staff="' + esc(worker.id) + '">' +
        '<div><strong>' + esc(worker.name) + '</strong> · ' +
        esc(money(worker.wage.gold)) + ' per shift' +
        (worker.wage.item ? ' · ' + esc(pretty(worker.wage.item)) +
          ' ×' + worker.wage.quantity : '') + '</div>' +
        '<div class="economy-controls economy-four">' +
        '<label>New gold wage' + input("wage-gold", worker.wage.gold) + '</label>' +
        '<label>Goods wage' + choose("wage-item",
          '<option value="">None</option>' +
          options((econ.goods || []).map(x => ({id:x,name:pretty(x)})))) + '</label>' +
        '<label>Goods quantity' + input("wage-quantity", 0) + '</label>' +
        doButton("job-wage", "Set wage", 'data-worker="' + esc(worker.id) + '"') +
        '</div></div>').join("") || '<p class="small">No employees yet.</p>';
      const offers = company.job_offers.map(x => esc(x.name) + " · " +
        money(x.wage.gold)).join("; ") || "None";
      const gear = company.equipment.map(g => ({id:g.id,
        name:pretty(g.kind) + " #" + g.id + " · Q" + g.quality}));
      const ownedGear = state.gear || [];
      const canManage = company.can_manage && !isBusy();
      return '<section class="panel economy-company" data-econ-company="' + cid + '">' +
        '<div class="panel-head"><div><h3>' + cid + '</h3>' +
        '<p>' + esc(pretty(company.industry)) + ' · ' + esc(company.city) +
        '</p></div></div>' +
        '<div class="economy-metrics">' +
        line("Treasury", money(company.gold)) +
        line("Quality", company.quality.effectiveness + "/100 · " +
          company.quality.stars + " stars") +
        line("Facility", "Level " + company.facility_level) +
        line("Completed shifts", company.shifts_completed) +
        line("Daily sales", company.daily_units_sold + " units · " +
          money(company.daily_revenue)) + '</div>' +
        '<p class="small">Recipe: ' + esc(tags(recipe.inputs)) + ' → ' +
        esc(tags(recipe.outputs)) + '</p>' +
        '<p class="small">Company stock: ' + tags(company.inventory) + '</p>' +
        '<div class="economy-controls economy-four">' +
        '<label>Gold amount' + input("gold-amount", 10, 1) + '</label>' +
        doButton("company-fund", "Add gold", disabled(!canManage)) +
        doButton("company-withdraw", "Withdraw gold", disabled(!canManage)) +
        '</div>' +
        '<div class="economy-controls economy-four">' +
        '<label>Goods' + choose("goods-item",
          options((econ.goods || []).map(x => ({id:x,name:pretty(x)})))) + '</label>' +
        '<label>Quantity' + input("goods-quantity", 1, 1) + '</label>' +
        doButton("company-stock", "Supply goods", disabled(!canManage)) +
        doButton("company-unstock", "Take goods", disabled(!canManage)) +
        '</div>' +
        '<div class="economy-controls economy-four">' +
        '<label>My equipment' + choose("personal-gear",
          options(ownedGear.map(g => ({id:g.id,name:pretty(g.kind) + " #" + g.id})))) + '</label>' +
        doButton("company-stock-gear", "Supply gear", disabled(!canManage || !ownedGear.length)) +
        '<label>Company equipment' + choose("company-gear", options(gear)) + '</label>' +
        doButton("company-take-gear", "Take gear", disabled(!canManage || !gear.length)) +
        '</div>' +
        '<h4>Employment</h4><p class="small">Pending offers: ' + esc(offers) + '</p>' +
        '<div class="economy-controls economy-four">' +
        '<label>Offer employment to' + choose("worker-id",
          options(econ.candidates || [])) + '</label>' +
        '<label>Gold per shift' + input("offer-gold", 3) + '</label>' +
        '<label>Goods wage' + choose("offer-item",
          '<option value="">None</option>' +
          options((econ.goods || []).map(x => ({id:x,name:pretty(x)})))) + '</label>' +
        '<label>Goods quantity' + input("offer-quantity", 0) + '</label>' +
        doButton("job-offer", "Send job offer",
          disabled(!canManage || !(econ.candidates || []).length)) + '</div>' +
        '<div class="economy-staff-list">' + staff + '</div>' +
        '<div class="economy-controls economy-four">' +
        '<label><input type="checkbox" data-econ-perk="training"' +
          (company.perks.includes("training") ? " checked" : "") +
          '> Training</label>' +
        '<label><input type="checkbox" data-econ-perk="meal"' +
          (company.perks.includes("meal") ? " checked" : "") +
          '> Meals from stock</label>' +
        '<label><input type="checkbox" data-econ-perk="medical"' +
          (company.perks.includes("medical") ? " checked" : "") +
          '> Medical supplies</label>' +
        doButton("company-perks", "Apply perks", disabled(!canManage)) +
        doButton("company-upgrade", "Upgrade facility", disabled(!canManage ||
          company.facility_level >= 5)) + '</div>' +
        '</section>';
    }).join("");
    return heading("", "Companies", "") + intro +
      (cards || panel("Your companies", "", '<p>No owned companies yet.</p>'));
  }

  function renderEmployment() {
    const econ = ctx.getState().economy || {};
    const jobs = (econ.jobs || []).map(job =>
      '<div class="economy-job">' +
      '<strong>' + esc(job.company_id) + '</strong> · ' +
      esc(pretty(job.industry)) + ' · ' + esc(money(job.wage.gold)) + " per shift" +
      (job.wage.item ? ' · ' + esc(pretty(job.wage.item)) +
        ' ×' + job.wage.quantity : '') +
      '<div class="economy-actions">' +
      doButton("job-shift", "Work shift", 'data-company="' + esc(job.company_id) +
        '"' + disabled(!job.can_shift)) +
      doButton("job-leave", "Leave job", 'data-company="' + esc(job.company_id) + '"') +
      '</div>' +
      (job.ready_minutes ? '<p class="small">Ready in ' +
        esc(job.ready_minutes) + ' game minutes</p>' : '') + '</div>').join("");
    const offers = (econ.job_offers || []).map(offer =>
      '<div class="economy-job"><strong>' + esc(offer.company_id) + '</strong> · ' +
      esc(pretty(offer.industry)) + ' · ' + esc(money(offer.wage.gold)) +
      ' per shift' +
      '<div class="economy-actions">' + doButton("job-accept", "Accept offer",
        'data-company="' + esc(offer.company_id) + '"' +
        disabled(!offer.can_accept)) + '</div></div>').join("");
    const w = ctx.getState().player.work;
    return heading("", "Occupation", "") + '<div class="stack">' +
      panel("Work stats", "",
        line("Manual", w.manual) +
        line("Intelligence", w.intelligence) +
        line("Endurance", w.endurance) +
        line("Shifts completed", w.shifts)) +
      panel("Employment offers", "Offers from player-owned companies.",
        offers || '<p class="small">No pending offers.</p>') +
      panel("My jobs", "Working a shift consumes real company materials and pays its agreed wage.",
        jobs || '<p class="small">No active company employment.</p>') + '</div>';
  }

  function renderStalls() {
    const state = ctx.getState();
    const econ = state.economy || {};
    const sources = econ.market_sources || [];
    const goods = (econ.goods || []).map(x => ({id:x,name:pretty(x)}));
    const gear = [...(state.gear || []),
      ...(econ.owned || []).flatMap(c => c.equipment.map(g => ({...g,source:c.id})))];
    const gearOptions = gear.map(g =>
      '<option value="' + g.id + '">' + esc(pretty(g.kind) + " #" +
      g.id + " · Q" + g.quality + (g.source ? " (" + g.source + ")" : "")) +
      '</option>').join("");
    const controls = sources.length ?
      '<div class="economy-controls economy-four" data-econ-listing="true">' +
      '<label>Seller' + choose("seller",
        options(sources)) + '</label>' +
      '<label>Goods' + choose("listing-item", options(goods)) + '</label>' +
      '<label>Quantity' + input("listing-quantity", 1, 1) + '</label>' +
      '<label>Price per unit' + input("listing-price", 10, 1) + '</label>' +
      doButton("list-goods", "List goods") +
      '<label>Equipment' + choose("listing-gear", gearOptions) + '</label>' +
      doButton("list-gear", "List equipment", disabled(!gear.length)) +
      '</div>' : '<p class="small">Visit a settlement to list or buy goods.</p>';
    const buyer = sources.length ?
      '<label class="economy-buyer">Buy with ' + choose("buyer",
        options(sources)) + '</label>' : "";
    const rows = (econ.listings || []).map(x =>
      '<div class="economy-listing" data-econ-listing-id="' + x.id + '">' +
      '<div><strong>' + esc(pretty(x.item)) +
      (x.quality ? " · Q" + x.quality : "") + '</strong>' +
      '<p class="small">Seller: ' + esc(x.seller) + ' · ' +
      esc(x.quantity) + ' available · ' +
      esc(money(x.unit_price)) + ' each</p></div>' +
      '<div class="economy-actions">' +
      (x.can_cancel ? doButton("listing-cancel", "Cancel", 'data-offer-id="' +
        x.id + '"') :
      '<label class="economy-quantity">Quantity' + input("buy-quantity", 1, 1) + '</label>' +
      doButton("listing-buy", "Buy", 'data-offer-id="' + x.id + '"')) +
      '</div></div>').join("");
    return panel("Player market", "Local listings are held in escrow; the server settles every purchase.",
      controls + buyer + (rows ||
        '<p class="small">No player listings at this settlement yet.</p>'));
  }

  return { renderCompanies, renderEmployment, renderStalls };
}
