# Host a private playtest on Render

The game remains a **single-player** prototype. This configuration creates a **paid, single-instance Render web service** with an attached persistent disk and HTTPS at the Render edge. It does **not** turn the game into multiplayer or a hardened production service.

## Before you deploy

The web client code currently lives in PR #22's \`feat/first-playable-web-client\` branch, while this hosting integration is on \`feat/render-single-player-hosting\`. Deploy this hosting branch until the changes are reviewed and merged.

**Cost:** This Blueprint declares a paid \`0.5c-512mb\` instance with a 1 GB persistent disk. Render charges separately according to current compute and disk prices; check the total shown in the Render dashboard **before** confirming creation. Don't select a free ephemeral service if retaining saves matters.

**Authentication:** Render must receive \`GAME_ACCESS_TOKEN\` in its dashboard as a secret, **not committed to GitHub**. Generate a long random token locally or in a private Colab cell:

\`\`\`python
import secrets
print(secrets.token_urlsafe(32))
\`\`\`

Copy the result into the prompted **GAME_ACCESS_TOKEN** field during Blueprint creation. Never paste this secret into GitHub or an issue comment. Anyone with the link and this code can access the **same** single-player save. It is not an account or multiplayer system.

## Deploy

1. Sign up or sign in at [Render](https://dashboard.render.com/), then connect the GitHub repository.
2. Choose **New → Blueprint**, select \`nwrowe/medieval-world-sim\`, and choose the branch \`feat/render-single-player-hosting\` if prompted.
3. Render reads the root \`render.yaml\`. Confirm the service plan is **paid** and that it includes the 1 GB disk at \`/var/data\`.
4. Enter \`GAME_ACCESS_TOKEN\` when prompted. This token must have at least 20 characters.
5. Review estimated charges, then create the Blueprint. Render builds with \`pip install -e .\`, starts the Python game via \`python -m medieval_world_sim.web.deploy\`, and assigns an \`https://...onrender.com\` address.
6. Open the URL on phone or desktop. Enter the access code when prompted. The same saved game is preserved between app restarts and deploys as long as the attached disk remains available.

The configured region is Ohio, but you may adjust it. Automatic deploys are disabled to avoid unintentional save migrations during rapid prototype changes. Manually deploy after reviewing changes.

## Security and limitations

- The frontend and game state share a **single code-protected session**. There are no individual player accounts.
- Render provides HTTPS to visitors; the game still speaks HTTP **inside** Render's managed proxy boundary.
- The server requires \`GAME_ACCESS_TOKEN\` and will **refuse to start** if missing. Use a strong random token and never expose it through source code, logs, or shared notebooks.
- Public static assets and \`/api/health\` do not reveal the saved character or access code; the \`/api/state\` endpoint and all mutations require the code.
- The single JSON action journal is **not** suitable for multiple server instances or competing players. The mounted disk and one web instance are intentional.
- Daily disk snapshots and disk ownership are host-managed; consider downloading/backing up saves separately before major upgrades. A deleted service or disk may result in data loss.
- Render's service is reachable from the internet. This is suitable only for a small private playtest with people you trust, not a public game launch. Harden authentication, rate limiting, abuse protection, and persistence before opening it widely.
- Existing character saves from Colab aren't transferred automatically. It is safest to create a new character on Render for the first test, then add explicit save import/export later if needed.
- You can stop or remove this service in Render to stop further charges, subject to Render's billing terms.

## Local verification

\`\`\`bash
python -m unittest discover -s tests -v
python -m medieval_world_sim.web.deploy
\`\`\`

The second command should **fail safely without \`GAME_ACCESS_TOKEN\`**. With \`GAME_ACCESS_TOKEN\` set, it starts the web service on the \`PORT\` environment variable or 10000.
