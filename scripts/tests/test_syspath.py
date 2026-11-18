"""Export with the add-on loaded from sys.path, not from an add-ons folder.

addon_utils.modules() does not list it then; the MDL header's version must
come from the package's bl_info instead of raising IndexError.
    blender -b --factory-startup --python scripts/tests/test_syspath.py -- <folder holding neverblender>
"""

import os
import sys

import addon_utils
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nvbtest  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
sys.path.insert(0, os.path.abspath(argv[0]))
import neverblender  # noqa: E402
neverblender.register()
from neverblender import nvb_def, nvb_mdl  # noqa: E402

R = nvbtest.Results()
listed = [m for m in addon_utils.modules() if m.bl_info.get('name') == 'Neverblender']
R.check(not listed, 'fix5 precondition: the add-on is not in addon_utils.modules()', str(listed))

base = bpy.data.objects.new('t_syspath', None)
bpy.context.scene.collection.objects.link(base)
me = bpy.data.meshes.new('t_syspath_m')
me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
obj = bpy.data.objects.new('t_syspath_m', me)
bpy.context.scene.collection.objects.link(obj)
obj.parent = base

options = nvb_def.ExportOptions()
options.scene = bpy.context.scene
options.depsgraph = bpy.context.evaluated_depsgraph_get()
options.mdlname = 't_syspath'
options.export_wirecolor = True  # set by the export operator
lines = []
try:
    nvb_mdl.Mdl.generate_ascii(base, lines, options)
    version = '.'.join(str(v) for v in neverblender.bl_info['version'])
    R.check(lines and lines[0].startswith('# NeverBlender ' + version + '|'),
            'fix5 export works and names the version from bl_info', lines[:1])
except Exception as e:  # noqa: BLE001
    R.check(False, 'fix5 export works and names the version from bl_info', repr(e))
R.finish()
