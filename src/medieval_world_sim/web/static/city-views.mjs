/* City services: contracts, guilds, merits, schooling, and social venues.
 * Renders read-only server projections; commands remain with app.js handlers.
 */
export function createCityViews(ctx) {
  const { esc, pretty, money, dur, button, disabled, isBusy,
    heading, panel, characterRow, chip } = ctx;

  function futurePage(kicker, title, narrative, next, label, nested = false) {
    return (nested ? "" : heading("", title, "")) +
      '<section class="story-panel"><div class="section-kicker">Coming chapter</div>' +
      '<h3>' + esc(title) + '</h3><p>' + esc(narrative) + '</p>' +
      '<p class="small">This location is planned. It cannot yet award gold, XP, ' +
      'contracts, or equipment.</p>' + button(label, 'data-tab="' + esc(next) + '"',
        "secondary") + '</section>';
  }
  const contractScenes = {
    warrior_patrol: "You take your position along the weathered city wall. By the end of your patrol, the guard captain signs your report and orders your wage paid from the city treasury.",
    mage_copywork: "Beneath the guild's high windows, you copy protective sigils until your fingertips ache. The archivist checks your script, then pays you from the guild's civic stipend.",
    church_supplies: "You bring a bundle of herbs to the infirmary. The sisters inventory it for their patients and offer a modest payment from the city's charitable allowance.",
    labor_shift: "You join the porters hauling grain and supplies through the market yard. After the last cart is loaded, the foreman counts out your wages.",
  };
  function contractBoard(venue, title = "Available Work") {
    const state = ctx.getState();
    const latestContract = ctx.getLatestContract();
    const p = state.player;
    const offers = (state.contracts || []).filter(contract => contract.venue === venue);
    const items = offers.map(contract => {
      const can = !isBusy() && contract.cooldown_available &&
        contract.can_pay && contract.has_material &&
        p.stamina >= contract.stamina && p.mana >= contract.mana;
      const costs = [contract.stamina ? contract.stamina + ' stamina' : null,
        contract.mana ? contract.mana + ' mana' : null,
        contract.material ? '1 ' + pretty(contract.material) : null].filter(Boolean);
      return '<div class="contract-card"><div><h3>' + esc(contract.title) + '</h3>' +
        '<p>' + esc(contract.description) + '</p>' +
        '<div class="contract-terms"><span>+' + contract.reward + ' gold</span>' +
        '<span>' + esc(costs.length ? costs.join(' · ') : 'No item cost') + '</span>' +
        '<span>+' + contract.cooldown_minutes + 'm Job cooldown</span></div>' +
        (!contract.can_pay ? '<p class="small">The city cannot currently fund this offer.</p>' :
         !contract.has_material ? '<p class="small">You need ' + esc(pretty(contract.material)) + '.</p>' :
         !contract.cooldown_available ?
           '<p class="small">Job cooldown limit: 24h. Pass game time to work again.</p>' : '') +
        '</div>' +
        button("Complete contract", 'data-ui="contract" data-contract="' +
          esc(contract.id) + '"' + disabled(!can), "secondary") + '</div>';
    }).join("");
    let report = "";
    if (latestContract && offers.some(c => c.id === latestContract.contract_id)) {
      const scene = contractScenes[latestContract.contract_id] || "You finish your work and receive payment.";
      report = '<div class="practice-report" role="status"><h3>Contract completed</h3>' +
        '<p>' + esc(scene) + '</p><div class="practice-rewards"><span>+' +
        latestContract.reward + ' gold</span><span>+' + latestContract.xp_gained +
        ' XP</span></div></div>';
    }
    return report + panel(title, "",
      items || '<p class="empty">No contracts are posted here.</p>');
  }
  function renderMercenaryJobs() {
    return heading("", "Mercenary Jobs", "") +
      '<section class="story-panel"><h3>Work for hire</h3>' +
      '<p>Patrol the city, assist the magical guild, deliver church supplies, or take merchant contracts. ' +
      'Each completed job uses the existing city-funded rewards and cooldown limits.</p></section>' +
      '<div class="stack">' +
      contractBoard("warriors", "Warrior contracts") +
      contractBoard("mageguild", "Mage contracts") +
      contractBoard("church", "Church contracts") +
      contractBoard("job", "Merchant contracts") +
      '</div>';
  }
  function renderChurch() {
    const state = ctx.getState();
    const service = state.church || {};
    return heading("", "Church of the Hearth", "") +
      '<section class="story-panel"><h3>The candlelit nave</h3>' +
      '<p>The sisters keep a lamp lit for travelers returning injured from the roads. ' +
      '"We turn away no prayer," says the matron, "but herbs and bandages cost coin."</p>' +
      (service.used_today ? '<p class="small">You have received your treatment today.</p>' : '') +
      button("Receive healing · " + money(service.price || 20),
        'data-ui="church-heal"' + disabled(!service.available ||
        state.player.gold < service.price || isBusy()), "gold") +
      '</section>';
  }
  function renderTrack() {
    const state = ctx.getState();
    const track = state.track || {}, p = state.player;
    const horses = (track.horses || []).map(h => {
      const eligible = !isBusy() && p.stamina >= track.race_cost &&
        p.gold >= track.entry_fee && !track.cooldown_remaining;
      return '<div class="mini-card"><div class="mini-card-title">♞ ' +
        esc(h.name) + '</div><div class="mini-card-sub">Speed ' + h.speed +
        ' · Endurance ' + h.stamina + ' · ' +
        (h.owned ? 'In your stable' : money(h.price)) + '</div>' +
        (h.owned ?
          button('Race · ' + money(track.entry_fee),
            'data-ui="horse-race" data-breed="' + esc(h.id) + '"' +
            disabled(!eligible), "gold") :
          button('Buy · ' + money(h.price),
            'data-ui="horse-buy" data-breed="' + esc(h.id) + '"' +
            disabled(isBusy() || p.gold < h.price), "secondary")) +
        '</div>';
    }).join('');
    const last = track.last_result;
    return heading("", "", "") +
      '<section class="story-panel"><h3>The Five Cities Circuit</h3>' +
      '<p>In Oathmere, a rider is judged as much by the patience of their mount as ' +
      'the courage of their hand. At the city track, novice jockeys race for ' +
      'coin and honor beneath the pennants of the five roads.</p>' +
      '<p>Riding experience: <strong>' + (track.riding_xp || 0) +
      ' XP</strong> · Entry ' + money(track.entry_fee || 10) +
      ' · ' + (track.race_cost || 15) + ' stamina · ' +
      'Winner receives 30 gold.</p>' +
      (track.cooldown_remaining ? '<p>Next race in ' +
        dur(track.cooldown_remaining) + ' simulated time.</p>' : '') +
      '</section>' + panel("Your stable & horse market",
        "Buy horses permanently; their speed and endurance determine race performance.",
        '<div class="card-grid">' + horses + '</div>') +
      (last ? panel("Latest race", "",
        '<p><strong>' + esc(pretty(last.breed)) + ' placed #' + last.placing +
        '</strong> · Your score ' + last.score + ' · Opponents ' +
        last.rival_scores.join(' / ') + '</p>' +
        '<p>+' + last.xp + ' riding XP · Prize ' + money(last.prize) + '</p>') : '');
  }
  function renderGuilds() {
    const state = ctx.getState();
    const info = state.guilds || {}, own = info.my_guild, rules = info.rules || {};
    const directory = (info.directory || []).map(g =>
      '<div class="equipment-item"><div><h3>' + esc(g.name) +
      '</h3><p>' + g.members + ' members</p></div></div>').join('');
    let myGuild = '';
    if (own) {
      const roster = Object.entries(own.members).map(([id, role]) =>
        '<div class="inventory-row"><span>' + esc(id === 'hero' ? state.name : id) +
        '</span>' + chip(pretty(role)) + '</div>').join('');
      myGuild = panel(own.name, 'Your ' + pretty(own.role) + ' role',
        '<div class="resource-list">' +
        chip('Rating ' + own.rating) + chip('Wins ' + own.wins) +
        chip('Losses ' + own.losses) + '</div>' +
        '<h4>Members</h4>' + roster +
        '<p class="small">Invitations, officer appointments and membership ' +
        'permissions exist in the engine. A multi-account server is required ' +
        'to make guild recruitment useful across real players.</p>' +
        button('Leave guild', 'data-ui="guild-leave"' + disabled(isBusy() ||
        Object.keys(own.members).length > 1 && own.role === 'leader'), 'ghost'));
    } else {
      myGuild = panel('Found your guild',
        'Choose a banner name and pay a one-time 100 gold charter fee.',
        '<div class="button-group"><input class="field" id="guild-name" maxlength="40" ' +
        'placeholder="Guild name (3–40 characters)" aria-label="Guild name">' +
        button('Found Guild · ' + money(info.founding_cost || 100),
          'data-ui="guild-found"' + disabled(isBusy() ||
          state.player.gold < (info.founding_cost || 100)), 'gold') + '</div>');
    }
    return heading('', 'Guilds', '') +
      '<div class="stack">' + myGuild +
      panel('The Guild Hall', 'Existing banners', directory ||
        '<p class="small">No guilds have been founded yet.</p>') +
      panel('Ranked wars — framework', 'The system is designed, but matchmaking and war attacks are not enabled.',
        '<p>Two guilds will face a ' + (rules.notice_minutes / 60) +
        '-hour preparation period followed by at most ' +
        (rules.duration_minutes / 60) + ' hours of competition.</p>' +
        '<div class="resource-list">' + chip('Cumulative War Score') +
        chip('Roster lock') + chip('No outside interference') +
        chip('Surrender available') + '</div>' +
        '<p class="small">Score targets will scale with roster size. ' +
        'Participation, performance, and victory each contribute to rewards. ' +
        'The Elo-based matchmaker, fortifications and reward payments are future work.</p>') +
      '</div>';
  }
  function renderMerits() {
    const state = ctx.getState();
    const info = state.merits || {};
    const feats = (info.achievements || []).map(f =>
      '<div class="equipment-item"><div><h3>' + esc(f.name) +
      '</h3><p>' + esc(f.description) + '</p></div>' +
      (f.claimed ? chip('Claimed') :
        button(f.eligible ? 'Claim merit' : 'Locked',
          'data-ui="merit-claim" data-achievement="' + esc(f.id) + '"' +
          disabled(!f.eligible || isBusy()), f.eligible ? 'gold' : 'ghost')) +
      '</div>').join('');
    const upgrades = (info.upgrades || []).map(perk =>
      '<div class="equipment-item"><div><h3>' + esc(perk.name) +
      '</h3><p>' + esc(perk.description) + '</p></div>' +
      (perk.owned ? chip('Owned') :
        button('Buy · ' + perk.cost + ' merits',
          'data-ui="merit-buy" data-perk="' + esc(perk.id) + '"' +
          disabled(info.balance < perk.cost || isBusy()), 'secondary')) +
      '</div>').join('');
    return '<div class="stack">' +
      panel('Your merit ledger', '',
        '<div class="resource-list">' + chip('Available: ' + (info.balance || 0)) +
        chip('Lifetime earned: ' + (info.total_earned || 0)) + '</div>') +
      panel('Achievements', 'Complete goals throughout Oathmere.', feats) +
      panel('Permanent improvements', 'Spend earned merits on carefully bounded advantages.', upgrades) +
      '</div>';
  }
  function renderCityHall() {
    return '<section class="story-panel"><h3>Quests</h3>' +
      '<p>New adventurers will begin with a guided introduction to Oathmere. ' +
      'As you grow in experience, new missions and adventures will become available.</p>' +
      '<p class="small">Quests are coming soon.</p></section>';
  }
  function renderJob() {
    const state = ctx.getState();
    const w = state.player.work;
    return heading("", "Occupation", "") +
      panel("Work Stats", "",
        characterRow("Manual", w.manual) +
        characterRow("Intelligence", w.intelligence) +
        characterRow("Endurance", w.endurance) +
        characterRow("Shifts completed", w.shifts));
  }
  function renderTraining() {
    const state = ctx.getState();
    const pending = ctx.getPending();
    const expandedUniversitySchool = ctx.getExpandedUniversitySchool();
    const hall = state.training_hall || { schools: [], active: null };
    const studies = hall.active;
    const studying = studies ?
      '<p class="small university-progress">Studying ' +
      esc(pretty(studies.school)) + ' · Course ' + (studies.index + 1) +
      ' · ' + Math.max(1, Math.ceil(studies.remaining_minutes / 1440)) +
      ' simulated days remaining</p>' : '';
    const tiles = hall.schools.map(school => {
      const courses = school.courses.map((course, index) => {
        const fee = Number(course.tuition);
        const blocked = pending || isBusy() || state.player.gold < fee || !course.available;
        const action = course.completed ? chip("Completed") :
          course.active ? chip("In progress") :
          button("Enroll · " + money(fee),
            'data-ui="course-enroll" data-school="' + esc(school.id) +
            '" data-index="' + index + '"' + disabled(blocked), "secondary");
        return '<div class="university-course"><div><strong>' +
          esc(course.name) + '</strong><small>' + course.days +
          ' days · +' + course.stat_bonus + ' ' + esc(pretty(school.stat)) +
          ' · Tuition ' + money(fee) + '</small></div>' + action + '</div>';
      }).join('');
      return '<details class="university-school" data-university="' +
        esc(school.id) + '"' +
        (expandedUniversitySchool === school.id ? ' open' : '') +
        '><summary><span><strong>' +
        esc(school.name) + '</strong><small>' +
        school.completed + ' of ' + school.total + ' courses completed</small></span>' +
        '<span class="university-expand" aria-hidden="true">⌄</span></summary>' +
        '<div class="university-school-body">' +
        '<p class="small">Graduation: 1 merit' +
        (school.capstone_perk ? ' · +' + school.capstone_perk.bonus +
          ' ' + esc(pretty(school.capstone_perk.stat)) : '') +
        (school.martial_perk ? ' · +' + school.martial_perk.bonus +
          ' ' + esc(pretty(school.martial_perk.stat)) : '') +
        '</p>' +
        courses + '</div></details>';
    }).join('');
    return heading("", "University", "") + studying +
      '<div class="university-grid">' + tiles + '</div>';
  }
  function renderTavern() {
    const secureWorldClock = ctx.getSecureWorldClock();
    const pending = ctx.getPending();
    return heading("A place to rest", "Wayfarer's Tavern",
      secureWorldClock ? "Take shelter and listen to rumors." :
        "Take shelter, listen to rumors, or advance the simulation.") +
      '<section class="story-panel"><div class="section-kicker">The common room</div>' +
      '<h3>A seat by the hearth</h3><p>The innkeeper nods toward an empty bench. ' +
      'Around you, travelers discuss the roads and the promise of work in distant cities.</p>' +
      (secureWorldClock ?
        '<p class="small">Your character recuperates as real server time passes. ' +
        'Resting here does not accelerate shared time.</p>' :
        '<p class="small">Resting advances simulated world time and restores resources. ' +
        'The clock in the header continues to show real Eastern time.</p>' +
        '<div class="button-group">' +
        button("Rest 1 hour", 'data-ui="advance" data-minutes="60"' + disabled(pending), "secondary") +
        button("Pass 6 hours", 'data-ui="advance" data-minutes="360"' + disabled(pending), "ghost") +
        '</div>') + '</section>';
  }


  return { renderMercenaryJobs, renderChurch, renderTrack,
    renderGuilds, renderMerits, renderCityHall, renderJob, renderTraining, renderTavern };
}
