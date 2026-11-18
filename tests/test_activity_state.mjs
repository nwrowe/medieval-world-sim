/* Play-test regressions: accelerated cooldowns, unspent merit alerts, and
 * browser-only Settings. No DOM shim or network connection required.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { scaledTimerSeconds, totalUnspentMerits } from
  "../src/medieval_world_sim/web/static/activity-state.mjs";

assert.equal(scaledTimerSeconds(75 * 60, 1, 1, 0), 75);
assert.equal(scaledTimerSeconds(75 * 60, 1, 1, .5), 74.5);
assert.equal(scaledTimerSeconds(75 * 60, 1, 1, 75), 0);
assert.equal(scaledTimerSeconds(75 * 60, 60, 30, 1), 75 * 60 - 31);
assert.equal(scaledTimerSeconds(75 * 60, 60, null, 100), 75 * 60);

const ledger = {
  balance: 2,
  achievements: [
    { id: "one", eligible: true, claimed: false, award: 1 },
    { id: "two", eligible: true, claimed: false, award: 2 },
    { id: "three", eligible: false, claimed: false, award: 1 },
  ],
};
assert.equal(totalUnspentMerits(ledger), 5);
ledger.achievements[0].claimed = true;
ledger.balance += 1;
assert.equal(totalUnspentMerits(ledger), 5,
  "claiming must not decrease or increase total available merits");
ledger.balance -= 2;
assert.equal(totalUnspentMerits(ledger), 3,
  "purchasing upgrades must reduce available merits");
ledger.achievements[1].claimed = true;
ledger.balance += 2;
assert.equal(totalUnspentMerits(ledger), 3);
assert.equal(totalUnspentMerits({ balance: 0, achievements: [] }), 0);
assert.equal(totalUnspentMerits({ balance: 4, achievements: [] }), 4);

const app = readFileSync(
  new URL("../src/medieval_world_sim/web/static/app.js", import.meta.url), "utf8");
const style = readFileSync(
  new URL("../src/medieval_world_sim/web/static/styles.css", import.meta.url), "utf8");
const character = readFileSync(
  new URL("../src/medieval_world_sim/web/static/character-views.mjs", import.meta.url), "utf8");
assert.match(app, /refreshActivityStrip\(strip\)/);
assert.doesNotMatch(app, /strip\.innerHTML\s*=\s*activityIcons\(\)/);
assert.match(app, /data-activity-key="cooldown-/);
assert.match(app, /data-activity-key="merits"/);
assert.match(app, /data-timer-display/);
assert.match(app, /readout\.textContent\s*=\s*remaining/);
assert.match(app, /const seconds = timerSeconds\(remaining \* 60\)/);
assert.match(app, /const time = fullCountdown\(seconds\)/);
assert.match(app, /timerAttrs\(tip, remaining \* 60, seconds\)/);
assert.match(app, /let themePreference = "light"/);
assert.match(app, /totalUnspentMerits\(merits\)/);
assert.match(app, /data-ui="settings-open"/);
assert.match(app, /case "settings-theme":/);
assert.match(app, /oathmere\.appearance\.theme/);
assert.match(app, /Email & notifications/);
assert.match(app, /No email is currently sent/);
assert.match(style, /\.equipment-storage-panel\s*\{\s*margin-top:18px/);
assert.match(character, /class="equipment-storage-panel"/);
assert.match(style, /:root\[data-theme="dark"\]/);
assert.match(style, /\.settings-grid/);
console.log("Cooldown, merit count, Equipment gap, and Settings contract tests passed");
