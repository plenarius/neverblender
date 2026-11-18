"""Export meshes made in Blender, for comparing the MDLs between Blender versions.

    blender -b --factory-startup --python scripts/tests/crossversion.py -- <outdir> [mesh.json]...

Each mesh is exported with Smoothing: Groups, with and without Distinct
Smoothing groups. The built-in meshes are: two smooth regions touching only
at a vertex, a grid of 1,500 quads that are each a region of their own, and
33 regions around one vertex (more than the 31 groups). A mesh.json holds
{name, verts, faces, smooth (per face), sharp (edges as vertex pairs)}, e.g.
a model you may not commit. run_crossversion.sh runs this in each version
and compares the outputs.
"""

import json
import math
import os
import random
import sys

import addon_utils
import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
out = os.path.abspath(argv[0])
os.makedirs(out, exist_ok=True)
addon_utils.enable('neverblender', default_set=True)
prefs = bpy.context.preferences.addons['neverblender'].preferences


def builtin_meshes():
    meshes = []
    meshes.append(dict(
        name='x_vtxonly',
        verts=[(0, 0, 0), (-1, 1, 1), (-1.2, 0, 1.3), (-1, -1, 1), (1, 1, 0), (1.2, 0, -0.1), (1, -1, 0)],
        faces=[(0, 1, 2), (0, 2, 3), (0, 4, 5), (0, 5, 6)], smooth=None, sharp=[]))
    rnd = random.Random(2)
    nx, ny = 50, 30
    verts = [(x * 0.1, y * 0.1, round(rnd.uniform(0, 0.05), 4)) for y in range(ny + 1) for x in range(nx + 1)]
    faces = [(y * (nx + 1) + x, y * (nx + 1) + x + 1, (y + 1) * (nx + 1) + x + 1, (y + 1) * (nx + 1) + x)
             for y in range(ny) for x in range(nx)]
    sharp = [(q[i], q[(i + 1) % 4]) for q in faces for i in range(4)]
    meshes.append(dict(name='x_quads', verts=verts, faces=faces, smooth=None, sharp=sharp))
    n = 66
    verts = [(0, 0, 1)] + [(round(math.cos(2 * math.pi * i / n), 6), round(math.sin(2 * math.pi * i / n), 6), 0)
                           for i in range(n)]
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    meshes.append(dict(name='x_cone', verts=verts, faces=faces, smooth=None,
                       sharp=[(0, 1 + i) for i in range(0, n, 2)]))
    return meshes


def build(d):
    for coll in (bpy.data.objects, bpy.data.meshes):
        for item in list(coll):
            coll.remove(item)
    base = bpy.data.objects.new(d['name'], None)
    bpy.context.scene.collection.objects.link(base)
    me = bpy.data.meshes.new(d['name'] + '_m')
    me.from_pydata([tuple(v) for v in d['verts']], [], [tuple(f) for f in d['faces']])
    me.update()
    smooth = d.get('smooth')
    for i, p in enumerate(me.polygons):
        p.use_smooth = True if smooth is None else bool(smooth[i])
    sharp = {tuple(sorted(e)) for e in d.get('sharp', [])}
    for e in me.edges:
        if tuple(sorted(e.vertices)) in sharp:
            e.use_edge_sharp = True
    obj = bpy.data.objects.new(d['name'] + '_m', me)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = base
    return base


meshes = builtin_meshes()
for path in argv[1:]:
    with open(path) as f:
        meshes.append(json.load(f))
for d in meshes:
    for distinct in (False, True):
        base = build(d)
        prefs.export_smoothgroups_distinct_verts = distinct
        for o in bpy.context.scene.objects:
            o.select_set(False)
        base.select_set(True)
        bpy.context.view_layer.objects.active = base
        name = d['name'] + ('_d' if distinct else '')
        bpy.ops.scene.nvb_mdlexport(filepath=os.path.join(out, name + '.mdl'), export_walkmesh=False,
                                    export_animations=False, cleanmodels_check=False,
                                    cleanmodels_compile=False, export_smoothing_mode='GROUP')
        print('CROSSVERSION exported', name)
sys.stdout.flush()
os._exit(0)
