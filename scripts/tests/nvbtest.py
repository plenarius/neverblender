"""Helpers shared by the Blender-run tests (run_tests.sh puts this folder on sys.path)."""

import math
import os
import sys


def parse_meshes(path):
    """Each mesh node of an ASCII MDL as (name, verts, faces), faces as (a, b, c, group)."""
    meshes = []
    with open(path, encoding='latin-1') as f:
        lines = f.read().splitlines()
    name, verts, faces = None, [], []
    i = 0
    while i < len(lines):
        t = lines[i].split()
        if t and t[0].lower() == 'node' and len(t) >= 3:
            name, verts, faces = t[2], [], []
        elif t and t[0].lower() == 'verts' and len(t) == 2:
            n = int(t[1])
            verts = [tuple(map(float, lines[i + 1 + k].split()[:3])) for k in range(n)]
            i += n
        elif t and t[0].lower() == 'faces' and len(t) == 2:
            n = int(t[1])
            faces = [tuple(map(int, lines[i + 1 + k].split()[:4])) for k in range(n)]
            i += n
        elif t and t[0].lower() == 'endnode':
            if name is not None and faces:
                meshes.append((name, verts, faces))
            name = None
        i += 1
    return meshes


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _unit(a):
    length = math.sqrt(sum(x * x for x in a))
    return [x / length for x in a] if length > 1e-20 else [0, 0, 0]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def bad_corners(verts, faces):
    """Face corners whose normal, as the game computes it, is more than 60
    degrees off the face's own normal.

    The game's rule (Moonglow mg-mdl ascii.rs; nwn-mdl-spec MDL-MESH-031/032):
    a corner takes the normal an earlier face computed at the same vertex if
    their groups share a bit (and the normals are not opposite); otherwise it
    sums the area normals of the face and the later faces sharing a bit.
    Same as contract-models-triage/scripts/sgcheck2.py.
    """
    area = [_cross(_sub(verts[b], verts[a]), _sub(verts[c], verts[a])) for a, b, c, g in faces]
    un = [_unit(a) for a in area]
    at = {}
    for fi, f in enumerate(faces):
        for v in f[:3]:
            lst = at.setdefault(v, [])
            if fi not in lst:
                lst.append(fi)
    normals = []
    bad = 0
    for fi, f in enumerate(faces):
        cn = []
        for c in range(3):
            v = f[c]
            n = None
            for g in at[v]:
                if g < fi and (faces[g][3] & f[3]):
                    k = list(faces[g][:3]).index(v)
                    m = normals[g][k]
                    if _dot(un[fi], m) >= -0.99:
                        n = m
                        break
            if n is None:
                s = list(area[fi])
                for g in at[v]:
                    if g > fi and (faces[g][3] & f[3]):
                        s = [s[i] + area[g][i] for i in range(3)]
                n = _unit(s) if any(s) else un[fi]
            cn.append(n)
            if _dot(n, un[fi]) < 0.5:
                bad += 1
        normals.append(cn)
    return bad


def file_bad_corners(path):
    return sum(bad_corners(v, f) for _, v, f in parse_meshes(path))


class Results:
    def __init__(self):
        self.failed = []
        self.passed = 0

    def check(self, cond, label, detail=''):
        if cond:
            self.passed += 1
            print('PASS', label)
        else:
            self.failed.append(label)
            print('FAIL', label, detail)

    def finish(self):
        print('RESULT {} passed, {} failed{}'.format(
            self.passed, len(self.failed), (': ' + ', '.join(self.failed)) if self.failed else ''))
        sys.stdout.flush()
        os._exit(1 if self.failed else 0)
