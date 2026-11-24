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
      const can = !isBusy() && !state.active_contract &&
        contract.cooldown_available && contract.can_pay &&
        contract.has_material &&
        p.stamina >= contract.stamina && p.mana >= contract.mana;
      const costs = [contract.stamina ? contract.stamina + ' stamina' : null,
        contract.mana ? contract.mana + ' mana' : null].filter(Boolean);
      const itemRequired = contract.material === "herbs" ? "1 bunch of herbs" :
        "1 " + pretty(contract.material);
      const explanation = !contract.can_pay ?
        'The city cannot currently fund this offer.' :
        state.active_contract ? 'Finish your current assignment first.' :
        contract.cooldown_remaining ?
          'Available in ' + dur(contract.cooldown_remaining) + '.' :
        !contract.has_material ?
          'You need ' + itemRequired + ' to initiate this contract (consumed upon start).' :
        p.mana < contract.mana ?
          'You need ' + contract.mana + ' mana to initiate this contract.' :
        p.stamina < contract.stamina ?
          'You need ' + contract.stamina + ' stamina to initiate this contract (you have ' +
          p.stamina + ').' : '';
      return '<div class="contract-card"><div><h3>' + esc(contract.title) + '</h3>' +
        '<p>' + esc(contract.description) + '</p>' +
        '<div class="contract-terms"><span>+' + contract.reward + ' gold</span>' +
        (costs.length ? '<span>Start: ' + esc(costs.join(' · ')) + '</span>' : '') +
        '<span>' + esc(dur(contract.duration_minutes)) + ' shift</span></div>' +
        (explanation ? '<p class="small">' + esc(explanation) + '</p>' : '') +
        (contract.material && contract.has_material && !explanation ?
          '<p class="small">' + esc(itemRequired) +
          ' will be consumed upon start.</p>' : '') +
        '</div>' +
        button("Start shift", 'data-ui="contract" data-contract="' +
          esc(contract.id) + '"' + disabled(!can), "secondary") + '</div>';
    }).join("");
    let report = "";
    if (latestContract && state.active_contract &&
        latestContract.contract_id === state.active_contract.contract_id &&
        offers.some(c => c.id === latestContract.contract_id)) {
      report = '<div class="practice-report" role="status"><h3>Job initiated</h3>' +
        '<p>' + esc(latestContract.title) + ' · Payment and XP awarded at shift completion.</p></div>';
    }
    return report + panel(title, "",
      items || '<p class="empty">No contracts are posted here.</p>');
  }
  function renderMercenaryJobs() {
    const active = ctx.getState().active_contract;
    const activePanel = active ? panel("Current assignment", "",
      '<p><strong>' + esc(active.title) + '</strong> · ' +
      esc(dur(active.remaining_minutes)) +
      ' remaining. Wages and XP are awarded on completion.</p>') : "";
    return heading("", "Mercenary Jobs", "") +
      '<div class="stack">' + activePanel +
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
    return '<section class="story-panel"><h3>Riding</h3>' +
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
    const info = state.guilds || {}, own = info.my_guild;
    const war = info.war, rules = info.rules || {};
    const busy = isBusy();
    const players = state.users || [];
    const display = id => {
      const found = players.find(p => p.id === id);
      return own?.member_names?.[id] || found?.name ||
        (id === state.actor_id || id === "hero" ? state.name : "Unknown adventurer");
    };
    const rights = own?.my_rights || [];
    const can = right => rights.includes(right);
    const directory = (info.directory || []).map(g =>
      '<div class="equipment-item"><div><strong>' + esc(g.name) +
      '</strong><p class="small">' + g.members + ' members</p></div></div>').join('');
    const invites = (info.invitations || []).map(inv =>
      '<div class="equipment-item"><span>Invitation: ' + esc(inv.name) + '</span>' +
      button('Accept', 'data-ui="guild-join" data-guild="' + esc(inv.id) + '"' +
        disabled(busy), 'gold') + '</div>').join('');
    if (!own) {
      return heading('', 'Guilds', '') + '<div class="stack">' +
        (invites ? panel('Guild invitations', '', invites) : '') +
        panel('Found a guild', 'Choose a name and pay a one-time 100 gold charter fee.',
          '<div class="button-group"><input class="field" id="guild-name" ' +
          'minlength="3" maxlength="40" placeholder="Guild name (3–40 characters)" ' +
          'aria-label="Guild name">' +
          button('Found Guild · ' + money(info.founding_cost || 100),
            'data-ui="guild-found"' +
            disabled(busy || state.player.gold < (info.founding_cost || 100)), 'gold') +
          '</div><p class="small">Guild names must contain between 3 and 40 characters.</p>') +
        panel('Guild Hall', 'Established banners', directory ||
          '<p class="small">No guilds founded yet.</p>') + '</div>';
    }

    const roster = Object.entries(own.members).map(([id, role]) => {
      const granted = own.rights?.[id] || [];
      const manage = own.role === 'leader' && id !== state.actor_id && id !== 'hero';
      const controls = manage ?
        '<details class="war-member-permissions"><summary>Manage member rights</summary>' +
        '<div class="war-rights">' +
        ['invite', 'enlist', 'milestones', 'spoils'].map(right =>
          button((granted.includes(right) ? '✓ ' : '+ ') + right,
            'data-ui="guild-right" data-member="' + esc(id) +
            '" data-right="' + right + '" data-enabled="' +
            (!granted.includes(right)) + '"' + disabled(busy),
            granted.includes(right) ? 'secondary' : 'ghost')).join('') +
        button(role === 'officer' ? 'Remove officer' : 'Make officer',
          'data-ui="guild-role" data-member="' + esc(id) + '" data-role="' +
          (role === 'officer' ? 'member' : 'officer') + '"' + disabled(busy), 'ghost') +
        '</div></details>' : (granted.length ? '<span class="small">' +
          esc(granted.join(', ')) + '</span>' : '');
      return '<div class="war-roster-entry"><div><strong>' + esc(display(id)) +
        '</strong> ' + chip(role) + '</div>' + controls + '</div>';
    }).join('');

    const eligibleTargets = players.filter(p => p.kind === 'human' &&
      !own.members[p.id] && p.id !== state.actor_id);
    const recruitment = can('invite') ?
      '<div class="button-group"><select class="field" id="guild-invite-target" ' +
      'aria-label="Player to invite"><option value="">Choose player</option>' +
      eligibleTargets.map(p => '<option value="' + esc(p.id) + '">' +
        esc(p.name) + '</option>').join('') + '</select>' +
      button('Invite', 'data-ui="guild-invite"' + disabled(busy), 'secondary') +
      '</div>' : '';
    const guildPanel = panel(own.name, 'Guild Hall',
      '<div class="resource-list">' + chip('Rating ' + own.rating) +
      chip('Wins ' + own.wins) + chip('Losses ' + own.losses) +
      chip(Object.keys(own.members).length + '/20 members') + '</div>' +
      '<h4>Members & rights</h4>' + roster + recruitment +
      '<p class="small">Only the leader can grant individual management rights. ' +
      'The milestones right allows that member to activate a war ability.</p>' +
      button('Leave guild', 'data-ui="guild-leave"' +
        disabled(busy || (own.role === 'leader' &&
          Object.keys(own.members).length > 1)), 'ghost'));

    const enlist = can('enlist') ?
      button(own.enlisted ? 'Withdraw war registration' : 'Sign up for weekly war',
        'data-ui="guild-enlist" data-enabled="' + (!own.enlisted) + '"' +
        disabled(busy || (!own.enlisted && Object.keys(own.members).length < 10)
          || war && ['notice','live'].includes(war.status)), 'gold') : '';
    const availability = '<p class="small">Weekly matching · 10–20 guild members required. ' +
      'Next matching in ' + esc(dur(Math.max(0, (info.next_match_minute || 0) -
      state.minute))) + '. Matched guilds get 24 hours notice and fight at Crownreach.</p>';
    const capital = (state.cities || []).find(c => c.id === 'crownreach')?.name || 'Crownreach';
    const atWarfront = state.player.city === 'crownreach' && !state.player.destination &&
      !state.world_map?.in_wilderness;
    const activeWar = war && ['notice','live'].includes(war.status);
    const practice = own.role === 'leader' ?
      button('Start solo practice vs Ashen Company', 'data-ui="war-practice"' +
        disabled(busy || activeWar || !atWarfront), 'secondary') +
      (!atWarfront ? '<p class="small">Travel to ' + esc(capital) +
        ' to start solo practice.</p>' + button('Open world map', 'data-tab="world"', 'ghost') :
        activeWar ? '<p class="small">Finish the current clash before starting another.</p>' :
        '<p class="small">Solo practice is available now. No other players are required.</p>') :
      '<p class="small">Your guild leader can start a solo practice match.</p>';

    let warContent = '';
    if (war) {
      const mine = war.mine, other = mine === war.guild_a ? war.guild_b : war.guild_a;
      const ownRoster = mine === war.guild_a ? war.roster_a : war.roster_b;
      const enemyRoster = mine === war.guild_a ? war.roster_b : war.roster_a;
      const myScore = mine === war.guild_a ? war.progress_a : war.progress_b;
      const enemyScore = mine === war.guild_a ? war.progress_b : war.progress_a;
      const myPressure = mine === war.guild_a ? war.pressure_a : war.pressure_b;
      const enemyPressure = mine === war.guild_a ? war.pressure_b : war.pressure_a;
      const myName = mine === war.guild_a ? war.name_a : war.name_b;
      const enemyName = mine === war.guild_a ? war.name_b : war.name_a;
      const pressureGoal = war.advantage === null ? rules.gain_hits : rules.break_hits;
      const pressureCopy = war.advantage === null ?
        'First to ' + rules.gain_hits + ' hits takes advantage' :
        war.advantage === mine ? 'Defend: opponent needs ' + rules.break_hits +
          ' hits to break your advantage' :
          'Counterattack: ' + rules.break_hits + ' hits to break their advantage';
      const powerNames = {
        field_hospital: 'Field Hospital', war_horn: 'War Horn', final_rally: 'Final Rally'
      };
      const powerDescriptions = {
        field_hospital: 'Reduce all routed teammates by 5 minutes',
        war_horn: '+50% progress speed for 10 minutes while advantage holds',
        final_rally: 'Restore every routed teammate'
      };
      const milestones = ['field_hospital', 'war_horn', 'final_rally'].map((power, index) => {
        const unlocked = (war.unlocks?.[mine] || []).includes(power);
        const used = (war.used?.[mine] || []).includes(power);
        const ready = unlocked && !used && can('milestones') &&
          war.status === 'live' &&
          (power !== 'war_horn' || war.advantage === mine);
        return '<div class="war-milestone"><div><strong>' + [25,50,75][index] +
          '% · ' + powerNames[power] + '</strong><p class="small">' +
          powerDescriptions[power] + '</p></div>' +
          button(used ? 'Used' : !unlocked ? 'Locked' :
                 !can('milestones') ? 'Leader right required' : 'Activate',
            'data-ui="war-milestone" data-power="' + power + '"' +
            disabled(busy || !ready), ready ? 'gold' : 'ghost') + '</div>';
      }).join('');
      const fighterRow = (f, enemy) => {
        const routed = f.routed_remaining > 0;
        const name = f.name === f.id ? display(f.id) : f.name;
        const condition = routed ? 'Routed ' + dur(f.routed_remaining) :
          !f.present ? 'Away' : 'Ready';
        const attackable = enemy && war.status === 'live' && war.present &&
          !war.my_routed && f.present && !routed;
        const restore = !enemy && routed && war.present && !war.my_routed &&
          war.status === 'live' && state.player.mana >= 5 &&
          !war.restore_cooldown;
        return '<div class="war-fighter"><div><strong>' + esc(name) + '</strong>' +
          '<span class="small"> · ' + esc(condition) + ' · Honor ' + f.honor +
          '</span></div>' + (attackable ?
            button('Attack', 'data-ui="war-attack" data-target="' + esc(f.id) +
              '"' + disabled(busy), 'secondary') : restore ?
            button('Restore', 'data-ui="war-restore" data-target="' + esc(f.id) +
              '"' + disabled(busy), 'ghost') : '') + '</div>';
      };
      const stage = war.status === 'live' ?
        '<div class="war-summary">' +
        '<div class="war-score"><strong>' + esc(myName) + '</strong>' +
        '<div class="war-progress"><span style="width:' + myScore +
        '%"></span></div><b>' + myScore + '%</b></div>' +
        '<div class="war-score"><strong>' + esc(enemyName) + '</strong>' +
        '<div class="war-progress enemy"><span style="width:' + enemyScore +
        '%"></span></div><b>' + enemyScore + '%</b></div>' +
        '<p><strong>' + (war.advantage === mine ? 'Your guild holds advantage' :
          war.advantage === other ? esc(enemyName) + ' holds advantage' :
          'Advantage contested') + '</strong> · ' +
        esc(dur(war.remaining_minutes)) + ' remaining</p>' +
        '<p class="small">' + pressureCopy + ' · Your hits ' + myPressure +
        '/' + pressureGoal + ' · Their hits ' + enemyPressure + '/' + pressureGoal +
        '</p></div>' : war.status === 'notice' ?
        '<p>Battle starts in ' + esc(dur(Math.max(0, war.start_minute - state.minute))) +
        '. Travel to Crownreach to prepare.</p>' :
        '<p>War complete. Winner: ' +
        esc(war.winner_id === mine ? myName : war.winner_id === other ?
          enemyName : 'Draw') + '. Honor totals are final.</p>';
      const joinLeave = war.status === 'live' ?
        war.present ?
          button('Leave battlefield', 'data-ui="war-leave"' +
            disabled(busy), 'ghost') :
          button('Enter warfront', 'data-ui="war-join"' +
            disabled(busy || war.my_routed ||
              state.player.city !== 'crownreach' ||
              state.player.destination), 'gold') : '';
      const treatment = war.status === 'live' && war.my_routed ?
        '<p>Routed: ' + dur(war.my_routed) + ' remaining</p>' +
        button('Use Field Dressing · ' + war.my_dressings + ' left',
          'data-ui="war-dressing"' +
          disabled(busy || !war.my_dressings || war.dressing_cooldown),
          'secondary') : '';
      const assist = war.status === 'live' && war.present ?
        (war.assistable || []).map(id => button('Assist ' + display(id),
          'data-ui="war-assist" data-attacker="' + esc(id) + '"' +
          disabled(busy || war.my_routed), 'secondary')).join('') : '';
      const chronicleNames = [
        ...ownRoster, ...enemyRoster
      ].map(f => [f.id, f.name === f.id ? display(f.id) : f.name]);
      chronicleNames.push([war.guild_a, war.name_a], [war.guild_b, war.name_b]);
      chronicleNames.sort((a,b) => b[0].length - a[0].length);
      const chronicle = (war.recent || []).map(line => {
        const readable = chronicleNames.reduce(
          (message, pair) => message.split(pair[0]).join(pair[1]), line);
        return '<div class="war-event">' + esc(readable) + '</div>';
      }).join('');
      const honor = [...ownRoster, ...enemyRoster].sort(
        (a,b) => b.honor - a.honor).slice(0,20).map(f =>
        '<div class="war-fighter"><span>' + esc(f.name === f.id ?
          display(f.id) : f.name) + '</span><strong>' + f.honor +
          ' Honor</strong></div>').join('');
      warContent = panel('Banner Clash · ' +
          (war.practice ? 'Practice match' : 'Ranked match'),
          war.status === 'live' ? 'Battlefront · Crownreach' :
          war.status === 'notice' ? 'Preparing for battle' : 'Battle results',
          stage + '<div class="button-group">' + joinLeave + treatment + assist +
          '</div>' +
          (war.status === 'live' ?
            '<div class="war-columns"><div><h4>Opposing fighters</h4>' +
            enemyRoster.map(f => fighterRow(f, true)).join('') +
            '</div><div><h4>Your fighters</h4>' +
            ownRoster.map(f => fighterRow(f, false)).join('') +
            '</div></div>' +
            '<h4>One-use milestone abilities</h4>' + milestones : '') +
          '<div class="war-columns"><div><h4>Honor ledger</h4>' +
          honor + '</div><div><h4>War Chronicle</h4>' +
          chronicle + '</div></div>' +
          '<p class="small">Honor measures the difficulty of successful hits. ' +
          'It guides later spoils decisions; practice matches award no ranked prizes.</p>');
    }
    const history = (info.history || []).filter(entry =>
      !war || entry.id !== war.id).map(entry =>
      '<details class="war-rules"><summary>' + esc(entry.id) +
      ' · ' + esc(entry.result) + ' · ' + entry.progress +
      '% progress' + (entry.practice ? ' · Practice' : '') +
      '</summary>' + [...entry.honor].sort((a,b) => b.score - a.score)
        .map(line => '<div class="war-fighter"><span>' +
          esc(display(line.id)) + '</span><strong>' + line.score +
          ' Honor</strong></div>').join('') + '</details>').join('');
    return heading('', 'Guilds', '') +
      '<div class="stack">' + warContent +
      panel('Guild warfare', own.enlisted ? 'Registered for weekly matching' :
        'Weekly matchmaking',
        availability + '<div class="button-group">' + enlist + practice +
        '</div><details class="war-rules"><summary>Banner Clash rules</summary>' +
        '<p>10 hits gain advantage; 7 opposing hits break it. ' +
        'Control progress is permanent: 60 cumulative minutes wins. ' +
        'Routed fighters recover in 10–15 minutes. ' +
        'Milestones unlock at 25%, 50%, and 75%. ' +
        'Wars end after 12 hours if neither guild reaches 100%.</p>' +
        '<p>Leaving a contested battlefield concedes a hit. ' +
        'Group attacks require another fighter to join an active duel. ' +
        'No automatic spoils distribution is enabled.</p></details>') + guildPanel +
      (history ? panel('Completed wars', 'Past Honor ledgers for contribution review',
        history) : '') +
      panel('Guild directory', 'Other banners', directory ||
        '<p class="small">No other guilds yet.</p>') + '</div>';
  }
  function renderMerits() {
    const state = ctx.getState();
    const info = state.merits || {};
    const feats = (info.achievements || []).map(f =>
      '<div class="equipment-item"><div><h3>' + esc(f.name) +
      '</h3><p>' + esc(f.description) + '</p></div>' +
      (f.claimed ? chip('Claimed') :
        button(f.eligible ? 'Claim Renown' : 'Locked',
          'data-ui="merit-claim" data-achievement="' + esc(f.id) + '"' +
          disabled(!f.eligible || isBusy()), f.eligible ? 'gold' : 'ghost')) +
      '</div>').join('');
    const upgrades = (info.upgrades || []).map(perk =>
      '<div class="equipment-item"><div><h3>' + esc(perk.name) +
      '</h3><p>' + esc(perk.description) + '</p></div>' +
      (perk.owned ? chip('Owned') :
        button('Buy · ' + perk.cost + ' Renown',
          'data-ui="merit-buy" data-perk="' + esc(perk.id) + '"' +
          disabled(info.balance < perk.cost || isBusy()), 'secondary')) +
      '</div>').join('');
    return '<div class="merits-layout">' +
      panel('Your Renown ledger', '',
        '<div class="resource-list">' + chip('Available to spend: ' + (info.balance || 0)) +
        chip('Lifetime earned: ' + (info.total_earned || 0)) + '</div>') +
      '<div class="merits-columns">' +
      panel('Achievements', 'Complete goals throughout Oathmere.', feats) +
      panel('Permanent improvements', '', upgrades) +
      '</div></div>';
  }
  function renderHarbor() {
    const state = ctx.getState();
    const inCrownreach = state.player.city === "crownreach" &&
      !state.player.destination && !state.world_map?.in_wilderness;
    if (!inCrownreach) return heading("", "Harbor", "") +
      panel("Crownreach Harbor", "",
        '<p class="small">Visit Crownreach to explore its harbor.</p>');
    return heading("", "Harbor", "") +
      '<section class="story-panel harbor-scene">' +
      '<div class="section-kicker">Crownreach waterfront</div>' +
      '<h3>Beyond the city walls, the harbor awaits</h3>' +
      '<p>Weathered piers stretch toward the open water. Boats and fishing ' +
      'will have a home here in a future chapter of Oathmere.</p>' +
      '<p class="small">The harbor is a placeholder for now. ' +
      'There are no voyages, fishing actions, or trades available yet.</p>' +
      '</section>';
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
    const studying = studies ? (() => {
      const school = hall.schools.find(item => item.id === studies.school);
      const course = school && school.courses[studies.index];
      const total = (course ? course.days : 1) * 1440;
      const remaining = Math.max(0, Number(studies.remaining_minutes) || 0);
      const elapsed = Math.min(total, Math.max(0, total - remaining));
      const name = course ? course.name : pretty(studies.school);
      return '<section class="university-progress" aria-label="Current university course">' +
        '<strong>Studying ' + esc(name) + '</strong>' +
        '<time class="university-countdown" role="timer" aria-live="off" ' +
        'data-university-countdown="true" ' + ctx.timerAttrs('', remaining * 60) +
        '>' + esc(ctx.timerText(remaining * 60)) + ' remaining</time>' +
        '<progress class="university-progress-meter" value="' + elapsed +
        '" max="' + total + '" data-total-minutes="' + total +
        '" aria-label="' + esc(name) + ' course progress"></progress>' +
        '<small class="university-progress-percent">' +
        Math.floor(elapsed * 100 / total) + '% complete</small>' +
        '</section>';
    })() : '';
    const tiles = hall.schools.map(school => {
      const schoolActive = Boolean(studies && studies.school === school.id);
      const courses = school.courses.map((course, index) => {
        const activeCourse = schoolActive && studies.index === index;
        const fee = Number(course.tuition);
        const blocked = pending || isBusy() || state.player.gold < fee || !course.available;
        const action = course.completed ? chip("Completed") :
          activeCourse ? chip("In progress") :
          button("Enroll · " + money(fee),
            'data-ui="course-enroll" data-school="' + esc(school.id) +
            '" data-index="' + index + '"' + disabled(blocked), "secondary");
        return '<div class="university-course' +
          (activeCourse ? ' is-active' : '') + '"><div><strong>' +
          esc(course.name) + '</strong><small>' +
          (activeCourse ? 'In progress' : course.days + ' days') +
          ' · +' + course.stat_bonus + ' ' + esc(pretty(school.stat)) +
          '</small></div>' + action + '</div>';
      }).join('');
      return '<details class="university-school' +
        (schoolActive ? ' is-active' : '') + '" data-university="' +
        esc(school.id) + '"' +
        (expandedUniversitySchool === school.id ? ' open' : '') +
        '><summary><span><strong>' +
        esc(school.name) + '</strong><small>' +
        school.completed + ' of ' + school.total + ' courses completed</small></span>' +
        '<span class="university-expand" aria-hidden="true">⌄</span></summary>' +
        '<div class="university-school-body">' +
        ((school.capstone_perk || school.martial_perk) ?
          '<p class="small">Graduation bonus' +
          (school.capstone_perk ? ': +' + school.capstone_perk.bonus +
            ' ' + esc(pretty(school.capstone_perk.stat)) : '') +
          (school.martial_perk ? (school.capstone_perk ? ' · +' : ': +') +
            school.martial_perk.bonus + ' ' +
            esc(pretty(school.martial_perk.stat)) : '') + '</p>' : '') +
        courses + '</div></details>';
    }).join('');
    return heading("", "University", "") + studying +
      '<div class="university-grid">' + tiles + '</div>';
  }
  function renderTavern() {
    const state = ctx.getState();
    const p = state.player, t = state.tavern || {};
    const remaining = t.room_cooldown_remaining || 0;
    const status = remaining ?
      '<p class="small">Another room in ' + esc(dur(remaining)) + '.</p>' : '';
    const cutoff = t.mead_remaining <= 0;
    return heading("", "Wayfarer's Tavern", "") +
      '<div class="stack">' +
      panel("Rent a room", "",
        '<p>Double Health, Stamina and Mana recovery for 30 minutes.</p>' +
        status +
        button("Rent room · " + money(t.room_price || 12),
          'data-ui="tavern-room"' +
          disabled(!t.room_available || isBusy()), "secondary")) +
      panel("Mug of mead", "",
        '<p>Enjoy a mug of mead.</p>' +
        (cutoff ? '<p class="small">You are cut off until noon Oathmere time.</p>' :
          '<p class="small">' + t.mead_remaining + ' of ' + t.mead_limit +
          ' drinks remaining until noon.</p>') +
        button(cutoff ? "Cut off until noon" : "Buy mead · " + money(t.mead_price || 3),
          'data-ui="tavern-mead"' + disabled(!t.mead_available || isBusy()),
          "secondary")) +
      (!ctx.getSecureWorldClock() ? panel("Pass time", "",
        button("Rest 1 hour", 'data-ui="advance" data-minutes="60"' +
          disabled(ctx.getPending()), "secondary") +
        button("Pass 6 hours", 'data-ui="advance" data-minutes="360"' +
          disabled(ctx.getPending()), "ghost")) : '') +
      '</div>';
  }

  return { renderMercenaryJobs, renderChurch, renderTrack, renderHarbor,
    renderGuilds, renderMerits, renderCityHall, renderJob, renderTraining, renderTavern };
}
