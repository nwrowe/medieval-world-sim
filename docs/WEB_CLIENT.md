# First playable web client — local single-player vertical slice

## Features

The responsive browser UI is backed directly by the \`WorldEngine\` and therefore inherits its item inventory and gold conservation, cooldowns, merchant stocks, regional prices, mana and house costs. The browser never directly edits gold, XP or city stock.

**Location-first screens**

- **Navigation:** The top bar contains Home, Equipment, **World**, Chronicle and Search. The left sidebar shows only the current city and its local destinations; there is no separate City Map page or duplicated location links.
- **World Map:** Illustrated fantasy atlas with clickable city markers, legitimate travel durations, resource harvesting and rest.
- **Market:** Buy only goods the local city regularly produces or currently stocks. Goods not carried in the regional inventory are hidden from the buy catalog. Goods the player carries from elsewhere appear in a separate *sell-only imports* panel. Prices, stock, daily quotas and city funds remain authoritative.
- **Inventory:** There is **no twenty-item cap in a city**. Road departure still checks the current carried load against the walking/horse/carriage limit of 12/16/20. Players can transfer stackable goods between their carried inventory and unlimited **city-specific storage** before traveling. Goods stored in one city remain there until the player returns; equipment is currently always carried.
- **Warriors Guild:** A short city-watch patrol pays finite city funds and awards genuine combat XP.
- **Mage Guild:** A copying assignment consumes mana, pays finite city funds and improves work Intelligence. Six-school study remains separately available.
- **Church:** An herb-delivery assignment consumes one real herb from inventory, transfers it into city merchant stock, pays from civic funds and improves work endurance.
- **Job:** A loading shift spends stamina, improves manual work stats, pays real wages and records a completed shift. The old introduction panel is removed.
- **Magic:** Six clickable school tiles show icons and skill progress. Each opens tiered spell rows with clear practice and unlock actions. The four 100-step tier meters reflect existing XP; unlock prerequisites and a **90–98%** success chance remain server-authoritative. Lower-tier practice stops once the next tier is learned. Unlocked spells are labeled as learned, while actual world spell effects remain future work.
- **Property:** Five housing tiers, facilities and faster road vehicles.
- **Training Hall:** Broader educational courses are still a planned feature; the job hall provides initial real work progression.
- **Character Home / Equipment / Chronicle:** Authoritative character statistics, purchased/equipped items, and event-specific Chronicle entries with real Eastern timestamps for newly saved actions.
- **Players (top-right):** A searchable directory of *actual* player accounts in this session. The current Python server holds **one** playable account. PvP requires additional account identity, authentication, and separate stored characters; the UI never invents opponents or allows self-attack.

The compact header has Health, Stamina and Mana progress meters, and shows next recovery in **simulated seconds** on hover when applicable. Three small indicators immediately after Gold show **Job, Food and Potion** cooldown balances. These are independent **stackable queues**, each capped at **24 simulated hours**; a use is refused before it would exceed the cap. Jobs add 60 simulated minutes, bread 30, meals 60, and healing potions 120. Food and potions can be used directly from the carried Inventory screen when the player would benefit from their recovery effects. This is not yet a wall-clock countdown: the current world advances when players rest, travel or explicitly pass time. Stamina normally restores one point every five simulated minutes; mana one point every ten; health has no normal passive tick and recovers from defeat after its recovery period. The rightmost clock shows actual Eastern date/time in 24-hour format.

The **estimated net worth** consists of gold plus the acquisition values of owned property/facilities/vehicles, local resale estimates of raw goods, and appraised gear value. It is not a guarantee of cash liquidation value.

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

## UI refinement — annotated atlas, Chronicle and magic study

- The header shows **Eastern local time in 24-hour notation**, without a timezone suffix. Eastern time is a real-world display clock; explicit `advance` actions still control simulation time, recovery and cooldowns.
- The **Chronicle** uses wall-clock timestamps for newly recorded actions and meaningful event details. Purchases identify the purchased gear and its price; equipment messages identify what was equipped or unequipped; magic practice records success, experience, and mana. Older saves remain loadable, but events written before timestamps were tracked show **“Earlier · timestamp unavailable”** rather than an invented date or repeated simulated hour. New journal records have an optional `recorded_at` UTC ISO string; the saved-game schema version remains 1, and this metadata does not affect simulation logic.
- The **World Map** includes an original SVG fantasy parchment map, with landmarks, royal roads, interactive glowing city buttons and a highlighted current position. Clicking an available distant city uses the existing server-validated travel command. The locations are illustrative, not geographic coordinates.
- **Magic Progression** adds four tier progress meters, each showing a 0–100 proficiency equivalent calculated from **existing school XP** thresholds 0, 30, 120, 350, 1000. They are a visual learning aid rather than hundreds of new skill levels or a new XP currency. Practicing an unlocked spell produces a small text-based event scene matched to the server-reported success, XP, mana cost and Insight; these scenes are flavor only and do not invent physical healing or gold rewards.
- The left city list includes the **Church of the Hearth** and its paid herb-delivery contract. The Armory appears in Crownreach only. Direct healing effects and longer multi-stage quests remain future features.
- The secondary location echo above each page and redundant eyebrow headlines are removed. Character **Home** opens directly with the green character profile card rather than repeating the character name and location above it.

## Persistence

All state-changing browser actions are validated on the server, and the session saves a versioned JSON journal to \`~/.medieval-world-sim/save.json\` (override with \`--save path\`). The journal stores the character name, initial seed and validated action parameters/IDs and time steps; on restart it reconstructs the authoritative state by replaying the same commands. Saves are atomically replaced after each successful step; failed actions and failed writes do not advance the session state. Unsupported or corrupt save versions fail explicitly rather than silently resetting the player's progress.

To preserve **old magic outcomes and save replay**, records that predate the revised 90–98% practice rule and tier lock replay under their original formula. Existing journal actions continue replaying under rulesets 1–2. New actions carry `ruleset: 3` to preserve the original non-stackable job and no-food/potion-cooldown semantics for older actions. The top-level save version is unchanged. Do not edit the ruleset markers by hand.

The journal is currently single-player and bounded to 20,000 records. Startup replay is linear in the number of actions; production server state snapshots and SQLite/Postgres are future upgrades. Only one server should open a given save path at a time. A new character uses a new save file; there is no in-browser delete/reset control.

## Backend/API

\`GET /\`, \`GET /app.js\`, \`GET /styles.css\` and \`GET /favicon.svg\` serve a static responsive frontend. \`GET /api/state\` returns detached, read-only world views including property definitions, magic node eligibility, city information and market quotes. \`POST /api/new\` creates one character. \`POST /api/action\` invokes an explicitly allowlisted game command with an idempotent request ID. \`POST /api/advance\` advances world time by a bounded integer 1–1440 minutes. \`GET /api/health\` reports process health.

The explicit web action allowlist includes **travel, gather, buy/sell raw goods, store/retrieve goods at your present city, consume, buy/upgrade homes, build facilities, purchase/select vehicles, unlock/practice/attune magic, purchase/equip/unequip starter gear, and complete civic contracts**. Actual company employment/ownership, player-to-player combat, autonomous NPC simulation, longer contracts and world spell effects are not yet in the web UI.

## Developer commands

\`\`\`bash
PYTHONPATH=src python -m unittest discover -s tests -v
node --check src/medieval_world_sim/web/static/app.js
python -m medieval_world_sim.web --help
\`\`\`

The standard test suite covers end-to-end HTTP action handling, replay, idempotent purchase requests, auth and origin protection, static file boundaries, and genuine game economics as well as the pre-existing simulations.

## Google Colab notebook preview

The default web server protects against being embedded in other pages. Colab's \`output.serve_kernel_port_as_iframe\` needs an explicit opt-in **\`--colab-preview\`** to permit notebook framing while keeping the rest of the Content Security Policy and same-origin API checks in place. The option accepts **localhost only**; it will not run with \`--host 0.0.0.0\`.

After cloning this branch and installing the project in Colab, mount Google Drive if you want to keep saves, then start the process:

\`\`\`python
import subprocess, sys, time, urllib.request
from google.colab import drive, output

drive.mount("/content/drive")
server = subprocess.Popen([
    sys.executable, "-m", "medieval_world_sim.web",
    "--host", "127.0.0.1", "--port", "8765",
    "--colab-preview",
    "--save", "/content/drive/MyDrive/medieval-world-save.json",
], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

time.sleep(2)
if server.poll() is not None:
    print("Server startup failed:", server.stderr.read().decode())
else:
    print(urllib.request.urlopen("http://127.0.0.1:8765/api/health").read().decode())
    output.serve_kernel_port_as_iframe(8765, height=850)
\`\`\`

If a previous game process is still running on port 8765, stop it first (for example \`server.terminate(); server.wait()\` in the earlier notebook cell) before starting a new process with the flag. If you already installed the game from GitHub in an editable Colab checkout, run \`!git pull\` in the project directory first to receive the new option. The preview still depends on Colab's proxy and browser settings, so some browsers may prevent it even with this fix.

**Security:** Colab preview relaxes *only framing* and should be used for a personal interactive notebook session. The temporary Colab proxy can have its own access restrictions; this mode is not designed for public hosting or sharing the game URL. Keep your notebook and save in your private Drive, and do not expose or forward port 8765 to the internet.
