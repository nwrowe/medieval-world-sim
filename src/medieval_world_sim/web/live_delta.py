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
    return {
        "actor_id": current["actor_id"], "revision": current["revision"],
        "delta": True,
        **{key: value for key, value in current.items()
           if key not in ("actor_id", "revision") and previous.get(key) != value},
    }


def apply_activity_delta(previous: dict, delta: dict) -> dict:
    """Reference merger for Python protocol tests and SSE clients."""
    if delta.get("actor_id") != previous.get("actor_id"):
        raise ValueError("Invalid delta actor")
    if delta.get("revision", 0) <= previous.get("revision", 0):
        raise ValueError("Stale activity delta")
    return {**previous, **{key: value for key, value in delta.items()
                          if key != "delta"}}
