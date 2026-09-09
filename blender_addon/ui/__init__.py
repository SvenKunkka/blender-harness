"""N-Panel UI ("AI Harness") for the add-on plus its operators.

The panel is a thin remote for the harness server: it shows connection status,
lets you start/stop the bridge, send a prompt, take screenshots, read the scene
and browse/undo the AI history. The full chat experience lives in the Web UI;
this panel deliberately stays compact (spec: not "a ChatGPT inside Blender").
"""

from __future__ import annotations

import bpy

AddonPreferences = bpy.types.AddonPreferences
Operator = bpy.types.Operator
Panel = bpy.types.Panel
StringProperty = bpy.props.StringProperty
IntProperty = bpy.props.IntProperty

ADDON_PKG = __package__.split(".")[0] if __package__ else "blender_addon"


def _bridge():
    from blender_addon.transport.bridge import bridge

    return bridge()


def _prefs(context):
    return context.preferences.addons[ADDON_PKG].preferences


# ---------------------------------------------------------------------------
# preferences
# ---------------------------------------------------------------------------

class BHH_AddonPreferences(AddonPreferences):
    bl_idname = ADDON_PKG

    host: StringProperty(name="Harness host", default="127.0.0.1")
    port: IntProperty(name="Harness port", default=9876, min=1, max=65535)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, "host")
        row.prop(self, "port")


# ---------------------------------------------------------------------------
# operators
# ---------------------------------------------------------------------------

class BHH_OT_connect(Operator):
    bl_idname = "bh_harness.connect"
    bl_label = "Connect"
    bl_description = "Connect to the harness server"

    def execute(self, context):
        prefs = _prefs(context)
        br = _bridge()
        br.configure(prefs.host, prefs.port)
        br.start()
        self.report({"INFO"}, f"connecting to {prefs.host}:{prefs.port}…")
        return {"FINISHED"}


class BHH_OT_disconnect(Operator):
    bl_idname = "bh_harness.disconnect"
    bl_label = "Disconnect"
    bl_description = "Stop the harness connection"

    def execute(self, context):
        _bridge().stop()
        self.report({"INFO"}, "disconnected")
        return {"FINISHED"}


class BHH_OT_run_prompt(Operator):
    bl_idname = "bh_harness.run_prompt"
    bl_label = "Run"
    bl_description = "Send the prompt to the harness agent"

    def execute(self, context):
        prompt = context.scene.bh_prompt.strip()
        if not prompt:
            self.report({"WARNING"}, "type a prompt first")
            return {"CANCELLED"}
        br = _bridge()
        if not br.is_connected():
            self.report({"ERROR"}, "not connected — press Connect first")
            return {"CANCELLED"}
        rid = br.run_prompt(prompt)
        context.scene.bh_prompt = ""
        return {"FINISHED"}


class BHH_OT_server_action(Operator):
    bl_idname = "bh_harness.server_action"
    bl_label = "Server action"
    bl_description = "Ask the harness server to perform an action"
    action: StringProperty(default="history")
    history_id: IntProperty(default=0)

    def execute(self, context):
        br = _bridge()
        if not br.is_connected():
            self.report({"ERROR"}, "not connected")
            return {"CANCELLED"}
        if self.action == "undo_step":
            br.server_action("undo_step", {"history_id": self.history_id})
        elif self.action == "restore_step":
            br.server_action("restore_step", {"history_id": self.history_id})
        elif self.action == "checkpoint":
            br.server_action("checkpoint", {"label": f"manual {bpy.context.scene.name}"})
        elif self.action == "screenshot":
            br.server_action("screenshot")
        else:
            br.server_action(self.action)
        return {"FINISHED"}


class BHH_OT_clear_log(Operator):
    bl_idname = "bh_harness.clear_log"
    bl_label = "Clear log"

    def execute(self, context):
        _bridge().log_tail.clear()
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# panel
# ---------------------------------------------------------------------------

