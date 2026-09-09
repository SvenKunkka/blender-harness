"""Tool registry / JSON-schema / parity tests."""

from __future__ import annotations

import json

from harness_server.schemas.tools import to_llm_tool
from harness_server.tools.registry import all_tool_specs, spec_by_name

REQUIRED_CORE_TOOLS = {
    "get_scene_summary", "get_objects", "get_object_details", "get_selected_objects",
    "select_object", "rename_object", "duplicate_object", "delete_object",
    "hide_object", "show_object", "set_location", "move_object", "set_rotation",
    "rotate_object", "set_scale", "set_dimensions", "apply_transform",
    "create_cube", "create_uv_sphere", "create_cylinder", "create_plane",
    "create_mesh_from_vertices", "get_mesh_stats", "get_bounding_box",
    "add_bevel", "add_boolean", "add_solidify", "add_subdivision", "add_mirror",
    "add_array", "remove_modifier", "apply_modifier", "set_modifier_property",
    "create_material", "assign_material", "set_base_color", "set_metallic",
    "set_roughness", "list_materials", "create_camera", "set_active_camera",
    "frame_selected", "look_at_object", "set_camera_position",
    "capture_viewport", "render_image", "render_multi_angle", "capture_object_views",
    "save_blend", "save_blend_as", "get_current_file",
    "create_checkpoint", "restore_checkpoint", "list_checkpoints", "undo_last_ai_action",
    "execute_blender_python", "create_rounded_box", "create_shell",
    "set_exact_dimensions_mm", "measure_distance", "measure_object",
    "center_object", "align_objects", "mirror_object", "create_cutout",
    "create_hole", "create_repeated_holes", "set_wall_thickness",
    "create_simple_keyboard_case", "create_simple_mouse_volume", "create_simple_knob",
}

VALID_RISKS = {"safe", "mutating", "destructive", "exec"}
VALID_CATEGORIES = {"scene", "transform", "mesh", "modifier", "material",
                    "camera", "render", "file", "history", "product", "python", "misc"}


def test_core_tool_names_present():
    names = {s.name for s in all_tool_specs(include_exec=True)}
    missing = REQUIRED_CORE_TOOLS - names
    assert not missing, f"missing tools: {sorted(missing)}"


def test_unique_names_and_clean_schemas():
    specs = all_tool_specs(include_exec=True)
    seen = set()
    for s in specs:
        assert s.name not in seen, f"duplicate tool {s.name}"
        seen.add(s.name)
        assert s.description, f"{s.name} needs a description"
        assert s.risk in VALID_RISKS, f"{s.name} risk {s.risk}"
        assert s.category in VALID_CATEGORIES, f"{s.name} category {s.category}"
        params = s.parameters
        assert params.get("type") == "object", f"{s.name} parameters must be object schema"
        props = params.get("properties", {})
        assert isinstance(props, dict) and len(props) >= 0
        for req in params.get("required", []):
            assert req in props, f"{s.name}: required {req} not in properties"


def test_llm_tool_payload_serializable():
    spec = spec_by_name("set_dimensions")
    payload = to_llm_tool(spec)
    assert payload["type"] == "function"
    dumped = json.dumps(payload)
    assert "dimensions_mm" in dumped
    back = json.loads(dumped)
    assert back["function"]["name"] == "set_dimensions"


def test_every_spec_serializes_to_json():
    for s in all_tool_specs(include_exec=True):
        json.dumps(to_llm_tool(s))


def test_risk_filtering():
    assert spec_by_name("delete_object").risk == "destructive"
    assert spec_by_name("get_scene_summary").risk == "safe"
    assert spec_by_name("execute_blender_python").risk == "exec"
    without_exec = {s.name for s in all_tool_specs(include_exec=False)}
    assert "execute_blender_python" not in without_exec
