# Chat channels and local UI preview

**Status:** chat channel rules and an always-accessible browser drawer are implemented. The browser's **single-player** mode offers a local message preview; it is NOT a public multiplayer chat service. Only the one locally authenticated hero can post through the current server access token. Do not mistake the shared server code for separate human account authentication.

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

The currently deployed local mode is not multi-account hosting. The browser's global chat accepts a message that only the local hero can see. The current `X-Game-Token` is shared for one server, so users with that code are **not distinguished**. The implementation must not be described as secure independent-player chat.

Before enabling this on a public server, use an account-verified principal, a shared durable message store, access checks on every read/write, transport encryption, CSRF handling for cookie sessions, real-time delivery (WebSocket or SSE with authenticated reconnect), rate limiting, moderation/report/block controls, history pagination and retention policy. Channel permission must be checked server-side even if a client fabricates channel IDs.

The chat drawer currently does not poll or subscribe to updates from other human clients because the browser mode has no independent human sessions. That limitation should be resolved with the account system, not simulated via fake NPC messages.
