"""
Binary MDL decompiler for NeverWinter Nights models.

Based on the Cleanmodels 3 suite by OldMansBeard.
This module parses compiled/binary NWN MDL files and converts them
to ASCII format for importing into Blender via NeverBlender.
"""

import struct
import math


class BinaryMdlReader:
    """Reader for binary NWN MDL files."""

    # Node type codes from binary format
    NODE_TYPE_DUMMY = 1
    NODE_TYPE_LIGHT = 3
    NODE_TYPE_EMITTER = 5
    NODE_TYPE_REFERENCE = 17
    NODE_TYPE_TRIMESH = 33
    NODE_TYPE_SKIN = 97
    NODE_TYPE_ANIMMESH = 161
    NODE_TYPE_DANGLYMESH = 289
    NODE_TYPE_AABB = 545

    # Classification codes
    CLASSIFICATION_CODES = {
        1: 'EFFECT',
        2: 'TILE',
        4: 'CHARACTER',
        8: 'DOOR'
    }

    # Controller type codes
    CONTROLLER_TYPES = {
        # All nodes
        8: 'position',
        20: 'orientation',
        36: 'scale',
        # Lights
        76: ('color', 3),
        88: ('radius', 3),
        96: ('shadowradius', 3),
        100: ('verticaldisplacement', 3),
        140: ('multiplier', 3),
        # Emitters (node type 5)
        # Meshes (node type with bit 32 set)
        128: ('alpha', 'mesh'),
        # 100: selfillumcolor for meshes
    }

    def __init__(self, filepath):
        """Initialize the reader with a file path."""
        self.filepath = filepath
        self.data = b''  # Initialize as empty bytes
        self.raw_data_offset = 0
        self.raw_data_size = 0
        self.model_name = ""
        self.supermodel = ""
        self.classification = "UNKNOWN"
        self.animation_scale = 1.0
        self.ascii_lines = []
        self.node_list = []  # List of (node_number, node_name) for skin bone resolution
        # Deferred skin weight data - resolved after all nodes are read
        self.pending_skin_data = []  # List of (line_index, vertex_count, bone_part_numbers, weights_data, bone_refs_data)

    def read(self):
        """Read and parse the binary MDL file."""
        with open(self.filepath, 'rb') as f:
            self.data = f.read()

        self._read_file_header()
        self._read_model_header()

    def _read_int32(self, offset):
        """Read a signed 32-bit integer at the given offset."""
        if offset < 0 or offset + 4 > len(self.data):
            return 0
        return struct.unpack_from('<i', self.data, offset)[0]

    def _read_uint32(self, offset):
        """Read an unsigned 32-bit integer at the given offset."""
        if offset < 0 or offset + 4 > len(self.data):
            return 0
        return struct.unpack_from('<I', self.data, offset)[0]

    def _read_int16(self, offset):
        """Read a signed 16-bit integer at the given offset."""
        if offset < 0 or offset + 2 > len(self.data):
            return 0
        return struct.unpack_from('<h', self.data, offset)[0]

    def _read_uint16(self, offset):
        """Read an unsigned 16-bit integer at the given offset."""
        if offset < 0 or offset + 2 > len(self.data):
            return 0
        return struct.unpack_from('<H', self.data, offset)[0]

    def _read_byte(self, offset):
        """Read a single byte at the given offset."""
        if offset < 0 or offset >= len(self.data):
            return 0
        return self.data[offset]

    def _read_float(self, offset):
        """Read a 32-bit float at the given offset."""
        if offset < 0 or offset + 4 > len(self.data):
            return 0.0
        return struct.unpack_from('<f', self.data, offset)[0]

    def _read_string(self, offset, length):
        """Read a null-terminated string of max length at the given offset."""
        if offset < 0 or offset >= len(self.data):
            return ""
        end = min(offset + length, len(self.data))
        raw = self.data[offset:end]
        # Find null terminator
        null_pos = raw.find(b'\x00')
        if null_pos >= 0:
            raw = raw[:null_pos]
        try:
            return raw.decode('latin-1').lower()
        except:
            return ""

    def _read_ptr_array(self, offset):
        """Read a pointer array structure (ptr, count, allocated)."""
        start_ptr = self._read_int32(offset)
        num_elements = self._read_int32(offset + 4)
        # allocated = self._read_int32(offset + 8)

        if num_elements <= 0 or start_ptr == 0 or num_elements > 10000:
            return []

        ptr_list = []
        array_offset = start_ptr + 12
        for i in range(num_elements):
            ptr_list.append(self._read_int32(array_offset + i * 4))
        return ptr_list

    def _read_file_header(self):
        """Read the file header (first 12 bytes)."""
        # File header: BType(4), RawDataOffset(4), RawDataSize(4)
        self.raw_data_offset = self._read_int32(4)
        self.raw_data_size = self._read_int32(8)

    def _read_model_header(self):
        """Read the model header starting at offset 12."""
        offset = 12

        # Geometry header first
        offset, self.model_name, root_node_ptr = self._read_geometry_header(offset)

        # Model-specific data after geometry header
        # Skip 2 bytes
        offset += 2
        classification_code = self._read_byte(offset)
        offset += 1
        ignore_fog = self._read_byte(offset)
        offset += 1

        # Skip 4 bytes
        offset += 4

        # Animation header pointer array
        anim_header_ptrs = self._read_ptr_array(offset)
        offset += 12

        # Skip 4 bytes
        offset += 4

        # Bounding box
        bb_min_x = self._read_float(offset)
        bb_min_y = self._read_float(offset + 4)
        bb_min_z = self._read_float(offset + 8)
        bb_max_x = self._read_float(offset + 12)
        bb_max_y = self._read_float(offset + 16)
        bb_max_z = self._read_float(offset + 20)
        offset += 24

        model_radius = self._read_float(offset)
        offset += 4

        self.animation_scale = self._read_float(offset)
        offset += 4

        self.supermodel = self._read_string(offset, 64)
        if self.supermodel == 'null':
            self.supermodel = 'NULL'
        offset += 64

        # Set classification
        self.classification = self.CLASSIFICATION_CODES.get(classification_code, 'UNKNOWN')

        # Build ASCII output
        self.ascii_lines = []
        self.ascii_lines.append(f"newmodel {self.model_name}")
        self.ascii_lines.append(f"setsupermodel {self.model_name} {self.supermodel}")
        self.ascii_lines.append(f"classification {self.classification}")
        self.ascii_lines.append(f"setanimationscale {self.animation_scale:.2f}")

        # Begin geometry
        self.ascii_lines.append(f"beginmodelgeom {self.model_name}")

        # Read geometry nodes
        self._read_geometry_nodes(root_node_ptr, 'NULL')

        # Now resolve deferred skin weights (after all nodes are known)
        self._resolve_deferred_skin_weights()

        self.ascii_lines.append(f"endmodelgeom {self.model_name}")

        # Read animations
        for anim_ptr in anim_header_ptrs:
            if anim_ptr != 0:
                self._read_animation(anim_ptr)

        self.ascii_lines.append(f"donemodel {self.model_name}")
        self.ascii_lines.append("")

    def _read_geometry_header(self, offset):
        """Read a geometry header structure."""
        # P1, P2 (unused pointers)
        offset += 8

        # Model/Animation name (64 chars)
        name = self._read_string(offset, 64)
        offset += 64

        # Root node pointer
        root_node_ptr = self._read_int32(offset)
        offset += 4

        # NumNodes
        num_nodes = self._read_int32(offset)
        offset += 4

        # Skip 24 bytes
        offset += 24

        # RefCount
        ref_count = self._read_int32(offset)
        offset += 4

        # GeomType
        geom_type = self._read_byte(offset)
        offset += 1

        # Skip 3 bytes padding
        offset += 3

        return offset, name, root_node_ptr

    def _read_geometry_nodes(self, node_ptr, parent_name, depth=0, seen_nodes=None):
        """Recursively read geometry nodes."""
        if node_ptr == 0:
            return

        # Prevent infinite recursion
        if depth > 100:
            return
        if seen_nodes is None:
            seen_nodes = set()
        if node_ptr in seen_nodes:
            return
        seen_nodes.add(node_ptr)

        start = node_ptr + 12

        # Read node header
        node_name, node_type, node_number, inherit_color, child_ptrs, controllers = \
            self._read_node_header(start)

        # Store node for later bone resolution
        node_ref = len(self.node_list)
        self.node_list.append((node_number, node_name))

        # Get node type name
        node_type_name = self._get_node_type_name(node_type)

        # Output node header
        self.ascii_lines.append(f"node {node_type_name} {node_name}")
        self.ascii_lines.append(f"  parent {parent_name}")

        # Read node-specific data
        self._read_node_specific_data(start, node_type, node_ref)

        # Read controllers
        self._read_controllers(controllers, node_type)

        self.ascii_lines.append("endnode")

        # Process children
        for child_ptr in child_ptrs:
            self._read_geometry_nodes(child_ptr, node_name, depth + 1, seen_nodes)

    def _read_node_header(self, start):
        """Read the common node header."""
        offset = start

        # Skip F1-F6 (6 * 4 = 24 bytes)
        offset += 24

        inherit_color = self._read_int32(offset)
        offset += 4

        node_number = self._read_int32(offset)
        offset += 4

        # Node name (32 chars)
        node_name = self._read_string(offset, 32)
        offset += 32

        # Skip 8 bytes
        offset += 8

        # Child pointer array
        child_ptrs = self._read_ptr_array(offset)
        offset += 12

        # Controller key structure
        c_key_start_ptr = self._read_int32(offset)
        c_key_num_elements = self._read_int32(offset + 4)
        offset += 12  # ptr, num, allocated

        # Controller data structure
        c_data_start_ptr = self._read_int32(offset)
        c_data_num_elements = self._read_int32(offset + 4)
        offset += 12  # ptr, num, allocated

        node_type = self._read_int32(offset)
        offset += 4

        controllers = (c_key_start_ptr, c_key_num_elements, c_data_start_ptr, c_data_num_elements)

        return node_name, node_type, node_number, inherit_color, child_ptrs, controllers

    def _get_node_type_name(self, node_type):
        """Convert binary node type code to name."""
        type_map = {
            self.NODE_TYPE_DUMMY: 'dummy',
            self.NODE_TYPE_LIGHT: 'light',
            self.NODE_TYPE_EMITTER: 'emitter',
            self.NODE_TYPE_REFERENCE: 'reference',
            self.NODE_TYPE_TRIMESH: 'trimesh',
            self.NODE_TYPE_SKIN: 'skin',
            self.NODE_TYPE_ANIMMESH: 'animmesh',
            self.NODE_TYPE_DANGLYMESH: 'danglymesh',
            self.NODE_TYPE_AABB: 'aabb'
        }
        return type_map.get(node_type, 'dummy')

    def _read_node_specific_data(self, header_start, node_type, node_ref):
        """Read node type-specific data."""
        # Data starts after the common header
        # Header is 112 bytes: 24 (F1-F6) + 4 + 4 + 32 (name) + 8 (skip) + 12 (child ptr array)
        #                      + 12 (c_key) + 12 (c_data) + 4 (type) = 112 bytes
        data_offset = header_start + 112

        if node_type == self.NODE_TYPE_DUMMY:
            # Dummy has no extra data
            pass
        elif node_type == self.NODE_TYPE_LIGHT:
            self._read_light_data(data_offset)
        elif node_type == self.NODE_TYPE_EMITTER:
            self._read_emitter_data(data_offset)
        elif node_type == self.NODE_TYPE_REFERENCE:
            self._read_reference_data(data_offset)
        elif node_type == self.NODE_TYPE_TRIMESH:
            self._read_mesh_data(data_offset)
        elif node_type == self.NODE_TYPE_SKIN:
            self._read_skin_data(data_offset, node_ref)
        elif node_type == self.NODE_TYPE_ANIMMESH:
            self._read_mesh_data(data_offset)
        elif node_type == self.NODE_TYPE_DANGLYMESH:
            self._read_danglymesh_data(data_offset)
        elif node_type == self.NODE_TYPE_AABB:
            self._read_mesh_data(data_offset)

    def _read_light_data(self, offset):
        """Read light-specific data."""
        flare_radius = self._read_float(offset)
        offset += 4

        # Skip 12 bytes
        offset += 12

        # Flare sizes array
        flare_sizes_ptr = self._read_int32(offset)
        num_flare_sizes = self._read_int32(offset + 4)
        offset += 12

        # Flare positions array
        flare_positions_ptr = self._read_int32(offset)
        num_flare_positions = self._read_int32(offset + 4)
        offset += 12

        # Flare color shifts array
        flare_color_shifts_ptr = self._read_int32(offset)
        num_flare_color_shifts = self._read_int32(offset + 4)
        offset += 12

        # Flare texture names pointer array
        flare_tex_names_ptrs = self._read_ptr_array(offset)
        offset += 12

        light_priority = self._read_int32(offset)
        offset += 4
        ambient_only = self._read_int32(offset)
        offset += 4
        dynamic_type = self._read_int32(offset)
        offset += 4
        affect_dynamic = self._read_int32(offset)
        offset += 4
        shadow = self._read_int32(offset)
        offset += 4
        generate_flare = self._read_int32(offset)
        offset += 4
        fading_light = self._read_int32(offset)
        offset += 4

        self.ascii_lines.append(f"  flareradius {flare_radius:.5f}")
        self.ascii_lines.append(f"  lightpriority {light_priority}")
        self.ascii_lines.append(f"  ambientonly {ambient_only}")
        self.ascii_lines.append(f"  ndynamictype {dynamic_type}")
        self.ascii_lines.append(f"  affectdynamic {affect_dynamic}")
        self.ascii_lines.append(f"  shadow {shadow}")
        self.ascii_lines.append(f"  generateflare {generate_flare}")
        self.ascii_lines.append(f"  fadinglight {fading_light}")

        # Read flare arrays if present
        if num_flare_sizes > 0 and flare_sizes_ptr != 0:
            self._read_float_array("flaresizes", flare_sizes_ptr, num_flare_sizes, 1)
        if num_flare_positions > 0 and flare_positions_ptr != 0:
            self._read_float_array("flarepositions", flare_positions_ptr, num_flare_positions, 1)
        if num_flare_color_shifts > 0 and flare_color_shifts_ptr != 0:
            self._read_float_array("flarecolorshifts", flare_color_shifts_ptr, num_flare_color_shifts, 3)
        if flare_tex_names_ptrs:
            self.ascii_lines.append(f"  texturenames {len(flare_tex_names_ptrs)}")
            for ptr in flare_tex_names_ptrs:
                tex_name = self._read_string(ptr + 12, 64)
                self.ascii_lines.append(f"    {tex_name}")

    def _read_float_array(self, name, ptr, count, values_per_entry):
        """Read an array of floats."""
        self.ascii_lines.append(f"  {name} {count}")
        array_offset = ptr + 12
        for i in range(count):
            values = []
            for j in range(values_per_entry):
                val = self._read_float(array_offset + (i * values_per_entry + j) * 4)
                values.append(f"{val:.5f}")
            self.ascii_lines.append("    " + " ".join(values))

    def _read_emitter_data(self, offset):
        """Read emitter-specific data."""
        deadspace = self._read_float(offset)
        self.ascii_lines.append(f"  deadspace {deadspace:.5f}")
        offset += 4

        blast_radius = self._read_float(offset)
        self.ascii_lines.append(f"  blastradius {blast_radius:.5f}")
        offset += 4

        blast_length = self._read_float(offset)
        self.ascii_lines.append(f"  blastlength {blast_length:.5f}")
        offset += 4

        x_grid = self._read_int32(offset)
        self.ascii_lines.append(f"  xgrid {x_grid}")
        offset += 4

        y_grid = self._read_int32(offset)
        self.ascii_lines.append(f"  ygrid {y_grid}")
        offset += 4

        spawn_type = self._read_int32(offset)
        self.ascii_lines.append(f"  spawntype {spawn_type}")
        offset += 4

        update = self._read_string(offset, 32)
        self.ascii_lines.append(f"  update {update}")
        offset += 32

        render = self._read_string(offset, 32)
        self.ascii_lines.append(f"  render {render}")
        offset += 32

        blend = self._read_string(offset, 32)
        self.ascii_lines.append(f"  blend {blend}")
        offset += 32

        texture = self._read_string(offset, 64)
        self.ascii_lines.append(f"  texture {texture}")
        offset += 64

        chunk_name = self._read_string(offset, 16)
        if chunk_name:
            self.ascii_lines.append(f"  chunkname {chunk_name}")
        offset += 16

        two_sided_tex = self._read_int32(offset)
        self.ascii_lines.append(f"  twosidedtex {two_sided_tex}")
        offset += 4

        loop = self._read_int32(offset)
        self.ascii_lines.append(f"  loop {loop}")
        offset += 4

        render_order = self._read_int16(offset)
        self.ascii_lines.append(f"  renderorder {render_order}")
        offset += 2

        # Skip 2 bytes padding
        offset += 2

        emitter_flags = self._read_int32(offset)
        p2p = emitter_flags & 1
        p2p_sel = (emitter_flags & 2) >> 1
        affected_by_wind = (emitter_flags & 4) >> 2
        m_is_tinted = (emitter_flags & 8) >> 3
        bounce = (emitter_flags & 16) >> 4
        random = (emitter_flags & 32) >> 5
        inherit = (emitter_flags & 64) >> 6
        inherit_vel = (emitter_flags & 128) >> 7
        inherit_local = (emitter_flags & 256) >> 8
        splat = (emitter_flags & 512) >> 9
        inherit_part = (emitter_flags & 1024) >> 10

        self.ascii_lines.append(f"  p2p {p2p}")
        self.ascii_lines.append(f"  p2p_sel {p2p_sel}")
        self.ascii_lines.append(f"  affectedbywind {affected_by_wind}")
        self.ascii_lines.append(f"  m_istinted {m_is_tinted}")
        self.ascii_lines.append(f"  bounce {bounce}")
        self.ascii_lines.append(f"  random {random}")
        self.ascii_lines.append(f"  inherit {inherit}")
        self.ascii_lines.append(f"  inheritvel {inherit_vel}")
        self.ascii_lines.append(f"  inherit_local {inherit_local}")
        self.ascii_lines.append(f"  splat {splat}")
        self.ascii_lines.append(f"  inherit_part {inherit_part}")

    def _read_reference_data(self, offset):
        """Read reference node data."""
        ref_model = self._read_string(offset, 64)
        self.ascii_lines.append(f"  refmodel {ref_model}")
        offset += 64

        reattachable = self._read_int32(offset)
        self.ascii_lines.append(f"  reattachable {reattachable}")

    def _read_mesh_data(self, offset):
        """Read common mesh data (trimesh, aabb, animmesh)."""
        # Skip 8 bytes
        offset += 8

        face_array_ptr = self._read_int32(offset)
        n_faces = self._read_int32(offset + 4)
        offset += 8

        # Skip 44 bytes
        offset += 44

        diffuse_r = self._read_float(offset)
        diffuse_g = self._read_float(offset + 4)
        diffuse_b = self._read_float(offset + 8)
        offset += 12

        ambient_r = self._read_float(offset)
        ambient_g = self._read_float(offset + 4)
        ambient_b = self._read_float(offset + 8)
        offset += 12

        specular_r = self._read_float(offset)
        specular_g = self._read_float(offset + 4)
        specular_b = self._read_float(offset + 8)
        offset += 12

        shininess = self._read_float(offset)
        offset += 4

        shadow = self._read_int32(offset)
        offset += 4

        beaming = self._read_int32(offset)
        offset += 4

        render = self._read_int32(offset)
        offset += 4

        transparency_hint = self._read_int32(offset)
        offset += 4

        render_hint = self._read_int32(offset)
        offset += 4

        bitmap = self._read_string(offset, 64)
        offset += 64

        texture1 = self._read_string(offset, 64)
        offset += 64

        texture2 = self._read_string(offset, 64)
        offset += 64

        material_name = self._read_string(offset, 64)
        offset += 64

        tilefade = self._read_int32(offset)
        offset += 4

        # Skip 24 bytes
        offset += 24

        # Vertex index count array
        vert_ind_cnt_ptr = self._read_int32(offset)
        num_vert_ind_cnt = self._read_int32(offset + 4)
        offset += 12

        # Vertex index offset array
        vert_ind_off_ptr = self._read_int32(offset)
        num_vert_ind_off = self._read_int32(offset + 4)
        offset += 12

        # Skip 16 bytes
        offset += 16

        vertex_raw_data_ptr = self._read_int32(offset)
        offset += 4

        vertex_count = self._read_int16(offset)
        offset += 2

        texture_count = self._read_int16(offset)
        offset += 2

        tverts0_raw_data_ptr = self._read_int32(offset)
        offset += 4
        tverts1_raw_data_ptr = self._read_int32(offset)
        offset += 4
        tverts2_raw_data_ptr = self._read_int32(offset)
        offset += 4
        tverts3_raw_data_ptr = self._read_int32(offset)
        offset += 4

        vertex_normals_ptr = self._read_int32(offset)
        offset += 4

        vertex_colors_ptr = self._read_int32(offset)
        offset += 4

        # Skip 12 bytes
        offset += 12

        vertex_tangents_ptr = self._read_int32(offset)
        offset += 4

        # Skip 4 bytes
        offset += 4

        vertex_bitangents_ptr = self._read_int32(offset)
        offset += 4

        lightmapped = self._read_byte(offset)
        offset += 1

        rotate_texture = self._read_byte(offset)
        offset += 1

        # Skip 10 bytes padding (end of mesh structure)
        offset += 10

        # Output mesh properties
        self.ascii_lines.append(f"  diffuse {diffuse_r:.5f} {diffuse_g:.5f} {diffuse_b:.5f}")
        self.ascii_lines.append(f"  ambient {ambient_r:.5f} {ambient_g:.5f} {ambient_b:.5f}")
        self.ascii_lines.append(f"  specular {specular_r:.5f} {specular_g:.5f} {specular_b:.5f}")
        self.ascii_lines.append(f"  shininess {int(shininess)}")
        self.ascii_lines.append(f"  shadow {shadow}")
        self.ascii_lines.append(f"  beaming {beaming}")
        self.ascii_lines.append(f"  render {render}")
        self.ascii_lines.append(f"  transparencyhint {transparency_hint}")

        if render_hint == 2:
            self.ascii_lines.append("  renderhint NormalAndSpecMapped")

        if bitmap:
            self.ascii_lines.append(f"  bitmap {bitmap}")
        if texture1:
            self.ascii_lines.append(f"  texture1 {texture1}")
        if texture2:
            self.ascii_lines.append(f"  texture2 {texture2}")
        if material_name:
            self.ascii_lines.append(f"  materialname {material_name}")
        if tilefade != 0:
            self.ascii_lines.append(f"  tilefade {tilefade}")
        if lightmapped != 0:
            self.ascii_lines.append(f"  lightmapped {lightmapped}")
        self.ascii_lines.append(f"  rotatetexture {rotate_texture}")

        # Sanity check vertex/face counts
        if vertex_count < 0 or vertex_count > 100000:
            vertex_count = 0
        if n_faces < 0 or n_faces > 100000:
            n_faces = 0

        # Read vertex data from raw data section
        if vertex_count > 0 and vertex_raw_data_ptr != -1:
            self._read_vertices(vertex_raw_data_ptr, vertex_count)

        # Read tverts
        if vertex_count > 0 and tverts0_raw_data_ptr != -1:
            self._read_tverts(tverts0_raw_data_ptr, vertex_count, "tverts")
        if texture_count > 1 and tverts1_raw_data_ptr != -1:
            self._read_tverts(tverts1_raw_data_ptr, vertex_count, "tverts1")
        if texture_count > 2 and tverts2_raw_data_ptr != -1:
            self._read_tverts(tverts2_raw_data_ptr, vertex_count, "tverts2")
        if texture_count > 3 and tverts3_raw_data_ptr != -1:
            self._read_tverts(tverts3_raw_data_ptr, vertex_count, "tverts3")

        # Read normals - re-enabled now that header offset is fixed
        if vertex_count > 0 and vertex_normals_ptr != -1:
            self._read_normals(vertex_normals_ptr, vertex_count)

        # Read vertex colors
        if vertex_count > 0 and vertex_colors_ptr != -1:
            self._read_colors(vertex_colors_ptr, vertex_count)

        # Read tangents
        bitangents = []
        if vertex_count > 0 and vertex_bitangents_ptr != -1:
            bitangents = self._read_bitangents(vertex_bitangents_ptr, vertex_count)
        if vertex_count > 0 and vertex_tangents_ptr != -1 and bitangents:
            self._read_tangents(vertex_tangents_ptr, bitangents, vertex_count)

        # Read faces
        if n_faces > 0 and face_array_ptr != 0:
            self._read_faces(face_array_ptr, n_faces)

        return offset, vertex_count

    def _read_skin_data(self, offset, node_ref):
        """Read skin mesh data."""
        # First read common mesh data
        mesh_end_offset, vertex_count = self._read_mesh_data(offset)

        # Skin-specific data comes immediately after common mesh structure
        # mesh_end_offset points to after the mesh data (including 10-byte padding)
        skin_offset = mesh_end_offset

        # Skip 12 bytes
        skin_offset += 12

        skin_weights_raw_ptr = self._read_int32(skin_offset)
        skin_offset += 4

        skin_bone_ref_raw_ptr = self._read_int32(skin_offset)
        skin_offset += 4

        # Skip 44 bytes
        skin_offset += 44

        # Read bone part numbers (64 entries, 2 bytes each)
        # These map bone indices (0-63) to NODE TRAVERSAL INDICES
        # The values are indices into self.node_list (the order nodes were read)
        # NOT node numbers! This matches cleanmodels' nth_node mechanism.
        bone_part_numbers = []
        for i in range(64):
            part = self._read_int16(skin_offset + i * 2)
            bone_part_numbers.append(part)
        skin_offset += 128

        # DEFER weight resolution until all nodes are read
        # (some bones might be later in the tree traversal)
        if vertex_count > 0 and skin_weights_raw_ptr != -1 and skin_bone_ref_raw_ptr != -1:
            weights_start = self.raw_data_offset + 12 + skin_weights_raw_ptr
            bone_refs_start = self.raw_data_offset + 12 + skin_bone_ref_raw_ptr

            # Read all weight and bone ref data now
            weights_data = []
            bone_refs_data = []
            for v in range(vertex_count):
                w1 = self._read_float(weights_start + v * 16)
                w2 = self._read_float(weights_start + v * 16 + 4)
                w3 = self._read_float(weights_start + v * 16 + 8)
                w4 = self._read_float(weights_start + v * 16 + 12)
                weights_data.append((w1, w2, w3, w4))

                b1 = self._read_int16(bone_refs_start + v * 8)
                b2 = self._read_int16(bone_refs_start + v * 8 + 2)
                b3 = self._read_int16(bone_refs_start + v * 8 + 4)
                b4 = self._read_int16(bone_refs_start + v * 8 + 6)
                bone_refs_data.append((b1, b2, b3, b4))

            # Store placeholder and data for later resolution
            placeholder_index = len(self.ascii_lines)
            self.ascii_lines.append(f"  weights {vertex_count}")  # Header
            # Add placeholders for each vertex weight line
            for v in range(vertex_count):
                self.ascii_lines.append("    ")  # Placeholder

            # Store data for deferred resolution
            self.pending_skin_data.append((
                placeholder_index,
                vertex_count,
                bone_part_numbers,
                weights_data,
                bone_refs_data
            ))


    def _resolve_deferred_skin_weights(self):
        """Resolve skin weights after all nodes have been read.
        
        This is necessary because bone nodes might appear after skin nodes
        in the tree traversal, so we can't resolve bone names until all
        nodes are in self.node_list. Matches cleanmodels' deferred approach.
        """
        for (placeholder_index, vertex_count, bone_part_numbers, 
             weights_data, bone_refs_data) in self.pending_skin_data:
            # Now node_list is complete, we can resolve bone names
            for v in range(vertex_count):
                w1, w2, w3, w4 = weights_data[v]
                b1, b2, b3, b4 = bone_refs_data[v]

                weight_pairs = []
                for weight, bone_ref in [(w1, b1), (w2, b2), (w3, b3), (w4, b4)]:
                    if weight > 0 and 0 <= bone_ref < 64:
                        # bone_part_numbers[bone_ref] gives a TRAVERSAL INDEX
                        node_index = bone_part_numbers[bone_ref]
                        # Look up the bone name by traversal index
                        if 0 <= node_index < len(self.node_list):
                            _, bone_name = self.node_list[node_index]
                            weight_pairs.append(f"{bone_name} {weight:.5f}")

                # Update the placeholder line (offset by 1 to skip the header)
                line_index = placeholder_index + 1 + v
                if weight_pairs:
                    self.ascii_lines[line_index] = "    " + " ".join(weight_pairs)
                # else leave the empty placeholder

    def _read_danglymesh_data(self, offset):
        """Read dangly mesh data."""
        # First read common mesh data
        mesh_end_offset, vertex_count = self._read_mesh_data(offset)

        # Danglymesh-specific data comes immediately after common mesh structure
        # mesh_end_offset points to after the mesh data (including 10-byte padding)
        dangly_offset = mesh_end_offset

        constraint_ptr = self._read_int32(dangly_offset)
        num_constraints = self._read_int32(dangly_offset + 4)
        dangly_offset += 12

        displacement = self._read_float(dangly_offset)
        dangly_offset += 4
        tightness = self._read_float(dangly_offset)
        dangly_offset += 4
        period = self._read_float(dangly_offset)
        dangly_offset += 4

        self.ascii_lines.append(f"  displacement {displacement:.5f}")
        self.ascii_lines.append(f"  tightness {tightness:.5f}")
        self.ascii_lines.append(f"  period {period:.5f}")

        # Read constraints
        if num_constraints > 0 and constraint_ptr != 0:
            self.ascii_lines.append(f"  constraints {num_constraints}")
            array_offset = constraint_ptr + 12
            for i in range(num_constraints):
                val = self._read_float(array_offset + i * 4)
                self.ascii_lines.append(f"    {val:.1f}")

    def _read_vertices(self, raw_ptr, count):
        """Read vertex coordinates from raw data section."""
        self.ascii_lines.append(f"  verts {count}")
        start = self.raw_data_offset + 12 + raw_ptr
        for i in range(count):
            x = self._read_float(start + i * 12)
            y = self._read_float(start + i * 12 + 4)
            z = self._read_float(start + i * 12 + 8)
            self.ascii_lines.append(f"    {x:.5f} {y:.5f} {z:.5f}")

    def _read_tverts(self, raw_ptr, count, name):
        """Read texture coordinates from raw data section."""
        self.ascii_lines.append(f"  {name} {count}")
        start = self.raw_data_offset + 12 + raw_ptr
        for i in range(count):
            u = self._read_float(start + i * 8)
            v = self._read_float(start + i * 8 + 4)
            self.ascii_lines.append(f"    {u:.5f} {v:.5f} 0")

    def _read_normals(self, raw_ptr, count):
        """Read vertex normals from raw data section."""
        self.ascii_lines.append(f"  normals {count}")
        start = self.raw_data_offset + 12 + raw_ptr
        for i in range(count):
            x = self._read_float(start + i * 12)
            y = self._read_float(start + i * 12 + 4)
            z = self._read_float(start + i * 12 + 8)
            self.ascii_lines.append(f"    {x:.5f} {y:.5f} {z:.5f}")

    def _read_colors(self, raw_ptr, count):
        """Read vertex colors from raw data section."""
        self.ascii_lines.append(f"  colors {count}")
        start = self.raw_data_offset + 12 + raw_ptr
        for i in range(count):
            r = self._read_byte(start + i * 4)
            g = self._read_byte(start + i * 4 + 1)
            b = self._read_byte(start + i * 4 + 2)
            # Output as 0-255 integers (NeverBlender will convert)
            self.ascii_lines.append(f"    {r} {g} {b}")

    def _read_bitangents(self, raw_ptr, count):
        """Read bitangent signs from raw data section."""
        bitangents = []
        start = self.raw_data_offset + 12 + raw_ptr
        for i in range(count):
            val = self._read_float(start + i * 4)
            bitangents.append(val)
        return bitangents

    def _read_tangents(self, raw_ptr, bitangents, count):
        """Read tangent vectors from raw data section."""
        self.ascii_lines.append(f"  tangents {count}")
        start = self.raw_data_offset + 12 + raw_ptr
        for i in range(count):
            x = self._read_float(start + i * 12)
            y = self._read_float(start + i * 12 + 4)
            z = self._read_float(start + i * 12 + 8)
            bt = bitangents[i] if i < len(bitangents) else 1.0
            self.ascii_lines.append(f"    {x:.5f} {y:.5f} {z:.5f} {bt:.1f}")

    def _read_faces(self, face_ptr, count):
        """Read face data."""
        self.ascii_lines.append(f"  faces {count}")
        start = face_ptr + 12

        for i in range(count):
            face_offset = start + i * 32

            # Face normal (unused but part of structure)
            # nx = self._read_float(face_offset)
            # ny = self._read_float(face_offset + 4)
            # nz = self._read_float(face_offset + 8)
            # d = self._read_float(face_offset + 12)

            surface_id = self._read_int32(face_offset + 16)

            # Adjacent faces (unused in ASCII)
            # adj1 = self._read_int16(face_offset + 20)
            # adj2 = self._read_int16(face_offset + 22)
            # adj3 = self._read_int16(face_offset + 24)

            v1 = self._read_int16(face_offset + 26)
            v2 = self._read_int16(face_offset + 28)
            v3 = self._read_int16(face_offset + 30)

            # Face format: v1 v2 v3 smoothgroup tv1 tv2 tv3 material
            # In binary, tverts indices are same as vertex indices
            # Use smoothgroup 1 (not 0) so the importer uses per-vertex normals
            # for smooth shading. Smoothgroup 0 means "non-smooth" which marks
            # all edges as sharp.
            self.ascii_lines.append(f"    {v1} {v2} {v3} 1 {v1} {v2} {v3} {surface_id}")

    def _read_controllers(self, controllers, node_type):
        """Read controller data."""
        c_key_start_ptr, c_key_num_elements, c_data_start_ptr, c_data_num_elements = controllers

        if c_key_num_elements <= 0 or c_key_start_ptr == 0 or c_data_start_ptr == 0:
            return

        for i in range(c_key_num_elements):
            key_offset = c_key_start_ptr + 12 + i * 12

            controller_type = self._read_int32(key_offset)
            num_rows = self._read_int16(key_offset + 4)
            first_time_key_idx = self._read_int16(key_offset + 6)
            first_data_value_idx = self._read_int16(key_offset + 8)
            num_cols = self._read_byte(key_offset + 10)

            if num_rows <= 0:
                continue

            bezier = num_cols & 16
            true_num_cols = num_cols & 15

            # Get controller name and handle it
            self._read_controller_data(
                controller_type, node_type, num_rows,
                first_time_key_idx, first_data_value_idx,
                true_num_cols, c_data_start_ptr, bezier
            )

    def _get_controller_name(self, controller_type, node_type):
        """Get the parameter name for a controller type."""
        # Common controllers for all nodes
        if controller_type == 8:
            return 'position', 3
        elif controller_type == 20:
            return 'orientation', 4
        elif controller_type == 36:
            return 'scale', 1

        # Light-specific controllers
        if node_type == self.NODE_TYPE_LIGHT:
            if controller_type == 76:
                return 'color', 3
            elif controller_type == 88:
                return 'radius', 1
            elif controller_type == 96:
                return 'shadowradius', 1
            elif controller_type == 100:
                return 'verticaldisplacement', 1
            elif controller_type == 140:
                return 'multiplier', 1

        # Mesh-specific controllers
        if node_type & 32:  # Has mesh bit
            if controller_type == 100:
                return 'selfillumcolor', 3
            elif controller_type == 128:
                return 'alpha', 1

        # Emitter controllers would go here...

        return None, 0

    def _read_controller_data(self, controller_type, node_type, num_rows,
                              first_time_idx, first_data_idx, num_cols,
                              c_data_start_ptr, bezier):
        """Read and output controller data."""
        ctrl_name, expected_cols = self._get_controller_name(controller_type, node_type)

        if ctrl_name is None:
            return

        # For single-row controllers at time 0, output as static parameter
        if num_rows == 1:
            time_offset = c_data_start_ptr + 12 + first_time_idx * 4
            time_val = self._read_float(time_offset)

            if abs(time_val) < 0.0001:
                data_offset = c_data_start_ptr + 12 + first_data_idx * 4
                if num_cols == 4 and ctrl_name == 'orientation':
                    # Quaternion to axis-angle conversion
                    q1 = self._read_float(data_offset)
                    q2 = self._read_float(data_offset + 4)
                    q3 = self._read_float(data_offset + 8)
                    q4 = self._read_float(data_offset + 12)
                    axis, angle = self._quaternion_to_axis_angle(q1, q2, q3, q4)
                    self.ascii_lines.append(f"  {ctrl_name} {axis[0]:.5f} {axis[1]:.5f} {axis[2]:.5f} {angle:.5f}")
                elif expected_cols == 3:
                    v1 = self._read_float(data_offset)
                    v2 = self._read_float(data_offset + 4)
                    v3 = self._read_float(data_offset + 8)
                    self.ascii_lines.append(f"  {ctrl_name} {v1:.5f} {v2:.5f} {v3:.5f}")
                elif expected_cols == 1:
                    v1 = self._read_float(data_offset)
                    self.ascii_lines.append(f"  {ctrl_name} {v1:.5f}")
                return

        # Multiple rows - output as keyframes
        key_suffix = 'bezierkey' if bezier else 'key'
        key_name = f"{ctrl_name}{key_suffix}"

        self.ascii_lines.append(f"  {key_name} {num_rows}")

        time_offset = c_data_start_ptr + 12 + first_time_idx * 4
        data_offset = c_data_start_ptr + 12 + first_data_idx * 4

        for row in range(num_rows):
            time_val = self._read_float(time_offset + row * 4)

            if num_cols == 4 and ctrl_name == 'orientation':
                q1 = self._read_float(data_offset)
                q2 = self._read_float(data_offset + 4)
                q3 = self._read_float(data_offset + 8)
                q4 = self._read_float(data_offset + 12)
                axis, angle = self._quaternion_to_axis_angle(q1, q2, q3, q4)
                self.ascii_lines.append(f"    {time_val:.5f} {axis[0]:.5f} {axis[1]:.5f} {axis[2]:.5f} {angle:.5f}")
                data_offset += 16
            elif expected_cols == 3 or num_cols == 3:
                v1 = self._read_float(data_offset)
                v2 = self._read_float(data_offset + 4)
                v3 = self._read_float(data_offset + 8)
                self.ascii_lines.append(f"    {time_val:.5f} {v1:.5f} {v2:.5f} {v3:.5f}")
                data_offset += 12
            else:  # 1 column
                v1 = self._read_float(data_offset)
                self.ascii_lines.append(f"    {time_val:.5f} {v1:.5f}")
                data_offset += 4

    def _quaternion_to_axis_angle(self, q1, q2, q3, q4):
        """Convert quaternion (x, y, z, w) to axis-angle representation."""
        # q4 is w (scalar), q1-q3 are x,y,z (vector)
        if abs(q4) > 0.9999:
            # Near identity - no rotation
            return (0.0, 0.0, 0.0), 0.0

        r1 = q1*q1 + q2*q2 + q3*q3
        if r1 == 0:
            return (0.0, 0.0, 0.0), 0.0

        r2 = r1 + q4*q4
        if r2 == 0:
            return (0.0, 0.0, 0.0), 0.0

        angle = 2 * math.acos(q4 / math.sqrt(r2))
        f = math.sqrt(r1)
        axis = (q1/f, q2/f, q3/f)

        return axis, angle

    def _read_animation(self, anim_ptr):
        """Read an animation."""
        start = anim_ptr + 12

        # Read geometry header for animation
        offset = start
        # Skip P1, P2
        offset += 8

        anim_name = self._read_string(offset, 64)
        offset += 64

        root_node_ptr = self._read_int32(offset)
        offset += 4

        # Skip num_nodes
        offset += 4
        # Skip 24 bytes
        offset += 24
        # Skip ref_count
        offset += 4
        # Skip geom_type
        offset += 4

        # Animation-specific data
        anim_length = self._read_float(offset)
        offset += 4

        trans_time = self._read_float(offset)
        offset += 4

        anim_root = self._read_string(offset, 64)
        offset += 64

        event_ptr = self._read_int32(offset)
        offset += 4

        num_events = self._read_int32(offset)
        offset += 4

        # Output animation header
        self.ascii_lines.append(f"newanim {anim_name} {self.model_name}")
        self.ascii_lines.append(f"  length {anim_length:.5f}")
        self.ascii_lines.append(f"  transtime {trans_time:.5f}")
        self.ascii_lines.append(f"  animroot {anim_root}")

        # Read events
        if num_events > 0 and event_ptr != 0:
            event_start = event_ptr + 12
            for i in range(num_events):
                event_offset = event_start + i * 36
                event_time = self._read_float(event_offset)
                event_name = self._read_string(event_offset + 4, 32)
                self.ascii_lines.append(f"  event {event_time:.5f} {event_name}")

        # Read animation nodes
        if root_node_ptr != 0:
            self._read_animation_nodes(root_node_ptr, anim_name)

        self.ascii_lines.append(f"doneanim {anim_name} {self.model_name}")
        self.ascii_lines.append("")

    def _read_animation_nodes(self, node_ptr, anim_name, parent_name='NULL', depth=0, seen_nodes=None):
        """Recursively read animation nodes."""
        if node_ptr == 0:
            return

        # Prevent infinite recursion
        if depth > 100:
            return
        if seen_nodes is None:
            seen_nodes = set()
        if node_ptr in seen_nodes:
            return
        seen_nodes.add(node_ptr)

        start = node_ptr + 12

        # Read node header (same structure as geometry nodes)
        node_name, node_type, node_number, inherit_color, child_ptrs, controllers = \
            self._read_node_header(start)

        # Get node type name
        node_type_name = self._get_node_type_name(node_type)

        # Output animation node
        self.ascii_lines.append(f"  node {node_type_name} {node_name}")
        self.ascii_lines.append(f"    parent {parent_name}")

        # Read animation controllers (keyframes)
        self._read_animation_controllers(controllers, node_type)

        self.ascii_lines.append("  endnode")

        # Process children
        for child_ptr in child_ptrs:
            self._read_animation_nodes(child_ptr, anim_name, node_name, depth + 1, seen_nodes)

    def _read_animation_controllers(self, controllers, node_type):
        """Read animation controller keyframes."""
        c_key_start_ptr, c_key_num_elements, c_data_start_ptr, c_data_num_elements = controllers

        if c_key_num_elements <= 0 or c_key_start_ptr == 0 or c_data_start_ptr == 0:
            return

        for i in range(c_key_num_elements):
            key_offset = c_key_start_ptr + 12 + i * 12

            controller_type = self._read_int32(key_offset)
            num_rows = self._read_int16(key_offset + 4)
            first_time_key_idx = self._read_int16(key_offset + 6)
            first_data_value_idx = self._read_int16(key_offset + 8)
            num_cols = self._read_byte(key_offset + 10)

            if num_rows <= 0:
                continue

            bezier = num_cols & 16
            true_num_cols = num_cols & 15

            # Get controller name
            ctrl_name, expected_cols = self._get_controller_name(controller_type, node_type)
            if ctrl_name is None:
                continue

            key_suffix = 'bezierkey' if bezier else 'key'
            key_name = f"{ctrl_name}{key_suffix}"

            self.ascii_lines.append(f"    {key_name} {num_rows}")

            time_offset = c_data_start_ptr + 12 + first_time_key_idx * 4
            data_offset = c_data_start_ptr + 12 + first_data_value_idx * 4

            for row in range(num_rows):
                time_val = self._read_float(time_offset + row * 4)

                if true_num_cols == 4 and ctrl_name == 'orientation':
                    q1 = self._read_float(data_offset)
                    q2 = self._read_float(data_offset + 4)
                    q3 = self._read_float(data_offset + 8)
                    q4 = self._read_float(data_offset + 12)
                    axis, angle = self._quaternion_to_axis_angle(q1, q2, q3, q4)
                    self.ascii_lines.append(f"      {time_val:.5f} {axis[0]:.5f} {axis[1]:.5f} {axis[2]:.5f} {angle:.5f}")
                    data_offset += 16
                elif expected_cols == 3 or true_num_cols == 3:
                    v1 = self._read_float(data_offset)
                    v2 = self._read_float(data_offset + 4)
                    v3 = self._read_float(data_offset + 8)
                    self.ascii_lines.append(f"      {time_val:.5f} {v1:.5f} {v2:.5f} {v3:.5f}")
                    data_offset += 12
                else:
                    v1 = self._read_float(data_offset)
                    self.ascii_lines.append(f"      {time_val:.5f} {v1:.5f}")
                    data_offset += 4

    def get_ascii(self):
        """Return the decompiled ASCII MDL content."""
        return '\n'.join(self.ascii_lines)


def decompile(filepath):
    """Decompile a binary MDL file and return ASCII content."""
    try:
        reader = BinaryMdlReader(filepath)
        reader.read()
        return reader.get_ascii()
    except Exception as e:
        import traceback
        print(f"NeverBlender: Decompile error: {e}")
        traceback.print_exc()
        return None


def is_binary_mdl(filepath):
    """Check if a file is a binary MDL."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
            return header == b'\x00\x00\x00\x00'
    except:
        return False
