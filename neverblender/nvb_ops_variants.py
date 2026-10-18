"""Make a robe's, cloak's or armour part's variants with cleanmodels.

The model is exported to a temporary folder and handed to
`cleanmodels variants`, which fits it to every other race and phenotype of
its gender (or the bodies picked in the list). With "Show on Bodies", each
variant is imported on its body into a Variants collection, one row per race
and one column per phenotype, so the fit can be checked before the files are
used.
"""

import os
import queue
import shutil
import tempfile
import threading
import json

import bpy

from . import nvb_cleanmodels
from . import nvb_utils

PREVIEW_SPACING_X = 1.6  # between phenotypes
PREVIEW_SPACING_Y = 2.5  # between races


PREVIEW_KEY = "nvb_variant_of"  # on preview objects: the name of the model they preview


def get_model(context):
    """The aurora base of the active object (the model to make variants of).

    For a preview, the model it is a preview of.
    """
    obj = context.object
    source = obj.get(PREVIEW_KEY) if obj else None
    if source:
        return bpy.data.objects.get(source)
    return nvb_utils.get_mdl_base(obj, context.collection, context.scene)


def get_cleanmodels(context):
    """Return (path, error): a cleanmodels new enough for variants."""
    addon_prefs = context.preferences.addons[__package__].preferences
    path, version = nvb_cleanmodels.find_from_prefs(addon_prefs)
    if not path:
        return None, "cleanmodels not found (add-on preferences)"
    if version < nvb_cleanmodels.VARIANTS_VERSION:
        return None, "Variants need cleanmodels {}.{}.{} or later (found {}.{}.{})".format(
            *nvb_cleanmodels.VARIANTS_VERSION, *version)
    return path, ""


def has_dry_run(cm_path):
    """Whether this cleanmodels has variants --dry-run, learnedFrom and adjusts."""
    version = nvb_cleanmodels.version_of(cm_path)
    return bool(version) and version >= nvb_cleanmodels.DRY_RUN_VERSION


def active_adjusts(settings):
    """The fit settings that change at least one chosen variant, or None if unknown."""
    chosen = [b for b in settings.bodies if b.use and b.learned_from >= 0]
    if not chosen:
        return None
    return {a for b in chosen for a in b.adjusts.split(",") if a}


def resource_args(context):
    """(game_dir, resource_dir) for cleanmodels."""
    addon_prefs = context.preferences.addons[__package__].preferences
    settings = context.scene.nvb_cm_variants
    return (bpy.path.abspath(addon_prefs.cleanmodels_game_dir),
            bpy.path.abspath(settings.resource_dir))


def export_model(context, mdl_base, folder):
    """Export mdl_base (with its MTRs) to folder and return the file path."""
    filepath = os.path.join(folder, mdl_base.name + ".mdl")
    # The exporter exports the model of the active object
    with context.temp_override(active_object=mdl_base, object=mdl_base):
        bpy.ops.scene.nvb_mdlexport(filepath=filepath, batch_mode='OFF', export_walkmesh=False,
                                    cleanmodels_check=False, cleanmodels_compile=False)
    return filepath


def fill_body_list(settings, mdl_name, bodies, plan=None):
    """Fill the body list, keeping the choices made for the same model.

    plan: the dry run's variants (cleanmodels 4.8.0 or later), or None.
    """
    plan = {v.get("target"): v for v in plan or []}
    keep = {}
    if settings.bodies_model == mdl_name:
        keep = {b.name: b.use for b in settings.bodies}
    settings.bodies.clear()
    for body in bodies:
        if body.get("source"):
            continue
        item = settings.bodies.add()
        item.name = body["prefix"]
        item.race = body.get("raceName", "")
        item.phenotype = body.get("phenotype", 0)
        item.phenotype_name = body.get("phenotypeName", "")
        item.same_shape = body.get("sameShape", "")
        item.use = keep.get(item.name, True)
        variant = plan.get(item.name)
        if variant:
            item.learned_from = variant.get("learnedFrom", 0)
            item.exists = variant.get("action") in ("replace", "skip")
            item.adjusts = ",".join(variant.get("adjusts") or [])
    settings.bodies_model = mdl_name
    settings.bodies_index = 0


