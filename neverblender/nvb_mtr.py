"""TODO: DOC."""

import glob
import os
import struct

from . import nvb_utils
from . import nvb_def
from . import nvb_parse
from .nvb_materialnode import Materialnode


# The renderhint a new material starts with (NVB_PG_material_mtr)
DEFAULT_RENDERHINT = "NormalAndSpecMapped"

# Resource types whose names a stock texture or material goes by
_STOCK_TYPES = {3, 6, 2033, 2072}  # tga, plt, dds, mtr
_stock_names = dict()  # game install -> set of lower-case resrefs


def _key_names(path, names):
    """Add the texture and material resrefs a KEY V1 file lists."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 64 or data[0:8] != b"KEY V1  ":
        return
    key_count, key_off = struct.unpack_from("<I", data, 12)[0], struct.unpack_from("<I", data, 20)[0]
    for i in range(key_count):
        o = key_off + i * 22
        if o + 22 > len(data):
            break
        if struct.unpack_from("<H", data, o + 16)[0] in _STOCK_TYPES:
            names.add(data[o:o + 16].rstrip(b"\0").decode("latin-1").lower())


def _erf_names(path, names):
    """Add the texture and material resrefs an ERF (texture pack) holds."""
    with open(path, "rb") as f:
        hdr = f.read(160)
        if len(hdr) < 160 or hdr[0:4] not in (b"ERF ", b"HAK ", b"MOD "):
            return
        count = struct.unpack_from("<I", hdr, 16)[0]
        key_off = struct.unpack_from("<I", hdr, 24)[0]
        f.seek(key_off)
        keys = f.read(count * 24)
    for i in range(len(keys) // 24):
        k = keys[i * 24:i * 24 + 24]
        if struct.unpack_from("<H", k, 20)[0] in _STOCK_TYPES:
            names.add(k[:16].rstrip(b"\0").decode("latin-1").lower())


def stock_texture_names(game_dir=""):
    """Names of the game's own textures and materials, or None without a
    game install (the Game folder preference, $NWN_ROOT or the usual
    install locations)."""
    try:
        from .cleanmodels import find_game_install
        root = find_game_install(game_dir)
    except Exception:
        return None
    if not root or not os.path.isdir(os.path.join(root, "data")):
        return None
    if root not in _stock_names:
        names = set()
        data_dir = os.path.join(root, "data")
        try:
            for kf in sorted(glob.glob(os.path.join(glob.escape(data_dir), "*.key"))):
                _key_names(kf, names)
            for erf in sorted(glob.glob(os.path.join(glob.escape(data_dir), "*", "*.erf"))):
                _erf_names(erf, names)
        except (OSError, struct.error):
            pass
        _stock_names[root] = names if names else None
    return _stock_names[root]


class Mtr(object):
    """A material read from an mtr file."""
    def __init__(self, name='unnamed'):
        """TODO: DOC."""
        self.name = name

        self.filepath = ''

        self.texture_list = [None] * 15
        self.renderhint = ""
        self.parameters = dict()
        self.customshaderVS = ''  # Vertex shader
        self.customshaderGS = ''  # Geometry shader
        self.customshaderFS = ''  # Fragment shader

    @staticmethod
    def parse_ascii_param_value(str_values):
        """Parses parameter values from list of strings."""
        values = []
        for sv in str_values:
            if not nvb_utils.isNumber(sv):
                break
            values.append(float(sv))
        return values

    @staticmethod
    def get_mtr_name(blen_material, from_out_node=False, strip_trailing=False):
        """Parses parameter values from list of strings."""
        mtr_name = ""
        # bad idea, might be multiple object with the same name
        #if from_out_node:  # Read from output node first
        #    out_node = Materialnode.get_output_node(blen_material)
        #    mtr_name = Materialnode.get_node_identifier(out_node, False)
        if not mtr_name:  # Read from material name if no output node
            mtr_name = blen_material.name
        if strip_trailing:  # Strip trailing numbers
            mtr_name = nvb_utils.strip_trailing_numbers(mtr_name)
        return mtr_name

    @staticmethod
    def get_mtr_params(blen_material):
        """Parses parameter values from list of strings."""
        param_list = []
        for pa in blen_material.nvb.mtr.param_list:
            if pa.pname.lower() not in param_list:  # Keep unique
                param_name = pa.pname.lower()
                param_type = pa.ptype
                param_values = [float(v) for v in pa.pvalue.strip().split()]
                param = (param_name, param_type, param_values)
                param_list.append(param)
        return param_list

    def read_mtr(self, filepath):
        """Load contents of a mtr file."""
        if not filepath:
            return False

        self.filepath = filepath
        # Generate a name, strip file extension
        self.name = os.path.splitext(os.path.basename(filepath))[0]
        try:
            # Latin-1, as models are read: any byte reads (UTF-8 would fail on
            # an accented comment)
            mtrFile = open(os.fsencode(filepath), 'r', encoding='latin-1')
        except IOError:
            return False
        ascii_data = mtrFile.read()
        self.parse_ascii(ascii_data)
        mtrFile.close()
        return True

    def parse_ascii(self, ascii_data):
        """Parse the whole mtr file."""
        ascii_lines = [l.strip().split() for l in ascii_data.splitlines()]
        for line in ascii_lines:
            self.parse_ascii_line(line)

    def parse_ascii_line(self, line):
        """Parse a single line from the ascii mtr file."""
        label = ''
        try:
            label = line[0].lower()
        except (IndexError, AttributeError):
            return  # Probably empty line or comment
        if label.startswith('//') or label.startswith('#'):
            return  # Comment line
        if label == 'renderhint':
            # A bare "renderhint" (older exports wrote one) means no hint
            self.renderhint = line[1] if len(line) > 1 else ''
        elif label == 'parameter':
            # Old format: parameter int/float name value
            try:
                param_type = line[1].lower()
                param_name = line[2]
                param_value = line[3:7]
            except IndexError:
                return
            else:
                param_value = Mtr.parse_ascii_param_value(param_value)
                self.parameters[param_name] = (param_type, param_value)
        elif label == 'customshadervs':
            self.customshaderVS = line[1]
        elif label == 'customshaderfs':
            self.customshaderFS = line[1]
        elif label == 'customshadergs':
            self.customshaderGS = line[1]
        elif label.startswith('texture'):
            if label[7:]:  # 'texture' is followed by a number
                idx = int(label[7:])
                self.texture_list[idx] = nvb_parse.ascii_texture(line[1])
        else:
            # Try to parse as simple parameter format: name value(s)
            # e.g., "twosided 1" or "envmaptexture normals"
            if len(line) >= 2:
                param_name = label
                param_values = Mtr.parse_ascii_param_value(line[1:5])
                if param_values:
                    # Determine type based on values (int if all are whole numbers)
                    if all(v == int(v) for v in param_values):
                        param_type = 'int'
                    else:
                        param_type = 'float'
                    self.parameters[param_name] = (param_type, param_values)

    @staticmethod
    def is_imported(blen_material):
        """True if the material came from a model that named an MTR (or a
        materialname): its MTR is written back as it was read."""
        mtr_props = blen_material.nvb.mtr
        return bool(mtr_props.mdl_bitmap or mtr_props.mdl_materialname)

    @staticmethod
    def is_needed(blen_material, tex_list):
        """True if the material holds anything an MDL cannot: an MTR is then
        written. A material with only a diffuse texture (and the default
        renderhint, no parameters and no shaders) is written into the MDL.

        tex_list: the material's textures, null for an empty slot.
        """
        mtr_props = blen_material.nvb.mtr
        if Mtr.is_imported(blen_material):
            return True
        if any(t and t != nvb_def.null for t in tex_list[1:]):
            return True  # normal, specular, roughness, height, illumination, ...
        if mtr_props.shader_vs or mtr_props.shader_fs or mtr_props.shader_gs:
            return True
        if len(mtr_props.param_list) > 0:
            return True
        hint = mtr_props.renderhint.strip()
        return bool(hint) and hint != DEFAULT_RENDERHINT

    @staticmethod
    def stock_name_warning(mtr_name, blen_material, tex_list, options):
        """The export log's warning for an MTR named like a stock texture or
        material, or ''. An MTR overrides every model that uses the texture
        of that name once it is in a hak or the override folder."""
        if Mtr.is_imported(blen_material):
            return ''  # Written back as it was read
        stock = stock_texture_names(getattr(options, 'cleanmodels_game_dir', ''))
        name = mtr_name.lower()
        if stock is not None:
            if name not in stock:
                return ''
            return ("{}.mtr (material {}): {} is the name of a stock NWN texture or material. "
                    "In a hak or the override folder this MTR replaces the material of every "
                    "model that uses {}, stock models included. Rename the material.").format(
                        mtr_name, blen_material.name, mtr_name, mtr_name)
        diffuse = tex_list[0].lower() if tex_list and tex_list[0] else ''
        if name != diffuse:
            return ''
        return ("{}.mtr (material {}) has the name of its diffuse texture. If {} is a stock "
                "NWN texture, this MTR replaces the material of every model that uses it "
                "(stock models included) once it is in a hak or the override folder; "
                "rename the material unless that is intended. (No game install found to "
                "check against: set the Game folder in the add-on preferences.)").format(
                    mtr_name, blen_material.name, tex_list[0])

    @staticmethod
    def generate_ascii(blen_material, options):
        """Generate a mtr file as asciilines."""
        ascii_lines = []
        tex_list = Materialnode.get_texture_list(blen_material)
        # Clean up texture list, delete trailing "null"
        tex_list = [t if t else nvb_def.null for t in tex_list]
        while tex_list and tex_list[-1] == nvb_def.null:
            _ = tex_list.pop()
        # Add shader specification
        if blen_material.nvb.mtr.shader_vs or blen_material.nvb.mtr.shader_fs or blen_material.nvb.mtr.shader_gs:
            # Custom Shaders
            ascii_lines.append("// Shaders")
            if blen_material.nvb.mtr.shader_vs:
                ascii_lines.append("customshaderVS " + blen_material.nvb.mtr.shader_vs)
            if blen_material.nvb.mtr.shader_fs:
                ascii_lines.append("customshaderFS " + blen_material.nvb.mtr.shader_fs)
            if blen_material.nvb.mtr.shader_gs:
                ascii_lines.append("customshaderGS " + blen_material.nvb.mtr.shader_gs)
            ascii_lines.append("")
        elif tex_list and (tex_list[:3].count(nvb_def.null) <= 1):
            # Add Renderhint; an empty one (an imported mtr without a hint)
            # is NormalAndSpecMapped when a normal or specular texture is
            # present, as for materials written into the mdl, else omitted
            hint = blen_material.nvb.mtr.renderhint
            if not hint and any(t != nvb_def.null for t in tex_list[1:3]):
                hint = "NormalAndSpecMapped"
            if hint:
                ascii_lines.append("// Renderhint")
                ascii_lines.append("renderhint " + hint)
                ascii_lines.append("")
        # Add list of textures
        # Only export texture0 if there are additional textures (texture1, etc.)
        if len(tex_list) > 1:
            ascii_lines.append("// Textures")
            fstr = 'texture{:d} {:s}'
            # The model's own 'bitmap' (a PLT, say) is the diffuse map next to
            # a 'materialname': leave texture0 out as the imported mtr did
            first = 0
            mtr_props = blen_material.nvb.mtr
            if mtr_props.mdl_materialname and mtr_props.mdl_bitmap and \
               not mtr_props.mdl_mtr_texture0 and \
               tex_list[0].lower() == mtr_props.mdl_bitmap.lower():
                first = 1
            ascii_lines.extend([fstr.format(i, t)
                                for i, t in enumerate(tex_list) if i >= first])
            ascii_lines.append("")
        # Add parameters
        # Convert blender param list to dict
        param_dict = dict()
        for param in blen_material.nvb.mtr.param_list:
            param_name = param.pname
            param_type = param.ptype
            param_values = Mtr.parse_ascii_param_value(param.pvalue.strip().split())
            param_id = param_name.lower()
            param_dict[param_id] = [param_name, param_type, param_values]
        # Write the parameters to MTR
        if len(param_dict) > 0:
            ascii_lines.append("// Parameters")
            for _, [param_name, param_type, param_values] in param_dict.items():
                if len(param_values) > 0:
                    if param_type == "int":  # a single int
                        sv = str(int(param_values[0]))
                        ascii_lines.append("parameter int " + param_name + " " + sv)
                    elif param_type == "float":  # up to 4 floats
                        sv = ' '.join([str(v) for v in param_values[:4]])
                        ascii_lines.append("parameter float " + param_name + " " + sv)
        return ascii_lines
