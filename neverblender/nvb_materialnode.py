"""TODO: DOC."""

import os
import collections
import bpy

from . import nvb_utils


class Materialnode(object):
    """Collection of function for dealing with shader nodes."""

    @staticmethod
    def get_output_node(material):
        """Search for the output node in this node list."""
        # Material has to have a node tree, and up to Blender 4.5 use it
        # (Blender 5.0 always uses it and deprecates use_nodes)
        if not material.node_tree:
            return None
        if bpy.app.version < (5, 0, 0) and not material.use_nodes:
            return None
        # Grab all outputs
        output_nodes = [n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL']
        if not output_nodes:
            return None
        # If there are multiple output nodes we have to choose one
        # We'll pick the one with the most input links
        output_nodes.sort(
            key=(lambda n: len([i for i in n.inputs if i.is_linked])),
            reverse=True)
        return output_nodes[0]

    @staticmethod
    def get_connected_nodes(origin_socket, matching_node=lambda _: True, follow_socket=lambda _: True):
        """Search for the output node in this node list."""
        def dfsearch(result, depth, socket, matching_node, follow_socket):
            if not socket or not socket.is_linked or not follow_socket(socket):
                return
            # Get connected node
            for l in socket.links:
                n = l.from_node
                #print(n.type + " " + n.label)
                if matching_node(n):
                    # Found a matchting node
                    result.append((n, depth))
                else:
                    # Not a match, keep looking through inputs
                    for s in n.inputs:
                        dfsearch(result, depth+1, s, matching_node, follow_socket)
        # Get a list of all matching nodes
        node_list = []
        dfsearch(node_list, 0, origin_socket, matching_node, follow_socket)
        # sort the list by distance to origin socket (for selection between closest and farthest)
        return [n[0] for n in sorted(node_list, key=lambda x:x[1])]

    @staticmethod
    def get_alpha_value(socket, fail_value=1.0):
        """Get tha alpha value from the socket."""
        if socket:
            # Transparency needs to be inverted
            if socket.name == 'Transparency':
                return (1.0 - socket.default_value)
            else:
                return socket.default_value
        return fail_value

    @staticmethod
    def get_color_value(socket, fail_value=(1.0, 1.0, 1.0, 1.0)):
        """Get tha color value from the socket."""
        if socket:
            return socket.default_value
        return fail_value

    @staticmethod
    def get_node_identifier(node, fallback_to_name=False):
        """Return node label if specified or the (unique) node name."""
        # Restored from Neverblender 2.8: the 4.0 release removed it but
        # get_texture_name still calls it for a texture node with no image,
        # which is what re-importing a model whose material is still in the
        # scene runs into.
        if node.label:
            return node.label
        elif fallback_to_name:
            return node.name
        return "ERROR"

    @staticmethod
    def get_texture_name(texture_node, fail_value="ERROR"):
        """Get a texture from a texture node."""
        # No texture node: None=Null
        if texture_node and texture_node.image:
            img = texture_node.image
            # Get name from filepath or (Blender's) image name
            tex_name = None
            # Try image.filepath first (it may return a unusable path)
            if img.filepath:
                tex_name = os.path.splitext(os.path.basename(img.filepath))[0]
            # Check if the name from filepath is present and useable
            # If not try the image name directly instead
            if not tex_name and img.name:
                tex_name = os.path.splitext(os.path.basename(img.name))[0]
            return tex_name

        # No image, use node identifier (either node label or node name)
        return Materialnode.get_node_identifier(texture_node, True)

    @staticmethod
    def get_texture_list(material):
        """Get a list of relevant textures and colors for this material."""
        texture_list = [None] * 15

        # Get Output nodes
        node_out = Materialnode.get_output_node(material)
        if node_out:
            # Get shader node
            matching_nodes = Materialnode.get_connected_nodes(node_out.inputs['Surface'],
                                                              matching_node=lambda n: n.type in ['BSDF_PRINCIPLED', 'EEVEE_SPECULAR'])
            if matching_nodes:
                shader_node = matching_nodes[0]
                # Diffuse
                matching_nodes = Materialnode.get_connected_nodes(origin_socket=shader_node.inputs['Base Color'],
                                                                  matching_node=lambda n: n.type.startswith('TEX_'))
                texture_list[0] = Materialnode.get_texture_name(matching_nodes[0]) if matching_nodes else None

                # Normal
                matching_nodes = Materialnode.get_connected_nodes(origin_socket=shader_node.inputs['Normal'],
                                                                  matching_node=lambda n: n.type.startswith('TEX_'),
                                                                  follow_socket=lambda s: s.name in ['Normal', 'Color'])
                texture_list[1] = Materialnode.get_texture_name(matching_nodes[0]) if matching_nodes else None

                # Specular
                if 'Specular IOR Level' in shader_node.inputs:
                    input_socket_name = 'Specular IOR Level'  # Blender 4.0
                else:
                    input_socket_name = 'Specular'  # Blender 3.6
                matching_nodes = Materialnode.get_connected_nodes(origin_socket=shader_node.inputs[input_socket_name],
                                                                  matching_node=lambda n: n.type.startswith('TEX_'))
                texture_list[2] = Materialnode.get_texture_name(matching_nodes[0]) if matching_nodes else None

                # Roughness
                matching_nodes = Materialnode.get_connected_nodes(origin_socket=shader_node.inputs['Roughness'],
                                                                  matching_node=lambda n: n.type.startswith('TEX_'))
                texture_list[3] = Materialnode.get_texture_name(matching_nodes[0]) if matching_nodes else None

                # Height/AO
                # Two options:
                # 1. Connected to shader node "Normal"
                # 2. Connected to output node "displacement"
                matching_nodes = Materialnode.get_connected_nodes(origin_socket=shader_node.inputs['Normal'],
                                                         matching_node=lambda n: n.type.startswith('TEX_'),
                                                         follow_socket=lambda s: s.name in ['Normal', 'Height', 'Value'])
                if not matching_nodes:
                    matching_nodes = Materialnode.get_connected_nodes(node_out.inputs['Displacement'],
                                                                      matching_node=lambda n: n.type.startswith('TEX_'),
                                                                      follow_socket=lambda s: s.name in ['Displacement', 'Normal', 'Height', 'Value'])
                texture_list[4] = Materialnode.get_texture_name(matching_nodes[0]) if matching_nodes else None

                # Emissive
                # Only match texture nodes specifically named for emission to avoid
                # picking up the diffuse texture through the selfillum color mix chain
                if 'Emissive Color' in shader_node.inputs: # Evee specular shader
                    input_socket_name = 'Emissive Color'  # Blender 4.0, bdsf shader
                elif 'Emission Color' in shader_node.inputs:
                    input_socket_name = 'Emission Color'  # Blender 4.0, bdsf shader
                else:
                    input_socket_name = 'Emission'  # Blender 3.6, bdsf shader
                matching_nodes = Materialnode.get_connected_nodes(origin_socket=shader_node.inputs[input_socket_name],
                                                                  matching_node=lambda n: n.type.startswith('TEX_') and n.name == 'texture_emission')
                texture_list[5] = Materialnode.get_texture_name(matching_nodes[0]) if matching_nodes else None

        return texture_list

    @staticmethod
    def add_node_data_bsdf(material, output_label, texture_list, options):
        """Setup up material nodes for Principled BSDF Shader."""
        # Cache because lazy
        nodes = material.node_tree.nodes
        links = material.node_tree.links

        # Create an output and shaders
        node_out = nodes.new('ShaderNodeOutputMaterial')
        node_out.label = output_label
        node_out.location = (936, 577)

        node_shader = nodes.new('ShaderNodeBsdfPrincipled')
        node_shader.name = 'shader_bsdf'
        node_shader.location = (-81, 552)
        links.new(node_out.inputs[0], node_shader.outputs[0])

        # Alpha/Transparency from MDL

        # Use a math node to incorporate aurora alpha from MDL
        node_alpha_math = nodes.new('ShaderNodeMath')
        node_alpha_math.label = "Math Alpha"
        node_alpha_math.name = "math_alpha_math"
        node_alpha_math.location = (-1542, -456)
        node_alpha_math.operation = 'MULTIPLY'
        node_alpha_math.use_clamp = True
        node_alpha_math.inputs[0].default_value = 1.0

        links.new(node_shader.inputs['Alpha'], node_alpha_math.outputs[0])

        node_alpha_attr = nodes.new('ShaderNodeAttribute')
        node_alpha_attr.label = "Mdl Alpha"
        node_alpha_attr.name = "attr_alpha_mdl"
        node_alpha_attr.location = (-2058, -760)
        node_alpha_attr.attribute_type = 'OBJECT'
        node_alpha_attr.attribute_name = 'nvb.alpha'

        links.new(node_alpha_math.inputs[1], node_alpha_attr.outputs[2])

        # # # # # # # # # # # # # # # # # # #
        # Diffuse
        node_diff_tex = None
        node_diff_mix = None
        node_diff_attr = None

        node_diff_attr = nodes.new('ShaderNodeAttribute')
        node_diff_attr.label = "Mdl Diffuse"
        node_diff_attr.name = "attr_diffuse_mdl"
        node_diff_attr.location = (-1800, 1000)
        node_diff_attr.attribute_type = 'OBJECT'
        node_diff_attr.attribute_name = 'nvb.diffuse'

        # Add an extra mix rgb node and link it
        node_diff_mix = nodes.new('ShaderNodeMix')
        node_diff_mix.label = "Color: Diffuse"
        node_diff_mix.data_type = 'RGBA'
        node_diff_mix.blend_type = 'MULTIPLY'
        node_diff_mix.location = (-1300, 900)
        node_diff_mix.clamp_factor = True
        node_diff_mix.clamp_result = True
        node_diff_mix.inputs[0].default_value = 1.0  # factor
        node_diff_mix.inputs[6].default_value = (1.0,1.0,1.0, 0.0) # A
        node_diff_mix.inputs[7].default_value = (1.0,1.0,1.0, 0.0) # B

        links.new(node_shader.inputs['Base Color'], node_diff_mix.outputs[2])
        links.new(node_diff_mix.inputs[6], node_diff_attr.outputs[0])

        if texture_list[0]:
            # Setup: Image Texture (Color) => Principled BSDF
            # Setup: Image Texture (Alpha) => Mix Transparent (Factor)
            node_diff_tex = nodes.new('ShaderNodeTexImage')
            node_diff_tex.label = "Texture: Diffuse"
            node_diff_tex.name = "texture_diffuse"
            node_diff_tex.location = (-2000, 763)
            node_diff_tex.image = nvb_utils.create_image(texture_list[0], options.filepath, options.tex_search)
            node_diff_tex.image.colorspace_settings.name = 'sRGB'

            links.new(node_alpha_math.inputs['Value'], node_diff_tex.outputs['Alpha'])
            links.new(node_diff_mix.inputs[7], node_diff_tex.outputs['Color'])

        # # # # # # # # # # # # # # # # # # #
        # 1 = Normal
        node_norm_tex = None
        node_norm = None
        if texture_list[1]:
            # Setup: Image Texture => Normal Map => Principled BSDF
            node_norm_tex = nodes.new('ShaderNodeTexImage')
            node_norm_tex.label = "Texture: Normal"
            node_norm_tex.name = "texture_normal"
            node_norm_tex.location = (-941, -693)
            node_norm_tex.image = nvb_utils.create_image(texture_list[1], options.filepath, options.tex_search)
            node_norm_tex.image.colorspace_settings.name = 'Non-Color'

            node_norm = nodes.new('ShaderNodeNormalMap')
            node_norm.label = "Normal Map"
            node_norm.name = "vector_normal_map"
            node_norm.location = (-646, -591)

            links.new(node_norm.inputs['Color'], node_norm_tex.outputs['Color'])
            links.new(node_shader.inputs['Normal'], node_norm.outputs['Normal'])

        # # # # # # # # # # # # # # # # # # #
        # 2 = Specular
        node_spec_tex = None
        if 'Specular IOR Level' in node_shader.inputs:
            input_socket_name = 'Specular IOR Level'  # Blender 4.0
        else:
            input_socket_name = 'Specular' # Blender 3.6
        node_shader.inputs[input_socket_name].default_value = 0.0
        if texture_list[2]:
            # Setup: Image Texture => Principled BSDF
            node_spec_tex = nodes.new('ShaderNodeTexImage')
            node_spec_tex.label = "Texture: Specular"
            node_spec_tex.name = "texture_specular"
            node_spec_tex.location = (-1373, 371)
            node_spec_tex.image = nvb_utils.create_image(texture_list[2], options.filepath, options.tex_search)
            node_spec_tex.image.colorspace_settings.name = 'Non-Color'

            links.new(node_shader.inputs[input_socket_name], node_spec_tex.outputs[0])

        # # # # # # # # # # # # # # # # # # #
        # 3 = Roughness
        node_rough_tex = None
        if texture_list[3]:
            # Setup: Image Texture => Principled BSDF
            node_rough_tex = nodes.new('ShaderNodeTexImage')
            node_rough_tex.label = "Texture: Roughness"
            node_rough_tex.name = "texture_roughness"
            node_rough_tex.location = (-1022, 309)
            node_rough_tex.image = nvb_utils.create_image(texture_list[3], options.filepath, options.tex_search)
            node_rough_tex.image.colorspace_settings.name = 'Non-Color'

            links.new(node_shader.inputs['Roughness'], node_rough_tex.outputs['Color'])

        # # # # # # # # # # # # # # # # # # #
        # 4 = Height/AO/Parallax/Displacement
        node_height_tex = None
        if texture_list[4]:
            # Setup, 2 options:
            if False:
                # 1. Image Texture => Displacement => Material Output
                node_height_tex = nodes.new('ShaderNodeTexImage')
                node_height_tex.label = "Texture: Height"
                node_height_tex.name = "texture_height"
                node_height_tex.location = (227, 353)
                node_height_tex.image = nvb_utils.create_image(texture_list[4], options.filepath, options.tex_search)
                node_height_tex.image.colorspace_settings.name = 'Non-Color'

                # Displacement offset (from mtr, 0.0 by default)
                node_displ_offset = nodes.new('ShaderNodeMath')
                node_displ_offset.label = "Displacement Offset"
                node_displ_offset.name = "math_displacement_offset"
                node_displ_offset.location = (515, 453)
                node_displ_offset.operation = 'ADD'
                node_displ_offset.use_clamp = True
                node_displ_offset.inputs[0].default_value = 0.0
                if mtr_displacement_offset:
                    node_displ_offset.inputs[0].default_value = mtr_displacement_offset
                node_displ_offset.inputs[1].default_value = 0.0

                node_displ = nodes.new('ShaderNodeDisplacement')
                node_displ.name = "vector_displacement"
                node_displ.location = (727, 508)

                # Links: height texture => displacement offset (1) => displacement (Height) => material output
                links.new(node_displ_offset.inputs[1], node_height_tex.outputs['Color'])
                links.new(node_displ.inputs['Height'], node_displ_offset.outputs['Value'])
                links.new(node_out.inputs['Displacement'], node_displ.outputs['Displacement'])
            else:  # options.mat_displacement_mode == 'BUMP'
                # 2. Image Texture => Bump Node => Shader
                node_height_tex = nodes.new('ShaderNodeTexImage')
                node_height_tex.label = "Texture: Height"
                node_height_tex.name = "texture_height"
                node_height_tex.location = (-940, -429)
                node_height_tex.image = nvb_utils.create_image(texture_list[4], options.filepath, options.tex_search)
                node_height_tex.image.colorspace_settings.name = 'Non-Color'

                # Displacement offset (from mtr, 0.0 by default)
                node_displ_offset = nodes.new('ShaderNodeMath')
                node_displ_offset.label = "Displacement Offset"
                node_displ_offset.name = "math_displacement_offset"
                node_displ_offset.location = (-638, -328)
                node_displ_offset.operation = 'ADD'
                node_displ_offset.use_clamp = True
                node_displ_offset.inputs[0].default_value = 0.0
                if False:  # TODO: read displacement offset
                    node_displ_offset.inputs[0].default_value = mtr_displacement_offset
                node_displ_offset.inputs[1].default_value = 0.0

                node_bump = nodes.new('ShaderNodeBump')
                node_bump.name = "vector_bump"
                node_bump.location = (-384, -232)

                # Links: height texture => displacement offset (1) => bump (Height) => Shader (Normal)
                links.new(node_displ_offset.inputs[1], node_height_tex.outputs['Color'])
                links.new(node_bump.inputs['Height'], node_displ_offset.outputs['Value'])
                links.new(node_shader.inputs['Normal'], node_bump.outputs['Normal'])

                # Re-link normal node to bump node (previouly linked directly to shader)
                if node_norm:
                    links.new(node_bump.inputs['Normal'], node_norm.outputs['Normal'])

        # # # # # # # # # # # # # # # # # # #
        # 5 = Emission/Self Illumination
        if 'Emission Color' in node_shader.inputs:
            input_socket_name = 'Emission Color'  # Blender 4.0
        else:
            input_socket_name = 'Emission'  # Blender 3.6
        if not options.mat_ignore_selfillum_color:
            # Extra color node for MDL selfillum color
            node_emit_attr = nodes.new('ShaderNodeAttribute')
            node_emit_attr.label = "Mdl Selfillum"
            node_emit_attr.name = "attr_selfillum_mdl"
            node_emit_attr.location = (-1569, -115)
            node_emit_attr.attribute_type = 'OBJECT'
            node_emit_attr.attribute_name = 'nvb.selfillum'

            # Mix node: Multiplies selfillum color from MDL with diffuse color
            node_emit_mix1 = nodes.new('ShaderNodeMix')
            node_emit_mix1.label = "Mix: Self-Illumination"
            node_emit_mix1.name = "mix_selfillum_mul"
            node_emit_mix1.data_type = 'RGBA'
            node_emit_mix1.blend_type = 'MULTIPLY'
            node_emit_mix1.location = (-1358, 3)
            node_emit_mix1.clamp_result = True
            node_emit_mix1.clamp_factor = True
            node_emit_mix1.inputs[0].default_value = 1.0

            links.new(node_emit_mix1.inputs[6], node_diff_mix.outputs[2])
            links.new(node_emit_mix1.inputs[7], node_emit_attr.outputs[0])

            # Emissive/selfillum texture (only from mtr, may not be present)
            node_emit_tex = None
            if texture_list[5] and not options.mat_ignore_selfillum_texture:
                node_emit_tex = nodes.new('ShaderNodeTexImage')
                node_emit_tex.label = "Texture: Emission"
                node_emit_tex.name = "texture_emission"
                node_emit_tex.location = (-1192, -61)
                node_emit_tex.image = nvb_utils.create_image(texture_list[5], options.filepath, options.tex_search)
                node_emit_tex.image.colorspace_settings.name = 'sRGB'

                # 2nd mix node: Adds emissive texture to MDL selfillum color
                node_emit_mix2 = nodes.new('ShaderNodeMix')
                node_emit_mix2.label = "Mix: Add Self-Illumination"
                node_emit_mix2.name = "mix_selfillum_add"
                node_emit_mix2.data_type = 'RGBA'
                node_emit_mix2.blend_type = 'ADD'
                node_emit_mix2.location = (-753, 98)
                node_emit_mix2.clamp_result = True
                node_emit_mix2.clamp_factor = True
                node_emit_mix2.inputs[0].default_value = 1.0
                node_emit_mix2.inputs[6].default_value = (0.0, 0.0, 0.0, 1.0)
                node_emit_mix2.inputs[7].default_value = (0.0, 0.0, 0.0, 1.0)

                # Link 1st mix node inputs
                links.new(node_emit_mix2.inputs[6], node_emit_mix1.outputs[2])
                links.new(node_emit_mix2.inputs[7], node_emit_tex.outputs['Color'])

                # Finally link to shader
                links.new(node_shader.inputs[input_socket_name], node_emit_mix2.outputs[2])
            else:  # no emissive texture
                # link directly to shader
                links.new(node_shader.inputs[input_socket_name], node_emit_mix1.outputs[2])

    @staticmethod
    def add_node_data_spec(material, output_label, texture_list, options):
        """Setup up material nodes for Eevee Specular Shader."""
        # Cache because lazy
        nodes = material.node_tree.nodes
        links = material.node_tree.links

        # Create an output and shaders
        node_out = nodes.new('ShaderNodeOutputMaterial')
        node_out.label = output_label
        node_out.location = (936, 577)

        node_shader = nodes.new('ShaderNodeEeveeSpecular')
        node_shader.name = 'shader_eevee_specular'
        node_shader.location = (-81, 552)
        links.new(node_out.inputs[0], node_shader.outputs[0])

        # Alpha/Transparency from MDL

        # Use a math node to incorporate aurora alpha from MDL
        node_invert = nodes.new('ShaderNodeInvert')
        node_invert.label = "Alpha to Transparency"
        node_invert.name = "invert_alpha2trans"
        node_invert.location = (-881, -290)

        links.new(node_shader.inputs['Transparency'], node_invert.outputs[0])

        node_alpha_math = nodes.new('ShaderNodeMath')
        node_alpha_math.label = "Math Alpha"
        node_alpha_math.name = "math_alpha_math"
        node_alpha_math.location = (-1542, -456)
        node_alpha_math.operation = 'MULTIPLY'
        node_alpha_math.use_clamp = True
        node_alpha_math.inputs[0].default_value = 1.0

        links.new(node_invert.inputs['Color'], node_alpha_math.outputs[0])

        node_alpha_attr = nodes.new('ShaderNodeAttribute')
        node_alpha_attr.label = "Mdl Alpha"
        node_alpha_attr.name = "attr_alpha_mdl"
        node_alpha_attr.location = (-2058, -760)
        node_alpha_attr.attribute_type = 'OBJECT'
        node_alpha_attr.attribute_name = 'nvb.alpha'

        links.new(node_alpha_math.inputs[1], node_alpha_attr.outputs[2])

        # # # # # # # # # # # # # # # # # # #
        # Diffuse
        node_diff_tex = None
        node_diff_mix = None
        node_diff_attr = None

        node_diff_attr = nodes.new('ShaderNodeAttribute')
        node_diff_attr.label = "Mdl Diffuse"
        node_diff_attr.name = "attr_diffuse_mdl"
        node_diff_attr.location = (-1800, 1000)
        node_diff_attr.attribute_type = 'OBJECT'
        node_diff_attr.attribute_name = 'nvb.diffuse'

        # Add an extra mix rgb node and link it
        node_diff_mix = nodes.new('ShaderNodeMix')
        node_diff_mix.label = "Color: Diffuse"
        node_diff_mix.data_type = 'RGBA'
        node_diff_mix.blend_type = 'MULTIPLY'
        node_diff_mix.location = (-1300, 900)
        node_diff_mix.clamp_factor = True
        node_diff_mix.clamp_result = True
        node_diff_mix.inputs[0].default_value = 1.0  # factor
        node_diff_mix.inputs[6].default_value = (1.0,1.0,1.0, 0.0) # A
        node_diff_mix.inputs[7].default_value = (1.0,1.0,1.0, 0.0) # B

        links.new(node_shader.inputs['Base Color'], node_diff_mix.outputs[2])
        links.new(node_diff_mix.inputs[6], node_diff_attr.outputs[0])

        if texture_list[0]:
            # Setup: Image Texture (Color) => Principled BSDF
            # Setup: Image Texture (Alpha) => Mix Transparent (Factor)
            node_diff_tex = nodes.new('ShaderNodeTexImage')
            node_diff_tex.label = "Texture: Diffuse"
            node_diff_tex.name = "texture_diffuse"
            node_diff_tex.location = (-2000, 763)
            node_diff_tex.image = nvb_utils.create_image(texture_list[0], options.filepath, options.tex_search)
            node_diff_tex.image.colorspace_settings.name = 'sRGB'

            links.new(node_alpha_math.inputs['Value'], node_diff_tex.outputs['Alpha'])
            links.new(node_diff_mix.inputs[7], node_diff_tex.outputs['Color'])

        # # # # # # # # # # # # # # # # # # #
        # 1 = Normal
        node_norm_tex = None
        node_norm = None
        if texture_list[1]:
            # Setup: Image Texture => Normal Map => Principled BSDF
            node_norm_tex = nodes.new('ShaderNodeTexImage')
            node_norm_tex.label = "Texture: Normal"
            node_norm_tex.name = "texture_normal"
            node_norm_tex.location = (-941, -693)
            node_norm_tex.image = nvb_utils.create_image(texture_list[1], options.filepath, options.tex_search)
            node_norm_tex.image.colorspace_settings.name = 'Non-Color'

            node_norm = nodes.new('ShaderNodeNormalMap')
            node_norm.label = "Normal Map"
            node_norm.name = "vector_normal_map"
            node_norm.location = (-646, -591)

            links.new(node_norm.inputs['Color'], node_norm_tex.outputs['Color'])
            links.new(node_shader.inputs['Normal'], node_norm.outputs['Normal'])

        # # # # # # # # # # # # # # # # # # #
        # 2 = Specular
        node_spec_tex = None
        if 'Specular IOR Level' in node_shader.inputs:
            input_socket_name = 'Specular IOR Level'  # Blender 4.0
        else:
            input_socket_name = 'Specular' # Blender 3.6
        node_shader.inputs[input_socket_name].default_value = [0.0, 0.0, 0.0, 1.0]
        if texture_list[2]:
            # Setup: Image Texture => Principled BSDF
            node_spec_tex = nodes.new('ShaderNodeTexImage')
            node_spec_tex.label = "Texture: Specular"
            node_spec_tex.name = "texture_specular"
            node_spec_tex.location = (-1373, 371)
            node_spec_tex.image = nvb_utils.create_image(texture_list[2], options.filepath, options.tex_search)
            node_spec_tex.image.colorspace_settings.name = 'Non-Color'

            links.new(node_shader.inputs[input_socket_name], node_spec_tex.outputs[0])

        # # # # # # # # # # # # # # # # # # #
        # 3 = Roughness
        node_rough_tex = None
        if texture_list[3]:
            # Setup: Image Texture => Principled BSDF
            node_rough_tex = nodes.new('ShaderNodeTexImage')
            node_rough_tex.label = "Texture: Roughness"
            node_rough_tex.name = "texture_roughness"
            node_rough_tex.location = (-1022, 309)
            node_rough_tex.image = nvb_utils.create_image(texture_list[3], options.filepath, options.tex_search)
            node_rough_tex.image.colorspace_settings.name = 'Non-Color'

            links.new(node_shader.inputs['Roughness'], node_rough_tex.outputs['Color'])

        # # # # # # # # # # # # # # # # # # #
        # 4 = Height/AO/Parallax/Displacement
        node_height_tex = None
        if texture_list[4]:
            # Setup, 2 options:
            if False:
                # 1. Image Texture => Displacement => Material Output
                node_height_tex = nodes.new('ShaderNodeTexImage')
                node_height_tex.label = "Texture: Height"
                node_height_tex.name = "texture_height"
                node_height_tex.location = (227, 353)
                node_height_tex.image = nvb_utils.create_image(texture_list[4], options.filepath, options.tex_search)
                node_height_tex.image.colorspace_settings.name = 'Non-Color'

                # Displacement offset (from mtr, 0.0 by default)
                node_displ_offset = nodes.new('ShaderNodeMath')
                node_displ_offset.label = "Displacement Offset"
                node_displ_offset.name = "math_displacement_offset"
                node_displ_offset.location = (515, 453)
                node_displ_offset.operation = 'ADD'
                node_displ_offset.use_clamp = True
                node_displ_offset.inputs[0].default_value = 0.0
                if mtr_displacement_offset:
                    node_displ_offset.inputs[0].default_value = mtr_displacement_offset
                node_displ_offset.inputs[1].default_value = 0.0

                node_displ = nodes.new('ShaderNodeDisplacement')
                node_displ.name = "vector_displacement"
                node_displ.location = (727, 508)

                # Links: height texture => displacement offset (1) => displacement (Height) => material output
                links.new(node_displ_offset.inputs[1], node_height_tex.outputs['Color'])
                links.new(node_displ.inputs['Height'], node_displ_offset.outputs['Value'])
                links.new(node_out.inputs['Displacement'], node_displ.outputs['Displacement'])
            else:  # options.mat_displacement_mode == 'BUMP'
                # 2. Image Texture => Bump Node => Shader
                node_height_tex = nodes.new('ShaderNodeTexImage')
                node_height_tex.label = "Texture: Height"
                node_height_tex.name = "texture_height"
                node_height_tex.location = (-940, -429)
                node_height_tex.image = nvb_utils.create_image(texture_list[4], options.filepath, options.tex_search)
                node_height_tex.image.colorspace_settings.name = 'Non-Color'

                # Displacement offset (from mtr, 0.0 by default)
                node_displ_offset = nodes.new('ShaderNodeMath')
                node_displ_offset.label = "Displacement Offset"
                node_displ_offset.name = "math_displacement_offset"
                node_displ_offset.location = (-638, -328)
                node_displ_offset.operation = 'ADD'
                node_displ_offset.use_clamp = True
                node_displ_offset.inputs[0].default_value = 0.0
                if mtr_displacement_offset:
                    node_displ_offset.inputs[0].default_value = mtr_displacement_offset
                node_displ_offset.inputs[1].default_value = 0.0

                node_bump = nodes.new('ShaderNodeBump')
                node_bump.name = "vector_bump"
                node_bump.location = (-384, -232)

                # Links: height texture => displacement offset (1) => bump (Height) => Shader (Normal)
                links.new(node_displ_offset.inputs[1], node_height_tex.outputs['Color'])
                links.new(node_bump.inputs['Height'], node_displ_offset.outputs['Value'])
                links.new(node_shader.inputs['Normal'], node_bump.outputs['Normal'])

                # Re-link normal node to bump node (previouly linked directly to shader)
                if node_norm:
                    links.new(node_bump.inputs['Normal'], node_norm.outputs['Normal'])

        # # # # # # # # # # # # # # # # # # #
        # 5 = Emission/Self Illumination
        # Extra color node for MDL selfillum color
        node_emit_attr = nodes.new('ShaderNodeAttribute')
        node_emit_attr.label = "Mdl Selfillum"
        node_emit_attr.name = "attr_selfillum_mdl"
        node_emit_attr.location = (-1569, -115)
        node_emit_attr.attribute_type = 'OBJECT'
        node_emit_attr.attribute_name = 'nvb.selfillum'

        # Mix node: Multiplies selfillum color from MDL with diffuse color
        node_emit_mix1 = nodes.new('ShaderNodeMix')
        node_emit_mix1.label = "Mix: Self-Illumination"
        node_emit_mix1.name = "mix_selfillum_mul"
        node_emit_mix1.data_type = 'RGBA'
        node_emit_mix1.blend_type = 'MULTIPLY'
        node_emit_mix1.location = (-1358, 3)
        node_emit_mix1.clamp_result = True
        node_emit_mix1.clamp_factor = True
        node_emit_mix1.inputs[0].default_value = 1.0

        links.new(node_emit_mix1.inputs[6], node_diff_mix.outputs[2])
        links.new(node_emit_mix1.inputs[7], node_emit_attr.outputs[0])

        # Emissive/selfillum texture (only from mtr, may not be present)
        node_emit_tex = None
        input_socket_name = 'Emissive Color'
        if texture_list[5]:
            node_emit_tex = nodes.new('ShaderNodeTexImage')
            node_emit_tex.label = "Texture: Emission"
            node_emit_tex.name = "texture_emission"
            node_emit_tex.location = (-1192, -61)
            node_emit_tex.image = nvb_utils.create_image(texture_list[5], options.filepath, options.tex_search)
            node_emit_tex.image.colorspace_settings.name = 'sRGB'

            # 2nd mix node: Adds emissive texture to MDL selfillum color
            node_emit_mix2 = nodes.new('ShaderNodeMix')
            node_emit_mix2.label = "Mix: Add Self-Illumination"
            node_emit_mix2.name = "mix_selfillum_add"
            node_emit_mix2.data_type = 'RGBA'
            node_emit_mix2.blend_type = 'ADD'
            node_emit_mix2.location = (-753, 98)
            node_emit_mix2.clamp_result = True
            node_emit_mix2.clamp_factor = True
            node_emit_mix2.inputs[0].default_value = 1.0
            node_emit_mix2.inputs[6].default_value = (0.0, 0.0, 0.0, 1.0)
            node_emit_mix2.inputs[7].default_value = (0.0, 0.0, 0.0, 1.0)

            # Link 1st mix node inputs
            links.new(node_emit_mix2.inputs[6], node_emit_mix1.outputs[2])
            links.new(node_emit_mix2.inputs[7], node_emit_tex.outputs['Color'])

            # Finally link to shader
            links.new(node_shader.inputs[input_socket_name], node_emit_mix2.outputs[2])
        else:  # no emissive texture
            # link directly to shader
            links.new(node_shader.inputs[input_socket_name], node_emit_mix1.outputs[2])

    @staticmethod
    def add_node_data(material, output_name, texture_list, options):
        """Select shader nodes based on options."""
        if (options.mat_shader == 'ShaderNodeEeveeSpecular'):
            Materialnode.add_node_data_spec(material, output_name, texture_list, options)
        else:
            Materialnode.add_node_data_bsdf(material, output_name, texture_list, options)
