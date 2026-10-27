bl_info = {
    "name": "myBlend Recovery",
    "author": "Malik",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "Top Bar > myBlend",
    "description": "External compressed version history for complete Blender files",
    "category": "System",
}

import bpy
import gzip
import json
import os
import re
import shutil
import tempfile
from datetime import datetime


_MANIFEST = "manifest.json"
_PREFIX = "myBlend_"
_ASSET_DIR = "assets"


def _blend_path():
    return bpy.data.filepath


def _history_dir():
    path = _blend_path()
    if not path:
        return ""
    return os.path.join(os.path.dirname(path), ".myBlend.history")


def _read_manifest():
    directory = _history_dir()
    if not directory:
        return []
    path = os.path.join(directory, _MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            return []
        for index, entry in enumerate(data):
            entry["number"] = index + 1
            entry["image_count"] = len(entry.get("images", []))
        return data
    except (OSError, ValueError):
        return []


def _write_manifest(entries):
    for index, entry in enumerate(entries):
        entry["number"] = index + 1
        entry["image_count"] = len(entry.get("images", []))
    directory = _history_dir()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, _MANIFEST)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(entries, file, indent=2)
    os.replace(temporary, path)
    try:
        os.system('attrib +h "%s"' % directory)
    except OSError:
        pass


