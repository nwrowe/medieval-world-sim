"""Safe editable authoring overlays for a seed/versioned Oathmere atlas.

No existing IDs are regenerated: overrides change labels/positions, and custom
sites/events have stable author-chosen IDs. These are designer artifacts, not
live multiplayer actions or a mutable server world.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import re

from .society import ExplorationSite
from .landmarks import Landmark

CONTENT_SCHEMA_VERSION = 1
ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
ROOT_KEYS = frozenset({
    "schema_version", "seed", "width", "height", "generator_version",
    "settlements", "sites", "landmarks",
    "additional_sites", "additional_landmarks", "event_locations",
})


@dataclass(frozen=True)
class EventLocation:
    id: str
    name: str
    kind: str
    x: int
    y: int
    description: str
    starts_at: str
    ends_at: str


def _fields(row: object, allowed: set[str], label: str) -> dict:
    if not isinstance(row, dict):
        raise ValueError(f"{label} must be a JSON object")
    unknown = set(row) - allowed
    if unknown:
        raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")
    return row


def _text(value: object, label: str, limit: int = 90) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must be nonempty text up to {limit} characters")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} cannot contain control characters")
    return value.strip()


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid stable content ID: {value!r}")
    return value


def _point(world, row: dict, old, label: str, *, dry: bool) -> tuple[int, int]:
    x = row.get("x", old.x if old else None)
    y = row.get("y", old.y if old else None)
    if type(x) is not int or type(y) is not int or not (0 <= x < world.width and 0 <= y < world.height):
        raise ValueError(f"{label} must reference a valid hex coordinate")
    if dry and (world.tile(x, y).elevation_m <= 0 or
                world.tile(x, y).waterbody == "lake"):
        raise ValueError(f"{label} must be on dry land")
    return x, y


def _number(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer from {low} to {high}")
    return value


def _date(value: object, label: str) -> tuple[str, datetime]:
    string = _text(value, label, 50)
    try:
        parsed = datetime.fromisoformat(string.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must specify UTC (e.g. 2026-12-01T00:00:00Z)")
    return string, parsed


def _list(data, label):
    if not isinstance(data, list) or len(data) > 200:
        raise ValueError(f"{label} must be an array with at most 200 entries")
    return data


def apply_content(world, content: dict):
    """Validate/overlay stable user-owned content; never modify world in-place."""
    row = _fields(content, set(ROOT_KEYS), "content")
    if row.get("schema_version") != CONTENT_SCHEMA_VERSION:
        raise ValueError(f"Content schema_version must be {CONTENT_SCHEMA_VERSION}")
    for field in ("seed", "width", "height", "generator_version"):
        if field in row:
            expected = world.version if field == "generator_version" else getattr(world, field)
            if type(row[field]) is not int or row[field] != expected:
                raise ValueError(f"Content {field} does not match the selected world")
    settlements = list(world.settlements)
    sites = list(world.sites)
    landmarks = list(world.landmarks)
    settlements_by_id = {s.id: i for i, s in enumerate(settlements)}
    sites_by_id = {s.id: i for i, s in enumerate(sites)}
    landmarks_by_id = {m.id: i for i, m in enumerate(landmarks)}
    name_registry = set()
    for key, replacement in _fields(row.get("settlements", {}), set(settlements_by_id),
                                    "settlements").items():
        value = _fields(replacement, {"name"}, f"settlements.{key}")
        settlements[settlements_by_id[key]] = replace(
            settlements[settlements_by_id[key]],
            name=_text(value.get("name"), f"settlements.{key}.name"))
    for s in settlements:
        name = s.name.casefold()
        if name in name_registry:
            raise ValueError("Settlement names must remain unique")
        name_registry.add(name)

    site_fields = {"name", "kind", "x", "y", "danger", "clue"}
    for key, replacement in _fields(row.get("sites", {}), set(sites_by_id), "sites").items():
        value = _fields(replacement, site_fields, f"sites.{key}")
        old = sites[sites_by_id[key]]
        x, y = _point(world, value, old, f"sites.{key}", dry=True)
        sites[sites_by_id[key]] = replace(
            old, x=x, y=y, biome=world.tile(x, y).biome,
            name=_text(value.get("name", old.name), "site name"),
            kind=_text(value.get("kind", old.kind), "site kind", 50),
            danger=_number(value.get("danger", old.danger), "site danger", 1, 10),
            clue=_text(value.get("clue", old.clue), "site clue", 300))
    landmark_fields = {"name", "kind", "x", "y", "importance", "reason"}
    for key, replacement in _fields(row.get("landmarks", {}), set(landmarks_by_id),
                                    "landmarks").items():
        value = _fields(replacement, landmark_fields, f"landmarks.{key}")
        old = landmarks[landmarks_by_id[key]]
        x, y = _point(world, value, old, f"landmarks.{key}", dry=True)
        landmarks[landmarks_by_id[key]] = replace(
            old, x=x, y=y,
            name=_text(value.get("name", old.name), "landmark name"),
            kind=_text(value.get("kind", old.kind), "landmark kind", 50),
            importance=_number(value.get("importance", old.importance),
                               "landmark importance", 1, 10),
            reason=_text(value.get("reason", old.reason), "landmark reason", 300))

    used = set(sites_by_id) | set(landmarks_by_id) | set(settlements_by_id)
    for obj in _list(row.get("additional_sites", []), "additional_sites"):
        v = _fields(obj, site_fields | {"id"}, "additional_sites entry")
        ident = _identifier(v.get("id"))
        if ident in used:
            raise ValueError(f"Duplicate location ID: {ident}")
        used.add(ident)
        x, y = _point(world, v, None, ident, dry=True)
        sites.append(ExplorationSite(
            ident, _text(v.get("name"), "site name"),
            _text(v.get("kind"), "site kind", 50), x, y,
            _number(v.get("danger"), "site danger", 1, 10),
            world.tile(x, y).biome, _text(v.get("clue"), "site clue", 300)))
    for obj in _list(row.get("additional_landmarks", []), "additional_landmarks"):
        v = _fields(obj, landmark_fields | {"id"}, "additional_landmarks entry")
        ident = _identifier(v.get("id"))
        if ident in used:
            raise ValueError(f"Duplicate location ID: {ident}")
        used.add(ident)
        x, y = _point(world, v, None, ident, dry=True)
        landmarks.append(Landmark(
            ident, _text(v.get("name"), "landmark name"),
            _text(v.get("kind"), "landmark kind", 50), x, y,
            _number(v.get("importance"), "importance", 1, 10),
            _text(v.get("reason"), "reason", 300)))

    event_fields = {"id", "name", "kind", "x", "y", "description",
                    "starts_at", "ends_at"}
    events = []
    for obj in _list(row.get("event_locations", []), "event_locations"):
        v = _fields(obj, event_fields, "event_locations entry")
        ident = _identifier(v.get("id"))
        if ident in used:
            raise ValueError(f"Duplicate location ID: {ident}")
        used.add(ident)
        x, y = _point(world, v, None, ident, dry=False)
        start, at = _date(v.get("starts_at"), "event starts_at")
        end, until = _date(v.get("ends_at"), "event ends_at")
        if until <= at:
            raise ValueError(f"{ident} must end after it begins")
        events.append(EventLocation(
            ident, _text(v.get("name"), "event name"),
            _text(v.get("kind"), "event kind", 50), x, y,
            _text(v.get("description"), "event description", 500), start, end))

    return replace(world, settlements=tuple(settlements), sites=tuple(sites),
                   landmarks=tuple(landmarks), event_locations=tuple(events))


def export_content_template(world):
    """A complete editable map-content template bound to one seed and version.

    Current city/ruin/landmark names and positions are written into the file,
    so users can modify existing locations without looking up generated IDs.
    """
    return {
        "schema_version": CONTENT_SCHEMA_VERSION,
        "seed": world.seed, "width": world.width, "height": world.height,
        "generator_version": world.version,
        "settlements": {s.id: {"name": s.name} for s in world.settlements},
        "sites": {s.id: {"name": s.name, "kind": s.kind, "x": s.x, "y": s.y,
                         "danger": s.danger, "clue": s.clue} for s in world.sites
                  if not s.id.startswith("custom-")},
        "landmarks": {m.id: {"name": m.name, "kind": m.kind, "x": m.x, "y": m.y,
                             "importance": m.importance, "reason": m.reason}
                      for m in world.landmarks if not m.id.startswith("custom-")},
        "additional_sites": [asdict(s) | {"biome": None} for s in ()
                             ],  # Blank slots: new locations must have a unique ID.
        "additional_landmarks": [],
        "event_locations": [asdict(e) for e in world.event_locations],
    }


def load_content(path: Path) -> dict:
    """Read a small UTF-8 JSON authored manifest with strict duplicate keys."""
    if path.stat().st_size > 256_000:
        raise ValueError("World content files must be <=256 KB")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Repeated JSON key: {key}")
            result[key] = value
        return result
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    if not isinstance(data, dict):
        raise ValueError("World content must be a JSON object")
    return data
