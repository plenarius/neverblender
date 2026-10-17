import math
import os

import bpy

from . import nvb_mtr
from . import nvb_def
from . import nvb_parse
from . import nvb_utils
from .nvb_materialnode import Materialnode


class Material(object):
    """A material read from an mdl node."""

    def __init__(self):
        """TODO: DOC."""
        self.materialname = ""
        self.bitmap = ""
        self.renderhint = ""
        self.texture_list = [None]*15
        self.mtr_data = None

    def generate_material_name(self, mdl_bitmap, mdl_materialname, texture0, force_lowercase=False):
        """Generates a material name for use in blender."""
        # 'materialname' over 'texture0'/'bitmap' over Default
        if mdl_materialname:
            mat_name = mdl_materialname
        elif mdl_bitmap:
            mat_name = mdl_bitmap
        elif texture0 and (texture0 is not nvb_def.null):
            mat_name = texture0
        else:
            mat_name = ""  # Blender will create a default name
        if force_lowercase:
            mat_name = mat_name.lower()
        return mat_name

    def find_blender_material(self, options):
        """Finds a material in blender with the same settings as this one."""
        def check_textures(texture_list1, texture_list2, ignore_case=True):
            """Check if the texture lists match."""
            if ignore_case:
                return ([t1.lower() if t1 else None for t1 in texture_list1] == [t2.lower() if t2 else None for t2 in texture_list2])
            else:
                return (texture_list1 == texture_list2)

        def check_shaders(blen_material, mtr_data):
            """Check if the shader from an MTR file match the ones in the blender material."""
            shader1_vs = ""
            shader1_fs = ""
            if blen_material:
                shader1_vs = blen_mat.nvb.mtr.shader_vs
                shader1_fs = blen_mat.nvb.mtr.shader_fs
            # MTR file may be undefined
            shader2_vs = ""
            shader2_fs = ""
            if mtr_data:
                shader2_vs = mtr_data.customshaderVS
                shader2_fs = mtr_data.customshaderFS
            return (shader1_vs == shader2_vs) and (shader1_fs == shader2_fs)

        #print("####################")
        #print("looking for: ")
        #print(self.texture_list)
        #print(self.color_list)
        #print(self.alpha)
        for blen_mat in bpy.data.materials:
            if not blen_mat.name.startswith("wok_"):
                #print("#")
                #print("Checking: " + blen_mat.name)
                tex_list = Materialnode.get_texture_list(blen_mat)
                #print(tex_list)
                #print(col_list)
                #print(alpha)
                # Compare textures, colors and alpha
                if ( (tex_list and len(tex_list) >= 5) and check_textures(tex_list[:5], self.texture_list[:5], True) and
                     check_shaders(blen_mat, self.mtr_data) ):
                    #print("MATCH!")
                    return blen_mat
        return None

    def mtr_read(self, options):
        """Read the contents of the mtr file specified in the mdl file."""
        def get_mtr_path(mtr_name, mtr_dir):
            mtr_filename = mtr_name + '.mtr'
            mtr_dir, _ = os.path.split(mtr_dir)
            return nvb_utils.find_file_nocase(mtr_dir, mtr_filename)

        # if an mtr_name has been specified try opening it
        # but don't do anything else!
        if self.materialname:
            if self.materialname in options.mtrdb:
                self.mtr_data = options.mtrdb[self.materialname]
            else:
                mtr_path = get_mtr_path(self.materialname, options.filepath)
                if os.path.isfile(mtr_path):
                    mtr = nvb_mtr.Mtr(self.materialname)
                    if mtr.read_mtr(mtr_path):
                        options.mtrdb[self.materialname] = mtr
                        self.mtr_data = mtr
        # Try opening "bitmap"
        elif self.bitmap:
            if self.bitmap in options.mtrdb:
                self.mtr_data = options.mtrdb[self.bitmap]
            else:
                mtr_path = get_mtr_path(self.bitmap, options.filepath)
                if os.path.isfile(mtr_path):
                    # bitmap is an mtr file
                    mtr = nvb_mtr.Mtr(self.bitmap)
                    if mtr.read_mtr(mtr_path):
                        options.mtrdb[self.bitmap] = mtr
                        self.mtr_data = mtr
                else:
                    # bitmap is not an mtr file
                    pass

    def mtr_merge(self):
        """Merges the contents of the mtr file into this material."""
        # Merge values from mtr into this material
        if self.mtr_data:
            self.renderhint = self.mtr_data.renderhint
            # Load all existing textures from the mtr into the material
            self.texture_list = \
                [t2 if t2 else t1 for t1, t2 in
                 zip(self.texture_list, self.mtr_data.texture_list)]
            # Load all existing colors from the mtr into the material
            # self.color_list = \
            #     [c2 if c2 else c1 for c1, c2 in
            #      zip(self.color_list, self.mtr_data.color_list)]

    def create_blender_material(self, options, mdl_bitmap, mdl_materialname, mdl_textures, always_create_new=True):
        """Returns a blender material with the stored values."""
        blen_mat_name = self.generate_material_name(mdl_bitmap, mdl_materialname, mdl_textures[0], options.mat_mtr_lowercase)

        self.materialname = mdl_materialname
        self.bitmap = mdl_bitmap

        self.texture_list = mdl_textures
        if not self.texture_list[0]:
            self.texture_list[0] = mdl_bitmap

        # Load mtr values into this material
        # This will override values from mdl, even the ones previously ignored (from the mdl)
        if options.mat_use_mtr:
            self.mtr_read(options)
            self.mtr_merge()

        if options.mat_mtr_lowercase:
            self.texture_list = [t.lower() if t else t for t in self.texture_list]
        # Look for similar materials to avoid duplicates
        blender_mat = None
        if options.mat_automerge and not always_create_new:
            blender_mat = self.find_blender_material(options)
        # Create new material if necessary
        if not blender_mat:
            blender_mat = bpy.data.materials.new(blen_mat_name)
            blender_mat.blend_method = 'HASHED'  # 'BLEND' doesn't play nice
            blender_mat.show_transparent_back = False
            blender_mat.use_backface_culling = True

            blender_mat.nvb.mtr.use = bool(self.materialname) or self.mtr_data is not None
            if blender_mat.nvb.mtr.use and self.mtr_data:
                blender_mat.nvb.mtr.renderhint = self.mtr_data.renderhint
                blender_mat.nvb.mtr.shader_vs = self.mtr_data.customshaderVS
                blender_mat.nvb.mtr.shader_gs = self.mtr_data.customshaderGS
                blender_mat.nvb.mtr.shader_fs = self.mtr_data.customshaderFS
            blender_mat.use_nodes = True
            blender_mat.node_tree.nodes.clear()
            Materialnode.add_node_data(blender_mat, blen_mat_name, self.texture_list, options)
        return blender_mat

    @staticmethod
    def generate_ascii(obj, ascii_lines, options):
        fstr_tex0 = '  ' + options.mat_diffuse_ref + ' {:s}'
        blen_material = obj.active_material
        if obj.nvb.render and blen_material:
            tex_list = Materialnode.get_texture_list(blen_material)

            # Clean up texture list, delete trailing "null"
            tex_list = [t if t else nvb_def.null for t in tex_list]
            while tex_list and tex_list[-1] == nvb_def.null:
                _ = tex_list.pop()
            # Write textures
            if blen_material.nvb.mtr.use:
                # MTRs are exported in a second pass
                mtr_name = nvb_mtr.Mtr.get_mtr_name(blen_material)
                ascii_lines.append('  ' + options.mat_mtr_ref + ' ' + mtr_name)
                # AddOn options specify whether to actually write material data to mtr file
                if options.mat_mtr_generate:
                    options.mtr_list.add((mtr_name, blen_material.name))
            else:
                # Write to MDL: Can only export the first three textures
                # Also fix texture name to ascii
                tex_list = [nvb_utils.generate_mdl_identifier(t) for t in tex_list[:3]]
                # Add Renderhint if normal or specular texture is present
                if (tex_list[1:].count(nvb_def.null) < len(tex_list[1:])):
                    ascii_lines.append('  renderhint NormalAndSpecMapped')
                # Export textures
                fstr_list = [fstr_tex0, '  texture1 {:s}', '  texture2 {:s}']
                for i, tex in enumerate(tex_list):
                    ascii_lines.append(fstr_list[i].format(tex))
        else:
            ascii_lines.append(fstr_tex0.format(nvb_def.null))