def _safe_name(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value[:80] or "Version"


def _asset_root():
    return os.path.join(_history_dir(), _ASSET_DIR)


def _entry_size(entry):
    total = int(entry.get("size", 0))
    for image in entry.get("images", []):
        total += int(image.get("size", 0))
    return total


def _history_size(entries=None):
    if entries is None:
        entries = _read_manifest()
    return sum(_entry_size(entry) for entry in entries)


def _format_size(value):
    units = ("B", "KB", "MB", "GB")
    size = float(value)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return "%.1f %s" % (size, unit)
        size /= 1024.0


def _copy_external_images(version_key):
    images = []
    asset_dir = os.path.join(_asset_root(), version_key)
    os.makedirs(asset_dir, exist_ok=True)
    used_names = set()
    for image in bpy.data.images:
        if image.source != "FILE":
            continue
        source_path = bpy.path.abspath(image.filepath)
        if not source_path or not os.path.isfile(source_path):
            continue
        base_name = os.path.basename(source_path)
        name, ext = os.path.splitext(base_name)
        candidate = base_name
        index = 1
        while candidate in used_names:
            candidate = "%s_%d%s" % (name, index, ext)
            index += 1
        used_names.add(candidate)
        destination = os.path.join(asset_dir, candidate)
        shutil.copy2(source_path, destination)
        images.append({
            "name": image.name,
            "src": source_path,
            "file": candidate,
            "size": os.path.getsize(destination),
        })
    return images


def _restore_external_images(entry, history_dir=None):
    version_key = entry.get("id")
    if not version_key:
        return 0
    history_dir = history_dir or _history_dir()
    copied = 0
    for image in entry.get("images", []):
        file_name = image.get("file")
        image_name = image.get("name")
        if not image_name or not file_name:
            continue
        asset_path = os.path.join(history_dir, _ASSET_DIR, version_key, file_name)
        if not os.path.isfile(asset_path):
            continue
        try:
            image_data = bpy.data.images.get(image_name)
            if image_data is None:
                image_data = bpy.data.images.load(asset_path, check_existing=True)
            image_data.filepath = asset_path
            image_data.reload()
            copied += 1
        except (OSError, RuntimeError):
            continue
    return copied


def _save_snapshot(name, include_images):
    source = _blend_path()
    if not source or not os.path.isfile(source):
        raise RuntimeError("Save the current .blend file before creating a version")
    directory = _history_dir()
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = _safe_name(name)
    version_key = "%s%s_%s" % (_PREFIX, stamp, safe)
    filename = "%s.blend.gz" % version_key
    destination = os.path.join(directory, filename)
    temporary_blend = tempfile.NamedTemporaryFile(
        suffix=".blend", delete=False, dir=directory
    ).name
    temporary_gzip = destination + ".tmp"
    try:
        if not bpy.ops.wm.save_as_mainfile(filepath=temporary_blend, copy=True):
            raise RuntimeError("Blender could not write the snapshot")
        with open(temporary_blend, "rb") as source_file:
            with gzip.open(temporary_gzip, "wb", compresslevel=6) as target_file:
                shutil.copyfileobj(source_file, target_file)
        if os.path.getsize(temporary_gzip) < 32:
            raise RuntimeError("Snapshot validation failed")
        os.replace(temporary_gzip, destination)
    finally:
        for path in (temporary_blend, temporary_gzip):
            if os.path.exists(path):
                os.remove(path)
    copied_images = _copy_external_images(version_key) if include_images else []
    entries = _read_manifest()
    entries.append({
        "id": version_key,
        "number": len(entries) + 1,
        "name": name.strip() or "Version",
        "file": filename,
        "created": datetime.now().isoformat(timespec="seconds"),
        "size": os.path.getsize(destination),
        "image_count": len(copied_images),
        "images": copied_images,
    })
    _write_manifest(entries)
    return entries[-1]


def _remove_entry(entry):
    path = os.path.join(_history_dir(), entry["file"])
    if os.path.isfile(path):
        os.remove(path)
    version_key = entry.get("id")
    if version_key:
        asset_dir = os.path.join(_asset_root(), version_key)
        if os.path.isdir(asset_dir):
            shutil.rmtree(asset_dir)


def _selected_index(settings, entries):
    try:
        index = int(settings.version_index)
    except (TypeError, ValueError):
        index = -1
    if index < 0 or index >= len(entries):
        return -1
    return index


def _reset_version_selection(settings, entries):
    if entries:
        settings.version_index = "0"
    else:
        settings.version_index = "-1"


class MYBLEND_OT_save(bpy.types.Operator):
    bl_idname = "myblend.save_version"
    bl_label = "Save myBlend Version"
    bl_description = "Create a compressed external snapshot of the complete .blend file"

    def execute(self, context):
        try:
            entry = _save_snapshot(
                context.scene.myblend.version_name,
                context.scene.myblend.include_images,
            )
        except (OSError, RuntimeError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Saved %s (images: %d, versions: %d)"
            % (entry["name"], entry["image_count"], entry["number"]),
        )
        return {"FINISHED"}


class MYBLEND_OT_restore(bpy.types.Operator):
    bl_idname = "myblend.restore_version"
    bl_label = "Restore Selected Version"
    bl_description = "Restore the complete Blender scene from a myBlend snapshot"

    def execute(self, context):
        entries = _read_manifest()
        index = _selected_index(context.scene.myblend, entries)
        if index < 0:
            self.report({"WARNING"}, "Select a saved version")
            return {"CANCELLED"}
        original = _blend_path()
        history_dir = _history_dir()
        try:
            selected = entries[index]
            temporary = tempfile.NamedTemporaryFile(
                suffix=".blend", delete=False
            ).name
            try:
                with gzip.open(os.path.join(_history_dir(), selected["file"]), "rb") as source:
                    with open(temporary, "wb") as target:
                        shutil.copyfileobj(source, target)
                bpy.ops.wm.open_mainfile(filepath=temporary, load_ui=False)
                restored_images = _restore_external_images(selected, history_dir)
                bpy.ops.wm.save_as_mainfile(filepath=original)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
        except (OSError, RuntimeError) as error:
            self.report({"ERROR"}, "Restore failed: %s" % error)
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Restored %s (%d images); use Save Version to create a new checkpoint"
            % (selected["name"], restored_images),
        )
        return {"FINISHED"}


class MYBLEND_OT_delete(bpy.types.Operator):
    bl_idname = "myblend.delete_version"
    bl_label = "Delete Selected Version"

    def execute(self, context):
        entries = _read_manifest()
        index = _selected_index(context.scene.myblend, entries)
        if index < 0:
            self.report({"WARNING"}, "Select a saved version")
            return {"CANCELLED"}
        entry = entries.pop(index)
        try:
            _remove_entry(entry)
            _write_manifest(entries)
        except OSError as error:
            self.report({"ERROR"}, "Delete failed: %s" % error)
            return {"CANCELLED"}
        _reset_version_selection(context.scene.myblend, entries)
        self.report({"INFO"}, "Deleted %s" % entry["name"])
        return {"FINISHED"}


