# First playable web client — local single-player vertical slice

## Features

The responsive browser UI is backed directly by the \`WorldEngine\` and therefore inherits its item inventory and gold conservation, cooldowns, merchant stocks, regional prices, mana and house costs. The browser never directly edits gold, XP or city stock.

**Screens**

- **Explore:** Five-city travel, exact personalized trip durations, progress while traveling, resource harvesting and cooldowns, rest/day advancement, inventory and an activity chronicle.
- **Market:** Local merchant bids and asks for each raw material, actual city stock/funds and buy/sell quantity controls. Travel with goods and sell at higher destination prices.
- **Magic:** All six schools and their 36 nodes. See requirements, unlock nodes using Insight, practice with mana, and select up to two Tier III attunements. Magic effects and paid jobs are *not* available yet.
- **Property:** Buy and upgrade a home; purchase stables or carriage houses, buy a horse or carriage, and choose transport. Homes add XP in their home city, and purchased vehicles affect road journey time and travel carrying capacity.

The first player starts in Goldmeadow with 240 gold, and can trade, travel and gather to earn more. Resource deposits and hourly regeneration are part of the existing simulation. The clock is explicitly advanced by pressing **Rest 1 hour / Pass 6 hours / Next day**, or **Complete journey** after beginning travel. The world **does not continue advancing in real time while the app is closed**, nor do independent background NPCs run in this specific solo session. Those are future systems.

## Quick start

Requires Python 3.11+.

\`\`\`bash
python -m pip install -e .
python -m medieval_world_sim.web
\`\`\`

Then open \`http://127.0.0.1:8765\` on the same computer.

For a phone on the same *trusted private* Wi-Fi or LAN:

\`\`\`bash
python -m medieval_world_sim.web --host 0.0.0.0 --port 8765
\`\`\`

Open \`http://COMPUTER_LAN_IP:8765\` on the phone, enter the access code printed in the server terminal. You may need to permit the computer's firewall to accept local incoming TCP connections on 8765. The phone needs only its browser; the Python server **must remain running on the computer**. This provides a mobile-friendly web UI, not an Android/iOS-native installed application.

**LAN security:** Binding \`0.0.0.0\` intentionally requires an access token. The server rejects cross-origin actions, limits payload sizes, serves only an explicit static-asset allowlist and exposes a limited set of engine actions. However the connection is **unencrypted HTTP**; only run on trusted private networks. Do not port-forward it or deploy directly on a public host. Public deployment requires TLS, strong session authentication, durable transactions and rate limiting.

## Persistence

All state-changing browser actions are validated on the server, and the session saves a versioned JSON journal to \`~/.medieval-world-sim/save.json\` (override with \`--save path\`). The journal stores the character name, initial seed and validated action parameters/IDs and time steps; on restart it reconstructs the authoritative state by replaying the same commands. Saves are atomically replaced after each successful step; failed actions and failed writes do not advance the session state. Unsupported or corrupt save versions fail explicitly rather than silently resetting the player's progress.

The journal is currently single-player and bounded to 20,000 records. Startup replay is linear in the number of actions; production server state snapshots and SQLite/Postgres are future upgrades. Only one server should open a given save path at a time. A new character uses a new save file; there is no in-browser delete/reset control.

## Backend/API

\`GET /\`, \`GET /app.js\`, \`GET /styles.css\` and \`GET /favicon.svg\` serve a static responsive frontend. \`GET /api/state\` returns detached, read-only world views including property definitions, magic node eligibility, city information and market quotes. \`POST /api/new\` creates one character. \`POST /api/action\` invokes an explicitly allowlisted game command with an idempotent request ID. \`POST /api/advance\` advances world time by a bounded integer 1–1440 minutes. \`GET /api/health\` reports process health.

The explicit web action allowlist is **travel, gather, buy/sell raw goods, consume, buy/upgrade homes, build facilities, purchase/select vehicles, unlock/practice/attune magic**. Company ownership, combat, player-versus-player markets, autonomous NPC simulation, world effects and higher-level trading contracts exist partially in the engine but are not yet in the web UI. The client does not pretend to expose those gameplay loops yet.

## Developer commands

\`\`\`bash
PYTHONPATH=src python -m unittest discover -s tests -v
node --check src/medieval_world_sim/web/static/app.js
python -m medieval_world_sim.web --help
\`\`\`

The standard test suite covers end-to-end HTTP action handling, replay, idempotent purchase requests, auth and origin protection, static file boundaries, and genuine game economics as well as the pre-existing simulations.
