# Phase 1: multiplayer economy and API abuse controls

**Scope:** opt-in localhost-only multi-account development server. This is not a
public hosting certification. It preserves existing accounts and world journals;
production deployment still needs a database ledger, incident response, backups,
TLS, production identity and edge-level rate limiting.

## Operator setup (PowerShell)

Start from the checked-out project directory.

1. Issue an invitation **without starting the HTTP server**:

   ```powershell
   python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-dev.sqlite3" --issue-invites 2
   ```

   The CLI prints two separate 192-bit random invitation codes. Give one code
   to each intended player. They expire in seven days and can be redeemed once.
   Only code SHA-256 digests are saved in SQLite. Never share the codes publicly.

2. Start the safer local server:

   ```powershell
   python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-dev.sqlite3"
   ```

   Existing players can sign in without an invitation. New registrations must
   enter an operator-issued invitation in the registration form.

3. **Local rapid gameplay testing only:** to retain the historical free
   registration and user-initiated simulation time controls, explicitly run:

   ```powershell
   python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-dev.sqlite3" --dev-open-registration --dev-fast-forward
   ```

   These overrides are **not** safe against coordinated economic abuse.

## Threat model and controls

| Attack | Server-side control |
| --- | --- |
| An attacker creates many accounts and gifts their 240g onboarding grants to one character | The operator must issue a unique one-use invitation for each newly funded character, plus a bounded daily registration budget. The human operator decides who receives a code. |
| A player repeatedly posts `/api/advance` to finish everyone's cooldowns, regenerate stock, or choose favorable race times | The normal server derives world time from elapsed server wall-clock minutes and persists each advance in the command journal. The HTTP fast-forward route is rejected unless `--dev-fast-forward` is explicitly enabled. |
| A player uses the publicly known world seed to predict magic practice or horse racing results | New multiplayer actions use a secret per-world 256-bit HMAC key stored only in the operator's SQLite database. Individual journal actions indicate the RNG version, preserving old replay. |
| Automated chat, login guessing, or API action floods | Per-remote/authenticated-account HTTP token buckets, chat-specific throttling and bounded key storage. This is a single-process local limiter, not an internet edge control. |
| Legitimate actions deliberately fill the 20,000-row journal | SQLite-backed 24-hour quotas: 400 commands per account, 100 chat commands per account, 4,000 commands across the whole world, 24 registrations. Same request ID replay remains idempotent. |
| An attacker retries a purchase, trade, or combat action or guesses another actor ID | Existing authenticated actor binding, per-account idempotent receipts, transactional rollback, ownership checks, escrow and invariant verification remain in place. |

**Important limitations:**

- Invitations are not proof of one unique human. An operator can issue multiple
  codes to one player; a stolen valid code can be redeemed. An identity and
  account-abuse program is still needed before public hosting.
- Existing character balances are unchanged. Older records used a public seed
  for magic/racing outcomes, and the server must replay them with that same
  algorithm. The new private RNG applies only to newly committed actions.
- Server wall time is committed in capped increments of at most one simulated
  day per request. An idle server catches up when activity resumes; this
  prevents an unbounded replay step. It is not a final production clock
  scheduler or a substitute for persistent snapshots.
- Current transaction isolation uses one process lock, an in-memory world and
  whole-state rollback. This will not safely scale to several server instances.
- The SQLite database contains password verifier material, invite digests and
  the world RNG key. Restrict file and backup access to trusted operators.
- Rate limits are deliberately modest and local. They reset on process
  restart. HTTP 429 means the request was rejected; retry only when appropriate.
  Persistent 24-hour journal quotas survive restart.
- No rate limiter can prevent all resource exhaustion of a single-process app.
  This service remains restricted to localhost, and `MAX_JOURNAL` still bounds
  the life of the append-only prototype without database checkpoints.

## Backward compatibility and rollback

The SQLite schema adds an invitation table, world metadata, private-key
generation, and nullable per-command version fields. Old actions have
`secure_roll=NULL` and continue to use their original deterministic rolls.
New clock entries appear as replayable journal `advance` entries. Account
identities, balances, escrows, gear IDs, trades and chat remain unchanged.

**Back up the SQLite file before upgrading.** A post-upgrade database is not
guaranteed to load in older application versions; rollback requires restoring
a pre-upgrade database backup in addition to reverting code.

## Attack-oriented regression tests

`tests/test_phase1_abuse_security.py` checks one-use invites, denied anonymous
starter-money creation, restart persistence, server-time authorization, exact
keyed magic/racing replay, legacy unkeyed replay, HTTP login flood protection,
token-bucket thread safety and daily action limits.

Run the full suite with:

```powershell
python -m unittest discover -s tests -v
```

Future production milestones still require security testing with real
concurrent clients, account recovery, backups and a relational asset ledger.