class MYBLEND_OT_cleanup(bpy.types.Operator):
    bl_idname = "myblend.cleanup"
    bl_label = "Apply Retention Limit"

    def execute(self, context):
        entries = _read_manifest()
        count_limit = max(1, context.scene.myblend.max_versions)
        size_limit = max(1, context.scene.myblend.max_history_mb) * 1024 * 1024
        removed = 0
        while len(entries) > count_limit or _history_size(entries) > size_limit:
            _remove_entry(entries.pop(0))
            removed += 1
        _write_manifest(entries)
        _reset_version_selection(context.scene.myblend, entries)
        self.report({
            "INFO"
        }, "Kept %d versions (%s)" % (len(entries), _format_size(_history_size(entries))))
        return {"FINISHED"}


def _version_items(self, context):
    entries = _read_manifest()
    return [(str(index), "#%d %s | %d images | %s" % (
                entry.get("number", index + 1),
                entry["name"],
                entry.get("image_count", 0),
                entry["created"],
            ), "")
            for index, entry in enumerate(entries)] or [("-1", "No saved versions", "")]


class MYBLEND_Settings(bpy.types.PropertyGroup):
    version_name: bpy.props.StringProperty(name="Version Name", default="Checkpoint")
    version_index: bpy.props.EnumProperty(
        name="Saved Version", items=_version_items
    )
    max_versions: bpy.props.IntProperty(name="Keep Versions", default=10, min=1, max=100)
    max_history_mb: bpy.props.IntProperty(
        name="Max History Size (MB)",
        description="Delete oldest versions when compressed history exceeds this size",
        default=2048,
        min=1,
        max=1048576,
    )
    include_images: bpy.props.BoolProperty(
        name="Include External Images",
        description="Copy file-based images into each version snapshot",
        default=True,
    )


class MYBLEND_PT_panel(bpy.types.Panel):
    bl_label = "myBlend Recovery"
    bl_idname = "MYBLEND_PT_panel"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "SCENE"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.myblend
        if not _blend_path():
            layout.label(text="Save the .blend file first")
            return
        entries = _read_manifest()
        layout.label(text="External history: .myBlend.history")
        layout.label(text="Saved versions: %d" % len(entries))
        layout.label(text="History size: %s" % _format_size(_history_size(entries)))
        layout.prop(settings, "version_name")
        layout.prop(settings, "include_images")
        layout.operator("myblend.save_version", icon="FILE_TICK")
        layout.prop(settings, "version_index")
        row = layout.row(align=True)
        row.operator("myblend.restore_version", icon="LOOP_BACK")
        row.operator("myblend.delete_version", icon="TRASH")
        layout.prop(settings, "max_versions")
        layout.prop(settings, "max_history_mb")
        layout.operator("myblend.cleanup", icon="SORTSIZE")


class MYBLEND_PT_view3d_panel(bpy.types.Panel):
    bl_label = "myBlend Recovery"
    bl_idname = "MYBLEND_PT_view3d_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "myBlend"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.myblend
        if not _blend_path():
            layout.label(text="Save the .blend file first")
            return
        entries = _read_manifest()
        layout.label(text="Saved versions: %d" % len(entries))
        layout.label(text="History size: %s" % _format_size(_history_size(entries)))
        layout.prop(settings, "version_name")
        layout.prop(settings, "include_images")
        layout.operator("myblend.save_version", icon="FILE_TICK")
        layout.prop(settings, "version_index")
        row = layout.row(align=True)
        row.operator("myblend.restore_version", icon="LOOP_BACK")
        row.operator("myblend.delete_version", icon="TRASH")
        layout.prop(settings, "max_versions")
        layout.prop(settings, "max_history_mb")
        layout.operator("myblend.cleanup", icon="SORTSIZE")


_classes = (
    MYBLEND_Settings,
    MYBLEND_OT_save,
    MYBLEND_OT_restore,
    MYBLEND_OT_delete,
    MYBLEND_OT_cleanup,
    MYBLEND_PT_panel,
    MYBLEND_PT_view3d_panel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.myblend = bpy.props.PointerProperty(type=MYBLEND_Settings)


def unregister():
    del bpy.types.Scene.myblend
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
