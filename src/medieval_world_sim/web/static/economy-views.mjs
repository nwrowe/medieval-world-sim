/* Player economy: company ownership, jobs and local escrowed listings.
 * Pure presentation. It never authenticates, transfers assets or changes state.
 */
export function createEconomyViews(ctx) {
  const { esc, pretty, money, button, disabled, heading, panel, isBusy, timerAttrs, fullCountdown } = ctx;
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
  const requirements = values => Object.entries(values || {})
    .map(([key,min]) => pretty(key) + " ≥ " + min).join(" · ");
  const countdown = minutes => minutes == null ? "Legacy offer" :
    '<span class="offer-countdown"' + timerAttrs("Expires in ", minutes * 60) +
    '><span data-timer-display>' + fullCountdown(minutes * 60) + '</span></span>';
  const tags = (values) => Object.entries(values || {}).filter(([, n]) => n > 0)
    .map(([key, amount]) => esc(pretty(key)) + ' ×' + amount).join(" · ") || "None";

  function renderCompanies() {
    const state = ctx.getState();
    const econ = state.economy || {};
    const owned = econ.owned || [];
    const directory = econ.directory || [];
    const industries = econ.industries || [];
    const section = ctx.getCompanySection ? ctx.getCompanySection() : "overview";
    const canStart = owned.length === 0 && !isBusy() &&
      state.player.city === "crownreach" && !state.player.destination &&
      !state.world_map?.in_wilderness;
    const industryOptions = industries.map(x =>
      '<option value="' + esc(x.id) + '">' + esc(pretty(x.id)) + '</option>').join("");
    const intro = owned.length ? "" :
      panel("Found a company", "",
        '<div class="economy-controls economy-four">' +
        '<label>Company Name' +
        '<input id="economy-new-id" class="field" maxlength="40" ' +
        'placeholder="Silver Oak Trading"></label>' +
        '<label>Trade' + choose("industry", industryOptions) + '</label>' +
        '<label>Initial funding' + input("investment", 120, 1) + '</label>' +
        doButton("company-found", "Found company", disabled(!canStart)) +
        '</div>');

    const cards = owned.map(company => {
      const cid = esc(company.id);
      const title = esc(company.name || pretty(company.id));
      const recipe = industries.find(x => x.id === company.industry) || {};
      const products = recipe.products || [];
      const current = products.find(p => p.id === company.product) || products[0] || {};
      const productOptions = products.map(p =>
        '<option value="' + esc(p.id) + '"' +
        (p.id === company.product ? ' selected' : '') + '>' +
        esc(pretty(p.id)) + ' · ' + esc(tags(p.inputs)) +
        ' → ' + esc(tags(p.outputs)) + '</option>').join("");
      const canManage = company.can_manage && !isBusy();
      const ownedGear = state.gear || [];
      const gear = (company.equipment || []).map(g => ({
        id:g.id, name:pretty(g.kind) + " #" + g.id + " · Q" + g.quality
      }));
      const tabs = [
        ["overview","Overview"],["production","Production"],["stock","Stock & funds"],
        ["staff","Employment"],["ownership","Ownership"]
      ].map(([id,name]) =>
        button(name, 'data-ui="company-section" data-section="' + id +
          '" aria-pressed="' + (section === id) + '"' +
          '', "secondary")).join("");
      let content = "";
      if (section === "overview") {
        content = '<div class="economy-metrics">' +
          line("Treasury", money(company.gold)) +
          line("Quality", company.quality.effectiveness + "/100 · " +
            company.quality.stars + " stars") +
          line("Facility", "Level " + company.facility_level) +
          line("Completed shifts", company.shifts_completed) +
          line("Career stage", company.career_stage + " / 5") +
          line("Positions", company.employees.length + " filled / " + company.capacity) +
          line("Daily sales", company.daily_units_sold + " units · " +
            money(company.daily_revenue)) +
          line("Current product", pretty(company.product)) +
          '</div>';
      } else if (section === "production") {
        content = '<p class="small">Current recipe: ' + esc(tags(current.inputs)) +
          ' → ' + esc(tags(current.outputs)) + '</p>' +
          '<div class="economy-controls economy-four">' +
          '<label>Produce' + choose("product", productOptions) + '</label>' +
          doButton("company-product", "Select product",
            disabled(!canManage || products.length < 2)) + '</div>';
      } else if (section === "stock") {
        content = '<p class="small">Company stock: ' + tags(company.inventory) + '</p>' +
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
            options(ownedGear.map(g => ({
              id:g.id,name:pretty(g.kind) + " #" + g.id
            })))) + '</label>' +
          doButton("company-stock-gear", "Supply gear",
            disabled(!canManage || !ownedGear.length)) +
          '<label>Company equipment' + choose("company-gear", options(gear)) + '</label>' +
          doButton("company-take-gear", "Take gear",
            disabled(!canManage || !gear.length)) + '</div>';
      } else if (section === "staff") {
        const vacant = (company.positions || []).filter(p => p.status === "open");
        const roleChoices = vacant.map(p => '<option value="' + esc(p.id) +
          '">' + esc(p.title) + ' · ' + esc(requirements(p.requirements)) +
          '</option>').join("");
        const roster = (company.positions || []).map(p =>
          '<div class="economy-position"><strong>' + esc(p.title) + '</strong>' +
          '<span>' + esc(p.worker || (p.status === "offered" ? "Offer pending" : "Open")) +
          '</span><small>' + esc(requirements(p.requirements)) + '</small></div>').join("");
        const applicants = (company.applicants || []).map(a => {
          const eligible = vacant.filter(p => (a.eligible_positions || []).includes(p.id));
          const choices = eligible.map(p => '<option value="' + esc(p.id) + '"' +
            (p.id === a.position_id ? ' selected' : '') + '>' +
            esc(p.title) + '</option>').join("");
          return '<div class="economy-job" data-econ-applicant="' + esc(a.id) +
            '"><strong>' + esc(a.name) + '</strong> · ' + esc(a.position) +
            (eligible.length ? '<div class="economy-controls economy-applicant-controls">' +
              '<label>Position' + choose("applicant-position", choices) + '</label>' +
              '<label>Gold per shift' + input("applicant-gold", 3, 1) + '</label>' +
              doButton("company-accept-applicant", "Accept", 'data-worker="' +
                esc(a.id) + '"' + disabled(!canManage)) + '</div>' :
              '<p class="small">No eligible vacancy currently available.</p>') +
            '</div>';
        }).join("") || '<p class="small">No applications.</p>';
        const staff = (company.employees || []).map(w =>
          '<div class="economy-staff" data-econ-staff="' + esc(w.id) + '">' +
          '<strong>' + esc(w.name) + '</strong> · ' + esc(w.position) +
          ' · ' + esc(money(w.wage.gold)) + ' per shift' +
          '<div class="economy-controls economy-applicant-controls">' +
          '<label>Gold per shift' + input("wage-gold", w.wage.gold, 1) + '</label>' +
          doButton("job-wage", "Set wage", 'data-worker="' + esc(w.id) +
            '"' + disabled(!canManage)) + '</div></div>').join("") ||
          '<p class="small">No employees yet.</p>';
        const offers = (company.job_offers || []).map(o =>
          '<div class="economy-job"><strong>' + esc(o.name) + '</strong> · ' +
          esc(o.position) + ' · ' + esc(money(o.wage.gold)) +
          ' per shift · ' + countdown(o.expires_in_minutes) + '</div>').join("") ||
          '<p class="small">No pending offers.</p>';
        const names = (econ.candidates || []).map(c =>
          '<option value="' + esc(c.name) + '"></option>').join("");
        content = '<p class="small">' + company.employees.length + ' employees · ' +
          company.capacity + ' positions · ' + vacant.length + ' vacant</p>' +
          '<h4>Career positions</h4><div class="economy-roster">' + roster + '</div>' +
          '<div class="economy-actions">' +
          doButton("company-hiring", company.hiring ? "Close hiring" : "Open hiring",
            disabled(!canManage)) + '</div>' +
          '<h4>Applications</h4>' + applicants +
          '<h4>Send job offer</h4><div class="economy-controls economy-offer-controls">' +
          '<label>Player name<input class="field" data-econ-field="worker-name" ' +
          'list="company-candidates-' + cid +
          '" placeholder="Type a player name" autocomplete="off" maxlength="60">' +
          '<datalist id="company-candidates-' + cid + '">' + names +
          '</datalist></label>' +
          '<label>Position' + choose("offer-position", roleChoices) + '</label>' +
          '<label>Gold per shift' + input("offer-gold", 3, 1) + '</label>' +
          doButton("job-offer", "Send job offer",
            disabled(!canManage || !vacant.length)) + '</div>' +
          '<h4>Pending offers</h4>' + offers +
          '<h4>Employees</h4>' + staff +
          '<h4>Benefits & facilities</h4><div class="economy-controls economy-four">' +
          '<label><input type="checkbox" data-econ-perk="training"' +
          (company.perks.includes("training") ? " checked" : "") + '> Training</label>' +
          '<label><input type="checkbox" data-econ-perk="meal"' +
          (company.perks.includes("meal") ? " checked" : "") + '> Meals from stock</label>' +
          '<label><input type="checkbox" data-econ-perk="medical"' +
          (company.perks.includes("medical") ? " checked" : "") + '> Medical supplies</label>' +
          doButton("company-perks", "Apply perks", disabled(!canManage)) +
          doButton("company-upgrade", "Upgrade facility",
            disabled(!canManage || company.facility_level >= 5)) + '</div>';
      } else if (section === "ownership") {
        content = '<p class="small">A sale transfers the entire business, including ' +
          'funds, inventory, equipment and existing employment agreements.</p>' +
          (company.sale_price ?
            '<p>Listed for ' + esc(money(company.sale_price)) + '</p>' : '') +
          '<div class="economy-controls economy-four">' +
          '<label>Asking price' + input("sale-price", company.sale_price || 100, 1) +
          '</label>' +
          doButton("company-list-for-sale", "List for sale", disabled(!canManage)) +
          doButton("company-cancel-sale", "Cancel listing",
            disabled(!canManage || !company.sale_price)) + '</div>' +
          '<div class="economy-actions">' +
          doButton("company-dissolve", "Dissolve company", disabled(!canManage)) +
          '</div><p class="small">Dissolving returns the treasury, goods and ' +
          'equipment (including listed stock) to you and releases employees.</p>';
      }
      return '<section class="panel economy-company" data-econ-company="' + cid + '">' +
        '<div class="panel-head"><div><h3>' + title + '</h3><p>' +
        esc(pretty(company.industry)) + ' · ' + esc(pretty(company.city)) +
        '</p></div></div>' +
        '<nav class="company-tabs" aria-label="Manage company">' + tabs + '</nav>' +
        '<div class="company-section">' + content + '</div></section>';
    }).join("");
    const sales = directory.filter(c => c.sale_price > 0).map(c =>
      '<div class="economy-listing"><div><strong>' + esc(c.name) + '</strong>' +
      '<p class="small">' + esc(pretty(c.industry)) + ' · ' +
      esc(pretty(c.city)) + ' · Level ' + c.facility_level +
      ' facility · ' + c.shifts_completed + ' shifts · ' +
      esc(money(c.daily_revenue)) + ' daily revenue</p></div>' +
      doButton("company-buy", "Buy · " + money(c.sale_price),
        'data-company="' + esc(c.id) + '"' + disabled(!c.can_buy)) +
      '</div>').join("") || '<p class="small">No companies listed for sale.</p>';
    return heading("", "Companies", "") +
      (intro ? intro : "") + cards +
      '<div class="company-marketplace">' + panel("Company marketplace", "", sales) + '</div>';
  }

  function renderEmployment() {
    const econ = ctx.getState().economy || {};
    const jobs = (econ.jobs || []).map(job =>
      '<div class="economy-job">' +
      '<strong>' + esc(job.company_name || job.company_id) + '</strong> · ' +
      esc(pretty(job.industry)) + ' · ' + esc(money(job.wage.gold)) + " per shift" +
      (job.wage.item ? ' · ' + esc(pretty(job.wage.item)) +
        ' ×' + job.wage.quantity : '') +
      '<div class="economy-actions">' +
      doButton("job-shift", "Work shift", 'data-company="' +
        esc(job.company_id) + '"' + disabled(!job.can_shift)) +
      doButton("job-leave", "Leave job", 'data-company="' +
        esc(job.company_id) + '"') + '</div>' +
      (job.ready_minutes ? '<p class="small">Ready in ' +
        esc(job.ready_minutes) + ' game minutes</p>' : '') + '</div>').join("");
    const offers = (econ.job_offers || []).map(offer =>
      '<div class="economy-job"><strong>' +
      esc(offer.company_name || offer.company_id) + '</strong> · ' +
      esc(pretty(offer.industry)) + ' · ' + esc(money(offer.wage.gold)) +
      ' per shift' +
      '<div class="economy-actions">' + doButton("job-accept", "Accept offer",
        'data-company="' + esc(offer.company_id) + '"' +
        disabled(!offer.can_accept)) + '</div></div>').join("");
    const directory = (econ.directory || []).map(company => {
      const searchable = (company.name + " " + company.industry + " " +
        company.city).toLowerCase();
      const application = company.applied ?
        doButton("company-withdraw-application", "Withdraw application",
          'data-company="' + esc(company.id) + '"') :
        company.hiring ?
        doButton("company-apply", "Apply",
          'data-company="' + esc(company.id) + '"' +
          disabled(!company.can_apply)) :
        '<span class="small">Not hiring</span>';
      return '<div class="economy-job" data-company-search="' + esc(searchable) +
        '"><strong>' + esc(company.name) + '</strong> · ' +
        esc(pretty(company.industry)) + '<p class="small">' +
        esc(pretty(company.city)) + ' · ' + company.employees +
        ' employees · ' + (company.hiring ? "Accepting applications" : "Not hiring") +
        '</p><div class="economy-actions">' + application + '</div></div>';
    }).join("") || '<p class="small">No active companies.</p>';
    const w = ctx.getState().player.work;
    return heading("", "Occupation", "") + '<div class="stack">' +
      panel("Work stats", "",
        line("Manual", w.manual) + line("Intelligence", w.intelligence) +
        line("Endurance", w.endurance) + line("Shifts completed", w.shifts)) +
      panel("Employment offers", "", offers ||
        '<p class="small">No pending offers.</p>') +
      panel("My jobs", "", jobs ||
        '<p class="small">No active company employment.</p>') +
      panel("Find a company", "",
        '<label for="occupation-company-search">Search companies</label>' +
        '<input id="occupation-company-search" class="field" type="search" ' +
        'placeholder="Name, city or trade" maxlength="80" autocomplete="off">' +
        '<div id="occupation-company-list">' + directory + '</div>') +
      '</div>';
  }

  function renderLetters() {
    const offers = (ctx.getState().economy?.job_offers || []).map(o =>
      '<article class="economy-letter">' +
      '<h3>' + esc(o.position) + '</h3><p><strong>' + esc(o.company_name) +
      '</strong> · From ' + esc(o.sender || "Company owner") +
      ' · ' + esc(pretty(o.city)) + '</p>' +
      '<p>Gold per shift: <strong>' + esc(money(o.wage.gold)) +
      '</strong></p><p class="small">Required: ' +
      esc(requirements(o.requirements)) + '</p>' +
      '<p class="small">Expires in ' + countdown(o.expires_in_minutes) + '</p>' +
      (!o.can_accept ? '<p class="small">Visit the company city and meet the requirements to accept.</p>' : '') +
      '<div class="economy-actions">' +
      doButton("job-accept", "Accept", 'data-company="' +
        esc(o.company_id) + '"' + disabled(!o.can_accept)) +
      doButton("job-decline", "Decline", 'data-company="' +
        esc(o.company_id) + '"') + '</div></article>').join("") ||
      '<p class="small">No pending offers. Formal employment offers appear here for 48 Oathmere hours.</p>';
    return heading("", "Letters", "") + '<div class="stack">' +
      panel("Employment letters", "Review and respond to your job offers.", offers) + '</div>';
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

  return { renderCompanies, renderEmployment, renderStalls, renderLetters };
}
