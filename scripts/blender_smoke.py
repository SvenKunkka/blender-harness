"""Headless smoke test: run the add-on's tool handlers inside a real Blender.

Usage:
  blender --background --factory-startup --python scripts/blender_smoke.py

Exits 0 and prints BLENDER_HARNESS_SMOKE_OK when the core acceptance tools
work against live bpy: create objects, read scene JSON in mm, ids, transform,
bevel, materials, shell/keyboard product helpers, hole drill, checkpoint.
"""

import json
import os
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("BLENDER_HARNESS_DATA_DIR", os.path.join(tempfile.gettempdir(), "bh_smoke_data"))

import bpy  # noqa: E402

# clean slate
for coll in list(bpy.data.collections):
    for o in list(coll.objects):
        coll.objects.unlink(o)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)


def main() -> int:
    from blender_addon.scene import serializer
    from blender_addon.tools import dispatch

    checks = []

    def run(name, args):
        ok, res = dispatch(name, args)
        if not ok:
            raise RuntimeError(f"{name} failed: {res}")
        return res

    cube = run("create_cube", {"name": "MouseBody", "dimensions_mm": [120, 64, 39]})
    oid = cube["object_id"]
    assert cube["dimensions_mm"] == [120.0, 64.0, 39.0]
    checks.append("create_cube_mm")

    run("set_dimensions", {"object_id": oid, "dimensions_mm": [120, 64, 40]})
    entry = next(o for o in serializer.all_objects() if o["id"] == oid)
    assert entry["dimensions_mm"][2] == 40.0, entry
    checks.append("set_dimensions_mm")

    run("move_object", {"object_id": oid, "delta_mm": [5, 0, 0]})
    entry = next(o for o in serializer.all_objects() if o["id"] == oid)
    assert abs(entry["location_mm"][0] - 5.0) < 0.01
    checks.append("move_mm")

    run("add_bevel", {"object_id": oid, "width_mm": 2, "segments": 4})
    run("assign_material", {"object_id": oid, "material_name": "ABS_Black"})
    run("set_roughness", {"object_id": oid, "roughness": 0.6})

    summary = serializer.scene_summary()
    assert summary["object_count"] >= 1 and summary["active_object"]["id"] == oid
    checks.append("scene_summary")

    shell = run("create_shell", {"name": "Shell", "dimensions_mm": [100, 60, 20],
                                 "wall_thickness_mm": 2, "bottom_thickness_mm": 2,
                                 "corner_radius_mm": 5})
    checks.append("create_shell")

    kb = run("create_simple_keyboard_case", {"name": "KB75", "width_mm": 325, "depth_mm": 145,
                                             "height_mm": 18, "corner_radius_mm": 6,
                                             "wall_thickness_mm": 2})
    checks.append("keyboard_case")

    mouse = run("create_simple_mouse_volume", {"name": "Mouse", "length_mm": 120, "width_mm": 64,
                                               "height_mm": 39})
    assert mouse["object_id"]
    checks.append("mouse_volume")

    run("create_simple_knob", {"name": "Knob", "diameter_mm": 12, "height_mm": 8})
    checks.append("knob")

    # ids are stable across the scene
    ids = [o["id"] for o in serializer.all_objects()]
    assert len(ids) == len(set(ids)), "duplicate object ids!"
    checks.append("unique_ids")

    ck = run("create_checkpoint", {"label": "smoke"})
    assert ck["checkpoint_id"] and os.path.exists(ck["path"])
    checks.append("checkpoint")

    geo = run("get_bounding_box", {"object_id": mouse["object_id"]})
    assert geo["size_mm"][2] > 30, geo
    checks.append("bounding_box")

    print("BLENDER_HARNESS_SMOKE_OK " + json.dumps({"checks": checks, "object_count": len(ids)}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        print("BLENDER_HARNESS_SMOKE_FAIL")
        sys.exit(1)
