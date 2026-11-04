# Chat channels and local UI preview

**Status:** chat channel rules and an always-accessible browser drawer are implemented. The original **single-player** mode still offers a local message preview. The new optional **localhost-only multi-account development mode** provides independently authenticated player sessions and local direct/global chat between separate browser profiles. This is not a public multiplayer chat deployment; see [local setup](MULTIPLAYER_LOCAL_DEVELOPMENT.md).

## Accessible while playing

The game includes a collapsible fixed-position chat drawer, including on travel, combat and equipment screens. It shows recent server-authoritative messages, a compose box, and available channels. On small screens, it expands into a wider lower panel, leaving the primary game screen in place rather than navigating away.

## Channel rules (engine)

- `global`: visible to all real human actors in a shared world.
- `direct`: one-to-one; visible only to sender and explicitly addressed human recipient. NPC messaging and self-messaging rejected.
- `company`: only the owner and current employees can post/read.
- `guild`: only current guild members can post/read. This maps to the game's faction concept.
- `room`: custom private room, with name (3–40 chars) and explicit human member list (up to 20). Room creation is supported in the engine as a stretch-goal foundation.

Message sender is the **trusted principal** supplied to the world engine. There is no user-supplied sender field; characters cannot send as other people. Text messages have a 400-character cap and are shown through the client's HTML-escaping function. The engine retains up to 1000 messages, exposing only the last 100 *authorized* messages per user's view. Active membership is rechecked on each read, so leaving a guild removes access to its private discussion. Existing user chat commands are journaled and replayed on server restart.

## Deployment security

The original LAN `X-Game-Token` remains a **shared code for one game**, not a user identity. The experimental multi-account mode uses individual salted-hash logins and session-derived principals, but intentionally binds only to the **loopback interface**. It must not be treated as an internet-hosted multi-user chat server.

Before enabling this on a public server, use a production database, access checks on every read/write, transport encryption, robust origin and session protections, rate limiting, moderation/report/block controls, history pagination and retention policy. Channel permission must be checked server-side even if a client fabricates channel IDs.

The localhost multi-account chat drawer now uses **server-sent events (SSE)** at `/api/events`. Database commits wake a bounded set of authenticated event streams, and the server sends **only that account's authorized chat, trade, and progress data**. The browser updates the drawer automatically without refreshing the page or clearing the message composer. Streams send heartbeats, reconnect automatically, and revalidate the session. A small badge beside Chat counts incoming messages not yet viewed in that browser profile; per-account read markers are kept in browser local storage. They are not yet server-synchronized read receipts across multiple devices.

The event stream is restricted to the existing **localhost-only** multi-account service. Full production deployment still requires TLS, abuse prevention, production-grade persistence and operational review.