class NVB_OT_cm_variants_bodies(bpy.types.Operator):
    """List the bodies the active model can have variants for"""

    bl_idname = "nvb.cm_variants_bodies"
    bl_label = "Find Bodies"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_model(context) is not None

    def execute(self, context):
        cm_path, error = get_cleanmodels(context)
        if not cm_path:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        mdl_base = get_model(context)
        tmp_dir = tempfile.mkdtemp(prefix="nvb_variants_")
        settings = context.scene.nvb_cm_variants
        plan = None
        try:
            mdl_path = export_model(context, mdl_base, tmp_dir)
            bodies, error = nvb_cleanmodels.list_bodies(cm_path, mdl_path, *resource_args(context))
            if bodies is not None and has_dry_run(cm_path):
                # How each variant would be fitted, and which files exist
                out_dir = bpy.path.abspath(settings.output_dir)
                if not out_dir or out_dir.startswith("//"):
                    out_dir = os.path.join(tmp_dir, "out")  # nothing exists there
                plan, _ = nvb_cleanmodels.dry_run(cm_path, mdl_path, out_dir, settings.overwrite,
                                                  *resource_args(context))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if bodies is None:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        fill_body_list(settings, mdl_base.name, bodies, plan)
        msg = "{}: {} bodies".format(mdl_base.name, len(settings.bodies))
        existing = sum(1 for b in settings.bodies if b.exists)
        if existing:
            msg += ", {} already in the output folder".format(existing)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class NVB_OT_cm_variants_select(bpy.types.Operator):
    """Select or deselect every body in the list"""

    bl_idname = "nvb.cm_variants_select"
    bl_label = "Select Bodies"
    bl_options = {'UNDO'}

    action: bpy.props.EnumProperty(items=(('ALL', "All", "Select every body"),
                                          ('NONE', "None", "Deselect every body")))

    def execute(self, context):
        for body in context.scene.nvb_cm_variants.bodies:
            body.use = (self.action == 'ALL')
        return {'FINISHED'}


