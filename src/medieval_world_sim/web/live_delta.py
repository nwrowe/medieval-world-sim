"""Wire-efficient account-scoped SSE updates.

First event is a full scoped projection. Later events contain only changed
top-level fields plus actor ID and strictly increasing revision. Never put
the underlying WorldState or another actor's private assets on the stream.
"""

def activity_delta(previous: dict | None, current: dict) -> dict:
    if previous is None:
        return dict(current)
    if current["actor_id"] != previous["actor_id"]:
        raise ValueError("Cannot diff activity across actor identities")
    if current["revision"] <= previous["revision"]:
        raise ValueError("Activity revision must increase")
    changed = {
        key: value for key, value in current.items()
        if key not in ("actor_id", "revision") and previous.get(key) != value
    }
    # Presence changes happen frequently. A roster's city/HP/combat fields
    # are stable for these changes, so transmit only changed status IDs.
    # A real character change or roster reordering still sends full users.
    old_users, new_users = previous.get("users"), current.get("users")
    if ("users" in changed and isinstance(old_users, list)
            and isinstance(new_users, list) and len(old_users) == len(new_users)):
        changes = []
        for old, new in zip(old_users, new_users):
            if (not isinstance(old, dict) or not isinstance(new, dict)
                    or old.get("id") != new.get("id")
                    or {key: value for key, value in old.items() if key != "presence"}
                    != {key: value for key, value in new.items() if key != "presence"}):
                break
            if old.get("presence") != new.get("presence"):
                changes.append({"id": new["id"],
                                "presence": new.get("presence", "offline")})
        else:
            changed.pop("users")
            if changes:
                changed["presence_updates"] = changes
    return {"actor_id": current["actor_id"], "revision": current["revision"],
            "delta": True, **changed}


def apply_activity_delta(previous: dict, delta: dict) -> dict:
    """Reference merger for Python protocol tests and SSE clients."""
    if delta.get("actor_id") != previous.get("actor_id"):
        raise ValueError("Invalid delta actor")
    if delta.get("revision", 0) <= previous.get("revision", 0):
        raise ValueError("Stale activity delta")
    output = {**previous, **{key: value for key, value in delta.items()
                             if key not in ("delta", "presence_updates")}}
    patches = delta.get("presence_updates")
    if patches is not None:
        if "users" in delta or not isinstance(patches, list):
            raise ValueError("Invalid presence delta")
        users = output.get("users")
        if not isinstance(users, list):
            raise ValueError("Missing presence roster")
        known = {user["id"]: user for user in users}
        if len(known) != len(users):
            raise ValueError("Duplicate roster identities")
        replacements = {}
        for patch in patches:
            if (not isinstance(patch, dict) or set(patch) != {"id", "presence"}
                    or patch["id"] not in known or patch["id"] in replacements
                    or patch["presence"] not in ("active", "away", "offline")):
                raise ValueError("Invalid presence actor patch")
            replacements[patch["id"]] = patch["presence"]
        output["users"] = [
            {**user, "presence": replacements[user["id"]]}
            if user["id"] in replacements else user for user in users
        ]
    return output
