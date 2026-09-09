"""Canonical registry of every structured Blender tool.

The JSON Schemas defined here are what the LLM (and the Web UI) see. The Blender
add-on only needs to implement handlers for the same *names* — it never has to
parse these schemas.

Conventions (do not let the model ignore them):
  * every length is in millimetres (_mm), every angle in degrees (_deg) — the
    add-on converts to Blender metres/radians internally;
  * object references prefer the stable `object_id`; `object_name` is accepted
    as a convenience fallback by the add-on;
  * the agent must call get_objects / get_scene_summary before mutating.
"""

from __future__ import annotations

from typing import Any, Dict, List

from harness_server.schemas.tools import ToolSpec

# ---------------------------------------------------------------------------
# small schema builders
# ---------------------------------------------------------------------------


def obj() -> Dict[str, Any]:
    return {"type": "object"}


def _schema(props: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


def _mm3(desc: str = "Three component vector") -> Dict[str, Any]:
    return {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "description": desc}


_OBJECT_ID = {"type": "string", "description": "Stable Blender object id (from get_objects). You may also pass the object's exact name here."}
_NAME = {"type": "string", "description": "New display name."}
_NUMBER = {"type": "number"}
_BOOL = {"type": "boolean"}
_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}

# ---------------------------------------------------------------------------
# tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFS: List[Dict[str, Any]] = [
    # ------------------------------------------------------------- scene
    dict(name="get_scene_summary", category="scene", risk="safe",
         description="Read a compact summary of the current Blender scene: object count, active/selected objects, collections, camera, lights, unit settings. Call this first whenever you need to understand the scene.",
         parameters=_schema({}, [])),
    dict(name="get_objects", category="scene", risk="safe",
         description="List every object with its stable id, name, type, dimensions_mm, location_mm, rotation, mesh stats and modifier list. Use it to find the object_id you will operate on.",
         parameters=_schema({}, [])),
    dict(name="get_object_details", category="scene", risk="safe",
         description="Full details (id, dimensions in mm, location in mm, rotation in degrees, mesh stats, modifiers, materials) of one object.",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    dict(name="get_selected_objects", category="scene", risk="safe",
         description="Return the currently selected objects with ids and names.",
         parameters=_schema({}, [])),
    dict(name="select_object", category="scene", risk="safe",
         description="Select one object (optionally replacing the current selection).",
         parameters=_schema({"object_id": _OBJECT_ID, "replace": {**_BOOL, "description": "default true: clear existing selection first"}}, ["object_id"])),
    dict(name="rename_object", category="scene", risk="mutating",
         description="Rename an object (keeps its stable id).",
         parameters=_schema({"object_id": _OBJECT_ID, "new_name": _NAME}, ["object_id", "new_name"])),
    dict(name="duplicate_object", category="scene", risk="mutating",
         description="Duplicate an object into the same collection. Returns the new object id.",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "offset_mm": {**_mm3(), "description": "optional offset of the copy relative to the original"}}, ["object_id"])),
    dict(name="delete_object", category="scene", risk="destructive",
         description="Permanently delete one object. A checkpoint is created automatically before this runs.",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    dict(name="hide_object", category="scene", risk="safe",
         description="Hide an object in the viewport.",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    dict(name="show_object", category="scene", risk="safe",
         description="Unhide an object.",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    # -------------------------------------------------------- transform
    dict(name="set_location", category="transform", risk="mutating",
         description="Set the absolute world location of an object in millimetres.",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "location_mm": {**_mm3("new world location [x, y, z] in mm")}}, ["object_id", "location_mm"])),
    dict(name="move_object", category="transform", risk="mutating",
         description="Move an object by a delta in millimetres (world axes).",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "delta_mm": {**_mm3("[dx, dy, dz] in mm")}}, ["object_id", "delta_mm"])),
    dict(name="set_rotation", category="transform", risk="mutating",
         description="Set absolute Euler rotation in degrees (X, Y, Z order).",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "rotation_deg": {**_mm3("[rx, ry, rz] in degrees")}}, ["object_id", "rotation_deg"])),
    dict(name="rotate_object", category="transform", risk="mutating",
         description="Rotate an object by a delta in degrees (X, Y, Z order).",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "delta_deg": {**_mm3("[drx, dry, drz] in degrees")}}, ["object_id", "delta_deg"])),
    dict(name="set_scale", category="transform", risk="mutating",
         description="Set uniform-per-axis scale factors (multipliers, not mm).",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "scale": {**_mm3("[sx, sy, sz] scale factors")}}, ["object_id", "scale"])),
    dict(name="set_dimensions", category="transform", risk="mutating",
         description="Set the exact bounding-box dimensions of an object in millimetres (scales the object to match).",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "dimensions_mm": {**_mm3("[width, depth, height] target dimensions in mm")}},
                            ["object_id", "dimensions_mm"])),
    dict(name="apply_transform", category="transform", risk="mutating",
         description="Bake location/rotation/scale into the mesh data (origin reset). Apply only when geometry must be edited in place afterwards.",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    # ------------------------------------------------------------ mesh
    dict(name="create_cube", category="mesh", risk="mutating",
         description="Create a cube (optionally non-uniform box) in millimetres. Returns its object id.",
         parameters=_schema({
             "name": _NAME, "dimensions_mm": {**_mm3("width, depth, height in mm, default 100x100x100")},
             "location_mm": {**_mm3("optional world location of the box center in mm")}}, [])),
    dict(name="create_uv_sphere", category="mesh", risk="mutating",
         description="Create a UV sphere in millimetres. Returns its object id.",
         parameters=_schema({"name": _NAME, "radius_mm": _NUMBER,
                             "segments": {"type": "integer"}, "rings": {"type": "integer"},
                             "location_mm": {**_mm3("optional center location in mm")}}, [])),
    dict(name="create_cylinder", category="mesh", risk="mutating",
         description="Create a cylinder in millimetres. Returns its object id.",
         parameters=_schema({"name": _NAME, "radius_mm": _NUMBER, "depth_mm": _NUMBER,
                             "vertices": {"type": "integer"},
                             "location_mm": {**_mm3("optional center location in mm")}}, [])),
    dict(name="create_plane", category="mesh", risk="mutating",
         description="Create a flat quad plane in millimetres. Returns its object id.",
         parameters=_schema({"name": _NAME, "size_mm": {**_mm3("[width, depth] in mm, default [100, 100]")},
                             "location_mm": {**_mm3()}}, [])),
    dict(name="create_mesh_from_vertices", category="mesh", risk="mutating",
         description="Create a mesh from explicit vertices (mm) and optional faces (index lists). Vertex coordinates are local to the object origin. With no faces a verts-only point cloud is created. Returns object id.",
         parameters=_schema({
             "name": _NAME,
             "vertices_mm": {"type": "array", "items": {**_mm3("a vertex [x, y, z] in mm")},
                             "description": "at least 1 vertex"},
             "faces": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}},
                       "description": "optional polygon vertex-index loops, e.g. [[0,1,2,3]]"}}, []),
    ),
    dict(name="enter_edit_mode", category="mesh", risk="safe",
         description="Enter edit mode on an object (mesh only).",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    dict(name="exit_edit_mode", category="mesh", risk="safe",
         description="Leave edit mode back to object mode.",
         parameters=_schema({}, [])),
    dict(name="get_mesh_stats", category="mesh", risk="safe",
         description="Vertices/edges/faces/polygon triangles of an object's mesh.",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    dict(name="get_bounding_box", category="mesh", risk="safe",
         description="World-space axis-aligned bounding box in mm (min/max/center/size).",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    # --------------------------------------------------------- modifier
    dict(name="add_bevel", category="modifier", risk="mutating",
         description="Add a bevel modifier (rounds edges/corners). width_mm in millimetres.",
         parameters=_schema({"object_id": _OBJECT_ID, "width_mm": _NUMBER,
                             "segments": {"type": "integer", "description": "bevel smoothness segments (default 4)"},
                             "profile": {**_NUMBER, "description": "0..1 profile (default 0.5)"},
                             "limit_method": {"type": "string", "enum": ["ANGLE", "NONE"]}}, ["object_id", "width_mm"])),
    dict(name="add_boolean", category="modifier", risk="mutating",
         description="Add a boolean modifier to object_id using another mesh object (tool_object_id). Typical: cut a hole by subtracting a cylinder.",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "operation": {"type": "string", "enum": ["DIFFERENCE", "UNION", "INTERSECT"], "default": "DIFFERENCE"},
                             "tool_object_id": _OBJECT_ID}, ["object_id", "tool_object_id"])),
    dict(name="add_solidify", category="modifier", risk="mutating",
         description="Add a solidify modifier (wall thickness) in mm. Negative thickness goes inward.",
         parameters=_schema({"object_id": _OBJECT_ID, "thickness_mm": _NUMBER,
                             "offset": {**_NUMBER, "description": "-1..1 where the wall sits, default -1 (inward)"}}, ["object_id", "thickness_mm"])),
    dict(name="add_subdivision", category="modifier", risk="mutating",
         description="Add a subdivision-surface modifier for smoothing.",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "levels_viewport": {"type": "integer", "default": 2},
                             "levels_render": {"type": "integer"}}, ["object_id"])),
    dict(name="add_mirror", category="modifier", risk="mutating",
         description="Add a mirror modifier on one world axis.",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "axis": {"type": "string", "enum": ["X", "Y", "Z"], "default": "X"}}, ["object_id"])),
    dict(name="add_array", category="modifier", risk="mutating",
         description="Add an array (linear repeat) modifier: count copies spaced by offset_mm.",
         parameters=_schema({"object_id": _OBJECT_ID, "count": {"type": "integer", "minimum": 1},
                             "offset_mm": {**_mm3("spacing between copies in mm")}}, ["object_id", "count", "offset_mm"])),
    dict(name="remove_modifier", category="modifier", risk="mutating",
         description="Remove one modifier from an object by its exact modifier name.",
         parameters=_schema({"object_id": _OBJECT_ID, "modifier_name": _STR}, ["object_id", "modifier_name"])),
    dict(name="apply_modifier", category="modifier", risk="mutating",
         description="Apply (bake) one modifier into the mesh. modifier_name is required — list modifiers first via get_object_details.",
         parameters=_schema({"object_id": _OBJECT_ID, "modifier_name": _STR}, ["object_id", "modifier_name"])),
    dict(name="set_modifier_property", category="modifier", risk="mutating",
         description="Set a property on an existing modifier. Supported property keys by modifier type: bevel: width_mm, segments, profile; solidify: thickness_mm, offset; array: count, offset_mm (use offset vector [dx,dy,dz] per axis via key 'constant_offset' given as 3-array); subdivision: levels_viewport, levels_render; boolean: solver. Provide value as number or boolean or 3-array.",
         parameters=_schema({"object_id": _OBJECT_ID, "modifier_name": _STR,
                             "property": _STR, "value": {}} , ["object_id", "modifier_name", "property", "value"])),
    # --------------------------------------------------------- material
    dict(name="create_material", category="material", risk="mutating",
         description="Create a new Principled-BSDF material. color as hex string like '#336699'. Returns the material name.",
         parameters=_schema({"name": _NAME, "color_hex": {**_STR, "description": "#rrggbb base color"},
                             "metallic": {**_NUMBER, "description": "0..1"},
                             "roughness": {**_NUMBER, "description": "0..1"}}, ["name"])),
    dict(name="assign_material", category="material", risk="mutating",
         description="Assign a material to all faces of an object (creates the material if missing).",
         parameters=_schema({"object_id": _OBJECT_ID, "material_name": _STR}, ["object_id", "material_name"])),
    dict(name="set_base_color", category="material", risk="mutating",
         description="Set the base color of the object's first material (or a named material).",
         parameters=_schema({"object_id": _OBJECT_ID, "color_hex": {**_STR, "description": "#rrggbb"},
                             "material_name": {**_STR, "description": "optional; defaults to the object's first material"}},
                            ["object_id", "color_hex"])),
    dict(name="set_metallic", category="material", risk="mutating",
         description="Set metallic factor (0..1) of the object's first (or named) material.",
         parameters=_schema({"object_id": _OBJECT_ID, "metallic": _NUMBER, "material_name": _STR}, ["object_id", "metallic"])),
    dict(name="set_roughness", category="material", risk="mutating",
         description="Set roughness factor (0..1) of the object's first (or named) material.",
         parameters=_schema({"object_id": _OBJECT_ID, "roughness": _NUMBER, "material_name": _STR}, ["object_id", "roughness"])),
    dict(name="list_materials", category="material", risk="safe",
         description="List all materials in the file with the number of objects using them.",
         parameters=_schema({}, [])),
    # ----------------------------------------------------------- camera
    dict(name="create_camera", category="camera", risk="mutating",
         description="Create a camera object (optionally placed and aimed). Returns its object id.",
         parameters=_schema({"name": _NAME, "location_mm": {**_mm3()},
                             "look_at_object_id": _OBJECT_ID}, [])),
    dict(name="set_active_camera", category="camera", risk="safe",
         description="Make a camera the active scene camera.",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    dict(name="frame_selected", category="camera", risk="safe",
         description="Frame the selected objects in the 3D viewport (requires the UI viewport; returns an error headless).",
         parameters=_schema({}, [])),
    dict(name="look_at_object", category="camera", risk="mutating",
         description="Point camera_id at target_id (both object ids).",
         parameters=_schema({"camera_id": _OBJECT_ID, "target_id": _OBJECT_ID}, ["camera_id", "target_id"])),
    dict(name="set_camera_position", category="camera", risk="mutating",
         description="Move a camera to an absolute world location in mm. Omit camera_id to use the active camera.",
         parameters=_schema({"camera_id": _OBJECT_ID, "location_mm": {**_mm3()}}, ["location_mm"])),
    # ------------------------------------------------------ render/vision
    dict(name="capture_viewport", category="render", risk="safe",
         description="Render a PNG screenshot of the target object(s) — or the whole scene when object_ids is empty — from a stable 3/4 perspective. Returns the image (base64 PNG). Use it to visually verify geometry after edits.",
         parameters=_schema({"object_ids": {**_STR_LIST, "description": "optional object ids to frame; empty = whole scene"},
                             "width": {"type": "integer", "default": 1024},
                             "height": {"type": "integer", "default": 768}}, [])),
    dict(name="render_image", category="render", risk="safe",
         description="Render a single PNG from the active scene camera (or a 3/4 default when no camera).",
         parameters=_schema({"object_ids": {**_STR_LIST, "description": "optional framing target"},
                             "width": {"type": "integer", "default": 1024},
                             "height": {"type": "integer", "default": 768}}, [])),
    dict(name="render_multi_angle", category="render", risk="safe",
         description="Render PNG screenshots of the target object from several angles. Returns one image per requested angle.",
         parameters=_schema({"object_ids": {**_STR_LIST, "description": "optional ids to frame; empty = whole scene"},
                             "angles": {"type": "array", "items": {"type": "string", "enum": ["front", "back", "left", "right", "top", "bottom", "perspective"]}},
                             "width": {"type": "integer", "default": 1024},
                             "height": {"type": "integer", "default": 768}}, [])),
    dict(name="capture_object_views", category="render", risk="safe",
         description="Standard visual-verification capture: front, back, left, right, top and perspective renders of the target object(s).",
         parameters=_schema({"object_ids": {**_STR_LIST, "description": "optional ids; empty = whole scene"},
                             "width": {"type": "integer", "default": 640},
                             "height": {"type": "integer", "default": 480}}, [])),
    # -------------------------------------------------------------- file
    dict(name="save_blend", category="file", risk="safe",
         description="Save the current .blend to its existing path (fails if the file was never saved).",
         parameters=_schema({}, [])),
    dict(name="save_blend_as", category="file", risk="safe",
         description="Save the .blend to an absolute filepath (parent directory must exist).",
         parameters=_schema({"filepath": _STR}, ["filepath"])),
    dict(name="get_current_file", category="file", risk="safe",
         description="Return the current .blend file path (or null for an unsaved scene).",
         parameters=_schema({}, [])),
    # ----------------------------------------------------------- history
    dict(name="create_checkpoint", category="history", risk="safe",
         description="Create a named snapshot checkpoint of the whole scene (a .blend copy). Used for undo. You normally do NOT need to call this — the harness does it automatically before the first destructive change.",
         parameters=_schema({"label": _STR}, [])),
    dict(name="restore_checkpoint", category="history", risk="destructive",
         description="Restore the whole scene from a checkpoint id (from list_checkpoints). Wipes all later changes.",
         parameters=_schema({"checkpoint_id": _STR}, ["checkpoint_id"])),
    dict(name="list_checkpoints", category="history", risk="safe",
         description="List available scene checkpoints.",
         parameters=_schema({}, [])),
    dict(name="undo_last_ai_action", category="history", risk="destructive",
         description="Undo the most recent AI step by restoring its before-checkpoint.",
         parameters=_schema({}, [])),
    # ------------------------------------------------------------ python
    dict(name="execute_blender_python", category="python", risk="exec",
         description="Execute a short, sandboxed Python snippet with `bpy` and `C` (= bpy.context) available. BLOCKED by default — only enabled when the server config ALLOW_EXECUTE_PYTHON=true. Prefer structured tools whenever possible; use this only for operations no structured tool covers, keep code under ~60 lines, do not import anything but bpy/mathutils/math/json, do not touch files or subprocesses.",
         parameters=_schema({"code": _STR}, ["code"])),
    # ---------------------------------------------------- product design
    dict(name="create_rounded_box", category="product", risk="mutating",
         description="Product-design helper: create a solid box with rounded vertical corners in mm. Returns object id.",
         parameters=_schema({"name": _NAME, "dimensions_mm": {**_mm3("width, depth, height in mm")},
                             "corner_radius_mm": _NUMBER, "corner_segments": {"type": "integer", "default": 6}},
                            ["dimensions_mm", "corner_radius_mm"])),
    dict(name="create_shell", category="product", risk="mutating",
         description="Product-design helper: create a hollow shell (4 walls + closed bottom) of given outer dimensions in mm, wall thickness and bottom thickness, optionally with rounded vertical corners. Returns object id.",
         parameters=_schema({"name": _NAME, "dimensions_mm": {**_mm3("outer width, depth, height in mm")},
                             "wall_thickness_mm": _NUMBER, "bottom_thickness_mm": _NUMBER,
                             "corner_radius_mm": _NUMBER, "corner_segments": {"type": "integer", "default": 6}},
                            ["dimensions_mm", "wall_thickness_mm", "bottom_thickness_mm"])),
    dict(name="set_exact_dimensions_mm", category="product", risk="mutating",
         description="Product-design helper: set an object's exact outer dimensions in mm (identical to set_dimensions).",
         parameters=_schema({"object_id": _OBJECT_ID, "dimensions_mm": {**_mm3("width, depth, height in mm")}},
                            ["object_id", "dimensions_mm"])),
    dict(name="measure_distance", category="product", risk="safe",
         description="Measure the distance between two objects (origins, centers or closest points) in mm.",
         parameters=_schema({"object_a_id": _OBJECT_ID, "object_b_id": _OBJECT_ID,
                             "mode": {"type": "string", "enum": ["origin", "center", "closest"], "default": "origin"}},
                            ["object_a_id", "object_b_id"])),
    dict(name="measure_object", category="product", risk="safe",
         description="Measure an object: bounding dimensions in mm, world-space bounding box min/max/center.",
         parameters=_schema({"object_id": _OBJECT_ID}, ["object_id"])),
    dict(name="center_object", category="product", risk="mutating",
         description="Center an object: move its origin to the geometry center and/or move the object to the world origin (or to an optional anchor object).",
         parameters=_schema({"object_id": _OBJECT_ID,
                             "origin_to_geometry": {**_BOOL, "description": "default true"},
                             "move_to_world_origin": {**_BOOL, "description": "default false"},
                             "align_to": {**_OBJECT_ID, "description": "optional: align center with this object instead of the world origin"}}, ["object_id"])),
    dict(name="align_objects", category="product", risk="mutating",
         description="Align several objects along one axis (min/center/max) relative to a reference object (default: the active/selected first object).",
         parameters=_schema({"object_ids": {**_STR_LIST, "description": "ids to move"},
                             "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                             "mode": {"type": "string", "enum": ["min", "center", "max"]},
                             "reference_id": {**_OBJECT_ID, "description": "optional reference object; default active"}},
                            ["object_ids", "axis", "mode"])),
    dict(name="mirror_object", category="product", risk="mutating",
         description="Create a mirrored copy of an object across a plane through its own origin (X, Y or Z). Returns the mirrored object id.",
         parameters=_schema({"object_id": _OBJECT_ID, "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                             "name": _NAME}, ["object_id", "axis"])),
    dict(name="create_cutout", category="product", risk="mutating",
         description="Cut a rectangular passage (through-hole) out of a target object at a world position in mm. Returns nothing; the boolean is applied when possible.",
         parameters=_schema({"target_id": _OBJECT_ID,
                             "position_mm": {**_mm3("world position of the cutout center")},
                             "size_mm": {**_mm3("cutout width/depth/height in mm")}}, ["target_id", "position_mm", "size_mm"])),
    dict(name="create_hole", category="product", risk="mutating",
         description="Drill a circular hole through a target object at a world position in mm (cylinder boolean). Returns nothing.",
         parameters=_schema({"target_id": _OBJECT_ID, "position_mm": {**_mm3("world position of the hole center")},
                             "radius_mm": _NUMBER}, ["target_id", "position_mm", "radius_mm"])),
    dict(name="create_repeated_holes", category="product", risk="mutating",
         description="Drill a rectangular grid of circular holes (e.g. ventilation) in the XY plane of a target at a given center, with counts, spacing in mm and hole radius in mm. Holes extend through the object along +Z.",
         parameters=_schema({"target_id": _OBJECT_ID, "radius_mm": _NUMBER,
                             "count_x": {"type": "integer"}, "count_y": {"type": "integer"},
                             "spacing_mm": {**_mm3("[dx, dy] spacing between hole centers in mm")},
                             "center_mm": {**_mm3("world XY center of the grid; Z is ignored")},
                             "axis": {"type": "string", "enum": ["X", "Y", "Z"], "default": "Z"}},
                            ["target_id", "radius_mm", "count_x", "count_y", "spacing_mm"])),
    dict(name="set_wall_thickness", category="product", risk="mutating",
         description="Give an open mesh a wall by adding/applying a solidify modifier with the given wall thickness in mm (negative = inside).",
         parameters=_schema({"object_id": _OBJECT_ID, "thickness_mm": _NUMBER,
                             "apply": {**_BOOL, "description": "apply the modifier after adding (default false)"}},
                            ["object_id", "thickness_mm"])),
    dict(name="create_simple_keyboard_case", category="product", risk="mutating",
         description="Product-design helper: generate a simple 75%-style keyboard case base as a rounded shell in mm. Returns the case object id.",
         parameters=_schema({"name": _NAME, "width_mm": _NUMBER, "depth_mm": _NUMBER, "height_mm": _NUMBER,
                             "corner_radius_mm": _NUMBER, "wall_thickness_mm": _NUMBER,
                             "bottom_thickness_mm": {**_NUMBER, "default": 2.0},
                             "corner_segments": {"type": "integer", "default": 6}},
                            ["width_mm", "depth_mm", "height_mm", "corner_radius_mm", "wall_thickness_mm"])),
    dict(name="create_simple_mouse_volume", category="product", risk="mutating",
         description="Product-design helper: generate a simple symmetrical mouse volume (scaled sphere) with length/width/height in mm. Returns the object id.",
         parameters=_schema({"name": _NAME, "length_mm": _NUMBER, "width_mm": _NUMBER, "height_mm": _NUMBER,
                             "segments": {"type": "integer", "default": 48}, "rings": {"type": "integer", "default": 24}},
                            ["length_mm", "width_mm", "height_mm"])),
    dict(name="create_simple_knob", category="product", risk="mutating",
         description="Product-design helper: generate a simple cylindrical knob (optionally with rounded top edge via bevel) in mm. Returns the object id.",
         parameters=_schema({"name": _NAME, "diameter_mm": _NUMBER, "height_mm": _NUMBER,
                             "corner_radius_mm": _NUMBER, "location_mm": {**_mm3()}},
                            ["diameter_mm", "height_mm"])),
]

_BY_NAME: Dict[str, Dict[str, Any]] = {d["name"]: d for d in TOOL_DEFS}


def all_tool_specs(include_exec: bool = True) -> List[ToolSpec]:
    specs: List[ToolSpec] = []
    for d in TOOL_DEFS:
        if not include_exec and d["name"] == "execute_blender_python":
            continue
        specs.append(
            ToolSpec(
                name=d["name"],
                description=d["description"],
                category=d["category"],
                risk=d["risk"],
                timeout_default_s=float(d.get("timeout_default_s", 240 if d["category"] == "render" else 60)),
                parameters=d["parameters"],
            )
        )
    return specs


def spec_by_name(name: str) -> ToolSpec:
    specs = all_tool_specs(include_exec=True)
    for s in specs:
        if s.name == name:
            return s
    raise KeyError(f"unknown tool: {name}")


def llm_tools(include_exec: bool = True) -> List[Dict[str, Any]]:
    from harness_server.schemas.tools import specs_to_llm

    return specs_to_llm(all_tool_specs(include_exec=include_exec))


def risk_of(tool: str) -> str:
    d = _BY_NAME.get(tool)
    return d["risk"] if d else "safe"


def category_of(tool: str) -> str:
    d = _BY_NAME.get(tool)
    return d["category"] if d else "misc"


def is_known_tool(tool: str) -> bool:
    return tool in _BY_NAME
