"""A compact fake `bpy` module so the add-on's tool handlers can be exercised
outside Blender. Only the API surface actually used by blender_addon is
implemented; unsupported calls raise AttributeError loudly so tests never pass
by accident.

Install it with:  install_mock_bpy()  (replaces sys.modules['bpy']).
"""

from __future__ import annotations

import contextlib
import sys
import types
from typing import Any, Dict, List, Optional


class _IdDict(dict):
    """dict with .get and item access used for Blender custom properties."""


class Modifier:
    def __init__(self, name: str, type_: str) -> None:
        self.name = name
        self.type = type_
        self.width = 0.0
        self.segments = 1
        self.profile = 0.5
        self.thickness = 0.0
        self.offset = -1.0
        self.levels = 1
        self.render_levels = 1
        self.count = 1
        self.use_axis = [False, False, False]
        self.operation = "DIFFERENCE"
        self.object = None
        self.constant_offset_displace = (0.0, 0.0, 0.0)
        self.limit_method = "ANGLE"
        self.solver = "FAST"


class Modifiers:
    def __init__(self) -> None:
        self._list: List[Modifier] = []

    def new(self, name: str, type: str = "NONE") -> Modifier:
        m = Modifier(name, type)
        self._list.append(m)
        return m

    def remove(self, mod: Modifier) -> None:
        if mod in self._list:
            self._list.remove(mod)

    def __iter__(self):
        return iter(self._list)

    def __len__(self) -> int:
        return len(self._list)


class Vert:
    def __init__(self, co) -> None:
        self.co = tuple(co)


class Poly:
    def __init__(self, indices) -> None:
        self.vertices = list(indices)


class Edge:
    def __init__(self, a, b) -> None:
        self.vertices = (a, b)


class Mesh:
    def __init__(self, name: str) -> None:
        self.name = name
        self.vertices: List[Vert] = []
        self.edges: List[Edge] = []
        self.polygons: List[Poly] = []
        self.materials: List[Material] = []

    def from_pydata(self, vertices, edges, faces) -> None:
        self.vertices = [Vert(v) for v in vertices]
        self.polygons = [Poly(f) for f in faces]
        self.edges = []
        seen = set()
        for f in faces:
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                key = tuple(sorted((a, b)))
                if key not in seen:
                    seen.add(key)
                    self.edges.append(Edge(a, b))
        for e in edges or []:
            self.edges.append(Edge(e[0], e[1]))

    def update(self, **_) -> None:
        pass

    def copy(self) -> "Mesh":
        m = Mesh(self.name + "_copy")
        m.from_pydata([v.co for v in self.vertices], [], [p.vertices for p in self.polygons])
        m.materials = list(self.materials)
        return m


class CameraData:
    def __init__(self, name: str) -> None:
        self.name = name
        self.lens = 50.0


class LightData:
    def __init__(self, name: str) -> None:
        self.name = name
        self.energy = 10.0


class Material:
    def __init__(self, name: str) -> None:
        self.name = name
        self.use_nodes = False
        self.node_tree = None
        self.diffuse_color = (0.8, 0.8, 0.8, 1.0)
        self._props: Dict[str, Any] = {}

    def __getitem__(self, key):
        return self._props[key]

    def __setitem__(self, key, value):
        self._props[key] = value

    def get(self, key, default=None):
        return self._props.get(key, default)


class Object:
    def __init__(self, name: str, data: Any, type_: str) -> None:
        self.name = name
        self.data = data
        self.type = type_
        self.location = (0.0, 0.0, 0.0)
        self.rotation_euler = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self._dimensions = None
        self.hide_viewport = False
        self.hide_render = False
        self.hide_select = False
        self.parent = None
        self.rotation_mode = "XYZ"
        self.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        self.users_collection: List[Any] = []
        self.modifiers = Modifiers()
        self.selected = False
        self._props: Dict[str, Any] = {}

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __setitem__(self, key, value):
        self._props[key] = value

    def __getitem__(self, key):
        return self._props[key]

    @property
    def dimensions(self):
        if self._dimensions is not None:
            return self._dimensions
        if self.type == "MESH" and self.data is not None and self.data.vertices:
            xs = [v.co[0] for v in self.data.vertices]
            ys = [v.co[1] for v in self.data.vertices]
            zs = [v.co[2] for v in self.data.vertices]
            return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        return (0.0, 0.0, 0.0)

    @dimensions.setter
    def dimensions(self, value):
        self._dimensions = tuple(value)

    @property
    def bound_box(self):
        if self.type == "MESH" and self.data is not None and self.data.vertices:
            verts = self.data.vertices
            xs = [v.co[0] for v in verts]
            ys = [v.co[1] for v in verts]
            zs = [v.co[2] for v in verts]
            lo = (min(xs), min(ys), min(zs))
            hi = (max(xs), max(ys), max(zs))
            return (
                (lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], hi[1], lo[2]), (lo[0], hi[1], lo[2]),
                (lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]), (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2]),
            )
        return [(0, 0, 0)] * 8

    def select_set(self, value: bool) -> None:
        self.selected = bool(value)

    def select_get(self) -> bool:
        return self.selected

    def copy(self) -> "Object":
        o = Object(self.name, self.data, self.type)
        o.location = tuple(self.location)
        o.rotation_euler = tuple(self.rotation_euler)
        o.scale = tuple(self.scale)
        o._props = dict(self._props)
        return o


