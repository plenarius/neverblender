"""Export tests: smoothing groups, MTR files, shadow, tile walkmesh, run inside Blender.

Run with scripts/tests/run_tests.sh (it enables the add-on from a scratch
user scripts folder):
    blender -b --factory-startup --python scripts/tests/test_export.py -- <outdir>
"""

import contextlib
import io
import math
import os
import random
import signal
import sys

import addon_utils
import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nvbtest  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(argv[0] if argv else 'nvb_test_out')
os.makedirs(OUT, exist_ok=True)

addon_utils.enable('neverblender', default_set=True)
import neverblender  # noqa: E402,F401  (registered by addon_utils.enable)
from neverblender import nvb_utils, nvb_def  # noqa: E402

PREFS = bpy.context.preferences.addons['neverblender'].preferences
PREFS.cleanmodels_import = False  # Neverblender's own reader (shadow test)
R = nvbtest.Results()
SECTION_TIMEOUT = 180


def _timeout(signum, frame):
    raise TimeoutError('section took over {} s'.format(SECTION_TIMEOUT))


signal.signal(signal.SIGALRM, _timeout)
print('Blender', bpy.app.version_string)


def clear():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for item in list(coll):
            coll.remove(item)


def make_base(name):
    base = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(base)
    base.nvb.classification = nvb_def.Classification.UNKNOWN
    return base


def make_mesh(base, name, verts, faces, smooth=True, sharp=()):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = smooth
    sharp = {tuple(sorted(e)) for e in sharp}
    for e in me.edges:
        if tuple(sorted(e.vertices)) in sharp:
            e.use_edge_sharp = True
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = base
    return obj


def export(base, name, mode='GROUP', distinct=False, walkmesh=False, compile_binary=False):
    """Export base; return (path, console output)."""
    PREFS.export_smoothgroups_distinct_verts = distinct
    for o in bpy.context.scene.objects:
        o.select_set(False)
    base.select_set(True)
    bpy.context.view_layer.objects.active = base
    path = os.path.join(OUT, name + '.mdl')
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        bpy.ops.scene.nvb_mdlexport(filepath=path, export_walkmesh=walkmesh, export_animations=False,
                                    cleanmodels_check=False, cleanmodels_compile=compile_binary,
                                    export_smoothing_mode=mode)
    text = out.getvalue()
    sys.stdout.write(text)
    return path, text


def groups_of(path):
    return [f[3] for _, _, faces in nvbtest.parse_meshes(path) for f in faces]


def section(title):
    """Run a test section; an exception fails it without stopping the others."""
    def wrap(fn):
        signal.alarm(SECTION_TIMEOUT)  # The old Distinct colouring could run for hours
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            R.check(False, title, repr(e)[:300])
        finally:
            signal.alarm(0)
        return fn
    return wrap


base = obj = mat = None


def two_regions_at_a_vertex():
    # Region A folds up on the -x side, region B lies flat on the +x side;
    # they share vertex 0 and no edge.
    verts = [(0, 0, 0),
             (-1, 1, 1), (-1.2, 0, 1.3), (-1, -1, 1),   # A
             (1, 1, 0), (1.2, 0, -0.1), (1, -1, 0)]     # B
    faces = [(0, 1, 2), (0, 2, 3), (0, 4, 5), (0, 5, 6)]
    # Mesh face order puts B after A, so B's corner at 0 would take A's normal
    return verts, faces


@section('Fix 1: two smooth regions that touch only at a vertex')
def section_0():
    global base, obj, mat
    for distinct in (False, True):
        clear()
        base = make_base('t_vtxonly')
        v, f = two_regions_at_a_vertex()
        make_mesh(base, 't_vtxonly_m', v, f)
        path, _ = export(base, 't_vtxonly' + ('_d' if distinct else ''), distinct=distinct)
        g = groups_of(path)
        bad = nvbtest.file_bad_corners(path)
        R.check(bad == 0 and (g[0] & g[2]) == 0 and g[0] == g[1] and g[2] == g[3],
                'fix1 regions touching at a vertex get distinct groups (distinct={})'.format(distinct),
                'groups {} bad corners {}'.format(g, bad))


@section('A flat-shaded icosphere: every face its own region, five at each vertex')
def section_1():
    global base, obj, mat
    for distinct in (False, True):
        clear()
        base = make_base('t_ico')
        bm = bmesh.new()
        if bpy.app.version >= (3, 0, 0):
            bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
        me = bpy.data.meshes.new('t_ico_m')
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = False
        obj = bpy.data.objects.new('t_ico_m', me)
        bpy.context.scene.collection.objects.link(obj)
        obj.parent = base
        path, _ = export(base, 't_ico' + ('_d' if distinct else ''), distinct=distinct)
        bad = nvbtest.file_bad_corners(path)
        R.check(bad == 0, 'fix1 flat icosphere shades flat in game (distinct={})'.format(distinct),
                'bad corners {}'.format(bad))


def grid(nx, ny, seed=1):
    rnd = random.Random(seed)
    verts = [(x * 0.1, y * 0.1, rnd.uniform(0, 0.05)) for y in range(ny + 1) for x in range(nx + 1)]
    faces = [(y * (nx + 1) + x, y * (nx + 1) + x + 1, (y + 1) * (nx + 1) + x + 1, (y + 1) * (nx + 1) + x)
             for y in range(ny) for x in range(nx)]
    return verts, faces


@section('Fix 2: Distinct on dense meshes')
def section_2():
    global base, obj, mat
    clear()
    base = make_base('t_flat1500')
    v, f = grid(50, 30)  # 1,500 quads, 3,000 triangles, flat
    make_mesh(base, 't_flat1500_m', v, f, smooth=False)
    try:
        path, text = export(base, 't_flat1500', distinct=True)
        ok = os.path.isfile(path) and len(groups_of(path)) == 3000
        bad = nvbtest.file_bad_corners(path)
        R.check(ok and bad == 0 and 'RecursionError' not in text,
                'fix2 Distinct on a flat 1,500-face mesh', 'bad corners {}'.format(bad))
    except RecursionError as e:
        R.check(False, 'fix2 Distinct on a flat 1,500-face mesh', repr(e))


@section('Every quad its own smooth region (all quad borders sharp): 1,500 regions')
def section_3():
    global base, obj, mat
    # of two faces, four regions at each inner vertex
    clear()
    base = make_base('t_quads')
    v, f = grid(50, 30, seed=2)
    sharp = set()
    for q in f:
        for i in range(4):
            sharp.add((q[i], q[(i + 1) % 4]))
    make_mesh(base, 't_quads_m', v, f, smooth=True, sharp=sharp)
    for distinct in (False, True):
        path, text = export(base, 't_quads' + ('_d' if distinct else ''), distinct=distinct)
        g = groups_of(path)
        bad = nvbtest.file_bad_corners(path)
        R.check(len(g) == 3000 and bad == 0 and 'smoothing regions need more than' not in text,
                'fix2 1,500 two-face regions colour without overflow (distinct={})'.format(distinct),
                'bad corners {}'.format(bad))


@section('More regions around one vertex than there are bits: 33 two-face regions at')
def section_4():
    global base, obj, mat
    # the apex of a cone. Must export, and say so in the log.
    clear()
    base = make_base('t_cone')
    n = 66
    verts = [(0, 0, 1)] + [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0) for i in range(n)]
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    sharp = [(0, 1 + i) for i in range(0, n, 2)]  # every other spoke: 33 regions
    make_mesh(base, 't_cone_m', verts, faces, smooth=True, sharp=sharp)
    for distinct in (False, True):
        path, text = export(base, 't_cone' + ('_d' if distinct else ''), distinct=distinct)
        g = groups_of(path)
        R.check(len(g) == n and all(x > 0 for x in g) and 'need more than 31 smoothing groups' in text,
                'fix2 more regions than bits: exported, and the log says so (distinct={})'.format(distinct),
                'groups {} log {!r}'.format(sorted(set(g)), text[-400:]))


@section('The colouring itself on a random region graph, checked by the conflict test')
def section_5():
    global base, obj, mat
    rnd = random.Random(5)
    face_verts = [tuple(rnd.sample(range(4000), 3)) for _ in range(6000)]
    region_ids = [rnd.randrange(2500) for _ in range(6000)]
    graph = nvb_utils.AuroraSmoothgroupGraph()
    groups = graph.colour_regions(region_ids, face_verts)
    if graph.overflow_regions == 0:
        R.check(not nvb_utils.smoothgroups_conflict(region_ids, face_verts, groups),
                'fix2 colouring of 2,500 random regions has no conflicts')
    else:
        R.check(False, 'fix2 colouring of 2,500 random regions has no conflicts',
                'overflow {}'.format(graph.overflow_regions))


cube_v = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
cube_f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]

@section('Fix 3: Smoothing None writes group 0, Split group 1')
def section_6():
    global base, obj, mat
    clear()
    base = make_base('t_cube')
    make_mesh(base, 't_cube_m', cube_v, cube_f)
    path, _ = export(base, 't_cube_none', mode='NONE')
    g = groups_of(path)
    R.check(len(g) == 12 and set(g) == {0} and nvbtest.file_bad_corners(path) == 0,
            'fix3 Smoothing None writes group 0', str(sorted(set(g))))
    path, _ = export(base, 't_cube_split', mode='SPLIT')
    g = groups_of(path)
    R.check(len(g) == 12 and set(g) == {1}, 'fix3 Smoothing Split writes group 1', str(sorted(set(g))))


def textured_material(name, diffuse, normal=None):
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = [nd for nd in nt.nodes if nd.type == 'BSDF_PRINCIPLED'][0]
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.new(diffuse, 4, 4)
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    if normal:
        ntex = nt.nodes.new('ShaderNodeTexImage')
        ntex.image = bpy.data.images.new(normal, 4, 4)
        nmap = nt.nodes.new('ShaderNodeNormalMap')
        nt.links.new(ntex.outputs['Color'], nmap.inputs['Color'])
        nt.links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def mdl_lines(path):
    with open(path, encoding='latin-1') as f:
        return [ln.strip() for ln in f.read().splitlines()]


@section('Fix 4: an MTR only when the material needs one')
def section_7():
    global base, obj, mat
    for f_ in os.listdir(OUT):
        if f_.endswith('.mtr'):
            os.remove(os.path.join(OUT, f_))
    clear()
    base = make_base('t_mtr_diff')
    obj = make_mesh(base, 't_mtr_diff_m', cube_v, cube_f)
    mat = textured_material('t_diffmat', 't_difftex')
    obj.data.materials.append(mat)
    R.check(mat.nvb.mtr.use, 'fix4 Use MTR stays on by default')
    path, _ = export(base, 't_mtr_diff')
    lines = mdl_lines(path)
    R.check('bitmap t_difftex' in lines and not os.path.exists(os.path.join(OUT, 't_diffmat.mtr')),
            'fix4 diffuse-only material: bitmap in the MDL, no MTR',
            str([ln for ln in lines if ln.startswith(('bitmap', 'materialname'))]))

    clear()
    base = make_base('t_mtr_norm')
    obj = make_mesh(base, 't_mtr_norm_m', cube_v, cube_f)
    mat = textured_material('t_normmat', 't_normtex', normal='t_normtex_n')
    obj.data.materials.append(mat)
    path, _ = export(base, 't_mtr_norm')
    mtr_path = os.path.join(OUT, 't_normmat.mtr')
    mtr = mdl_lines(mtr_path) if os.path.exists(mtr_path) else []
    R.check('bitmap t_normmat' in mdl_lines(path) and 'texture1 t_normtex_n' in mtr,
            'fix4 normal-mapped material writes its MTR', str(mtr))

    clear()
    base = make_base('t_mtr_param')
    obj = make_mesh(base, 't_mtr_param_m', cube_v, cube_f)
    mat = textured_material('t_parammat', 't_paramtex')
    p = mat.nvb.mtr.param_list.add()
    p.pname, p.ptype, p.pvalue = 'Specularity', 'float', '0.5'
    obj.data.materials.append(mat)
    export(base, 't_mtr_param')
    R.check(os.path.exists(os.path.join(OUT, 't_parammat.mtr')), 'fix4 a parameter makes an MTR')


game = os.environ.get('NWN_ROOT', '')

@section('Stock name warning: with a game install (NWN_ROOT) the stock list is used,')
def section_8():
    global base, obj, mat
    # without one the MTR named like its diffuse texture is warned about
    clear()
    base = make_base('t_mtr_stock')
    obj = make_mesh(base, 't_mtr_stock_m', cube_v, cube_f)
    mat = textured_material('plc_rck', 'plc_rck', normal='t_rock_n')
    obj.data.materials.append(mat)
    PREFS.cleanmodels_game_dir = game if game else os.path.join(OUT, 'no-game')
    _, text = export(base, 't_mtr_stock')
    R.check('plc_rck.mtr (material plc_rck)' in text, 'fix4 warns about an MTR named like a stock texture',
            text[-300:])
    if game:
        R.check('stock NWN texture or material' in text, 'fix4 the warning used the game install')
    PREFS.cleanmodels_game_dir = os.path.join(OUT, 'no-game')
    clear()
    base = make_base('t_mtr_own')
    obj = make_mesh(base, 't_mtr_own_m', cube_v, cube_f)
    mat = textured_material('t_ownmat', 't_owntex', normal='t_owntex_n')
    obj.data.materials.append(mat)
    _, text = export(base, 't_mtr_own')
    R.check('.mtr (material' not in text, 'fix4 no warning for an MTR named unlike its texture')
    PREFS.cleanmodels_game_dir = ''


FIX = os.path.join(OUT, 'fixtures')
os.makedirs(FIX, exist_ok=True)
MESH = '''node trimesh {name}
  parent {model}
  {matline}
  render 1
{shadow}  verts 3
    0 0 0
    1 0 0
    0 1 0
  tverts 3
    0 0 0
    1 0 0
    0 1 0
  faces 1
    0 1 2 1 0 1 2 0
endnode
'''


def write_model(model, nodes, classification='character'):
    text = 'newmodel {m}\nsetsupermodel {m} NULL\nclassification {c}\nsetanimationscale 1\n' \
           'beginmodelgeom {m}\nnode dummy {m}\n  parent NULL\nendnode\n'.format(m=model, c=classification)
    text += ''.join(nodes)
    text += 'endmodelgeom {m}\ndonemodel {m}\n'.format(m=model)
    path = os.path.join(FIX, model + '.mdl')
    with open(path, 'w') as f:
        f.write(text)
    return path


def import_model(path):
    clear()
    bpy.ops.scene.nvb_mdlimport(filepath=path)
    return [o for o in bpy.context.scene.objects if o.parent is None and o.type == 'EMPTY'][0]


@section('An imported model that came with an MTR writes it back, diffuse-only too')
def section_9():
    global base, obj, mat
    with open(os.path.join(FIX, 't_impmtr.mtr'), 'w') as f:
        f.write('renderhint NormalAndSpecMapped\ntexture0 t_imptex\ntexture1 t_imptex_n\n'
                'parameter float Specularity 0.5\n')
    with open(os.path.join(FIX, 't_impdiff.mtr'), 'w') as f:
        f.write('texture0 t_impdifftex\n')
    src = write_model('t_impmtr', [
        MESH.format(name='m1', model='t_impmtr', matline='materialname t_impmtr', shadow=''),
        MESH.format(name='m2', model='t_impmtr', matline='materialname t_impdiff', shadow='')])
    base = import_model(src)
    mdl_path, _ = export(base, 't_impmtr')
    lines = mdl_lines(mdl_path)
    R.check('materialname t_impmtr' in lines and 'materialname t_impdiff' in lines
            and os.path.exists(os.path.join(OUT, 't_impmtr.mtr'))
            and os.path.exists(os.path.join(OUT, 't_impdiff.mtr')),
            'fix4 imported MTRs (normal-mapped and diffuse-only) are written back',
            str([ln for ln in lines if ln.startswith(('bitmap', 'materialname'))]))


AABB = '''node aabb {name}
  parent {model}
  bitmap null
  verts 3
    0 0 0
    1 0 0
    0 1 0
  faces 1
    0 1 2 0 0 0 0 1
endnode
'''


@section('Fix 6: shadow')
def section_10():
    global base, obj, mat
    clear()
    base = make_base('t_shadow_new')
    obj = make_mesh(base, 't_shadow_new_m', cube_v, cube_f)
    path, _ = export(base, 't_shadow_new')
    R.check(obj.nvb.shadow and 'shadow 1' in mdl_lines(path), 'fix6 a new mesh exports shadow 1')

    src = write_model('t_shadowimp', [
        MESH.format(name='s_none', model='t_shadowimp', matline='bitmap null', shadow=''),
        MESH.format(name='s_off', model='t_shadowimp', matline='bitmap null', shadow='  shadow 0\n'),
        MESH.format(name='s_on', model='t_shadowimp', matline='bitmap null', shadow='  shadow 1\n'),
        AABB.format(name='s_aabb', model='t_shadowimp')])
    base = import_model(src)
    objs = {o.name: o for o in bpy.context.scene.objects}
    R.check(objs['s_none'].nvb.shadow is True and objs['s_off'].nvb.shadow is False
            and objs['s_on'].nvb.shadow is True and objs['s_aabb'].nvb.shadow is False,
            'fix6 import keeps the model\'s shadow (no line: mesh 1, aabb 0)',
            str({k: objs[k].nvb.shadow for k in ('s_none', 's_off', 's_on', 's_aabb')}))
    path, _ = export(base, 't_shadowimp')
    lines = mdl_lines(path)
    shadows = []
    node = None
    for ln in lines:
        t = ln.split()
        if t[:1] == ['node']:
            node = t[2]
        elif t[:1] == ['shadow']:
            shadows.append((node, t[1]))
    R.check(dict(shadows) == {'s_none': '1', 's_off': '0', 's_on': '1'},
            'fix6 imported shadow values export unchanged (aabb writes none)', str(shadows))


def wok_positions(path):
    """The position lines of the aabb nodes in a .wok."""
    found, node = [], None
    for ln in mdl_lines(path):
        t = ln.split()
        if t[:1] == ['node']:
            node = t[1]
        elif t[:1] == ['endnode']:
            node = None
        elif node == 'aabb' and t[:1] == ['position']:
            found.append(' '.join(t[1:]))
    return found


@section('Tile walkmesh: the .wok has position 0 0 0 (the server centres a tile only with it)')
def section_11():
    global base, obj, mat
    from neverblender import nvb_cleanmodels
    src = write_model('t_tilewok', [AABB.format(name='t_tilewok_wg', model='t_tilewok')], 'tile')
    find = nvb_cleanmodels.find
    # Export Walkmesh writes Neverblender's .wok; compiling without it leaves the compiler's
    for label, walkmesh, compiled in (('walkmesh export', True, False), ('built-in compile', False, True),
                                      ('both', True, True)):
        base = import_model(src)
        name = 't_tilewok_' + label.split()[0]
        wok = os.path.join(OUT, name + '.wok')
        if os.path.exists(wok):
            os.remove(wok)
        # Neverblender's copy of the cleanmodels compiler, not a program on the PATH
        nvb_cleanmodels.find = lambda preferred=('',): (None, None)
        try:
            export(base, name, walkmesh=walkmesh, compile_binary=compiled)
        finally:
            nvb_cleanmodels.find = find
        pos = wok_positions(wok) if os.path.exists(wok) else None
        by_cm = pos is not None and mdl_lines(wok)[0] == '# Rewritten by cleanmodels'
        R.check(pos is not None and len(pos) == 1 and [float(x) for x in pos[0].split()] == [0, 0, 0]
                and by_cm == (not walkmesh),
                'tile .wok keeps position 0 0 0 ({})'.format(label),
                'positions {} written by cleanmodels {}'.format(pos, by_cm))


R.finish()
