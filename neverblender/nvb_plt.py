"""NWN PLT (Packed Layer Texture) support for NeverBlender.

Adds support for importing and exporting Neverwinter Nights PLT files,
which are used for character customization (skin, hair, armor colors, etc.).
"""

import os
import struct

import bpy
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper


# PLT Format Constants
PLT_HEADER_SIGNATURE = b"PLT V1  "
PLT_HEADER_SIZE = 24
PLT_RESERVED_BYTES = bytes([0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
PLT_NUM_LAYERS = 10
PLT_ALPHA_THRESHOLD = 25

PLT_LAYERS = [
    {"id": 0, "name": "skin",     "display": "Skin"},
    {"id": 1, "name": "hair",     "display": "Hair"},
    {"id": 2, "name": "metal1",   "display": "Metal 1"},
    {"id": 3, "name": "metal2",   "display": "Metal 2"},
    {"id": 4, "name": "cloth1",   "display": "Cloth 1"},
    {"id": 5, "name": "cloth2",   "display": "Cloth 2"},
    {"id": 6, "name": "leather1", "display": "Leather 1"},
    {"id": 7, "name": "leather2", "display": "Leather 2"},
    {"id": 8, "name": "tattoo1",  "display": "Tattoo 1"},
    {"id": 9, "name": "tattoo2",  "display": "Tattoo 2"},
]


class NVB_OT_plt_import(bpy.types.Operator, ImportHelper):
    """Import a Neverwinter Nights PLT file"""
    bl_idname = "nvb.plt_import"
    bl_label = "Import NWN PLT"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".plt"

    filter_glob: StringProperty(
        default="*.plt",
        options={'HIDDEN'},
        maxlen=255,
    )

    create_material: BoolProperty(
        name="Create Material",
        description="Create a material with the PLT layers as textures",
        default=True,
    )

    def execute(self, context):
        return import_plt(context, self.filepath, self.create_material)


class NVB_OT_plt_export(bpy.types.Operator, ExportHelper):
    """Export as a Neverwinter Nights PLT file"""
    bl_idname = "nvb.plt_export"
    bl_label = "Export NWN PLT"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".plt"

    filter_glob: StringProperty(
        default="*.plt",
        options={'HIDDEN'},
        maxlen=255,
    )

    image_prefix: StringProperty(
        name="Image Prefix",
        description="Prefix for the layer images (e.g., 'mytexture' looks for 'mytexture_skin', 'mytexture_hair', etc.)",
        default="",
    )

    def execute(self, context):
        return export_plt(context, self.filepath, self.image_prefix)


class NVB_OT_plt_setup(bpy.types.Operator):
    """Create empty images for all PLT layers"""
    bl_idname = "nvb.plt_setup"
    bl_label = "Setup PLT Layer Images"
    bl_options = {'REGISTER', 'UNDO'}

    prefix: StringProperty(
        name="Name Prefix",
        description="Prefix for the image names",
        default="texture",
    )

    width: bpy.props.IntProperty(
        name="Width",
        description="Image width in pixels",
        default=256,
        min=1,
        max=4096,
    )

    height: bpy.props.IntProperty(
        name="Height",
        description="Image height in pixels",
        default=256,
        min=1,
        max=4096,
    )

    def execute(self, context):
        for layer_info in PLT_LAYERS:
            image_name = f"{self.prefix}_{layer_info['name']}"

            if image_name not in bpy.data.images:
                img = bpy.data.images.new(image_name, self.width, self.height, alpha=True)
                # Initialize as transparent
                pixels = [0.0] * (self.width * self.height * 4)
                img.pixels = pixels

        self.report({'INFO'}, f"Created {PLT_NUM_LAYERS} PLT layer images with prefix '{self.prefix}'")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


def import_plt(context, filepath, create_material):
    """Import a PLT file and create Blender images for each layer."""

    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except IOError as e:
        print(f"NeverBlender PLT: Failed to read file: {e}")
        return {'CANCELLED'}

    # Validate header
    if len(data) < PLT_HEADER_SIZE:
        print("NeverBlender PLT: File too small")
        return {'CANCELLED'}

    signature = data[0:8]
    if signature != PLT_HEADER_SIGNATURE:
        print(f"NeverBlender PLT: Invalid signature: {signature}")
        return {'CANCELLED'}

    width = struct.unpack_from("<I", data, 16)[0]
    height = struct.unpack_from("<I", data, 20)[0]

    # Get base name from file
    base_name = os.path.splitext(os.path.basename(filepath))[0]

    # Parse pixel data and create images for each layer
    num_pixels = width * height
    created_images = []

    for layer_info in PLT_LAYERS:
        layer_id = layer_info["id"]
        layer_name = layer_info["name"]
        image_name = f"{base_name}_{layer_name}"

        # Create new image (RGBA) or reuse existing
        if image_name in bpy.data.images:
            img = bpy.data.images[image_name]
            if img.size[0] != width or img.size[1] != height:
                bpy.data.images.remove(img)
                img = bpy.data.images.new(image_name, width, height, alpha=True)
            else:
                # Unpack if packed so we can update pixels
                if img.packed_file:
                    img.unpack(method='REMOVE')
        else:
            img = bpy.data.images.new(image_name, width, height, alpha=True)

        # Build pixel data
        # Blender uses bottom-left origin like PLT, so no Y-flip needed
        # But Blender pixels are stored bottom-to-top in the array
        pixels = [0.0] * (width * height * 4)

        for y in range(height):
            for x in range(width):
                # PLT data is bottom-left origin
                plt_offset = PLT_HEADER_SIZE + (y * width + x) * 2
                if plt_offset + 1 >= len(data):
                    continue
                gray_value = data[plt_offset]
                pixel_layer = data[plt_offset + 1]

                # Blender image pixel index (also bottom-left origin)
                pixel_idx = (y * width + x) * 4

                if pixel_layer == layer_id:
                    gray_float = gray_value / 255.0
                    pixels[pixel_idx] = gray_float      # R
                    pixels[pixel_idx + 1] = gray_float  # G
                    pixels[pixel_idx + 2] = gray_float  # B
                    pixels[pixel_idx + 3] = 1.0         # A
                else:
                    pixels[pixel_idx] = 0.0      # R
                    pixels[pixel_idx + 1] = 0.0  # G
                    pixels[pixel_idx + 2] = 0.0  # B
                    pixels[pixel_idx + 3] = 0.0  # A

        img.pixels = pixels
        img.pack()
        created_images.append(img)

    # Optionally create a material with the layers
    if create_material:
        create_plt_material(base_name, created_images, width, height)

    # Register file for autoreload tracking
    try:
        from . import nvb_plt_autoreload
        nvb_plt_autoreload.register_plt_file(filepath, base_name)
    except ImportError:
        pass  # Autoreload module not available

    print(f"NeverBlender PLT: Imported {base_name} ({width}x{height})")
    return {'FINISHED'}


def create_plt_material(base_name, images, width, height):
    """Create a material with nodes for PLT layers."""

    mat_name = f"{base_name}_PLT"

    # Create or get material
    if mat_name in bpy.data.materials:
        mat = bpy.data.materials[mat_name]
    else:
        mat = bpy.data.materials.new(name=mat_name)

    # Blender < 4.0: use_nodes must be set to True to create the node_tree
    # Blender 4.0+: use_nodes was removed, node_tree is created automatically
    if bpy.app.version < (4, 0, 0):
        mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    nodes.clear()

    # Create output node
    output_node = nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (800, 0)

    # Create principled BSDF
    bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf_node.location = (500, 0)
    links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

    # Create mix nodes to combine layers
    # For now, just use the skin layer as base and overlay others
    y_offset = 300
    prev_color_socket = None

    for i, (layer_info, img) in enumerate(zip(PLT_LAYERS, images)):
        # Create image texture node
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = img
        tex_node.location = (-400, y_offset - i * 300)
        tex_node.label = layer_info["display"]

        if i == 0:
            # First layer - connect directly
            prev_color_socket = tex_node.outputs['Color']
        else:
            # Mix with previous using alpha
            mix_node = nodes.new('ShaderNodeMix')
            mix_node.data_type = 'RGBA'
            mix_node.location = (-100, y_offset - i * 150)
            mix_node.label = f"Mix {layer_info['display']}"

            links.new(prev_color_socket, mix_node.inputs[6])  # A (color)
            links.new(tex_node.outputs['Color'], mix_node.inputs[7])  # B (color)
            links.new(tex_node.outputs['Alpha'], mix_node.inputs[0])  # Factor

            prev_color_socket = mix_node.outputs[2]  # Result

    if prev_color_socket:
        links.new(prev_color_socket, bsdf_node.inputs['Base Color'])


def export_plt(context, filepath, image_prefix):
    """Export Blender images to a PLT file."""

    # Find images for each layer
    layer_images = []
    width = None
    height = None

    for layer_info in PLT_LAYERS:
        layer_name = layer_info["name"]

        # Try different naming conventions
        possible_names = [
            f"{image_prefix}_{layer_name}" if image_prefix else layer_name,
            f"{image_prefix}{layer_name}" if image_prefix else layer_name,
            layer_name,
        ]

        img = None
        for name in possible_names:
            if name in bpy.data.images:
                img = bpy.data.images[name]
                break

        layer_images.append(img)

        if img is not None:
            if width is None:
                width = img.size[0]
                height = img.size[1]

    if width is None:
        print("NeverBlender PLT: No images found for export")
        return {'CANCELLED'}

    # Build PLT data
    num_pixels = width * height
    plt_data = bytearray(num_pixels * 2)

    # Initialize with black on skin layer
    for i in range(num_pixels):
        plt_data[i * 2] = 0      # Black
        plt_data[i * 2 + 1] = 0  # Skin layer

    # Process each layer
    for layer_idx, img in enumerate(layer_images):
        if img is None:
            continue

        pixels = list(img.pixels)
        img_width = img.size[0]
        img_height = img.size[1]

        for y in range(min(height, img_height)):
            for x in range(min(width, img_width)):
                pixel_idx = (y * img_width + x) * 4

                r = pixels[pixel_idx]
                g = pixels[pixel_idx + 1]
                b = pixels[pixel_idx + 2]
                a = pixels[pixel_idx + 3]

                if a > PLT_ALPHA_THRESHOLD / 255.0:
                    gray = int((r + g + b) / 3.0 * 255)
                    out_idx = (y * width + x) * 2
                    plt_data[out_idx] = gray
                    plt_data[out_idx + 1] = layer_idx

    # Create header
    header = bytearray(PLT_HEADER_SIZE)
    header[0:8] = PLT_HEADER_SIGNATURE
    header[8:16] = PLT_RESERVED_BYTES
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 20, height)

    # Write file
    try:
        with open(filepath, "wb") as f:
            f.write(header)
            f.write(plt_data)
    except IOError as e:
        print(f"NeverBlender PLT: Failed to write file: {e}")
        return {'CANCELLED'}

    print(f"NeverBlender PLT: Exported {filepath} ({width}x{height})")
    return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(NVB_OT_plt_import.bl_idname, text="NWN PLT Texture (.plt)")


def menu_func_export(self, context):
    self.layout.operator(NVB_OT_plt_export.bl_idname, text="NWN PLT Texture (.plt)")


def menu_func_setup(self, context):
    self.layout.operator(NVB_OT_plt_setup.bl_idname)
