"""TODO: DOC."""

import math
import mathutils
from bpy_extras.io_utils import unpack_list

from . import nvb_def
from . import nvb_utils
from . import nvb_node
from .nvb_materialnode import Materialnode


class Animnode():
    """TODO: DOC."""

    # Keys that go into particle system settings
    emitter_properties = nvb_node.Emitter.property_dict
    # Keys that go directly into objects
    object_properties = {'position': ('', 3, float, ' {:> 6.5f}'),  # Needs conversio
                         'orientation': ('', 4, float, ' {:> 6.5f}'),  # Needs conversio
                         'scale': ('', 1, float,  ' {:> 6.5f}'),  # Needs conversio
                         'color': ('color', 3, float, ' {:>4.2f}'),
                         'radius': ('distance', 1, float, ' {:>6.5f}'),
                         'alpha': ('', 1, float, ' {:>4.2f}'),  # Needs conversion
                         'selfillumcolor': ('', 3, float, ' {:>4.2f}'),
                         'setfillumcolor': ('', 3, float,' {:>4.2f}')}

    def __init__(self, name='UNNAMED'):
        """TODO: DOC."""
        self.nodeidx = -1
        self.nodetype = nvb_def.Nodetype.DUMMY
        self.name = name
        self.parent = nvb_def.null

        self.emitter_data = dict()
        self.object_data = dict()

        # Animesh Data
        self.sampleperiod = 0.0
        self.facedef = []
        self.animtverts = []
        self.animverts = []

        self.uvdata = False  # Animmesh, uv animations present
        self.shapedata = False  # Animmesh, vertex animations present

    def __bool__(self):
        """Return false if the node is empty, i.e. no anims attached."""
        return self.object_data or self.emitter_data

    @staticmethod
    def insert_kfp(frames, values, action, dp, dp_dim, action_group=None, target=None):
        """Insert keyframe points into fcurves.
        
        Args:
            frames: List of frame numbers
            values: List of values (each value is a tuple/list of components)
            action: The action to insert keyframes into
            dp: Data path for the fcurves
            dp_dim: Number of dimensions (components) in the data path
            action_group: Optional group name for the fcurves
            target: Target object (required for Blender 5.0+)
        """
        if frames and values:
            fcu = [nvb_utils.get_fcurve(action, dp, i, action_group, target)
                   for i in range(dp_dim)]
            kfp_list = [fcu[i].keyframe_points for i in range(dp_dim)]
            kfp_cnt = list(map(lambda x: len(x), kfp_list))
            list(map(lambda x: x.add(len(values)), kfp_list))
            for i, (frm, val) in enumerate(zip(frames, values)):
                for d in range(dp_dim):
                    p = kfp_list[d][kfp_cnt[d]+i]
                    p.co = frm, val[d]
                    p.interpolation = 'LINEAR'
            list(map(lambda c: c.update(), fcu))

    def load_ascii(self, ascii_lines, nodeidx=-1):
        """TODO: DOC."""
        def find_end(ascii_lines):
            """Find the end of a key list.

            We don't know when a list of keys of keys will end. We'll have to
            search for the first non-numeric value
            """
            l_isNumber = nvb_utils.isNumber
            return next((i for i, v in enumerate(ascii_lines)
                         if not l_isNumber(v[0])), -1)

        self.nodeidx = nodeidx
        properties_list = [  # For easier parsing
            [type(self).emitter_properties, self.emitter_data],
            [type(self).object_properties, self.object_data]]
        l_isNumber = nvb_utils.isNumber
        for i, line in enumerate(ascii_lines):
            try:
                label = line[0].lower()
            except (IndexError, AttributeError):
                continue  # Probably empty line, skip it
            else:
                if l_isNumber(label):
                    continue
            if label == 'node':
                self.nodetype = line[1].lower()
                self.name = nvb_utils.str2identifier(line[2])
            elif label == 'endnode':
                return
            elif label == 'parent':
                self.parentName = nvb_utils.str2identifier(line[1])
            # Animeshes
            elif label == 'sampleperiod':
                # Stock GUI models write "1.#INF" for a single sample; like
                # cleanmodels, keep the default (0) for what isn't a number
                try:
                    self.sampleperiod = float(line[1])
                except ValueError:
                    self.sampleperiod = 0.0
                if not math.isfinite(self.sampleperiod):
                    self.sampleperiod = 0.0
            elif label == 'faces':
                if not self.facedef:
                    valcnt = int(line[1])
                    self.facedef = [list(map(int, v))
                                    for v in ascii_lines[i+1:i+valcnt+1]]
            elif label == 'animverts':
                if not self.animverts:
                    valcnt = int(line[1])
                    self.animverts = [list(map(float, v))
                                      for v in ascii_lines[i+1:i+valcnt+1]]
                    self.shapedata = True
            elif label == 'animtverts':
                if not self.animtverts:
                    valcnt = int(line[1])
                    self.animtverts = [(float(v[0]), float(v[1]))
                                       for v in ascii_lines[i+1:i+valcnt+1]]
                    self.uvdata = True
            else:  # Check for keys
                key_name = label
                key_is_single = True
                if key_name.endswith('key'):
                    key_is_single = False
                    key_name = key_name[:-3]
                for key_def, key_data in properties_list:
                    if key_name in key_def and key_name not in key_data:
                        data_path = key_def[key_name][0]
                        data_dim = key_def[key_name][1]
                        # key_converter = key_def[key_name][2]
                        if key_is_single:
                            data = [[0.0] + list(map(float,
                                    line[1:data_dim+1]))]
                        else:
                            keycnt = find_end(ascii_lines[i+1:])
                            data = [list(map(float, v[:data_dim+1]))
                                    for v in ascii_lines[i+1:i+keycnt+1]]
                        # values = \
                        # [[float(v[0])] + list(map(key_converter, v[1:]))
                        #  for v in values]
                        key_data[key_name] = [data, data_path, data_dim]
                        break

    def create_data_object(self, obj, anim, options):
        """Creates animations in object actions."""
        def data_conversion(label, obj, vals, options):
            if label == 'orientation':
                if obj.rotation_mode == 'AXIS_ANGLE':
                    dp = 'rotation_axis_angle'
                    dp_dim = 4
                    new_values = [[v[3], v[0], v[1], v[2]] for v in vals]
                elif obj.rotation_mode == 'QUATERNION':
                    dp = 'rotation_quaternion'
                    dp_dim = 4
                    quats = [mathutils.Quaternion(v[0:3], v[3]) for v in vals]
                    new_values = [[q.w, q.x, q.y, q.z] for q in quats]
                else:
                    dp = 'rotation_euler'
                    dp_dim = 3
                    # Run an euler filer
                    prev_eul = mathutils.Euler()
                    new_values = []
                    for v in vals:
                        quat = mathutils.Quaternion(v[0:3], v[3])
                        eul = quat.to_euler('XYZ', prev_eul)
                        #  eul = nvb_utils.eulerFilter(quat.to_euler(),
                        #  prev_eul)
                        new_values.append(eul)
                        prev_eul = eul
            elif label == 'position':
                scl = options.anim_scale
                dp = 'location'
                dp_dim = 3
                if scl:
                    new_values = [[l * scl for l in loc] for loc in vals]
                else:
                    new_values = vals
            elif label == 'scale':
                dp = 'scale'
                dp_dim = 3
                new_values = [v*dp_dim for v in vals]
            elif label == 'selfillumcolor':
                dp = 'nvb.selfillum'
                dp_dim = 3
                new_values = [v*dp_dim for v in vals]
            elif label == 'alpha':
                dp = 'nvb.alpha'
                dp_dim = 1
                new_values = [v*dp_dim for v in vals]

            return new_values, dp, dp_dim

        fps = options.scene.render.fps
        frame_start = anim.frameStart
        action = nvb_utils.get_action(obj, options.mdlname + '.' + obj.name)
        for label, (data, data_path, data_dim) in self.object_data.items():
            frames = [round(fps * d[0], 3) + frame_start for d in data]
            if not data_path:  # Needs conversion
                values, dp, dp_dim = data_conversion(
                    label, obj, [d[1:data_dim+1] for d in data], options)
            else:
                values = [d[1:data_dim+1] for d in data]
                dp = data_path
                dp_dim = data_dim
            Animnode.insert_kfp(frames, values, action, dp, dp_dim, target=obj)

    def create_data_emitter(self, obj, anim, options):
        """Creates animations in emitter actions."""

        part_sys = obj.particle_systems.active
        if not part_sys:
            return
        part_settings = part_sys.settings
        if not part_settings:
            return
        fps = options.scene.render.fps
        frame_start = anim.frameStart
        action = nvb_utils.get_action(part_settings, part_settings.name)
        for label, (data, data_path, data_dim) in self.emitter_data.items():
            frames = [round(fps * d[0], 3) + frame_start for d in data]
            values = [d[1:data_dim+1] for d in data]
            dp = data_path
            dp_dim = data_dim
            if dp.startswith('nvb'):  # Group custom properties
                Animnode.insert_kfp(frames, values, action, dp, dp_dim,
                                    'Aurora Emitter', target=part_settings)
            else:
                Animnode.insert_kfp(frames, values, action, dp, dp_dim,
                                    target=part_settings)

    def create_data_shape(self, obj, anim, animlength, options):
        """Import animated vertices as shapekeys."""
        # The samples are as many as the data holds: the game stores one set
        # of vertices per sample, which need not be length/period + 1 (a GUI
        # frame stores a single sample for a 1s animation).
        vert_cnt = len(obj.data.vertices)
        if vert_cnt == 0 or len(self.animverts) % vert_cnt != 0:
            print("Neverblender: WARNING - animvert sample size mismatch: " +
                  obj.name)
            return
        sample_cnt = len(self.animverts) // vert_cnt
        if sample_cnt > 1 and self.sampleperiod <= 0.00001:
            print("Neverblender: WARNING - sampleperiod period is 0 for " +
                  obj.name)
            return

        fps = options.scene.render.fps
        frame_start = anim.frameStart
        # Add Basis key holding original mesh data
        shape_keys = obj.data.shape_keys
        if not shape_keys or 'Basis' not in shape_keys.key_blocks:
            sk = obj.shape_key_add(name='Basis', from_mix=False)
            shape_keys = obj.data.shape_keys  # Might be created now
            shape_keys.name = options.mdlname + '.' + obj.name + '.sk'
        shape_keys.use_relative = False
        # Add absolute shape Keys
        sk_frame_list = []
        for idx in range(sample_cnt):
            sk_name = anim.name + str(idx)
            sk = obj.shape_key_add(name=sk_name, from_mix=False)
            sk_frame_list.append(sk.frame)
            sk_values = self.animverts[idx*vert_cnt:(idx+1)*vert_cnt]
            sk_values = [c for coords in sk_values for c in coords]
            sk.data.foreach_set('co', sk_values)
        # Get action, create one if necessary
        action = nvb_utils.get_action(shape_keys, shape_keys.name)
        # Insert keyframes
        kfOptions = {'FAST'}
        sample_dist = fps * self.sampleperiod
        fcu = nvb_utils.get_fcurve(action, 'eval_time', 0, target=shape_keys)
        for idx, eval_time in enumerate(sk_frame_list):
            kfp_frame = frame_start + (idx * sample_dist)
            fcu.keyframe_points.insert(kfp_frame, eval_time, options=kfOptions)
        fcu.update()

    def create_data_uv(self, obj, anim, animlength, options):
        """Import animated texture coordinates."""
        # One sample holds a coordinate per texture vertex the faces use (or,
        # in compiled models, per vertex); the samples are as many as the data
        # holds, which need not be length/period + 1.
        # Each face corner takes the sample value of its texture vertex, as
        # the mesh's faces give it (kept when this import created the mesh),
        # else as the animation's copy of the faces does, without the faces
        # that use a vertex twice (dropped from the mesh, see
        # Trimesh.clamp_faces).
        vert_cnt = len(obj.data.vertices)
        face_uv_indices = options.mesh_face_tverts.get(obj.data.name)
        if face_uv_indices is None or len(face_uv_indices) != len(obj.data.loops):
            facedef = [f for f in self.facedef
                       if len({min(max(0, i), vert_cnt - 1) for i in f[0:3]}) == 3]
            face_uv_indices = unpack_list([tuple(f[4:7]) for f in facedef])
        if len(face_uv_indices) != len(obj.data.loops):
            print("Neverblender: WARNING - animtvert face mismatch: " +
                  obj.name)
            return
        sample_size = 0
        for size in (max(face_uv_indices, default=-1) + 1, vert_cnt):
            if size > 0 and len(self.animtverts) % size == 0 and size > max(face_uv_indices, default=-1):
                sample_size = size
                break
        if not sample_size:
            print("Neverblender: WARNING - animtvert sample size mismatch: " +
                  obj.name)
            return
        if len(self.animtverts) // sample_size > 1 and self.sampleperiod <= 0.00001:
            print("Neverblender: WARNING - sampleperiod period is 0 for " +
                  obj.name)
            return
        # One 3D attribute per sample and face corner: (u, v, 0). Blender
        # allows only 8 UV maps per mesh, and 2D corner attributes count as
        # UV maps from Blender 3.5 on, 3D ones never do.
        sample_fstr = Animnode.animtverts_prefix(anim) + '{:d}'
        sampler = enumerate(zip(*[iter(self.animtverts)] * sample_size))
        for sample_idx, sample in sampler:
            coords = unpack_list([(*sample[i], 0.0) for i in face_uv_indices])
            attr = obj.data.attributes.new(sample_fstr.format(sample_idx),
                                           'FLOAT_VECTOR', 'CORNER')
            attr.data.foreach_set('vector', coords)

    @staticmethod
    def animtverts_prefix(anim):
        """Name prefix of an animation's UV samples (attributes or, in files
        made before 4.4.0, UV maps)."""
        return 'animtverts.' + anim.name + '.'

    @staticmethod
    def sampleperiod_prop(anim):
        """Name of the mesh property that keeps an animation's sample period."""
        return 'sampleperiod.' + anim.name

    @staticmethod
    def get_shape_samples(obj, anim):
        """The shape key samples of an animation: (frame, eval_time) of each
        eval_time keyframe in it, or [] if there are none."""
        shape_keys = obj.data.shape_keys
        if not shape_keys or shape_keys.use_relative or not shape_keys.key_blocks:
            return []
        try:
            action = shape_keys.animation_data.action
        except AttributeError:
            return []
        fcurves = nvb_utils.get_action_fcurves(action, shape_keys)
        fcu = fcurves.find(data_path='eval_time', index=0) if fcurves else None
        if not fcu:
            return []
        return [(k.co[0], k.co[1]) for k in fcu.keyframe_points
                if anim.frameStart <= round(k.co[0], 5) <= anim.frameEnd + 0.04]

    @staticmethod
    def animesh_sample_period(obj, anim, num_samples, options):
        """The time between an animation's samples: where its shape key
        samples are, else as imported, else the samples spread over the
        animation (a single sample spans all of it)."""
        fps = options.scene.render.fps
        frames = [f for f, _ in Animnode.get_shape_samples(obj, anim)]
        period = obj.data.get(Animnode.sampleperiod_prop(anim))
        if len(frames) >= 2:
            keyed = (frames[1] - frames[0]) / fps
            # Keyframe times are single precision: write the imported
            # period back exactly unless the keys were moved
            if period and abs(keyed - period) <= 1e-4 * period:
                return period
            return keyed
        if period:
            return period
        anim_length = (anim.frameEnd - anim.frameStart) / fps
        return anim_length / max(num_samples - 1, 1)

    @staticmethod
    def get_animtvert_samples(mesh, anim):
        """An animation's UV samples, in order: per sample, (u, v) per face corner."""
        prefix = Animnode.animtverts_prefix(anim)

        def index(name):
            suffix = name[len(prefix):]
            return int(suffix) if suffix.isdigit() else None
        samples = {}
        # Neverblender 4.3 and earlier stored them as UV maps
        for uvl in mesh.uv_layers:
            if uvl.name.startswith(prefix) and index(uvl.name) is not None:
                samples[index(uvl.name)] = [tuple(d.uv) for d in uvl.data]
        for attr in mesh.attributes:
            if attr.name.startswith(prefix) and index(attr.name) is not None and \
               attr.domain == 'CORNER' and attr.data_type == 'FLOAT_VECTOR':
                samples[index(attr.name)] = [tuple(d.vector[:2]) for d in attr.data]
        return [samples[k] for k in sorted(samples)]

    @staticmethod
    def create_restpose(obj, frame=1):
        """TODO: DOC."""
        def insert_kfp(fcurves, frame, val, dim):
            """TODO: DOC."""
            for j in range(dim):
                fcurves[j].keyframe_points.insert(frame, val[j],
                                                  options={'FAST'})
        # Get animation data
        animData = obj.animation_data
        if not animData:
            return  # No data = no animation = no need for rest pose
        # Get action
        action = animData.action
        if not action:
            return  # No action = no animation = no need for rest pose
        # Get fcurves using our compatibility helper
        fcurves = nvb_utils.get_action_fcurves(action, obj)
        if not fcurves:
            return
        if obj.rotation_mode == 'AXIS_ANGLE':
            dp = 'rotation_axis_angle'
            fcu = [fcurves.find(data_path=dp, index=i)
                   for i in range(4)]
            if fcu.count(None) < 1:
                rr = obj.nvb.restrot
                insert_kfp(fcu, frame, [rr[3], rr[0], rr[1], rr[2]], 4)
        if obj.rotation_mode == 'QUATERNION':
            dp = 'rotation_quaternion'
            fcu = [fcurves.find(data_path=dp, index=i)
                   for i in range(4)]
            if fcu.count(None) < 1:
                rr = obj.nvb.restrot
                q = mathutils.Quaternion((rr[0], rr[1], rr[2]), rr[3])
                insert_kfp(fcu, frame, [q.w, q.x, q.y, q.z], 4)
        else:
            dp = 'rotation_euler'
            fcu = [fcurves.find(data_path=dp, index=i)
                   for i in range(3)]
            if fcu.count(None) < 1:
                eul = mathutils.Quaternion(obj.nvb.restrot[:3],
                                           obj.nvb.restrot[3]).to_euler()
                insert_kfp(fcu, frame, eul, 3)
        fcu = [fcurves.find(data_path='location', index=i)
               for i in range(3)]
        if fcu.count(None) < 1:
            insert_kfp(fcu, frame, obj.nvb.restloc, 3)

    def create(self, obj, anim, animlength, options):
        """TODO:Doc."""
        if self.object_data:
            self.create_data_object(obj, anim, options)
        if self.emitter_data:
            self.create_data_emitter(obj, anim, options)
        # Animmesh data, do some sanity checks or things can go horribly wrong
        if self.uvdata or self.shapedata:
            # Sanity Check: No mesh
            if not obj.data:
                print("Neverblender: WARNING - No mesh data for " +
                    obj.name)
                return
            # A sample period of 0 is fine for a single sample only (see
            # create_data_shape and create_data_uv)
            # The samples are as many as the data holds, so the animation
            # length need not be a multiple of the period (and in floating
            # point rarely is exactly: 27 stock animmeshes were skipped).
            # Import animesh as UV sample attributes and shapekeys
            if obj.nvb.meshtype == nvb_def.Meshtype.ANIMMESH:
                # UV samples have no keyframes to keep their timing by
                if self.sampleperiod > 0.00001:
                    obj.data[Animnode.sampleperiod_prop(anim)] = self.sampleperiod
                if self.uvdata:
                    self.create_data_uv(obj, anim, animlength, options)
                if self.shapedata:
                    self.create_data_shape(obj, anim, animlength, options)

    @staticmethod
    def get_keys_emitter(psy, anim, key_data, options):
        """Get keys from particle settings."""
        action = psy.animation_data.action
        if not action:
            return
        fps = options.scene.render.fps
        anim_start = anim.frameStart
        anim_end = anim.frameEnd
        # List of exportable data paths with formats and conversion functions
        exports = []
        for aur_name, (dp, dp_dim, _, aur_fstr) in \
                Animnode.emitter_properties.items():
            exports.append([aur_name, dp_dim, aur_fstr, dp, dp_dim])
        # Get keyframe data
        all_fcurves = nvb_utils.get_action_fcurves(action, psy)
        if all_fcurves is None:
            return
        for aur_name, aur_dim, aur_fstr, dp, dp_dim in exports:
            fcu = [all_fcurves.find(data_path=dp, index=i)
                   for i in range(dp_dim)]
            if fcu.count(None) < dp_dim:  # ignore empty fcurves
                keyed_frames = list(set().union(
                    *[[k.co[0] for k in fcu[i].keyframe_points
                       if anim_start <= round(k.co[0], 5) <= anim_end + 0.04]
                      for i in range(dp_dim)]))
                keyed_frames.sort()
                aur_values = [[fcu[i].evaluate(f) for i in range(dp_dim)]
                              for f in keyed_frames]
                aur_times = [(f - anim_start) / fps for f in keyed_frames]
                aur_keys = list(zip(aur_times, aur_values))
                key_data.append([aur_name, aur_keys, aur_dim * aur_fstr])

    @staticmethod
    def get_keys_object(obj, anim, key_data, options):
        """Get keys from object actions."""
        def get_exports(rot_mode):
            """Get a list of data paths to export."""
            # [value name, value dimension, value format,
            #  data path, data path dimension, conversion function, default]
            exports = [
                ['scale', 1, ' {:> 6.5f}',
                 'scale', 1, None, [1.0]],
                ['selfillumcolor', 3, ' {:>4.2f}',
                 'nvb.selfillum', 3, None, [0.0, 0.0, 0.0]],
                ['color', 3, ' {:>4.2f}',
                 'color', 3, None, [0.0, 0.0, 0.0]],
                ['radius', 1, ' {:>6.5f}',
                 'shadow_soft_size', 1, None, [1.0]],
                ['position', 3, ' {:> 6.5f}',
                 'location', 3, convert_loc, [0.0, 0.0, 0.0]],
                ['alpha', 1, ' {:>4.2f}',
                 'nvb.alpha', 1, None, [1.0]]]
            if obj.rotation_mode == 'AXIS_ANGLE':
                exports.append(['orientation', 4, ' {:> 6.5f}',
                                'rotation_axis_angle', 4, convert_axan,
                                [1.0, 0.0, 0.0, 0.0]])
            elif obj.rotation_mode == 'QUATERNION':
                exports.append(['orientation', 4, ' {:> 6.5f}',
                                'rotation_quaternion', 4, convert_quat,
                                [1.0, 0.0, 0.0, 0.0]])
            else:
                exports.append(['orientation', 4, ' {:> 6.5f}',
                                'rotation_euler', 3, convert_eul,
                                [0.0, 0.0, 0.0]])
            return exports

        def convert_loc(obj, kfvalues):
            pinv = obj.matrix_parent_inverse
            return [(pinv @ mathutils.Matrix.Translation(v)).to_translation()
                    for v in kfvalues]

        def convert_eul(obj, kfvalues):
            pinv = obj.matrix_parent_inverse
            mats = [pinv @ mathutils.Euler(v, 'XYZ').to_matrix().to_4x4()
                    for v in kfvalues]
            return [[*q.axis, q.angle] for q in
                    [m.to_quaternion() for m in mats]]

        def convert_axan(obj, kfvalues):
            pinv = obj.matrix_parent_inverse
            mats = \
                [pinv @ mathutils.Quaternion(v[1:], v[0]).to_matrix().to_4x4()
                 for v in kfvalues]
            return [[*q.axis, q.angle] for q in
                    [m.to_quaternion() for m in mats]]

        def convert_quat(obj, kfvalues):
            pinv = obj.matrix_parent_inverse
            mats = [pinv @ mathutils.Quaternion(v).to_matrix().to_4x4()
                    for v in kfvalues]
            return [[*q.axis, q.angle] for q in
                    [m.to_quaternion() for m in mats]]

        # TODO: action = obj.data.animation_data.action
        # Now we're dealing with multiple actions per object? Thanks
        action_list = []
        # Get the action from the object
        try:
            action = obj.animation_data.action
        except AttributeError:
            pass
        else:
            action_list.append(action)
        # Get the action from the object's data
        try:
            action = obj.data.animation_data.action
        except AttributeError:
            pass
        else:
            action_list.append(action)

        if not action_list:
            return

        for action in action_list:
            # Grab animation meta data
            fps = options.scene.render.fps
            anim_start = anim.frameStart
            anim_end = anim.frameEnd
            # List of exportable data paths with formats and conversion functions
            exports = get_exports(obj.rotation_mode)
            # Get keyframe data
            all_fcurves = nvb_utils.get_action_fcurves(action, obj)
            if all_fcurves is None:
                return
            for aur_name, aur_dim, aur_fstr, dp, dp_dim, dp_conversion, default_val in exports:
                fcu = [all_fcurves.find(data_path=dp, index=i)
                    for i in range(dp_dim)]
                if fcu.count(None) < dp_dim:  # ignore empty fcurves
                    keyed_frames = list(set().union(
                        *[[k.co[0] for k in fcu[i].keyframe_points
                        if anim_start <= round(k.co[0], 5) <= anim_end+0.04]
                        for i in range(dp_dim) if fcu[i]]))
                    keyed_frames.sort()
                    # Get values at keyed frames and convert
                    values = [[fcu[i].evaluate(f) if fcu[i] else default_val[i]
                            for i in range(dp_dim)] for f in keyed_frames]
                    # values = [[fcu[i].evaluate(f) for i in range(dp_dim)]
                    #           for f in frames]
                    # Convert to the format used by MDLs
                    if dp_conversion is not None:
                        aur_values = dp_conversion(obj, values)
                    else:
                        aur_values = values
                    aur_times = [(f - anim_start) / fps for f in keyed_frames]
                    aur_keys = list(zip(aur_times, aur_values))
                    key_data.append([aur_name, aur_keys, aur_dim * aur_fstr])

    @staticmethod
    def generate_ascii_keys(obj, anim, asciiLines, options):
        """TODO: DOC."""
        key_data = []

        # 1. Object animation data
        Animnode.get_keys_object(obj, anim, key_data, options)
        # 2. particle System/Emitter animation data
        part_sys = obj.particle_systems.active
        if part_sys and part_sys.settings.animation_data:
            Animnode.get_keys_emitter(part_sys.settings,
                                      anim,
                                      key_data,
                                      options)
        # Add keys to ascii lines
        time_fstr = '{:> 6.3f}'
        for key_name, keys, val_fstr in key_data:
            num_keys = len(keys)
            if num_keys > 0:  # Create a key list
                asciiLines.append('    ' + key_name + 'key ' + str(num_keys))
                fstr = '      ' + time_fstr + val_fstr
                asciiLines.extend([fstr.format(k[0], *k[1]) for k in keys])
                asciiLines.append('    endlist')

    @staticmethod
    def generate_ascii_animesh_shapes(obj, anim, ascii_lines, options,
                                      required_samples=0):
        """Add data for animated vertices."""
        # Must be absolute shapekeys, keyed by eval_time
        eval_times = [et for _, et in Animnode.get_shape_samples(obj, anim)]
        if not eval_times:
            return -1
        key_blocks = obj.data.shape_keys.key_blocks

        # rel_kb = [(kb.frame, kb.data) for kb in key_blocks if not kb.mute]
        anim_verts = []
        for et in eval_times:
            # Each eval time is influenced by two shape keys max
            shape_key0 = next((kb for kb in reversed(key_blocks)
                               if kb.frame <= et), None)
            shape_key1 = next((kb for kb in key_blocks
                               if kb.frame >= et), shape_key0)
            interval = [shape_key0.frame, shape_key1.frame]
            factor = [et/sum(interval), 1.0-et/sum(interval)]
            values = [(factor[0] * d0.co) + (factor[1] * d1.co) for d0, d1 in
                      zip(shape_key0.data, shape_key1.data)]
            anim_verts.append(values)

        # Misc data for export
        if not anim_verts:
            return -1

        num_samples = len(eval_times)
        num_verts = len(anim_verts[0])
        if required_samples > 0:
            # Not necessary to add meta data
            # BUT: Sanity check
            if required_samples != num_samples:
                print("Neverblender: " +
                    "WARNING - anim verts/tverts mismatch: " + obj.name)
                return -1
        else:
            # Add meta data
            ascii_lines.append('    clipu 0.0')
            ascii_lines.append('    clipv 0.0')
            ascii_lines.append('    clipw 1.0')
            ascii_lines.append('    cliph 1.0')

            sample_period = Animnode.animesh_sample_period(obj, anim, num_samples, options)
            ascii_lines.append('    sampleperiod ' +
                            '{:.7g}'.format(sample_period))
        # Create ascii representation and add it to the output
        ascii_lines.append('    animverts ' + str(num_samples * num_verts))
        fstr = '     ' + 3 * ' {: 8.5f}'
        for av in anim_verts:
            ascii_lines.extend([fstr.format(*v) for v in av])
        ascii_lines.append('    endlist')

        return num_samples

    @staticmethod
    def generate_ascii_animesh_uv(obj, anim, ascii_lines, options,
                                  required_samples=0):
        """Add data for animated texture coordinates."""
        blen_mesh = obj.data
        if not blen_mesh:
            return -1
        anim_uv_samples = Animnode.get_animtvert_samples(blen_mesh, anim)
        # No anim tverts
        if not anim_uv_samples:
            return -1
        # Misc data for export
        num_samples = len(anim_uv_samples)
        num_tverts = len(anim_uv_samples[0])
        if required_samples > 0:
            # Not necessary to add meta data
            # BUT: Sanity check
            if required_samples != num_samples:
                print("Neverblender: " +
                      "WARNING - anim verts/tverts mismatch: " + obj.name)
                return -1
        else:
            # Add meta data
            ascii_lines.append('    clipu 0.0')
            ascii_lines.append('    clipv 0.0')
            ascii_lines.append('    clipw 1.0')
            ascii_lines.append('    cliph 1.0')

            sample_period = Animnode.animesh_sample_period(obj, anim, num_samples, options)
            ascii_lines.append('    sampleperiod ' +
                               '{:.7g}'.format(sample_period))
        # Create ascii representation and add it to the output
        ascii_lines.append('    animtverts ' + str(num_samples * num_tverts))
        fstr = '      {: 7.4f} {: 7.4f}  0'
        uv_coord_list = [[tuple(map(lambda x: round(x, 4), uv))
                         for uv in sample] for sample in anim_uv_samples]
        for coords in uv_coord_list:
            ascii_lines.extend([fstr.format(c[0], c[1]) for c in coords])
        ascii_lines.append('    endlist')

        return num_samples

    @staticmethod
    def generate_ascii_animesh(obj, anim, ascii_lines, options):
        """TODO:Doc."""
        if not obj.data:
            return
        # Check if the object is an animmesh:
        if (obj.type != 'MESH') or \
           (obj.nvb.meshtype != nvb_def.Meshtype.ANIMMESH):
            return
        tmp_lines = []
        nvb_node.Animmesh.generateAsciiMesh(obj, tmp_lines, options)
        ascii_lines.extend(['  ' + l for l in tmp_lines])
        samples = -1  # Samples > 0 also means not to write metadata (again)
        samples = Animnode.generate_ascii_animesh_uv(obj, anim, ascii_lines,
                                                     options, samples)
        Animnode.generate_ascii_animesh_shapes(obj, anim, ascii_lines,
                                               options, samples)

    @staticmethod
    def generate_ascii(obj, anim, ascii_lines, options):
        """TODO:Doc."""
        if not obj:
            return
        # Type + Name
        node_type = nvb_utils.getNodeType(obj)
        node_name = nvb_utils.generate_node_name(obj, options.strip_trailing)
        ascii_lines.append('  node ' + node_type + ' ' + node_name)
        # Parent
        parent_name = nvb_utils.generate_node_name(obj.parent,
                                                   options.strip_trailing)
        ascii_lines.append('    parent ' + parent_name)
        Animnode.generate_ascii_animesh(obj, anim, ascii_lines, options)
        Animnode.generate_ascii_keys(obj, anim, ascii_lines, options)
        ascii_lines.append('  endnode')
