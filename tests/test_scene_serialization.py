"""Scene serialization, stable object ids and mock-Blender tool behaviour."""

from __future__ import annotations


def test_create_cube_and_read_back(addon):
    dispatch = addon["dispatch"]
    serializer = addon["serializer"]

    ok, res = dispatch("create_cube", {"name": "MouseBody", "dimensions_mm": [120, 64, 39]})
    assert ok, res
    oid = res["object_id"]

    entries = serializer.all_objects()
    entry = next(o for o in entries if o["id"] == oid)
    assert entry["name"] == "MouseBody"
    assert entry["type"] == "MESH"
    assert entry["dimensions_mm"] == [120.0, 64.0, 39.0]
    assert entry["location_mm"] == [0.0, 0.0, 0.0]
    assert entry["mesh"]["vertices"] == 8

    summary = serializer.scene_summary()
    assert summary["object_count"] >= 1
    assert summary["active_object"]["id"] == oid


def test_ids_are_stable_across_rename(addon):
    dispatch = addon["dispatch"]
    serializer = addon["serializer"]

    _, res = dispatch("create_cube", {"name": "ShellA", "dimensions_mm": [10, 10, 10]})
    oid = res["object_id"]
    name_before = res["name"]

    ok, renamed = dispatch("rename_object", {"object_id": oid, "new_name": "CaseTop"})
    assert ok, renamed
    # same id after rename
    entry = next(o for o in serializer.all_objects() if o["id"] == oid)
    assert entry["name"] == "CaseTop"
    assert name_before != entry["name"]


def test_set_dimensions_and_move_in_mm(addon):
    dispatch = addon["dispatch"]
    serializer = addon["serializer"]
    _, cube = dispatch("create_cube", {"name": "Body", "dimensions_mm": [100, 100, 100]})
    oid = cube["object_id"]

    ok, res = dispatch("set_dimensions", {"object_id": oid, "dimensions_mm": [50, 30, 20]})
    assert ok, res
    assert res["dimensions_mm"] == [50.0, 30.0, 20.0]

    ok, moved = dispatch("move_object", {"object_id": oid, "delta_mm": [2, 0, -1.5]})
    assert ok, moved
    # 2mm along X, -1.5mm along Z => metres [0.002, 0, -0.0015]
    entry = next(o for o in serializer.all_objects() if o["id"] == oid)
    assert entry["location_mm"][0] == 2.0
    assert abs(entry["location_mm"][2] - (-1.5)) < 0.01


def test_delete_and_hide(addon):
    dispatch = addon["dispatch"]
    serializer = addon["serializer"]
    _, a = dispatch("create_cube", {"name": "A", "dimensions_mm": [10, 10, 10]})
    _, b = dispatch("create_cube", {"name": "B", "dimensions_mm": [10, 10, 10]})
    ok, res = dispatch("hide_object", {"object_id": a["object_id"]})
    assert ok and res["hidden"] is True

    ok, res = dispatch("delete_object", {"object_id": b["object_id"]})
    assert ok and res["deleted"] is True
    names = [o["name"] for o in serializer.all_objects()]
    assert "B" not in names


def test_add_bevel_then_serialize_modifier(addon):
    dispatch = addon["dispatch"]
    serializer = addon["serializer"]
    _, cube = dispatch("create_cube", {"name": "Rounded", "dimensions_mm": [100, 100, 100]})
    ok, res = dispatch("add_bevel", {"object_id": cube["object_id"], "width_mm": 2.5, "segments": 4})
    assert ok, res
    assert res["modifier_name"] == "Bevel"

    entry = next(o for o in serializer.all_objects() if o["id"] == cube["object_id"])
    bevels = [m for m in entry["modifiers"] if m["type"] == "BEVEL"]
    assert bevels and abs(bevels[0]["width_mm"] - 2.5) < 0.01


def test_product_helpers_create_real_meshes(addon):
    dispatch = addon["dispatch"]
    serializer = addon["serializer"]

    ok, case = dispatch("create_simple_keyboard_case", {
        "name": "KB75", "width_mm": 325, "depth_mm": 145, "height_mm": 18,
        "corner_radius_mm": 6, "wall_thickness_mm": 2, "bottom_thickness_mm": 2,
    })
    assert ok, case
    entry = next(o for o in serializer.all_objects() if o["id"] == case["object_id"])
    assert entry["name"] == "KB75"
    assert entry["mesh"]["faces"] > 6

    ok, mouse = dispatch("create_simple_mouse_volume", {
        "name": "Mouse", "length_mm": 120, "width_mm": 64, "height_mm": 39,
    })
    assert ok, mouse
    entry = next(o for o in serializer.all_objects() if o["id"] == mouse["object_id"])
    dims = entry["dimensions_mm"]
    assert abs(dims[0] - 120) < 1 and abs(dims[2] - 39) < 1, dims

    ok, knob = dispatch("create_simple_knob", {"name": "Knob", "diameter_mm": 12, "height_mm": 8,
                                               "corner_radius_mm": 1.5})
    assert ok, knob


def test_cutout_and_repeated_holes(addon):
    dispatch = addon["dispatch"]
    _, plate = dispatch("create_cube", {"name": "Plate", "dimensions_mm": [100, 60, 4]})
    pid = plate["object_id"]
    ok, res = dispatch("create_cutout", {"target_id": pid, "position_mm": [0, 0, 0],
                                         "size_mm": [20, 10, 10]})
    assert ok, res

    ok, res = dispatch("create_repeated_holes", {
        "target_id": pid, "radius_mm": 2, "count_x": 4, "count_y": 2,
        "spacing_mm": [10, 10], "center_mm": [0, 0, 0],
    })
    assert ok, res


def test_sandbox_executor_blocks_dangerous_code(addon):
    dispatch = addon["dispatch"]
    ok, res = dispatch("execute_blender_python", {"code": "import os\nos.system('rm -rf /')"})
    assert not ok
    assert "banned" in str(res) or "whitelist" in str(res)

    ok, res = dispatch("execute_blender_python", {"code": "x = 1 + 2\nprint(x)"})
    assert ok
    assert res["output"].strip() == "3"
    assert res["error"] is None


def test_addon_handler_registry_matches_server(addon):
    """Every tool the server could ask for has a handler in the add-on."""
    from harness_server.tools.registry import all_tool_specs

    server_names = {s.name for s in all_tool_specs(include_exec=True)}
    addon_names = set(addon["known_tools"]())
    missing = server_names - addon_names
    assert not missing, f"add-on missing handlers for: {sorted(missing)}"