class _LinkedObjects(list):
    """Collection.objects in real Blender has .link/.unlink; so does ours."""

    def __init__(self, collection: "Collection") -> None:
        super().__init__()
        self._coll = collection

    def link(self, obj: Object) -> None:
        if obj not in self:
            self.append(obj)
        if self._coll not in obj.users_collection:
            obj.users_collection.append(self._coll)

    def unlink(self, obj: Object) -> None:
        if obj in self:
            self.remove(obj)
        if self._coll in obj.users_collection:
            obj.users_collection.remove(self._coll)


class Collection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.objects = _LinkedObjects(self)

    def link(self, obj: Object) -> None:
        self.objects.link(obj)

    def unlink(self, obj: Object) -> None:
        self.objects.unlink(obj)


class _Registry:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: List[Any] = []

    def new(self, name: str, data: Any = None):
        if self.kind == "mesh":
            item = Mesh(name)
        elif self.kind == "material":
            item = Material(name)
        elif self.kind == "camera":
            item = CameraData(name)
        elif self.kind == "light":
            item = LightData(name)
        elif self.kind == "object":
            type_ = "EMPTY"
            if isinstance(data, Mesh):
                type_ = "MESH"
            elif isinstance(data, CameraData):
                type_ = "CAMERA"
            elif isinstance(data, LightData):
                type_ = "LIGHT"
            item = Object(name, data, type_)
            self._items.append(item)
            return item
        else:
            raise TypeError(self.kind)
        self._items.append(item)
        return item

    def remove(self, item, do_unlink: bool = True) -> None:
        if item in self._items:
            self._items.remove(item)
            if isinstance(item, Object) and do_unlink:
                for coll in list(item.users_collection):
                    coll.unlink(item)

    def get(self, name: str):
        for i in self._items:
            if i.name == name:
                return i
        return None

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


class _Render:
    def __init__(self) -> None:
        self.engine = "BLENDER_EEVEE_NEXT"
        self.resolution_x = 1920
        self.resolution_y = 1080
        self.resolution_percentage = 100
        self.filepath = "/tmp/out"
        self.image_settings = types.SimpleNamespace(file_format="PNG")


class _UnitSettings:
    system = "METRIC"
    scale_length = 1.0
    length_unit = "MILLIMETERS"
    mass_unit = "KILOGRAMS"


class Scene:
    def __init__(self, name: str, registry: "_Data") -> None:
        self.name = name
        self.collection = Collection("Collection")
        self.camera: Optional[Object] = None
        self.render = _Render()
        self.unit_settings = _UnitSettings()
        self._registry = registry


class _ViewLayer:
    def __init__(self, registry: "_Data") -> None:
        self.registry = registry
        self.active: Optional[Object] = None

    @property
    def objects(self):
        return self.registry.objects


class _Context:
    def __init__(self, data: "_Data") -> None:
        self.data = data
        self.scene = data.scene
        self.view_layer = _ViewLayer(data)
        self.mode = "OBJECT"
        self.selected_objects: List[Object] = []

    @contextlib.contextmanager
    def temp_override(self, **kwargs):
        yield kwargs


class _Ops:
    def __init__(self, ctx: _Context) -> None:
        self._ctx = ctx
        self.calls: List[tuple] = []
        self.object = _ObjectOps(ctx)
        self.wm = _WmOps(ctx)
        self.render = _RenderOps(ctx)
        self.mesh = _MeshOps(ctx)
        self.view3d = _View3dOps(ctx)

    def select_all(self, action: str) -> dict:
        if action == "DESELECT":
            for o in self._ctx.data.objects:
                o.selected = False
            self._ctx.selected_objects = []
        return {"FINISHED"}


