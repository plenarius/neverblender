"""Import each model and export it again with the default options.

    blender -b --factory-startup --python scripts/tests/roundtrip.py -- <outdir> <model.mdl>...

Run it once with each add-on version (run_roundtrip.sh) and compare the two
output folders: an imported model must export the same with both.
"""

import os
import sys
import traceback

import addon_utils
import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
out = os.path.abspath(argv[0])
os.makedirs(out, exist_ok=True)
addon_utils.enable('neverblender', default_set=True)
prefs = bpy.context.preferences.addons['neverblender'].preferences
if os.environ.get('NVB_TEST_GAME_DIR'):
    prefs.cleanmodels_game_dir = os.environ['NVB_TEST_GAME_DIR']

failed = 0
for src in argv[1:]:
    name = os.path.splitext(os.path.basename(src))[0]
    try:
        for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images,
                     bpy.data.actions, bpy.data.armatures):
            for item in list(coll):
                coll.remove(item)
        bpy.ops.scene.nvb_mdlimport(filepath=os.path.abspath(src))
        bases = [o for o in bpy.context.scene.objects
                 if o.parent is None and o.type == 'EMPTY' and o.nvb.emptytype == 'dummy']
        base = bases[0]
        for o in bpy.context.scene.objects:
            o.select_set(False)
        base.select_set(True)
        bpy.context.view_layer.objects.active = base
        bpy.ops.scene.nvb_mdlexport(filepath=os.path.join(out, name + '.mdl'),
                                    cleanmodels_check=False, cleanmodels_compile=False)
        print('ROUNDTRIP ok', name)
    except Exception:  # noqa: BLE001
        failed += 1
        traceback.print_exc()
        print('ROUNDTRIP FAILED', name)
sys.stdout.flush()
os._exit(1 if failed else 0)