class BHH_PT_main(Panel):
    bl_label = "AI Harness"
    bl_idname = "BHH_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Harness"

    def draw(self, context):
        br = _bridge()
        layout = self.layout
        connected = br.is_connected()

        # connection
        box = layout.box()
        row = box.row()
        icon = "CHECKMARK" if connected else ("TIME" if br.status == "connecting" else "ERROR")
        row.label(text=f"Status: {br.status}", icon=icon)
        if connected:
            box.label(text=f"server {br.server_version or '?'} · {br.connected_at}", icon="WORLD")
        elif br.last_error:
            box.label(text=br.last_error[:60], icon="ERROR")
        sub = box.row()
        prefs = _prefs(context)
        sub.prop(prefs, "host", text="")
        sub.prop(prefs, "port", text="")
        row2 = box.row(align=True)
        if not connected:
            row2.operator("bh_harness.connect", icon="PLAY")
        else:
            row2.operator("bh_harness.disconnect", icon="PAUSE")

        # selection + quick actions
        box = layout.box()
        active = context.view_layer.objects.active if context.view_layer else None
        if active is not None:
            oid = active.get("bh_id") or "no-id"
            box.label(text=f"Active: {active.name}  ({oid})", icon="OBJECT_DATA")
        else:
            box.label(text="No active object", icon="OBJECT_DATA")
        row = box.row(align=True)
        row.enabled = connected
        row.operator("bh_harness.server_action", text="Read Scene", icon="WORLD").action = "scene"
        row.operator("bh_harness.server_action", text="Shot", icon="RESTRICT_RENDER_OFF").action = "screenshot"
        row.operator("bh_harness.server_action", text="Ckpt", icon="FILE_TICK").action = "checkpoint"

        # prompt runner
        box = layout.box()
        box.label(text="Prompt", icon="GREASEPENCIL")
        box.prop(context.scene, "bh_prompt", text="")
        row = box.row()
        row.enabled = connected
        row.operator("bh_harness.run_prompt", icon="PLAY")
        if br.last_run_event:
            box.label(text="last event", icon="INFO")
            for chunk in _chunks(br.last_run_event, 60):
                box.label(text=chunk)
        elif br.last_prompt_result:
            box.label(text=str(br.last_prompt_result)[:80])

        # history
        box = layout.box()
        head = box.row()
        head.label(text=f"AI History ({len(br.history_rows)})", icon="HISTORY")
        head.operator("bh_harness.server_action", text="Refresh", icon="FILE_REFRESH").action = "history"
        if br.history_rows:
            for entry in br.history_rows[:8]:
                seq = entry.get("seq", "?")
                prompt = (entry.get("prompt") or "")[:28]
                st = entry.get("status", "")
                icon = "CHECKBOX_HLT" if st == "done" else ("CHECKBOX_DEHLT" if st == "undone" else "ERROR")
                row = box.row()
                row.label(text=f"v{seq} {prompt}", icon=icon)
                action = "undo_step" if st != "undone" else "restore_step"
                op = row.operator("bh_harness.server_action", text="↩" if st != "undone" else "⟳", emboss=False)
                op.action = action
                op.history_id = int(entry["id"])
        else:
            box.label(text="no history yet — run a prompt")

        # debug log
        box = layout.box()
        head = box.row()
        head.label(text="Debug Log", icon="CONSOLE")
        head.operator("bh_harness.clear_log", text="", icon="X", emboss=False)
        for line in br.log_tail[-8:]:
            box.label(text=line[:64])

        # hint
        layout.label(text="Web UI: http://127.0.0.1:9876  (or :5173 dev)", icon="URL")


def _chunks(text: str, n: int):
    return [text[i:i + n] for i in range(0, len(text), n)]


_CLASSES = [
    BHH_AddonPreferences,
    BHH_OT_connect,
    BHH_OT_disconnect,
    BHH_OT_run_prompt,
    BHH_OT_server_action,
    BHH_OT_clear_log,
    BHH_PT_main,
]


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    if not hasattr(bpy.types.Scene, "bh_prompt"):
        bpy.types.Scene.bh_prompt = StringProperty(
            name="AI Prompt", description="Natural-language instruction for the Blender Harness agent",
            default="", maxlen=6000, options={"TEXTAREA"})
    # re-arm the bridge pump after a checkpoint restore / file open
    if hasattr(bpy.app, "handlers") and callable(getattr(bpy.app.handlers, "load_post", None)):
        if _restart_pump not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(_restart_pump)


def unregister() -> None:
    if hasattr(bpy.app, "handlers") and _restart_pump in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_restart_pump)
    if hasattr(bpy.types.Scene, "bh_prompt"):
        try:
            del bpy.types.Scene.bh_prompt
        except Exception:  # noqa: BLE001
            pass
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:  # noqa: BLE001
            pass


def _restart_pump(*_args) -> None:
    try:
        _bridge().ensure_pump()
    except Exception:  # noqa: BLE001
        pass