class NVB_OT_cm_variants(bpy.types.Operator):
    """Make the active model's versions for other races and phenotypes with cleanmodels"""

    bl_idname = "nvb.cm_variants"
    bl_label = "Make Variants"
    bl_options = {'UNDO'}

    _timer = None
    _process = None
    _thread = None
    _queue = None
    _tmp_dir = ""

    @classmethod
    def poll(cls, context):
        return get_model(context) is not None

    def start(self, context):
        """Export the model and start cleanmodels. Returns an error message or ""."""
        settings = context.scene.nvb_cm_variants
        cm_path, error = get_cleanmodels(context)
        if not cm_path:
            return error
        out_dir = bpy.path.abspath(settings.output_dir)
        if not out_dir or out_dir.startswith("//"):
            return "Save the .blend file or choose an output folder"
        self.mdl_base = get_model(context)
        bodies = []
        if settings.bodies and settings.bodies_model == self.mdl_base.name:
            bodies = [b.name for b in settings.bodies if b.use]
            if not bodies:
                return "No bodies selected"
            if len(bodies) == len(settings.bodies):
                bodies = []  # all of them: let cleanmodels pick, as without a list
        os.makedirs(out_dir, exist_ok=True)
        self._tmp_dir = tempfile.mkdtemp(prefix="nvb_variants_")
        mdl_path = export_model(context, self.mdl_base, self._tmp_dir)
        preview_dir = os.path.join(self._tmp_dir, "preview") if settings.previews else ""
        game_dir, resource_dir = resource_args(context)
        try:
            self._process = nvb_cleanmodels.start_variants(
                cm_path, mdl_path, out_dir, bodies, settings.width, settings.length,
                settings.shape_arg(), settings.compile_binary, settings.overwrite,
                preview_dir, game_dir, resource_dir)
        except OSError as e:
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
            return str(e)
        self.out_dir = out_dir
        self.events = []
        self.stderr = []
        self.total = 0
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self.read_output, daemon=True)
        self._thread.start()
        context.window_manager.progress_begin(0, 100)
        return ""

    def invoke(self, context, event):
        error = self.start(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        """Scripts: run to the end without a modal loop."""
        error = self.start(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        self._thread.join()
        self._process.wait()
        return self.finish(context)

    def read_output(self):
        """Thread: move cleanmodels' output lines to the queue."""
        for line in self._process.stdout:
            self._queue.put(("out", line))
        for line in self._process.stderr:
            self._queue.put(("err", line))

    def drain(self):
        while True:
            try:
                kind, line = self._queue.get_nowait()
            except queue.Empty:
                return
            if kind == "err":
                if line.strip():
                    self.stderr.append(line.strip())
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            self.events.append(ev)
            self.total = ev.get("total", self.total)

    def modal(self, context, event):
        if event.type == 'ESC':
            self._process.terminate()
            self.cleanup(context)
            self.report({'WARNING'}, "Variants cancelled")
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        self.drain()
        done = sum(1 for ev in self.events if ev.get("type") == "done")
        if self.total:
            context.window_manager.progress_update(int(100 * done / self.total))
        context.workspace.status_text_set(
            "cleanmodels variants: {} of {} (Esc to cancel)".format(done, self.total or "?"))
        if self._thread.is_alive() or self._process.poll() is None:
            return {'RUNNING_MODAL'}
        return self.finish(context)

    def finish(self, context):
        self.drain()
        returncode = self._process.wait()
        try:
            errors = [ev.get("message", "") for ev in self.events if ev.get("type") == "error"]
            errors += [(ev.get("result") or {}).get("error") for ev in self.events
                       if ev.get("type") == "done" and (ev.get("result") or {}).get("error")]
            errors = [e.replace("add --overwrite", "tick Overwrite") for e in errors]
            written = sum(1 for ev in self.events if ev.get("type") == "done" and ev.get("output"))
            summary = next((ev.get("message", "") for ev in self.events if ev.get("type") == "summary"), "")
            if not written and (returncode != 0 or errors):
                msg = errors[0] if errors else self.stderr[-1] if self.stderr else \
                    "cleanmodels failed ({})".format(returncode)
                msg = "{}{}".format(summary + ": " if summary else "", msg.replace("cleanmodels: ", "", 1))
                context.scene.nvb_cm_variants.last_result = msg
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}
            if context.scene.nvb_cm_variants.previews:
                self.import_previews(context)
            done = [ev for ev in self.events if ev.get("type") == "done" and ev.get("output")]
            if any("adjusts" in ev for ev in done):  # cleanmodels 4.8.0 or later
                learned = sum(1 for ev in done if ev.get("learnedFrom"))
                measured = len(done) - learned
                how = ["{} learned from existing pairs".format(learned)] if learned else []
                how += ["{} measured".format(measured)] if measured and learned else []
                if how:
                    summary += " ({})".format(", ".join(how))
            if errors:
                msg, level = "{}; {}".format(summary, errors[0]), 'WARNING'
            else:
                msg, level = "{} in {}".format(summary, self.out_dir), 'INFO'
            context.scene.nvb_cm_variants.last_result = msg
            self.report({level}, msg)
            return {'FINISHED'}
        finally:
            self.cleanup(context)

    def cleanup(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        wm.progress_end()
        if getattr(context, "workspace", None):
            context.workspace.status_text_set(None)
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def import_previews(self, context):
        """Import each variant on its body: one row per race, one column per phenotype."""
        pairs = []  # (body prefix, fit path, body path)
        for ev in self.events:
            if ev.get("type") in ("source", "done") and ev.get("preview") and ev.get("body"):
                pairs.append((ev.get("target", ""), ev["preview"], ev["body"]))
        if not pairs:
            return
        coll_name = "Variants: " + self.mdl_base.name
        coll = bpy.data.collections.get(coll_name)
        if coll:
            for obj in list(coll.all_objects):
                bpy.data.objects.remove(obj)
            for child in list(coll.children_recursive):
                bpy.data.collections.remove(child)
        else:
            coll = bpy.data.collections.new(coll_name)
            context.scene.collection.children.link(coll)
        coll[PREVIEW_KEY] = self.mdl_base.name
        mat_body = preview_material("NVB Variant Body", (0.55, 0.55, 0.6, 1.0))
        mat_fit = preview_material("NVB Variant Fit", (0.75, 0.25, 0.2, 1.0))
        # Rows by race (pXr#), columns by phenotype (pXX#)
        races = sorted({p[2] for p, _, _ in pairs})
        phenotypes = sorted({p[3] for p, _, _ in pairs})
        old_materials = set(bpy.data.materials)
        old_images = set(bpy.data.images)
        for prefix, fit_path, body_path in pairs:
            location = (phenotypes.index(prefix[3]) * PREVIEW_SPACING_X,
                        -races.index(prefix[2]) * PREVIEW_SPACING_Y, 0.0)
            for path, mat in ((body_path, mat_body), (fit_path, mat_fit)):
                before = set(bpy.data.objects)
                with context.temp_override(collection=coll):
                    bpy.ops.scene.nvb_mdlimport(filepath=path, collections_use=False)
                for obj in set(bpy.data.objects) - before:
                    obj[PREVIEW_KEY] = self.mdl_base.name
                    if obj.parent is None:
                        obj.location = location
                    if obj.type == 'MESH':
                        obj.data.materials.clear()
                        obj.data.materials.append(mat)
            label = bpy.data.curves.new(prefix, 'FONT')
            label.body = prefix
            label.size = 0.25
            text = bpy.data.objects.new(prefix + " label", label)
            text[PREVIEW_KEY] = self.mdl_base.name
            text.location = (location[0] - 0.3, location[1] - 0.6, 0.0)
            coll.objects.link(text)
        # Importing made a preview active; the model stays the one to work on
        for obj in context.view_layer.objects:
            obj.select_set(False)
        if self.mdl_base.name in context.view_layer.objects:
            context.view_layer.objects.active = self.mdl_base
            self.mdl_base.select_set(True)
        # The previews' own materials and textures were replaced; drop them
        for mat in set(bpy.data.materials) - old_materials:
            if mat.users == 0:
                bpy.data.materials.remove(mat)
        for img in set(bpy.data.images) - old_images:
            if img.users == 0:
                bpy.data.images.remove(img)


def preview_material(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat
