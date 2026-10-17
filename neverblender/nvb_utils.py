"""TODO: DOC."""

import os
import math
import re
import collections
import unicodedata

import mathutils
import bpy
import bpy_extras.image_utils

from . import nvb_def


class NodeResolver():
    """Solves naming conflicts.

    There may be several nodes with the same name in the mdl.
    However, Blender object names are unique.
    """

    def __init__(self):
        """TODO: DOC."""
        self.nodes = collections.OrderedDict()

    def insert_obj(self, node_name, node_idx, obj_name):
        """TODO: DOC."""
        search_name = node_name.lower()
        if search_name not in self.nodes:
            self.nodes[search_name] = []
        self.nodes[search_name].append((obj_name, node_idx))

    def get_obj(self, node_name, node_idx):
        """TODO: DOC."""
        search_name = node_name.lower()
        if search_name not in self.nodes:
            return None
        matches = self.nodes[search_name]
        if len(matches) == 1:  # Only one object was created using this name
            return bpy.data.objects[matches[0][0]]
        elif len(matches) > 1:
            # Return the node with the same index (position in the mdl)
            filtered = list(filter(lambda x: x[1] == node_idx, matches))
            filtered.sort(key=lambda x: x[1])
            if filtered:
                return bpy.data.objects[filtered[0][0]]
        return None

    def get_obj_parent(self, node_name, node_idx):
        """TODO: DOC."""
        search_name = node_name.lower()
        if search_name not in self.nodes:
            return None
        matches = self.nodes[search_name]
        if len(matches) == 1:
            # Only one object was created using this node name
            return bpy.data.objects[matches[0][0]]
        elif len(matches) > 1:
            # Get all nodes with lower indices
            # (= located before this node in the MDL)
            filtered = list(filter(lambda x: x[1] < node_idx, matches))
            # Of these nodes, return the one with highest index
            if filtered:
                filtered.sort(key=lambda x: x[1])
                return bpy.data.objects[filtered[-1][0]]
        return None


class AuroraSmoothgroupGraph():
    """Generates smoothgroups from sharp edges by using graph colouring

    The generated smoothgoups do NOT share vertices. If that not a requirement
    (= them not sharing an sharp edge is enough) using calc_smooth_groups(use_bitflags=True)
    is sufficient
    """
    max_colours = 31  # NWN may only use 32 groups max

    def __init__(self):
        pass


    def is_colour_valid(self, v, colour, c):
        """Check if a color assignment is valid."""
        for i in range(self.V):
            if self.graph[v][i] == 1 and colour[i] == c:
                return False
        return True


    def create_colourization(self, colour, v):
        """Find a valid colourization of the graph."""
        if v == self.V:
            return True

        for c in range(1, self.max_colours + 1):
            if self.is_colour_valid(v, colour, c) == True:
                colour[v] = c
                if self.create_colourization(colour, v + 1) == True:
                    return True
                colour[v] = 0


    def calc_smooth_groups(self, blen_mesh):
        """Get a valid number of """
        group_ids, group_cnt = blen_mesh.calc_smooth_groups(use_bitflags=False)
        group_polys = [[fid for fid, g in enumerate(group_ids) if g==gid] for gid in range(1,group_cnt+1)]
        group_verts = [set([v for vl in [p.vertices[:] for pid, p in enumerate(blen_mesh.polygons) if pid in pid_list] for v in vl]) for pid_list in group_polys]

        self.graph = [[not g1.isdisjoint(g2) for g1 in group_verts] for g2 in group_verts]
        self.V = group_cnt

        # Get a graph colorization
        colour_list = [0] * self.V
        if self.create_colourization(colour_list, 0) == None:
            return []

        # Map colourization to faces
        #colour_list = [2**c for c in colour_list]
        smoothgroups = list([(face_idx, 2**(colour-1)) for face_idx in goup_face] for goup_face, colour in zip(group_polys, colour_list))
        smoothgroups = [item for sublist in smoothgroups for item in sublist]
        smoothgroups.sort(key=lambda x: x[0])
        smoothgroups = [sgi for (fi, sgi) in smoothgroups]

        return smoothgroups


def is_mdl_base(obj):
    """Return true if object obj is a rootdummy."""
    if not obj:
        return False
    return (obj.parent is None) and \
           (obj.type == 'EMPTY') and \
           (obj.nvb.emptytype == nvb_def.Emptytype.DUMMY)


def get_obj_mdl_base(obj):
    """Return the objects aurora root."""
    while obj:
        if is_mdl_base(obj):
            return obj
        obj = obj.parent
    return None


def get_mdl_base(obj=None, collection=None, scene=None):
    """Return any aurora base."""
    # 1. Check the object and its parents
    match = get_obj_mdl_base(obj)
    if match:
        return match
    # 2. Nothing was found, check objects in active collection
    if collection:
        matches = [m for m in collection.objects if is_mdl_base(m)]
        if matches:
            return matches[0]
    # 3. Still nothing, check objects in master collection
    matches = [m for m in scene.collection.all_objects if is_mdl_base(m)]
    if matches:
        return matches[0]
    return None


def get_active_collection(context):
    """Get active collection or create a new one"""
    view_layer = context.view_layer
    if view_layer.collections.active:
        collection = view_layer.collections.active.collection
    else:
        collection = context.scene.master_collection.new()
        view_layer.collections.link(collection)
    return collection


def get_fcurve(action, data_path, index=0, group_name=None):
    """Get the fcurve with specified properties or create one."""
    fcu = action.fcurves.find(data_path=data_path, index=index)
    if not fcu:  # Create new Curve
        fcu = action.fcurves.new(data_path=data_path, index=index)
        if group_name:  # Add curve to group
            if group_name in action.groups:
                group = action.groups[group_name]
            else:
                group = action.groups.new(group_name)
            fcu.group = group
    return fcu


def get_action(target, action_name):
    """Get the active action or create one."""
    # Get animation data, create if needed
    anim_data = target.animation_data
    if not anim_data:
        anim_data = target.animation_data_create()
    # Get action, create if needed
    action = anim_data.action
    if not action:
        action = bpy.data.actions.new(name=action_name)
        # action.use_fake_user = True
        anim_data.action = action
    return action


def get_aabb(mdl_base):
    """Find an AABB mesh for this mdl base."""
    def is_aabb(obj):
        """Return true if object obj is an aabb mesh."""
        return obj.type == 'MESH' and obj.nvb.meshtype == nvb_def.Meshtype.AABB
    ol = [c for c in mdl_base.children if is_aabb(c)]
    if len(ol) > 0:
        return ol[0]
    return None


def find_file_nocase(file_dir, file_name):
    """Return the case sensitive path to the file."""
    if file_dir == "" or file_name == "":
        return ""

    # If it actually exists, return it directly
    file_path = os.path.join(file_dir, file_name)
    if os.path.exists(file_path):
        return file_path

    try:  # we are expecting dirname to be a directory, but it could be a file
        file_list = os.listdir(file_dir)
    except OSError:
        return

    # Try to match filename in the directory
    search_name = file_name.lower()
    try:
        valid_name = next(fl for fl in file_list if fl.lower() == search_name)
    except StopIteration:
        return ""

    if valid_name:
        return os.path.join(file_dir, valid_name)

    return ""


def is_wkm_base(obj):
    """Return true if object obj is a root object for walkmeshes."""
    if not obj:
        return False
    return (obj.parent and
            obj.type == 'EMPTY' and
            (obj.nvb.emptytype == nvb_def.Emptytype.PWK or
             obj.nvb.emptytype == nvb_def.Emptytype.DWK))


def get_wkm_base(mdl_base, wkmtype):
    """Find a walkmesh root."""
    emptytype = nvb_def.Emptytype.PWK
    if wkmtype == nvb_def.Walkmeshtype.DWK:
        emptytype = nvb_def.Emptytype.DWK
    ol = [c for c in mdl_base.children
          if c.type == 'EMPTY' and c.nvb.emptytype == emptytype]
    if len(ol) > 0:
        return ol[0]
    return None


def create_wok_materials(mesh, update_existing=False, pad_to=0):
    """Adds walkmesh materials to the object."""
    # Add walkmesh materials
    for matname, matcolor in nvb_def.wok_materials:
        # Walkmesh materials are always shared between walkmeshes
        if matname in bpy.data.materials.keys():
            mat = bpy.data.materials[matname]
            mat_exists = True
        else:
            mat = bpy.data.materials.new(matname)
            mat_exists = False

        if not mat_exists or update_existing:
            mat.diffuse_color = matcolor
            mat.specular_intensity = 0.0
            mat.roughness = 1.0
            mat.use_backface_culling = True

        mesh.materials.append(mat)

    if pad_to > len(nvb_def.wok_materials):
        for i in range(len(nvb_def.wok_materials), pad_to+1):
            matname = "wok_unknown"+str(i)
            matcolor = (0.500, 0.000, 1.000, 1.0)
            if matname in bpy.data.materials.keys():
                mat = bpy.data.materials[matname]
                mat_exists = True
            else:
                mat = bpy.data.materials.new(matname)
                mat_exists = False

            if not mat_exists or update_existing:
                mat.diffuse_color = matcolor
                mat.specular_intensity = 0.0
                mat.roughness = 1.0
                mat.use_backface_culling = True

            mesh.materials.append(mat)

    mesh.materials.update()
    return len(mesh.materials) == max(len(nvb_def.wok_materials), pad_to+1)


def get_children_recursive(obj, obj_list):
    """Generate a list of ths objects children."""
    for c in obj.children:
        obj_list.append(c)
        get_children_recursive(c, obj_list)


def get_last_keyframe(root_obj):
    """Get the last keyed frame of this object and its children."""
    def get_max_frame(target):
        frame = nvb_def.anim_globstart
        if target:
            if target.animation_data and target.animation_data.action:
                for fcu in target.animation_data.action.fcurves:
                    frame = max(max([p.co[0] for p in fcu.keyframe_points],
                                    default=0), frame)
            return frame
    obj_list = [root_obj]
    get_children_recursive(root_obj, obj_list)
    frame_list = [nvb_def.anim_globstart]
    for obj in obj_list:
        frame_list.append(get_max_frame(obj))
        mat = obj.active_material
        if mat:
            frame_list.append(get_max_frame(mat))
        part_sys = obj.particle_systems.active
        if part_sys:
            frame_list.append(get_max_frame(part_sys.settings))
    return max(frame_list)


def get_frame_interval(obj):
    """Get the first and last keyed frame of this object and its children."""
    obj_list = [obj]
    get_children_recursive(obj, obj_list)
    max_frame = nvb_def.anim_globstart
    min_frame = nvb_def.anim_globstart + 1000
    for o in obj_list:
        if o.animation_data and o.animation_data.action:
            action = o.animation_data.action
            for fcu in action.fcurves:
                max_frame = max(max([p.co[0] for p in fcu.keyframe_points],
                                    default=0), max_frame)
                min_frame = min(min([p.co[0] for p in fcu.keyframe_points],
                                    default=0), min_frame)
    return (min_frame, max_frame)


def strip_trailing_numbers(s):
    """Removes trailing numbers resulting from duplicate object names."""
    return re.fullmatch(r'(.+?)(\.\d+)?$', s).group(1)


def generate_mdl_identifier(s):
    identifier = s.replace(' ', '_')
    identifier = unicodedata.normalize('NFKD', identifier).encode('ascii', 'ignore').decode()
    # identifier = re.sub(r'[^a-zA-Z0-9_!\-\.]', r'!', identifier)
    return identifier


def generate_node_name(obj, strip_trailing=False):
    """Return a name for node/objects for use in the mdl."""
    if obj:
        new_name = obj.name
        if strip_trailing:
            new_name = strip_trailing_numbers(new_name)
        new_name = generate_mdl_identifier(new_name)
        return new_name

    return nvb_def.null


def isNumber(s):
    """Check if the string s is a number."""
    try:
        float(s)
    except ValueError:
        return False
    else:
        return True


def str2bool(s):
    """Custom bool conversion: Integers != 0 and "true" are True."""
    try:
        b = (int(s) != 0)
    except ValueError:  # string literal
        try:
            b = (s.lower() == "true")
        except AttributeError:
            b = false
    return b


def str2int(s):
    """Custom int conversion. Convert to float first, then int."""
    return int(float(s))


def str2float(s):
    """Custom float conversion. Treat every error as 0.0."""
    try:
        f = float(s)
    except ValueError:
        f = 0.0
    return f


def str2identifier(s):
    """Convert to lower case. Convert 'null' to empty string."""
    if (not s or s.lower() == nvb_def.null):
        return ''
    return s.lower()


def str2texture(s):
    """Convert to lower case. Convert 'null' to nvb_def.null."""
    if (not s or s.lower() == nvb_def.null):
        return nvb_def.null
    return s.lower()


def toggle_anim_focus(scene, mdl_base):
    """Set the Start and end frames of the timeline."""
    animList = mdl_base.nvb.animList
    animIdx = mdl_base.nvb.animListIdx

    anim = animList[animIdx]
    if (scene.frame_start == anim.frameStart) and \
       (scene.frame_end == anim.frameEnd):
        # Set timeline to include all current
        scene.frame_start = 1
        lastFrame = 1
        for anim in animList:
            if lastFrame < anim.frameEnd:
                lastFrame = anim.frameEnd
        scene.frame_end = lastFrame
    else:
        # Set timeline to the current animation
        scene.frame_start = anim.frameStart
        scene.frame_end = anim.frameEnd
    scene.frame_current = scene.frame_start


def checkAnimBounds(mdl_base):
    """
    Check for animations of this mdl base.

    Returns true, if are non-overlapping and only use by one object.
    """
    if len(mdl_base.nvb.animList) < 2:
        return True
    # TODO: use an interval tree
    animBounds = [(a.frameStart, a.frameEnd, idx) for idx, a in
                  enumerate(mdl_base.nvb.animList)]
    for a1 in animBounds:
        for a2 in animBounds:
            if (a1[0] <= a2[1]) and (a2[0] <= a1[1]) and (a1[2] != a2[2]):
                return False
    return True


def amt_event_list_item_create(amt, event_name):
    event_list = amt.nvb.amt_event_list
    # Add new event
    event = event_list.add()
    amt.nvb.amt_event_list_idx = len(amt.nvb.amt_event_list)-1
    event.name = event_name
    # Add empty fcurves (to make sure they are conveniently grouped)
    anim_data = amt.animation_data
    if not anim_data:
        anim_data = amt.animation_data.create()
    action = anim_data.action
    if not action:
        action = bpy.data.actions.new(amt.name)
    data_path = 'nvb.amt_event_list[' + str(amt.nvb.amt_event_list_idx) + '].fire'
    fcu = get_fcurve(action, data_path, 0, 'Events')
    fcu.group = action.groups['Events']  # force group


def amt_event_list_init(amt):
    event_list = amt.nvb.amt_event_list
    if len(event_list) > 0:
        return
    amt.nvb.amt_event_list_idx = 0
    # Create new events:
    for ev_name in nvb_def.animation_event_names:
        ev = event_list.add()
        ev.name = ev_name


def create_anim_list_item(mdl_base, check_keyframes=False):
    """Append a new animation at the and of the animation list."""
    last_frame = max([nvb_def.anim_globstart] + [a.frameEnd for a in mdl_base.nvb.animList])
    if check_keyframes:
        last_frame = max(last_frame, get_last_keyframe(mdl_base))
    anim = mdl_base.nvb.animList.add()
    anim.name = mdl_base.name
    start = int(math.ceil((last_frame + nvb_def.anim_offset) / 10.0)) * 10
    anim.frameStart = start
    anim.frameEnd = start
    return anim


def getNodeType(obj):
    """Get the node type (dummy, trimesh, skin, ...) of the blender object."""
    objType = obj.type
    if objType == 'EMPTY':
        return obj.nvb.emptytype
    elif objType == 'MESH':
        return obj.nvb.meshtype
    elif objType in ('LIGHT', 'LAMP'):  # LIGHT since 2.8, LAMP, before
        return nvb_def.Nodetype.LIGHT
    return nvb_def.Nodetype.DUMMY


def setObjAuroraRot(obj, nwangle):
    """TODO: DOC."""
    rotmode = obj.rotation_mode
    if rotmode == 'QUATERNION':
        obj.rotation_quaternion = mathutils.Quaternion(nwangle[:3], nwangle[3])
    elif rotmode == 'AXIS_ANGLE':
        obj.rotation_axis_angle = [nwangle[3]] + nwangle[:3]
    else:  # Has to be euler
        q = mathutils.Quaternion(nwangle[:3], nwangle[3])
        obj.rotation_euler = q.to_euler(rotmode)


def getAuroraScale(obj):
    """If scale is uniform (x=y=z) return the value; Else return 1."""
    scale = obj.scale
    if (scale[0] == scale[1] == scale[2]):
        return scale[0]
    return 1.0


def eulerFilter(currEul, prevEul):
    """TODO: DOC."""
    def distance(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])

    def flip(e):
        f = e.copy()
        f[0] += math.pi
        f[1] *= -1
        f[1] += math.pi
        f[2] += math.pi
        return f

    def flipDiff(a, b):
        while abs(a - b) > math.pi:
            if a < b:
                b -= 2 * math.pi
            else:
                b += 2 * math.pi
        return b

    if not prevEul:  # Nothing to compare to, return original value
        return currEul
    # Original euler
    eul = currEul.copy()
    eul[0] = flipDiff(prevEul[0], eul[0])
    eul[1] = flipDiff(prevEul[1], eul[1])
    eul[2] = flipDiff(prevEul[2], eul[2])
    # Flipped euler
    flipEul = flip(eul)
    flipEul[0] = flipDiff(prevEul[0], flipEul[0])
    flipEul[1] = flipDiff(prevEul[1], flipEul[1])
    flipEul[2] = flipDiff(prevEul[2], flipEul[2])
    # Return the "better" = smoother euler
    currDist = distance(prevEul, eul)
    flipDist = distance(prevEul, flipEul)
    if flipDist < currDist:
        return flipEul
    else:
        return eul


def get_textures(material):
    """Get a list of (texture_idx, texture_name, texture_alpha) tuples."""
    def get_img_name(tslot):
        """Get the texture name for this texture slot."""
        imgname = ''
        tex = tslot.texture
        if tex.type == 'IMAGE':
            img = tex.image
            if img:
                if img.filepath:
                    imgname = \
                        os.path.splitext(os.path.basename(img.filepath))[0]
                elif img.name:
                    imgname = \
                        os.path.splitext(os.path.basename(img.name))[0]
        # Last resort: Texture name
        if not imgname:
            imgname = tex.name
        return imgname

    texList = [(idx, get_img_name(tslot), tslot.alpha_factor)
               for idx, tslot in enumerate(material.texture_slots)
               if tslot and material.use_textures[idx]]
    return texList


def create_image(img_name, img_path, tex_search):
    """TODO: Doc."""
    img_dir = os.path.dirname(img_path)
    # List of extensions we try will try to import
    img_ext_list = ['.tga', '.png', '.psd', '.dds']
    img = None
    for img_ext in img_ext_list:
        img = bpy_extras.image_utils.load_image(
            img_name + img_ext,
            img_dir,
            recursive=tex_search,
            place_holder=False,
            ncase_cmp=True,
            check_existing=True)
        if img:
            break
    # No image found => create a placeholder image instead
    if not img:
        img = bpy.data.images.new(name=img_name, width=512, height=512)
    img.name = img_name
    return img


def build_mesh(vertices, faces, mesh_name, vpf=3):
    mesh = bpy.data.meshes.new(mesh_name)
    # Create Verts
    mesh.vertices.add(len(vertices))
    mesh.vertices.foreach_set('co', [c for v in vertices for c in v])
    # Create Loops
    mesh.loops.add(len(faces) * vpf)
    mesh.loops.foreach_set('vertex_index', [i for f in faces for i in f])
    # Create Polygons
    mesh.polygons.add(len(faces))
    mesh.polygons.foreach_set('loop_start', range(0, len(faces) * vpf, vpf))
    mesh.polygons.foreach_set('loop_total', (vpf,) * len(faces))
    mesh.validate()
    mesh.update()
    return mesh


def create_texture(texname, imgname, filepath, tex_search):
    """TODO: Doc."""
    if texname in bpy.data.textures:
        # Load the image for the texture
        tex = bpy.data.textures[texname]
    else:
        tex = bpy.data.textures.new(texname, type='IMAGE')
        if (imgname in bpy.data.images):
            img = bpy.data.images[imgname]
            tex.image = img
        else:
            texpath = os.path.dirname(filepath)
            img = bpy_extras.image_utils.load_image(
                imgname + '.tga', texpath, recursive=tex_search,
                place_holder=False, ncase_cmp=True)
            if img is None:
                img = bpy.data.images.new(imgname, 512, 512)
            img.name = imgname
            tex.image = img
    return tex


def correct_emitter_parameters(param):
    """Correct emitter parameters, which are case sensitive."""
    correct = {'normal': 'Normal',
               'lighten': 'Lighten',
               'linked': 'Linked',
               'billboard_to_local_z': 'Billboard_to_Local_Z',
               'billboard_to_world_z': 'Billboard_to_World_Z',
               'aligned_to_world_z': 'Aligned_to_World_Z',
               'aligned_to_particle_dir': 'Aligned_to_Particle_Dir',
               'motion_blur': 'Motion_Blur',
               'fountain': 'Fountain',
               'single': 'Single',
               'explosion': 'Explosion',
               'lightning': 'Lightning'}
    if param in correct:
        return correct[param]
    return param


def create_setfile(mdl_list, ignore_stored_tile_id, store_tile_id, strip_trailing, collections_as_groups,
                   internal_name, is_interior, has_height_transition, env_map, transition, selector_height, displayname, unlocalized_name,
                   grass, grass_texture, grass_density, grass_height):

    def atoi(text):
        return int(text) if text.isdigit() else text

    def natural_keys(text):
        return [atoi(c) for c in re.split(r'(\d+)', text)]

    tiles = []
    tile_ids = dict()
    if ignore_stored_tile_id:
        # Re create all tile IDs, we just sort by model name
        tiles = sorted(mdl_list, key=lambda x: natural_keys(x.name))
        # Save them, if option is set
        if store_tile_id:
            for i, mdl in enumerate(tiles):
                mdl.nvb.nfo.tile_id = i

        for i, mdl in enumerate(tiles):
            tile_ids[mdl.name] = i
    else:
        # Keep existing tiles IDs at their old position
        # This may result in holes represented by None
        reserved_ids = [(mdl.nvb.nfo.tile_id, mdl) for mdl in mdl_list if mdl.nvb.nfo.tile_id >= 0]
        if reserved_ids:
            tiles = [None] * max(max(reserved_ids, key=lambda x: x[0])[0]+1, len(mdl_list))
            # Add tiles with reserved IDs
            for tile_id, mdl in reserved_ids:
                tiles[tile_id] = mdl
                tile_ids[mdl.name] = tile_id
        else:
            tiles = [None] * len(mdl_list)

        # Add tiles without IDs
        i = 0
        for mdl in sorted(mdl_list, key=lambda x: natural_keys(x.name)):
            # tile id < 0 are invalid, that means we auto assign a number
            if mdl.nvb.nfo.tile_id < 0:
                # Look for an empty spot to place this mdl
                while tiles[i] is not None:
                    i += 1
                tiles[i] = mdl
                tile_ids[mdl.name] = i

                if store_tile_id:
                    mdl.nvb.nfo.tile_id = i

    # Gather list of unique terrains
    terrains = set()
    terrains.update([mdl.nvb.nfo.tile_terrain_topleft for mdl in mdl_list])
    terrains.update([mdl.nvb.nfo.tile_terrain_topright for mdl in mdl_list])
    terrains.update([mdl.nvb.nfo.tile_terrain_bottomright for mdl in mdl_list])
    terrains.update([mdl.nvb.nfo.tile_terrain_bottomleft for mdl in mdl_list])
    # Terrains must be defined for every tile, i.e. can't be empty
    # Missing ones (=Empty String) must be defined, we're replace empty strings with "INVALID"
    if "" in terrains:
        terrains.remove("")
        if "INVALID" not in terrains:
            terrains.add("INVALID")

    # Gather list of unique crossers
    crossers = set()
    crossers.update([mdl.nvb.nfo.tile_crosser_top for mdl in mdl_list])
    crossers.update([mdl.nvb.nfo.tile_crosser_right for mdl in mdl_list])
    crossers.update([mdl.nvb.nfo.tile_crosser_bottom for mdl in mdl_list])
    crossers.update([mdl.nvb.nfo.tile_crosser_left for mdl in mdl_list])
    # Crossers may be undefined: We just the remove empty strings
    crossers.discard("")

    # Header
    ascii_lines = []
    ascii_lines.append("; NEVERWINTER NIGHTS TILESET FILE")
    ascii_lines.append("; DO NOT EDIT MANUALLY - UNLESS YOU KNOW WHAT YOU ARE DOING")
    ascii_lines.append("")

    # General
    ascii_lines.append("[GENERAL]")
    ascii_lines.append("Name={0}".format(internal_name))
    ascii_lines.append("Type=SET")
    ascii_lines.append("Version=V1.0")
    ascii_lines.append("Interior={0:d}".format(is_interior))
    ascii_lines.append("HasHeightTransition={0:d}".format(has_height_transition))
    ascii_lines.append("EnvMap={0}".format(env_map))
    ascii_lines.append("Transition={0:d}".format(transition))
    ascii_lines.append("SelectorHeight={0:d}".format(selector_height))
    ascii_lines.append("DisplayName={0:d}".format(displayname))
    if (displayname == -1):
        ascii_lines.append("UnlocalizedName={0}".format(unlocalized_name))
    # If There are valid terrains, select one at random (otherwise just a generic "Grass", can't leave it empty)
    if terrains:
        t = next(iter(terrains))
        ascii_lines.append("Border={0}".format(t))
        ascii_lines.append("Default={0}".format(t))
        ascii_lines.append("Floor={0}".format(t))
    else:
        ascii_lines.append("Border={0}".format("Grass"))
        ascii_lines.append("Default={0}".format("Grass"))
        ascii_lines.append("Floor={0}".format("Grass"))
    ascii_lines.append("")

    # Grass
    ascii_lines.append("[GRASS]")
    ascii_lines.append("Grass={0:d}".format(grass))
    if grass:
        ascii_lines.append("GrassTextureName={0}".format(grass_texture))
        ascii_lines.append("Density={0:.3}".format(grass_density))
        ascii_lines.append("Height={0:.3}".format(grass_height))
        ascii_lines.append("AmbientRed={0:.3}".format(0.5))
        ascii_lines.append("AmbientGreen={0:.3}".format(0.6))
        ascii_lines.append("AmbientBlue={0:.3}".format(0.3))
        ascii_lines.append("DiffuseRed={0:.3}".format(0.5))
        ascii_lines.append("DiffuseGreen={0:.3}".format(0.6))
        ascii_lines.append("DiffuseBlue={0:.3}".format(0.3))
    ascii_lines.append("")

    # Terrain types
    ascii_lines.append("[TERRAIN TYPES]")
    ascii_lines.append("Count={0:d}".format(len(terrains)))
    ascii_lines.append("")
    for i, t in enumerate(sorted(terrains)):
        ascii_lines.append("[TERRAIN{0}]".format(i))
        ascii_lines.append("Name={0}".format(t))
        ascii_lines.append("StrRef={0:d}".format(0))  # "Bad Strref"
        ascii_lines.append("")

    # Crosser types
    ascii_lines.append("[CROSSER TYPES]")
    ascii_lines.append("Count={0:d}".format(len(crossers)))
    ascii_lines.append("")
    for i, c in enumerate(sorted(crossers)):
        ascii_lines.append("[CROSSER{0}]".format(i))
        ascii_lines.append("Name={0}".format(c))
        ascii_lines.append("StrRef={0:d}".format(0))  # "Bad Strref"
        ascii_lines.append("")

    # Primary Rules (Always 0, we don't do this)
    ascii_lines.append("[PRIMARY RULES]")
    ascii_lines.append("Count={0:d}".format(0))
    ascii_lines.append("")

    # Secondary Rules (Always 0, unused)
    ascii_lines.append("[SECONDARY RULES]")
    ascii_lines.append("Count={0:d}".format(0))
    ascii_lines.append("")

    # Tiles
    ascii_lines.append("[TILES]")
    ascii_lines.append("Count={0:d}".format(len(tiles)))
    ascii_lines.append("")
    for tile_id, blen_obj in enumerate(tiles):
        # Might be None, which means padding
        if blen_obj:
            ascii_lines.append("[TILE{0:d}]".format(tile_id))
            if strip_trailing:
                ascii_lines.append("Model={0}".format(strip_trailing_numbers(blen_obj.name)))
            else:
                ascii_lines.append("Model={0}".format(blen_obj.name))
            ascii_lines.append("WalkMesh={0}".format("msb01"))
            # Terrain
            ascii_lines.append("TopLeft={0}".format(blen_obj.nvb.nfo.tile_terrain_topleft if blen_obj.nvb.nfo.tile_terrain_topleft else "INVALID"))
            ascii_lines.append("TopLeftHeight={0}".format(blen_obj.nvb.nfo.tile_terrain_topleft_height))
            ascii_lines.append("TopRight={0}".format(blen_obj.nvb.nfo.tile_terrain_topright if blen_obj.nvb.nfo.tile_terrain_topright else "INVALID"))
            ascii_lines.append("TopRightHeight={0}".format(blen_obj.nvb.nfo.tile_terrain_topright_height))
            ascii_lines.append("BottomLeft={0}".format(blen_obj.nvb.nfo.tile_terrain_bottomleft if blen_obj.nvb.nfo.tile_terrain_bottomleft else "INVALID"))
            ascii_lines.append("BottomLeftHeight={0}".format(blen_obj.nvb.nfo.tile_terrain_bottomleft_height))
            ascii_lines.append("BottomRight={0}".format(blen_obj.nvb.nfo.tile_terrain_bottomright if blen_obj.nvb.nfo.tile_terrain_bottomright else "INVALID"))
            ascii_lines.append("BottomRightHeight={0}".format(blen_obj.nvb.nfo.tile_terrain_bottomright_height))
            # Crosser
            ascii_lines.append("Top={0}".format(blen_obj.nvb.nfo.tile_crosser_top))
            ascii_lines.append("Right={0}".format(blen_obj.nvb.nfo.tile_crosser_right))
            ascii_lines.append("Bottom={0}".format(blen_obj.nvb.nfo.tile_crosser_bottom))
            ascii_lines.append("Left={0}".format(blen_obj.nvb.nfo.tile_crosser_left))
            # Lighting + Animation
            ascii_lines.append("MainLight1={0:d}".format(1))
            ascii_lines.append("MainLight2={0:d}".format(1))
            ascii_lines.append("SourceLight1={0:d}".format(1))
            ascii_lines.append("SourceLight2={0:d}".format(1))
            ascii_lines.append("AnimLoop1={0:d}".format(0))
            ascii_lines.append("AnimLoop2={0:d}".format(0))
            ascii_lines.append("AnimLoop3={0:d}".format(0))
            #
            ascii_lines.append("Doors={0:d}".format(blen_obj.nvb.nfo.tile_doors))
            ascii_lines.append("Sounds={0:d}".format(0))
            # Path and Visibility nodes
            ascii_lines.append("PathNode={0}".format(blen_obj.nvb.nfo.tile_pathnode))
            ascii_lines.append("Orientation={0:d}".format(blen_obj.nvb.nfo.tile_pathnode_orientation))
            if (blen_obj.nvb.nfo.tile_pathnode != blen_obj.nvb.nfo.tile_visnode):
                ascii_lines.append("VisibilityNode={0}".format(blen_obj.nvb.nfo.tile_visnode))
                ascii_lines.append("VisibilityOrientation={0:d}".format(blen_obj.nvb.nfo.tile_visnode_orientation))
            #
            ascii_lines.append("ImageMap2D={0}".format(blen_obj.nvb.nfo.tile_imagemap2d))
            ascii_lines.append("")

            # Add dummy door entries
            for i in range(blen_obj.nvb.nfo.tile_doors):
                ascii_lines.append("[TILE{0:d}DOOR{1:d}]".format(tile_id, i))
                ascii_lines.append("Type={0:d}".format(0))
                ascii_lines.append("X={0:.3f}".format(0.0))
                ascii_lines.append("Y={0:.3f}".format(0.0))
                ascii_lines.append("Z={0:.3f}".format(5.0))
                ascii_lines.append("Orientation={0:d}".format(90))
                ascii_lines.append("")
        else:
            ascii_lines.append("[TILE{0:d}]".format(tile_id))
            ascii_lines.append("Model=PADDING")
            ascii_lines.append("WalkMesh={0}".format("msb01"))
            # Terrain
            ascii_lines.append("TopLeft={0}".format("INVALID"))
            ascii_lines.append("TopLeftHeight=0")
            ascii_lines.append("TopRight={0}".format("INVALID"))
            ascii_lines.append("TopRightHeight=0")
            ascii_lines.append("BottomLeft={0}".format("INVALID"))
            ascii_lines.append("BottomLeftHeight=0")
            ascii_lines.append("BottomRight={0}".format("INVALID"))
            ascii_lines.append("BottomRightHeight=0")
            # Crosser
            ascii_lines.append("Top=")
            ascii_lines.append("Right=")
            ascii_lines.append("Bottom=")
            ascii_lines.append("Left=")
            # Lighting + Animation
            ascii_lines.append("MainLight1=0")
            ascii_lines.append("MainLight2=0")
            ascii_lines.append("SourceLight1=0")
            ascii_lines.append("SourceLight2=0")
            ascii_lines.append("AnimLoop1=0")
            ascii_lines.append("AnimLoop2=0")
            ascii_lines.append("AnimLoop3=0")
            #
            ascii_lines.append("Doors=0")
            ascii_lines.append("Sounds=0")
            # Path and Visibility nodes
            ascii_lines.append("PathNode=A")
            ascii_lines.append("Orientation=0")
            #
            ascii_lines.append("ImageMap2D=")
            ascii_lines.append("")

    # Groups
    ascii_lines.append("[GROUPS]")
    if collections_as_groups:
        # Only consider leaves and collections with objects in them and rows & columns defined
        coll_list = [coll for coll in bpy.data.collections if coll.objects and coll.nvb.nfo.tile_group_dim[0] > 0 and coll.nvb.nfo.tile_group_dim[1] > 0]
        ascii_lines.append("Count={0:d}".format(len(coll_list)))
        ascii_lines.append("")
        for i, coll in enumerate(coll_list):
            ascii_lines.append("[GROUP{0:d}]".format(i))
            ascii_lines.append("Name={0}".format(generate_mdl_identifier(coll.name)))
            ascii_lines.append("StrRef={0:d}".format(0))  # "Bad Strref"
            ascii_lines.append("Rows={0:d}".format(coll.nvb.nfo.tile_group_dim[0]))
            ascii_lines.append("Columns={0:d}".format(coll.nvb.nfo.tile_group_dim[1]))
            # Get mdl bases in this collection
            mdl_base_list = [obj for obj in coll.objects if is_mdl_base(obj)]
            mdl_base_list.sort(key=lambda x: natural_keys(x.name))
            req_tiles = coll.nvb.nfo.tile_group_dim[0] * coll.nvb.nfo.tile_group_dim[1]
            num_tiles = len(mdl_base_list[:req_tiles])
            # Make sure not to exceed rows*cols
            for j, obj in enumerate(mdl_base_list[:req_tiles]):
                ascii_lines.append("Tile{0:d}={1:d}".format(j, tile_ids[obj.name]))
            # Make sure to have at least rows*cols tiles. Fill missing ones with Tile-1 (any tile)
            if req_tiles > num_tiles:
                for j in range(num_tiles, req_tiles):
                    ascii_lines.append("Tile{0:d}={1:d}".format(j,-1))
            del mdl_base_list
            ascii_lines.append("")
    else:
        ascii_lines.append("Count={0:d}".format(0))
        ascii_lines.append("")

    return ascii_lines
