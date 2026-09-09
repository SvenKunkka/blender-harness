"""Stable object identifiers.

Every object gets a persistent custom property `bh_id` (e.g. "obj_00042").
The id survives renames, checkpoint restore and file saves because it lives on
the object itself. Handlers always accept the id; the display name is never a
reliable reference (duplicates, renames), so tools resolve via this module.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_ID_PROP = "bh_id"
_NEXT_PROP = "bh_next_id"

_id_re = re.compile(r"^obj_(\d+)$")


def _others_ids(obj) -> set:
    """Ids held by *other* objects — used to detect genuine collisions."""
    import bpy

    ids: set = set()
    for o in bpy.data.objects:
        if o is not obj:
            v = o.get(_ID_PROP)
            if v:
                ids.add(str(v))
    return ids


def ensure_obj_id(obj: Any, known: Optional[set] = None) -> str:
    """Return the stable id of an object, assigning a *unique* one if missing
    or if a collision exists (Blender can duplicate objects — with their custom
    properties — e.g. during boolean modifier application; we heal that here).

    `known` is the set of ids already handed out in the current sweep.
    """
    used = known if known is not None else _others_ids(obj)
    existing = obj.get(_ID_PROP)
    if existing and existing not in used:
        return str(existing)
    n = 1
    while f"obj_{n:05d}" in used:
        n += 1
    oid = f"obj_{n:05d}"
    obj[_ID_PROP] = oid
    if known is not None:
        known.add(oid)
    return oid


def current_ids() -> set:
    import bpy

    return {str(o.get(_ID_PROP)) for o in bpy.data.objects if o.get(_ID_PROP)}


def ensure_all() -> None:
    import bpy

    seen: set = set()
    for obj in bpy.data.objects:
        oid = ensure_obj_id(obj, seen)
        seen.add(oid)


def object_by_id(obj_id: str):
    import bpy

    for obj in bpy.data.objects:
        if str(obj.get(_ID_PROP)) == obj_id:
            return obj
    return None


def object_by_name(name: str):
    import bpy

    return bpy.data.objects.get(name)


def resolve_object(args: Dict[str, Any], field: str = "object_id", name_field: str = "object_name"):
    """Resolve an object from a tool argument dict.

    Prefers `field` (stable id) then `name_field` (exact name). Raises
    ValueError with helpful candidates when the reference is ambiguous/missing.
    """
    import bpy

    oid = args.get(field)
    name = args.get(name_field)
    if oid:
        obj = object_by_id(str(oid))
        if obj is not None:
            return obj
        raise ValueError(f"no object with id '{oid}' in this scene — call get_objects first")
    if name:
        obj = object_by_name(str(name))
        if obj is not None:
            return obj
        matches = [o for o in bpy.data.objects if str(name).lower() in o.name.lower()]
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"no object named '{name}' (found {len(matches)} partial matches)")
    candidates = [f"{o.get(_ID_PROP) or ''}:{o.name}" for o in list(bpy.data.objects)[:12]]
    raise ValueError(f"missing object reference — pass object_id (stable id from get_objects). Candidates: {candidates}")


def describe_object(obj: Any) -> Dict[str, Any]:
    return {"id": ensure_obj_id(obj), "name": obj.name}


def objects_affected_of(obj: Any) -> List[Dict[str, Any]]:
    return [describe_object(obj)]