class _ObjectOps:
    def __init__(self, ctx: _Context) -> None:
        self.ctx = ctx

    def mode_set(self, mode: str) -> dict:
        self.ctx.mode = mode
        return {"FINISHED"}

    def select_all(self, action: str) -> dict:
        return _Ops(self.ctx).select_all(action)

    def modifier_apply(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            kwargs.update(args[0])
        self.ctx.data.last_modifier_apply = kwargs
        return {"FINISHED"}

    def origin_set(self, *args, **kwargs):
        return {"FINISHED"}


class _MeshOps:
    def __init__(self, ctx: _Context) -> None:
        self.ctx = ctx

    def primitive_cube_add(self, *a, **kw):
        raise RuntimeError("not used by blender_addon (procedural builders)")


class _WmOps:
    def __init__(self, ctx: _Context) -> None:
        self.ctx = ctx
        self.saved_files: List[str] = []
        self.opened_files: List[str] = []

    def save_as_mainfile(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            kwargs.update(args[0])
        path = kwargs.get("filepath", "/tmp/x.blend")
        with open(path, "wb") as fh:
            fh.write(b"BLENDERTEST")
        self.saved_files.append(path)
        return {"FINISHED"}

    def save_mainfile(self, *args, **kwargs):
        path = kwargs.get("filepath", "/tmp/x.blend")
        with open(path, "wb") as fh:
            fh.write(b"BLENDERTEST")
        self.saved_files.append(path)
        return {"FINISHED"}

    def open_mainfile(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            kwargs.update(args[0])
        self.opened_files.append(kwargs.get("filepath", ""))
        return {"FINISHED"}


class _RenderOps:
    def __init__(self, ctx: _Context) -> None:
        self.ctx = ctx
        self.renders = 0

    def render(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            kwargs.update(args[0])
        self.renders += 1
        # simulate Blender writing the PNG
        import os

        target = self.ctx.scene.render.filepath
        with open(target, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
        return {"FINISHED"}


class _View3dOps:
    def __init__(self, ctx: _Context) -> None:
        self.ctx = ctx

    def view_selected(self, *a, **kw):
        return {"FINISHED"}


class _Data:
    def __init__(self) -> None:
        self.objects = _Registry("object")
        self.meshes = _Registry("mesh")
        self.materials = _Registry("material")
        self.cameras = _Registry("camera")
        self.lights = _Registry("light")
        self.collections = []
        self.scene = Scene("Scene", self)
        self.collections.append(self.scene.collection)
        self.scenes = [self.scene]
        self.filepath = ""
        self.last_modifier_apply = None


class _Timers:
    def __init__(self) -> None:
        self.registered: List[Any] = []

    def register(self, fn, persistent: bool = False):
        self.registered.append(fn)

    def unregister(self, fn):
        if fn in self.registered:
            self.registered.remove(fn)


class _Handlers:
    def __init__(self) -> None:
        self.load_post: List[Any] = []


class _Types:
    Scene = Scene
    Object = Object
    AddonPreferences = type("AddonPreferences", (), {"bl_idname": ""})
    Operator = type("Operator", (), {})
    Panel = type("Panel", (), {})


class _Utils:
    @staticmethod
    def register_class(cls):
        pass

    @staticmethod
    def unregister_class(cls):
        pass


def _make_props_module() -> types.ModuleType:
    p = types.ModuleType("bpy.props")

    def make(default):
        def factory(**kwargs):
            return kwargs.get("default", default)

        return factory

    p.StringProperty = make("")
    p.IntProperty = make(0)
    p.BoolProperty = make(False)
    p.FloatProperty = make(0.0)
    p.EnumProperty = make("")
    return p


def make_bpy_module() -> types.ModuleType:
    data = _Data()
    ctx = _Context(data)
    m = types.ModuleType("bpy")
    m.data = data
    m.context = ctx
    m.ops = _Ops(ctx)
    m.app = types.SimpleNamespace(version=(4, 2, 0), timers=_Timers(), handlers=_Handlers())
    m.types = _Types
    m.utils = _Utils
    m.props = _make_props_module()
    return m


def install_mock_bpy() -> types.ModuleType:
    mod = make_bpy_module()
    sys.modules["bpy"] = mod
    return mod


def reset_mock_bpy(mod: types.ModuleType) -> None:
    """Reset the shared fake to a pristine scene between tests."""
    data = mod.data
    for reg in (data.objects, data.meshes, data.materials, data.cameras, data.lights):
        reg._items.clear()
    data.scene = Scene("Scene", data)
    data.collections = [data.scene.collection]
    data.scenes = [data.scene]
    data.filepath = ""
    ctx = mod.context
    ctx.scene = data.scene
    ctx.view_layer = _ViewLayer(data)
    ctx.mode = "OBJECT"
    ctx.selected_objects = []
    mod.ops = _Ops(ctx)
