"""Contains Blender Operators for MDL Import/Export."""

import os
import math
import re

import bpy
import bpy_extras
import mathutils

from . import nvb_mdl
from . import nvb_mtr
from . import nvb_def
from . import nvb_utils


class NVB_OT_mdlexport(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """Export Aurora Engine model (.mdl)"""

    bl_idname = 'scene.nvb_mdlexport'
    bl_label = 'Export Aurora MDL'
    bl_options = {'PRESET'}

    filename_ext = '.mdl'
    filter_glob: bpy.props.StringProperty(
            default='*.mdl',
            options={'HIDDEN'})
    # Misc Export Settings
    export_animations: bpy.props.BoolProperty(
            name='Export Animations',
            description='Export animations',
            default=True)
    export_walkmesh: bpy.props.BoolProperty(
            name='Export Walkmesh',
            description='Export a walkmesh',
            default=True)
    export_smoothgroups: bpy.props.BoolProperty(
            name='Export Smooth Groups',
            description='Generate smooth groups from sharp edges'
                        '(When disabled every face belongs to the same group)',
            default=True)
    export_normals: bpy.props.BoolProperty(
            name='Export Normals',
            description='Add normals to MDL',
            default=False)
    export_tangents: bpy.props.BoolProperty(
            name='Export Tangents',
            description='Add tangents to MDL',
            default=False)
    export_smoothing_mode: bpy.props.EnumProperty(
            name='Smoothing',
            description='Smoothing method',
            items=(('GROUP', 'Groups',
                    'Generate smoothing groups from sharp edges and auto smooth setting'),
                   ('SPLIT', 'Split',
                    'Split meshes along sharp edges and auto smooth setting'),
                   ('NONE', 'None',
                    'No smoothing')),
            default='GROUP')
    # UV Map Export settings
    uv_merge: bpy.props.BoolProperty(
            name='Merge UVs',
            description='Join uv-vertices with identical coordinates',
            default=True)
    uv_mode: bpy.props.EnumProperty(
            name='Mode',
            description='Determines which meshes get uv maps',
            items=(('TEX', 'Textured Meshes',
                    'Add UV Maps only to textured and rendered meshes'),
                   ('REN', 'Rendered Meshes',
                    'Add UV Maps only to rendered meshes'),
                   ('ALL', 'All',
                    'Add UV Maps to all meshes')),
            default='REN')
    uv_order: bpy.props.EnumProperty(
            name='Order',
            description='Determines ordering of uv maps in MDL',
            items=(('AL0', 'Alphabetical',
                    'Alphabetical ordering'),
                   ('AL1', 'Alphabetical (Active First)',
                    'Alphabetical ordering, active UVMap will be first'),
                   ('ACT', 'Active Only',
                    'Export only the active UVMap')),
            default='ACT')
    # Blender Setting to use
    apply_modifiers: bpy.props.BoolProperty(
            name='Apply Modifiers',
            description='Apply Modifiers before exporting',
            default=True)
    strip_trailing: bpy.props.BoolProperty(
            name='Strip Trailing Numbers',
            description='Strips trailing numbers from object names',
            default=False)
    frame_set_zero: bpy.props.BoolProperty(
            name='Export at Frame 0',
            description='Set frame to 0 for export',
            default=False)
    batch_mode: bpy.props.EnumProperty(
            name='Batch Mode',
            description='Export multiple MDLs',
            items=(('OFF', 'Off', 'Export active MDL only'),
                   ('SEL', 'Selected', 'Export selected MDLs'),
                   ('SCN', 'Scene', 'Export all MDLs in active scene')),
            default='OFF')

    def mdl_export(self, context, options):
        """TODO: DOC."""
        def get_filepath(old_path, new_name, new_ext):
            """Creates filenames for walkmeshes and batch export."""
            old_dir = os.path.dirname(old_path)
            new_name = new_name + new_ext
            return os.path.join(old_dir, new_name)

        def get_walkmeshtype(mdl_base):
            """Creates filenames for walkmeshes and batch export."""
            if mdl_base.nvb.classification == nvb_def.Classification.DOOR:
                return nvb_def.Walkmeshtype.DWK
            elif mdl_base.nvb.classification == nvb_def.Classification.TILE:
                return nvb_def.Walkmeshtype.WOK
            else:
                return nvb_def.Walkmeshtype.PWK

        # (Re)set to object-mode, if an object is selected
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')
        # Set frame to zero, if specified in options
        if self.frame_set_zero:
            options.scene.frame_current = 0
            bpy.context.evaluated_depsgraph_get().update()
        # Gather MDLs to export
        mdl_list = []
        if options.batch_mode == 'OFF':  # Get active object only
            base = nvb_utils.get_mdl_base(context.object,
                                          options.scene.collection,
                                          options.scene)
            wkm_name = os.path.splitext(os.path.basename(options.filepath))[0]
            if base:
                mdl_list.append((base, options.filepath, wkm_name))
        else:  # Get multiple objects
            obj_list = []
            if options.batch_mode == 'SCN':
                # Get all object in scene (master collection)
                obj_list = bpy.context.scene.collection.all_objects
            elif options.batch_mode == 'SEL':
                # Get all selected objects
                obj_list = bpy.context.selected_objects
            for obj in obj_list:
                base = nvb_utils.get_obj_mdl_base(obj)
                if base and (base not in mdl_list):
                    # Build a custom filename
                    mdl_path = get_filepath(options.filepath,
                                            base.name, '.mdl')
                    mdl_list.append((base, mdl_path, base.name))
        # Export MDLs
        for mdl_base, mdl_path, wkm_name in mdl_list:
            options.mdlname = mdl_base.name
            options.filepath = mdl_path
            options.classification = mdl_base.nvb.classification
            # Export MDL
            ascii_lines = []
            nvb_mdl.Mdl.generate_ascii(mdl_base, ascii_lines, options)
            with open(os.fsencode(options.filepath), 'w', newline='\r\n') as f:
                f.write('\n'.join(ascii_lines))
            # Export walkmesh for MDL
            if options.geom_walkmesh:
                wkm_type = get_walkmeshtype(mdl_base)
                wkm_ext = '.' + wkm_type
                ascii_lines = []
                nvb_mdl.Mdl.generate_ascii_wkm(mdl_base, ascii_lines,
                                               wkm_type, options)
                if ascii_lines:
                    wkm_path = get_filepath(mdl_path, wkm_name, wkm_ext)
                    with open(os.fsencode(wkm_path), 'w', newline='\r\n') as f:
                        f.write('\n'.join(ascii_lines))
        # Export MTRs
        for mtr_name, blen_mat_name in options.mtr_list:
            blen_mat = bpy.data.materials[blen_mat_name]
            ascii_lines = nvb_mtr.Mtr.generate_ascii(blen_mat, options)
            mtr_path = get_filepath(options.filepath, mtr_name, '.mtr')
            with open(os.fsencode(mtr_path), 'w', newline='\r\n') as f:
                f.write('\n'.join(ascii_lines))
        return {'FINISHED'}

    def draw(self, context):
        """Draw the export UI."""
        layout = self.layout
        # Misc Export Settings
        box = layout.box()
        box.prop(self, 'export_animations')
        box.prop(self, 'export_walkmesh')
        #box.prop(self, 'export_smoothgroups')
        box.prop(self, 'export_normals')
        sub = box.column()  # only enable if normals are enabled
        sub.enabled = self.export_normals
        sub.prop(self, 'export_tangents')
        box.prop(self, 'export_smoothing_mode')
        # UV Map settings
        box = layout.box()
        box.label(text='UV Map Settings')
        sub = box.column()
        sub.prop(self, 'uv_merge')
        sub.prop(self, 'uv_mode')
        sub.prop(self, 'uv_order')
        # Blender Settings
        box = layout.box()
        box.label(text='Blender Settings')
        sub = box.column()
        sub.prop(self, 'apply_modifiers')
        sub.prop(self, 'strip_trailing')
        sub.prop(self, 'frame_set_zero')
        sub.prop(self, 'batch_mode')

    def execute(self, context):
        """TODO: DOC."""
        addon = context.preferences.addons[__package__]
        addon_prefs = addon.preferences

        options = nvb_def.ExportOptions()
        # Hidden seeting for internal use
        options.filepath = self.filepath
        options.scene = context.scene
        options.depsgraph = context.evaluated_depsgraph_get()
        # Material settings
        options.mat_mtr_generate = addon_prefs.export_mat_mtr_generate
        options.mat_mtr_ref = addon_prefs.export_mat_mtr_ref
        options.mat_diffuse_ref = addon_prefs.export_mat_diffuse_ref
        # Geometry options
        options.geom_import = True
        options.geom_normals = self.export_normals
        options.geom_tangents = self.export_tangents and self.export_normals
        options.geom_smoothing_split = (self.export_smoothing_mode == 'SPLIT')
        options.geom_smoothing_group = (self.export_smoothing_mode == 'GROUP')
        options.geom_smoothing_group_binary = addon_prefs.export_smoothgroups_binary
        options.geom_smoothing_group_distinct = addon_prefs.export_smoothgroups_distinct_verts
        options.geom_walkmesh = self.export_walkmesh
        # Misc Export Settings
        options.anim_export = self.export_animations
        options.export_metadata = addon_prefs.export_metadata
        options.export_wirecolor = addon_prefs.export_wirecolor
        # UV Map settings
        options.uv_merge = self.uv_merge
        options.uv_level = self.uv_mode
        options.uv_order = self.uv_order
        # Blender Settings
        options.apply_modifiers = self.apply_modifiers
        options.strip_trailing = self.strip_trailing
        options.batch_mode = self.batch_mode
        return self.mdl_export(context, options)

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(self)
        # Generate a file name from active object
        scene = context.scene
        mdl_base = nvb_utils.get_mdl_base(context.object,
                                          scene.collection,
                                          scene)
        if mdl_base:
            generated_name = nvb_utils.generate_node_name(mdl_base, True)
            self.filepath = generated_name + '.mdl'
        else:
            self.filepath = 'untitled.mdl'
        return {'RUNNING_MODAL'}


class NVB_OT_mdlimport(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    """Import Aurora Engine model (.mdl)"""

    bl_idname = 'scene.nvb_mdlimport'
    bl_label = 'Import Aurora MDL'
    bl_options = {'UNDO', 'PRESET'}

    files: bpy.props.CollectionProperty(
        name='File Path',
        description='Path used for importing the file',
        type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty()
    filter_glob: bpy.props.StringProperty(default='*.mdl;*.mdl.txt', options={'HIDDEN'})
    filename_ext = '.mdl'

    import_walkmesh: bpy.props.BoolProperty(
        name='Import Walkmesh',
        description='Load placeable and door walkmeshes',
        default=True)
    import_smoothgroups: bpy.props.BoolProperty(
        name='Import Smooth Groups',
        description='Import smooth groups as sharp edges',
        default=True)
    import_normals: bpy.props.BoolProperty(
        name='Import Normals',
        description='Import normals from MDL',
        default=True)
    # Materials Options
    mat_import: bpy.props.BoolProperty(
        name='Import Materials',
        description='Import materials and textures',
        default=True)
    mat_merge: bpy.props.BoolProperty(
        name='Merge Materials',
        description='Merge materials with the same values',
        default=True)
    mat_shader: bpy.props.EnumProperty(
        name='Shader',
        description='',
        items=(('ShaderNodeEeveeSpecular', 'Eevee Specular', ''),
               ('ShaderNodeBsdfPrincipled', 'Principled BSDF', '')),
        default='ShaderNodeBsdfPrincipled')
    tex_search: bpy.props.BoolProperty(
        name='Image Search',
        description='Search for images in subdirectories \n (Warning: May be slow)',
        default=False)
    # Animation Options
    anim_import: bpy.props.BoolProperty(name='Import Animations',
                                        description='Import animation data',
                                        default=True)
    anim_fps_use: bpy.props.BoolProperty(name='Use Custom fps',
                                         description='Use custom fps value',
                                         default=True)
    anim_fps: bpy.props.IntProperty(name='Scene Framerate',
                                    description='Custom fps value',
                                    default=30,
                                    min=1, max=60)
    anim_restpose: bpy.props.BoolProperty(
        name='Insert Rest Pose',
        description='Insert rest keyframe before every animation',
        default=True)
    # Blender Settings
    rotmode: bpy.props.EnumProperty(
        name='Rotation Mode',
        description='',
        items=(('AXIS_ANGLE', 'Axis Angle', ''),
               ('QUATERNION', 'Quaternion', ''),
               ('XYZ', 'Euler XYZ', '')),
        default='XYZ')
    collections_use: bpy.props.BoolProperty(
        name='Use Collections',
        description='Create a collection for each imported mdl',
        default=False)
    fix_uvs: bpy.props.BoolProperty(
        name='Fix degenerated UVs',
        description='Fix degenerated UV coordinates (tverts)',
        default=False)
    # Hidden options for automated scripts and mass import
    mdl_location: bpy.props.FloatVectorProperty(
        name='Location',
        description='Location of newly imported model',
        subtype='TRANSLATION',
        default=(0.0, 0.0, 0.0), size=3, options={'HIDDEN'})
    import_geometry: bpy.props.BoolProperty(
        name='Import Geometry',
        description='If disabled this will add animations to existing meshes',
        default=True, options={'HIDDEN'})
    hide_lights: bpy.props.BoolProperty(
        name='Hide Lights',
        description='Do not render Lights',
        default=True, options={'HIDDEN'})
    hide_fading: bpy.props.BoolProperty(
        name='Hide Fading Objects',
        description='Do not render Fading Objects',
        default=True, options={'HIDDEN'})
    ignore_selfillum: bpy.props.BoolProperty(
        name='Ignore Self-Illumination',
        description='Ignore self-illumination color and texture (texture5) from MTR files',
        default=False)

    def mdl_import(self, context, options):
        def load_file(context, mdl_filepath, options):
            mdl_filedir, mdl_filename = os.path.split(mdl_filepath)
            mdl_name = os.path.splitext(mdl_filename)[0]

            options.mdlname = mdl_name
            options.filepath = mdl_filepath

            # Create a new collection parented to the master collection
            if options.collections_use:
                parent_collection = options.scene.collection
                new_collection = bpy.data.collections.new(name=mdl_name)
                parent_collection.children.link(new_collection)
                options.collection = new_collection

            mdl = nvb_mdl.Mdl()
            mdl.parse_mdl(mdl_filepath, options)

            if options.geom_walkmesh:
                # Try loading the placeable walkmesh (pwk)
                pwk_filename = mdl_name + '.' + nvb_def.Walkmeshtype.PWK
                pwk_filepath = os.path.join(mdl_filedir, pwk_filename)
                if os.path.isfile(os.fsencode(pwk_filepath)):
                    mdl.parse_wkm(pwk_filepath,
                                  nvb_def.Walkmeshtype.PWK, options)
                # Try loading the door walkmesh (dwk)
                dwk_filename = mdl_name + '.' + nvb_def.Walkmeshtype.DWK
                dwk_filepath = os.path.join(mdl_filedir, dwk_filename)
                if os.path.isfile(os.fsencode(dwk_filepath)):
                    mdl.parse_wkm(dwk_filepath,
                                  nvb_def.Walkmeshtype.DWK, options)
            mdl.create(options)

        def generate_import_loc(i, placement='SPIRAL', spacing=10.0):
            """Generate a location for the imported model"""
            if placement == 'LINE':
                return (spacing * i, 0.0, 0.0)
            else:  # 'SPIRAL' is default
                k = math.floor(math.floor(math.sqrt(i)-1)/2)+1
                return (spacing * min(k, max(-k, -2*k + abs(i-(4*k*k)-k))),
                        spacing * min(k, max(-k, -2*k + abs(i-(4*k*k)+k))), 0.0)

        # Build list of files
        path_list = [os.path.join(self.directory, f.name) for f in self.files]
        if path_list:
            # Potentially multiple files => Always generate+overwrite locations
            loc_list = [generate_import_loc(i, options.placement) for i in range(len(path_list))]
            for loc, path in zip(loc_list, path_list):
                options.mdl_location = loc
                load_file(context, path, options)
        else:
            # Single file => NEVER overwrite locations
            if self.filepath:
                load_file(context, self.filepath, options)

        return {'FINISHED'}

    def draw(self, context):
        """Draw the export UI."""
        layout = self.layout
        # Misc Import Settings
        box = layout.box()
        box.prop(self, 'import_walkmesh')
        box.prop(self, 'import_smoothgroups')
        box.prop(self, 'import_normals')

        # Material Import Settings
        box = layout.box()
        box.prop(self, 'mat_import')
        sub = box.column()
        sub.enabled = self.mat_import
        sub.prop(self, 'mat_shader', text='')
        sub.prop(self, 'mat_merge')
        sub.prop(self, 'tex_search')
        sub.prop(self, 'ignore_selfillum')

        # Animation Import Settings
        box = layout.box()
        box.prop(self, 'anim_import')
        sub1 = box.column()
        sub1.enabled = self.anim_import
        sub1.prop(self, 'anim_restpose')
        row = sub1.row(align=True)
        row.prop(self, 'anim_fps_use', text='')
        sub2 = row.row(align=True)
        sub2.enabled = self.anim_fps_use
        sub2.prop(self, 'anim_fps')

        # Blender Settings
        box = layout.box()
        box.label(text='Blender Settings')
        box.prop(self, 'rotmode')
        box.prop(self, 'collections_use')
        box.prop(self, 'fix_uvs')

    def execute(self, context):
        """TODO: DOC."""
        addon = context.preferences.addons[__package__]
        addon_prefs = addon.preferences
        options = nvb_def.ImportOptions()
        # Hidden settings for internal use
        options.filepath = self.filepath
        options.scene = context.scene
        options.collection = context.collection
        options.dummy_type = addon_prefs.dummy_type
        options.dummy_size = addon_prefs.dummy_size
        options.placement = addon_prefs.import_placement
        options.hide_lights = self.hide_lights
        options.hide_fading = self.hide_fading
        options.mdl_location = self.mdl_location
        # handling of binary mdls
        options.compiler_use = addon_prefs.import_compiler_use
        options.compiler_path = addon_prefs.import_compiler_path
        options.compiler_command = addon_prefs.import_compiler_command
        # Geometry options
        options.geom_import = self.import_geometry
        options.geom_walkmesh = self.import_walkmesh
        options.geom_normals = self.import_normals
        options.geom_smoothgroups = self.import_smoothgroups
        options.geom_mesh_validation = addon_prefs.import_mesh_validation
        # Material Options
        options.mat_import = self.mat_import
        options.mat_mtr_lowercase = addon_prefs.import_mat_lowercase
        options.mat_automerge = self.mat_merge
        options.mat_shader = self.mat_shader
        options.mat_use_mtr = addon_prefs.import_mat_mtr
        options.mat_displacement_mode = addon_prefs.mat_displacement_mode
        options.mat_ignore_mdl_diffuse_color = addon_prefs.import_ignore_mdl_diffuse_color
        options.mat_ignore_mdl_specular_color = addon_prefs.import_ignore_mdl_specular_color
        options.mat_ignore_mdl_ambient_color = addon_prefs.import_ignore_mdl_ambient_color
        options.mat_ignore_selfillum_color = self.ignore_selfillum
        options.mat_ignore_selfillum_texture = self.ignore_selfillum
        options.tex_search = self.tex_search
        # Animation Options
        options.anim_import = self.anim_import
        options.anim_restpose = self.anim_restpose
        options.anim_fps_use = self.anim_fps_use
        options.anim_fps = self.anim_fps
        # Blender Settings
        options.rotmode = self.rotmode
        options.fix_uvs = self.fix_uvs
        options.collections_use = self.collections_use

        return self.mdl_import(context, options)


class NVB_OT_mdl_superimport(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    """Import animations from supermodel onto existing mdl"""
    bl_idname = 'scene.nvb_superimport'
    bl_label = 'Import Supermodel'

    files: bpy.props.CollectionProperty(
        name='File Path',
        description='Path used for importing the file',
        type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty()
    filter_glob: bpy.props.StringProperty(default='*.mdl;*.mdl.txt', options={'HIDDEN'})
    filename_ext = '.mdl'

    anim_fps_use: bpy.props.BoolProperty(name='Use Custom fps',
                                         description='Use custom fps value',
                                         default=False)
    anim_fps: bpy.props.IntProperty(name='Scene Framerate',
                                    description='Custom fps value',
                                    default=30,
                                    min=1, max=60)
    anim_restpose: bpy.props.BoolProperty(
        name='Insert Rest Pose',
        description='Insert rest keyframe before every animation',
        default=True)
    anim_ignore_existing: bpy.props.BoolProperty(
        name='Ignore Existing',
        description='Do not import already existing animations',
        default=True)

    def mdl_import(self, context, options):
        def load_file(mdl_filepath, mdl_base, options):
            _, mdl_filename = os.path.split(mdl_filepath)
            mdl_name = os.path.splitext(mdl_filename)[0]

            options.mdlname = mdl_name
            options.filepath = mdl_filepath
            mdl = nvb_mdl.Mdl()
            mdl.parse_mdl(mdl_filepath, options)
            mdl.create_super(mdl_base, options)

        # Build list of files
        pathlist = [os.path.join(self.directory, f.name) for f in self.files]
        # Import models
        mdl_base = nvb_utils.get_obj_mdl_base(context.object)
        if round(mdl_base.nvb.animscale, 3) != 1.0:
            options.anim_scale = mdl_base.nvb.animscale
        for filepath in pathlist:
            load_file(filepath, mdl_base, options)
        return {'FINISHED'}

    @classmethod
    def poll(self, context):
        """Check presence of aurora base."""
        return nvb_utils.get_obj_mdl_base(context.object) is not None

    def draw(self, context):
        """Draw the export UI."""
        layout = self.layout

        # Animation Import Settings
        box = layout.box()
        box.prop(self, 'anim_ignore_existing')
        box.prop(self, 'anim_restpose')
        row = box.row(align=True)
        row.prop(self, 'anim_fps_use', text='')
        sub = row.row(align=True)
        sub.enabled = self.anim_fps_use
        sub.prop(self, 'anim_fps')

    def execute(self, context):
        addon = context.preferences.addons[__package__]
        addon_prefs = addon.preferences
        options = nvb_def.ImportOptions()
        # Hidden settings for internal use
        options.scene = context.scene
        options.collection = context.collection
        options.dummy_type = addon_prefs.dummy_type
        options.dummy_size = addon_prefs.dummy_size
        # handling of binary mdls
        options.compiler_use = addon_prefs.import_compiler_use
        options.compiler_path = addon_prefs.import_compiler_path
        options.compiler_command = addon_prefs.import_compiler_command
        # Animations (duh)
        options.anim_import = True
        options.anim_fps_use = self.anim_fps_use
        options.anim_fps = self.anim_fps
        options.anim_restpose = self.anim_restpose
        options.anim_ignore_existing = self.anim_ignore_existing
        return self.mdl_import(context, options)

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(self)

        return {'RUNNING_MODAL'}


class NVB_OT_phenotype_batch_export(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """Export model scaled for all selected phenotypes (Elf, Halfling, Dwarf, Gnome, Half-Orc)"""

    bl_idname = 'scene.nvb_phenotype_batch_export'
    bl_label = 'Export Phenotypes'
    bl_options = {'PRESET'}

    filename_ext = '.mdl'
    filter_glob: bpy.props.StringProperty(
            default='*.mdl',
            options={'HIDDEN'})

    # Gender conversion scale factors (female human to male human)
    FEMALE_TO_MALE_SCALE = (1.3, 1.5, 1.26)
    # Inverse for male to female
    MALE_TO_FEMALE_SCALE = (1.0/1.3, 1.0/1.5, 1.0/1.26)

    # Female Phenotype scale factors: (prefix, x_scale, y_scale, z_scale, description)
    FEMALE_PHENOTYPES = [
        ('pfh0', 1.00, 1.00, 1.00, 'Female Human'),
        ('pfe0', 0.82, 0.81, 0.90, 'Female Elf'),
        ('pfa0', 0.65, 0.70, 0.70, 'Female Halfling'),
        ('pfd0', 1.25, 1.20, 0.99, 'Female Dwarf'),
        ('pfg0', 0.83, 0.84, 0.84, 'Female Gnome'),
        ('pfo0', 1.65, 1.48, 1.39, 'Female Half-Orc'),
    ]

    # Male Phenotype scale factors: (prefix, x_scale, y_scale, z_scale, description)
    MALE_PHENOTYPES = [
        ('pmh0', 1.00, 1.00, 1.00, 'Male Human'),
        ('pme0', 0.80, 0.80, 0.89, 'Male Elf'),
        ('pma0', 0.60, 0.70, 0.70, 'Male Halfling'),
        ('pmd0', 1.08, 1.05, 0.89, 'Male Dwarf'),
        ('pmg0', 0.85, 0.85, 0.81, 'Male Gnome'),
        ('pmo0', 1.50, 1.50, 1.30, 'Male Half-Orc'),
    ]

    # Export options (copied from main export)
    export_animations: bpy.props.BoolProperty(
            name='Export Animations',
            description='Export animations',
            default=True)
    export_walkmesh: bpy.props.BoolProperty(
            name='Export Walkmesh',
            description='Export placeable and door walkmeshes',
            default=True)
    export_normals: bpy.props.BoolProperty(
            name='Export Normals',
            description='Export normals to MDL',
            default=False)
    export_tangents: bpy.props.BoolProperty(
            name='Export Tangents',
            description='Export tangent and bitangent vectors to MDL',
            default=False)
    export_smoothing_mode: bpy.props.EnumProperty(
            name='Smoothing',
            description='Smoothing mode',
            items=(('NONE', 'None', 'No smoothing', 0),
                   ('SPLIT', 'Split', 'Split sharp edges', 1),
                   ('GROUP', 'Groups', 'Smoothgroups', 2)),
            default='SPLIT')
    apply_modifiers: bpy.props.BoolProperty(
            name='Apply Modifiers',
            description='Apply Modifiers before exporting',
            default=True)
    frame_set_zero: bpy.props.BoolProperty(
            name='Set Frame to 0',
            description='Set frame to zero before exporting',
            default=True)
    strip_trailing: bpy.props.BoolProperty(
            name='Strip Trailing Numbers',
            description='Strip trailing numbers from object names',
            default=True)
    uv_merge: bpy.props.BoolProperty(
            name='Merge verts by UV',
            description='Prevent UV seams from splitting vertices',
            default=False)
    uv_mode: bpy.props.EnumProperty(
            name='UV Mode',
            description='Determines which UV layers to export',
            items=(('NONE', 'None', '', 0),
                   ('ACT', 'Active', 'Export active UV layer', 1),
                   ('REN', 'Render', 'Export render UV layer', 2),
                   ('ALL', 'All', 'Export all UV layers', 3)),
            default='ALL')
    uv_order: bpy.props.EnumProperty(
            name='UV Order',
            description='Determines how UV layers are indexed',
            items=(('AL0', 'Alphabetical', '', 0),
                   ('CRT', 'Creation order', '', 1)),
            default='AL0')

    # Gender selection
    export_female: bpy.props.BoolProperty(
            name='Female',
            description='Export female phenotypes',
            default=True)
    export_male: bpy.props.BoolProperty(
            name='Male',
            description='Export male phenotypes',
            default=False)

    # Phenotype selection options
    export_human: bpy.props.BoolProperty(
            name='Human',
            description='Export scaled for Human',
            default=True)
    export_elf: bpy.props.BoolProperty(
            name='Elf',
            description='Export scaled for Elf',
            default=True)
    export_halfling: bpy.props.BoolProperty(
            name='Halfling',
            description='Export scaled for Halfling',
            default=True)
    export_dwarf: bpy.props.BoolProperty(
            name='Dwarf',
            description='Export scaled for Dwarf',
            default=True)
    export_gnome: bpy.props.BoolProperty(
            name='Gnome',
            description='Export scaled for Gnome',
            default=True)
    export_halforc: bpy.props.BoolProperty(
            name='Half-Orc',
            description='Export scaled for Half-Orc',
            default=True)
    export_original: bpy.props.BoolProperty(
            name='Original (Human)',
            description='Also export the original unscaled human model',
            default=True)
    
    # Cloak mode option
    is_cloak: bpy.props.BoolProperty(
            name='Cloak Mode',
            description='Export as cloak: sets supermodel to phenotype prefix and uses Transform Helper scaling method',
            default=False)

    def get_selected_phenotypes(self):
        """Return list of phenotypes to export based on checkbox selection.
        
        Returns tuples of (prefix, scale_x, scale_y, scale_z, description, is_male)
        where is_male indicates if this is a male phenotype.
        """
        selected = []
        
        # Add female phenotypes if selected
        if self.export_female:
            if self.export_human:
                selected.append((*self.FEMALE_PHENOTYPES[0], False))
            if self.export_elf:
                selected.append((*self.FEMALE_PHENOTYPES[1], False))
            if self.export_halfling:
                selected.append((*self.FEMALE_PHENOTYPES[2], False))
            if self.export_dwarf:
                selected.append((*self.FEMALE_PHENOTYPES[3], False))
            if self.export_gnome:
                selected.append((*self.FEMALE_PHENOTYPES[4], False))
            if self.export_halforc:
                selected.append((*self.FEMALE_PHENOTYPES[5], False))
        
        # Add male phenotypes if selected
        if self.export_male:
            if self.export_human:
                selected.append((*self.MALE_PHENOTYPES[0], True))
            if self.export_elf:
                selected.append((*self.MALE_PHENOTYPES[1], True))
            if self.export_halfling:
                selected.append((*self.MALE_PHENOTYPES[2], True))
            if self.export_dwarf:
                selected.append((*self.MALE_PHENOTYPES[3], True))
            if self.export_gnome:
                selected.append((*self.MALE_PHENOTYPES[4], True))
            if self.export_halforc:
                selected.append((*self.MALE_PHENOTYPES[5], True))
        
        return selected

    def is_base_model_male(self, mdl_base):
        """Detect if the base model is male (pmh0) or female (pfh0).
        
        Returns True if male, False if female.
        Checks the model name for pmh0/pfh0 prefix.
        """
        name = mdl_base.name.lower()
        if name.startswith('pmh0'):
            return True
        # Default to female if not clearly male
        return False

    def replace_phenotype_prefix(self, name, new_prefix):
        """Replace pfh0/pmh0 prefix with new phenotype prefix in a name."""
        # Match pfh0 or pmh0 at the start, possibly followed by underscore
        pattern = r'^p[fm]h0(_)?'
        if re.match(pattern, name, re.IGNORECASE):
            return re.sub(pattern, new_prefix + r'\1', name, flags=re.IGNORECASE)
        # If no pfh0/pmh0 prefix, just prepend
        return new_prefix + '_' + name

    def scale_object_hierarchy(self, obj, scale_x, scale_y, scale_z):
        """Scale an object and all its children recursively."""
        # Store original scale
        original_scale = obj.scale.copy()
        # Apply scale to this object
        obj.scale = (original_scale.x * scale_x,
                     original_scale.y * scale_y,
                     original_scale.z * scale_z)

    def apply_scale_to_hierarchy(self, obj, scale_x, scale_y, scale_z, parent_scale=None):
        """Apply scale to object hierarchy using Transform Helper approach.
        
        This modifies vertex data and animations directly, similar to the
        Transform Helper 'Apply Transform' functionality.
        """
        if parent_scale is None:
            parent_scale = mathutils.Vector((scale_x, scale_y, scale_z))
        
        for child in obj.children:
            # Get current transforms
            child_loc, child_rot, child_scale = child.matrix_basis.decompose()
            
            # Scale the location by parent scale
            new_loc = mathutils.Vector((
                child_loc.x * parent_scale.x,
                child_loc.y * parent_scale.y,
                child_loc.z * parent_scale.z
            ))
            
            # Update matrix_basis with scaled location, keep rotation
            child.matrix_basis = mathutils.Matrix.Translation(new_loc) @ \
                child_rot.to_matrix().to_4x4()
            
            # Apply scale to mesh data if it's a mesh
            if child.type == 'MESH':
                me = child.data
                for v in me.vertices:
                    v.co = mathutils.Vector((
                        v.co.x * parent_scale.x * child_scale.x,
                        v.co.y * parent_scale.y * child_scale.y,
                        v.co.z * parent_scale.z * child_scale.z
                    ))
                me.update()
            
            # Apply scale to animations
            self.apply_scale_to_animations(child, parent_scale)
            
            # Continue with children, combining scales
            combined_scale = mathutils.Vector((
                parent_scale.x * child_scale.x,
                parent_scale.y * child_scale.y,
                parent_scale.z * child_scale.z
            ))
            self.apply_scale_to_hierarchy(child, scale_x, scale_y, scale_z, combined_scale)

    def apply_scale_to_animations(self, obj, scale_vec):
        """Apply scale to animation keyframes."""
        if not (obj.animation_data and obj.animation_data.action):
            return
        
        action = obj.animation_data.action
        all_fcu = nvb_utils.get_action_fcurves(action, obj)
        if not all_fcu:
            return
        
        # Handle location keyframes
        loc_fcu = [all_fcu.find(data_path='location', index=i) for i in range(3)]
        if loc_fcu.count(None) < 1:
            frames = list(set().union(
                *[[k.co[0] for k in loc_fcu[i].keyframe_points] for i in range(3)]))
            frames.sort()
            
            for frame in frames:
                values = [loc_fcu[i].evaluate(frame) for i in range(3)]
                scaled_values = [
                    values[0] * scale_vec.x,
                    values[1] * scale_vec.y,
                    values[2] * scale_vec.z
                ]
                # Update keyframe values
                for i in range(3):
                    for kfp in loc_fcu[i].keyframe_points:
                        if abs(kfp.co[0] - frame) < 0.001:
                            kfp.co[1] = scaled_values[i]
                            break
            
            for fcu in loc_fcu:
                fcu.update()

    def get_walkmeshtype(self, mdl_base):
        """Get walkmesh type based on classification."""
        if mdl_base.nvb.classification == nvb_def.Classification.DOOR:
            return nvb_def.Walkmeshtype.DWK
        elif mdl_base.nvb.classification == nvb_def.Classification.TILE:
            return nvb_def.Walkmeshtype.WOK
        else:
            return nvb_def.Walkmeshtype.PWK

    def get_filepath(self, old_path, new_name, new_ext):
        """Build filepath with new name and extension."""
        old_dir = os.path.dirname(old_path)
        new_name = new_name + new_ext
        return os.path.join(old_dir, new_name)

    def export_single_mdl(self, context, mdl_base, filepath, options):
        """Export a single MDL file."""
        options.mdlname = mdl_base.name
        options.filepath = filepath
        options.classification = mdl_base.nvb.classification

        # Export MDL
        ascii_lines = []
        nvb_mdl.Mdl.generate_ascii(mdl_base, ascii_lines, options)
        with open(os.fsencode(filepath), 'w', newline='\r\n') as f:
            f.write('\n'.join(ascii_lines))

        # Export walkmesh
        if options.geom_walkmesh:
            wkm_type = self.get_walkmeshtype(mdl_base)
            wkm_ext = '.' + wkm_type
            ascii_lines = []
            nvb_mdl.Mdl.generate_ascii_wkm(mdl_base, ascii_lines,
                                           wkm_type, options)
            if ascii_lines:
                wkm_name = os.path.splitext(os.path.basename(filepath))[0]
                wkm_path = self.get_filepath(filepath, wkm_name, wkm_ext)
                with open(os.fsencode(wkm_path), 'w', newline='\r\n') as f:
                    f.write('\n'.join(ascii_lines))

    def execute(self, context):
        """Export model for all selected phenotypes."""
        addon_prefs = context.preferences.addons[__package__].preferences
        
        # Get MDL base
        mdl_base = nvb_utils.get_mdl_base(context.object,
                                          context.scene.collection,
                                          context.scene)
        if not mdl_base:
            self.report({'ERROR'}, 'No MDL base found')
            return {'CANCELLED'}


        # Set to object mode
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Set frame to zero if specified
        if self.frame_set_zero:
            context.scene.frame_current = 0
            context.evaluated_depsgraph_get().update()

        # Build export options
        options = nvb_def.ExportOptions()
        options.scene = context.scene
        options.depsgraph = context.evaluated_depsgraph_get()
        options.mat_mtr_generate = addon_prefs.export_mat_mtr_generate
        options.mat_mtr_ref = addon_prefs.export_mat_mtr_ref
        options.mat_diffuse_ref = addon_prefs.export_mat_diffuse_ref
        options.geom_import = True
        options.geom_normals = self.export_normals
        options.geom_tangents = self.export_tangents and self.export_normals
        options.geom_smoothing_split = (self.export_smoothing_mode == 'SPLIT')
        options.geom_smoothing_group = (self.export_smoothing_mode == 'GROUP')
        options.geom_smoothing_group_binary = addon_prefs.export_smoothgroups_binary
        options.geom_smoothing_group_distinct = addon_prefs.export_smoothgroups_distinct_verts
        options.geom_walkmesh = self.export_walkmesh
        options.anim_export = self.export_animations
        options.export_metadata = addon_prefs.export_metadata
        options.export_wirecolor = addon_prefs.export_wirecolor
        options.uv_merge = self.uv_merge
        options.uv_level = self.uv_mode
        options.uv_order = self.uv_order
        options.apply_modifiers = self.apply_modifiers
        options.strip_trailing = self.strip_trailing
        options.batch_mode = 'OFF'

        base_dir = os.path.dirname(self.filepath)
        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]

        exported_count = 0

        # Detect if base model is male or female
        base_is_male = self.is_base_model_male(mdl_base)

        # Export original (unscaled) if requested
        if self.export_original:
            self.export_single_mdl(context, mdl_base, self.filepath, options)
            exported_count += 1

        # Export each selected phenotype
        for prefix, scale_x, scale_y, scale_z, desc, target_is_male in self.get_selected_phenotypes():
            # Generate new filename
            new_filename = self.replace_phenotype_prefix(base_filename, prefix)
            new_filepath = os.path.join(base_dir, new_filename + '.mdl')
            new_mdl_name = self.replace_phenotype_prefix(mdl_base.name, prefix)

            # Calculate final scale, including gender conversion if needed
            final_scale_x = scale_x
            final_scale_y = scale_y
            final_scale_z = scale_z
            
            # Apply gender conversion if exporting to opposite gender
            if base_is_male and not target_is_male:
                # Male base -> Female target: apply male-to-female conversion first
                final_scale_x *= self.MALE_TO_FEMALE_SCALE[0]
                final_scale_y *= self.MALE_TO_FEMALE_SCALE[1]
                final_scale_z *= self.MALE_TO_FEMALE_SCALE[2]
            elif not base_is_male and target_is_male:
                # Female base -> Male target: apply female-to-male conversion first
                final_scale_x *= self.FEMALE_TO_MALE_SCALE[0]
                final_scale_y *= self.FEMALE_TO_MALE_SCALE[1]
                final_scale_z *= self.FEMALE_TO_MALE_SCALE[2]

            # Duplicate the entire model hierarchy
            bpy.ops.object.select_all(action='DESELECT')
            
            # Select mdl_base and all descendants
            mdl_base.select_set(True)
            for obj in mdl_base.children_recursive:
                obj.select_set(True)
            
            context.view_layer.objects.active = mdl_base
            
            # Duplicate (linked=False means geometry is copied, but materials stay linked)
            bpy.ops.object.duplicate(linked=False)
            
            # Get the duplicated base (it's now the active object)
            dup_base = context.active_object
            
            # Get all duplicated objects
            dup_objects = list(context.selected_objects)
            
            # Rename the duplicate base
            dup_base.name = new_mdl_name
            
            # Apply scaling based on mode
            if self.is_cloak:
                # Cloak mode: use Transform Helper approach and set supermodel
                # Supermodel is just the phenotype prefix (e.g., "pfe0", "pfa0")
                dup_base.nvb.supermodel = prefix
                self.apply_scale_to_hierarchy(dup_base, final_scale_x, final_scale_y, final_scale_z)
            else:
                # Standard mode: apply scale transform normally
                dup_base.scale = (final_scale_x, final_scale_y, final_scale_z)
                bpy.ops.object.select_all(action='DESELECT')
                for obj in dup_objects:
                    obj.select_set(True)
                context.view_layer.objects.active = dup_base
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            # Update depsgraph after modifications
            context.evaluated_depsgraph_get().update()
            options.depsgraph = context.evaluated_depsgraph_get()
            
            # Export the duplicate
            self.export_single_mdl(context, dup_base, new_filepath, options)
            exported_count += 1
            
            # Delete the duplicates
            bpy.ops.object.select_all(action='DESELECT')
            for obj in dup_objects:
                obj.select_set(True)
            bpy.ops.object.delete()
            
            # Clear selection
            bpy.ops.object.select_all(action='DESELECT')

        export_type = 'cloak phenotype' if self.is_cloak else 'phenotype'
        self.report({'INFO'}, f'Exported {exported_count} {export_type} model(s)')
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(self)
        # Generate a file name from active object
        mdl_base = nvb_utils.get_mdl_base(context.object,
                                          context.scene.collection,
                                          context.scene)
        if mdl_base:
            generated_name = nvb_utils.generate_node_name(mdl_base, True)
            self.filepath = generated_name + '.mdl'
        else:
            self.filepath = 'untitled.mdl'
        return {'RUNNING_MODAL'}

    def draw(self, context):
        """Draw export options."""
        layout = self.layout

        # Cloak Mode Option
        box = layout.box()
        box.label(text='Export Mode:', icon='MODIFIER')
        box.prop(self, 'is_cloak')
        if self.is_cloak:
            col = box.column(align=True)
            col.scale_y = 0.8
            col.label(text='Cloak mode will:', icon='INFO')
            col.label(text='  - Set supermodel to phenotype prefix')
            col.label(text='  - Use Transform Helper scaling method')

        # Gender Selection
        box = layout.box()
        box.label(text='Gender:', icon='COMMUNITY')
        row = box.row(align=True)
        row.prop(self, 'export_female')
        row.prop(self, 'export_male')

        # Phenotype Selection
        box = layout.box()
        box.label(text='Phenotypes to Export:', icon='GROUP_VERTEX')
        box.prop(self, 'export_original')
        box.separator()
        box.prop(self, 'export_human')
        box.prop(self, 'export_elf')
        box.prop(self, 'export_halfling')
        box.prop(self, 'export_dwarf')
        box.prop(self, 'export_gnome')
        box.prop(self, 'export_halforc')

        # Scale Reference
        box = layout.box()
        box.label(text='Scale Factors:', icon='INFO')
        
        if self.export_female:
            col = box.column(align=True)
            col.scale_y = 0.8
            col.label(text='Female:', icon='DOT')
            col.label(text='  Elf: 0.82 x 0.81 x 0.90')
            col.label(text='  Halfling: 0.65 x 0.70 x 0.70')
            col.label(text='  Dwarf: 1.25 x 1.20 x 0.99')
            col.label(text='  Gnome: 0.83 x 0.84 x 0.84')
            col.label(text='  Half-Orc: 1.65 x 1.48 x 1.39')
        
        if self.export_male:
            col = box.column(align=True)
            col.scale_y = 0.8
            col.label(text='Male:', icon='DOT')
            col.label(text='  Elf: 0.80 x 0.80 x 0.89')
            col.label(text='  Halfling: 0.60 x 0.70 x 0.70')
            col.label(text='  Dwarf: 1.08 x 1.05 x 0.89')
            col.label(text='  Gnome: 0.85 x 0.85 x 0.81')
            col.label(text='  Half-Orc: 1.50 x 1.50 x 1.30')

        # Export Options
        box = layout.box()
        box.label(text='Export Options:', icon='EXPORT')
        box.prop(self, 'export_animations')
        box.prop(self, 'export_walkmesh')
        box.prop(self, 'export_normals')
        box.prop(self, 'export_tangents')
        box.prop(self, 'export_smoothing_mode')
        box.prop(self, 'apply_modifiers')
        box.prop(self, 'frame_set_zero')
        box.prop(self, 'strip_trailing')

        # UV Options
        box = layout.box()
        box.label(text='UV Options:', icon='UV')
        box.prop(self, 'uv_merge')
        box.prop(self, 'uv_mode')
        box.prop(self, 'uv_order')


class NVB_OT_setexport(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """Import animations from supermodel onto existing mdl"""
    bl_idname = 'scene.nvb_setexport'
    bl_label = 'Export Setfile'
    bl_options = {'PRESET'}

    filename_ext = '.set'
    filter_glob: bpy.props.StringProperty(
            default='*.set',
            options={'HIDDEN'})

    # Export options
    selected_only: bpy.props.BoolProperty(
            name='Selected only',
            description='Export selected tiles only',
            default=False)
    ignore_classification: bpy.props.BoolProperty(
            name='Ignore Classification',
            description='If disabled, only exports MDLs with "tile" classification',
            default=True)
    strip_trailing: bpy.props.BoolProperty(
            name='Strip Trailing Numbers',
            description='Remove trailing numbers from object names',
            default=False)
    ignore_stored_tile_id: bpy.props.BoolProperty(
            name='Ignore stored tile Id',
            description='Ignore stored tile id and re-assign all tile ids',
            default=True)
    store_tile_id: bpy.props.BoolProperty(
            name='Store tile Id',
            description='Store assigned tile Id on models for re-export',
            default=False)
    collections_as_groups: bpy.props.BoolProperty(
            name='Collections As Groups',
            description='Use collections to generate tile groups, see collection properties',
            default=True)
    # setfile general options
    internal_name: bpy.props.StringProperty(
            name='Name',
            description='Internal Name',
            default="ttt99")
    is_interior: bpy.props.BoolProperty(
            name='Interior',
            description='Interior',
            default=False)
    has_height_transition: bpy.props.BoolProperty(
            name='Height Transition',
            description='If the tileset uses raise/lower',
            default=False)
    env_map: bpy.props.StringProperty(
            name='Environment Map',
            description='Environment Map',
            default="ttr01__ref01")
    transition: bpy.props.IntProperty(
            name='Transition',
            description='The height difference of model placed (in meters) at Height 0 and Height 1.',
            default=5, min=0, step=1)
    selector_height: bpy.props.IntProperty(
            name='Selector Height',
            description='Defines the height of the green wireframe cube when using selections in the toolset.',
            default=5, min=1, soft_max=20, step=1)
    displayname: bpy.props.IntProperty(
            name='Diplay Name',
            description='References an entry in dialog.tlk.',
            default=-1, min=-1)
    unlocalized_name: bpy.props.StringProperty(
            name='Unlocalized Name',
            description='Avoids having to use a dialog tlk entry. Set Display Name to -1 to enable.',
            default="MY_TILESET_NAME")
    # setfile grass options
    grass: bpy.props.BoolProperty(
            name='Grass',
            description='Toggle grass',
            default=False)
    grass_texture: bpy.props.StringProperty(
            name='Texture',
            description='Image for Grass Texture.',
            default="grass")
    grass_density: bpy.props.FloatProperty(
            name='Density',
            description='Grass Density',
            default=5.0, min=0.1, soft_max=10.0, step=0.1)
    grass_height: bpy.props.FloatProperty(
            name='Height',
            description='Grass Height',
            default=1.2, min=0.1, soft_max=10.0, step=0.1)

    @classmethod
    def poll(self, context):
        """Alwys possible (will produce empty setfile)."""
        return True

    def draw(self, context):
        """Draw the export UI."""
        layout = self.layout

        # Export settings
        box = layout.box()
        box.prop(self, 'selected_only')
        box.prop(self, 'ignore_classification')
        box.prop(self, 'strip_trailing')
        box.prop(self, 'ignore_stored_tile_id')
        box.prop(self, 'store_tile_id')
        box.prop(self, 'collections_as_groups')

        # General Settings
        box = layout.box()
        box.prop(self, 'internal_name')
        box.prop(self, 'is_interior')
        box.prop(self, 'has_height_transition')
        box.prop(self, 'env_map')
        box.prop(self, 'transition')
        box.prop(self, 'selector_height')
        box.prop(self, 'displayname')
        sub = box.column()  # only enable if normals are enabled
        sub.enabled = (self.displayname == -1)
        sub.prop(self, 'unlocalized_name')
        #Grass
        box = layout.box()
        box.prop(self, 'grass')
        sub = box.column()  # only enable if normals are enabled
        sub.enabled = (self.grass)
        sub.prop(self, 'grass_texture')
        sub.prop(self, 'grass_density')
        sub.prop(self, 'grass_height')


    def execute(self, context):
        """Export setfile."""
        obj_list = []
        if self.selected_only == 'SCN':
            obj_list = bpy.context.selected_objects
        else:
            obj_list = bpy.context.scene.collection.all_objects

        mdl_list = []
        for obj in obj_list:
            base = nvb_utils.get_obj_mdl_base(obj)
            if base and (self.ignore_classification or base.nvb.classification == 'tile') and (base not in mdl_list):
                mdl_list.append(base)

        ascii_setfile = nvb_utils.create_setfile(mdl_list,
                                                 self.ignore_stored_tile_id,
                                                 self.store_tile_id,
                                                 self.strip_trailing,
                                                 self.collections_as_groups,
                                                 self.internal_name,
                                                 self.is_interior,
                                                 self.has_height_transition,
                                                 self.env_map,
                                                 self.transition,
                                                 self.selector_height,
                                                 self.displayname,
                                                 self.unlocalized_name,
                                                 self.grass,
                                                 self.grass_texture,
                                                 self.grass_density,
                                                 self.grass_height)

        with open(os.fsencode(self.filepath), 'w', newline='\r\n') as f:
            f.write('\n'.join(ascii_setfile))

        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(self)

        return {'RUNNING_MODAL'}
