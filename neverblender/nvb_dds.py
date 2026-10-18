"""Show NWN-format DDS textures by converting them to PNG.

Formerly the standalone "NWN DDS textures" add-on.
"""

# Neverwinter Nights ships textures in its own DDS variant: a 20-byte header
# (width, height, channels, data size, alpha mean) followed by DXT1 (3 channels)
# or DXT5 (4 channels) blocks, with no "DDS " magic. Blender only reads standard
# DDS, so these show up as missing (magenta). This add-on watches for such
# images, decodes the top mip level to a PNG cached under
# ~/.cache/nwn-dds/<version>/<texture>.png, and points the image at it. The PNG
# has the texture's own file name, so an exporter that writes the image file's
# name as the model's bitmap (NeverBlender does) still writes the right one.
# Standard DDS files are left alone. Automatic conversion can be turned off in
# the add-on preferences; the Image editor's Image menu converts on demand.

import hashlib
import os
import struct
import zlib

import bpy
from bpy.app.handlers import persistent

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "nwn-dds")
SOURCE_KEY = "nwn_dds_source"  # custom property: the .dds an image was converted from


def _c565(c):
    return (((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)


def nwn_dds_header(path):
    """Return (width, height, channels) for an NWN-format DDS, else None."""
    try:
        with open(path, "rb") as f:
            head = f.read(20)
    except OSError:
        return None
    if len(head) < 20 or head[:4] == b"DDS ":
        return None  # too short, or a standard DDS that Blender reads itself
    w, h, ch = struct.unpack_from("<III", head, 0)
    if ch not in (3, 4) or not (0 < w <= 8192 and 0 < h <= 8192):
        return None
    return w, h, ch


def decode(data):
    """Decode the top mip level of an NWN-format DDS to RGBA rows."""
    w, h, ch = struct.unpack_from("<III", data, 0)
    dxt5 = ch == 4
    off = 20
    rows = [bytearray(w * 4) for _ in range(h)]
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            alphas = None
            if dxt5:
                a0, a1 = data[off], data[off + 1]
                bits = int.from_bytes(data[off + 2:off + 8], "little")
                off += 8
                if a0 > a1:
                    al = [a0, a1] + [((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)]
                else:
                    al = [a0, a1] + [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)] + [0, 255]
                alphas = [al[(bits >> (3 * i)) & 7] for i in range(16)]
            k0, k1, bits = struct.unpack_from("<HHI", data, off)
            off += 8
            p0, p1 = _c565(k0), _c565(k1)
            if k0 > k1 or dxt5:
                pal = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)), tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
            else:
                pal = [p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1)), (0, 0, 0)]
            for i in range(16):
                x, y = bx + i % 4, by + i // 4
                if x < w and y < h:
                    r, g, b = pal[(bits >> (2 * i)) & 3]
                    a = alphas[i] if alphas else 255
                    rows[y][4 * x:4 * x + 4] = bytes((r, g, b, a))
    return w, h, rows


def write_png(path, w, h, rows):
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + bytes(r) for r in rows)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        f.write(chunk(b"IEND", b""))


def cached_png(dds_path):
    """Convert dds_path to a PNG in the cache (once per file version) and return its path."""
    st = os.stat(dds_path)
    key = hashlib.sha1(f"{os.path.abspath(dds_path)}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:16]
    # The PNG keeps the texture's own file name: NeverBlender exports the image
    # file's name as the model's bitmap, so "c_antelope-<hash>.png" would have
    # renamed the bitmap. The version goes in the folder name instead.
    name = os.path.splitext(os.path.basename(dds_path))[0]
    folder = os.path.join(CACHE_DIR, key)
    png = os.path.join(folder, f"{name}.png")
    if not os.path.isfile(png):
        os.makedirs(folder, exist_ok=True)
        with open(dds_path, "rb") as f:
            w, h, rows = decode(f.read())
        tmp = png + ".tmp"
        write_png(tmp, w, h, rows)
        os.replace(tmp, png)
    return png


def convert_images():
    """Point every image that is an NWN-format DDS at a cached PNG. Returns the count."""
    n = 0
    for img in bpy.data.images:
        if img.get(SOURCE_KEY) or img.source != "FILE":
            continue
        path = bpy.path.abspath(img.filepath)
        if not path.lower().endswith(".dds") or not nwn_dds_header(path):
            continue
        try:
            png = cached_png(path)
        except Exception as e:  # a damaged file must not break the scene
            print(f"NeverBlender DDS: could not convert {path}: {e}")
            continue
        img[SOURCE_KEY] = path
        img.filepath = png
        img.reload()
        n += 1
    return n


_pending = False


def _deferred():
    global _pending
    _pending = False
    n = convert_images()
    if n:
        print(f"NeverBlender DDS: converted {n} texture(s)")
    return None  # run once


def is_enabled():
    """Check if automatic conversion is enabled in the preferences."""
    addon = bpy.context.preferences.addons.get(__package__)
    prefs = getattr(addon, "preferences", None)
    return prefs.dds_convert if prefs else True


@persistent
def _on_update(scene, depsgraph=None):
    # Data must not be changed inside a depsgraph handler; defer to a timer.
    global _pending
    if _pending or not is_enabled():
        return
    if any(i.source == "FILE" and not i.get(SOURCE_KEY) and i.filepath.lower().endswith(".dds") for i in bpy.data.images):
        _pending = True
        bpy.app.timers.register(_deferred, first_interval=0.1)


class NVB_OT_dds_convert(bpy.types.Operator):
    """Show NWN-format DDS textures by converting them to cached PNGs"""

    bl_idname = "image.nvb_dds_convert"
    bl_label = "Convert NWN DDS textures"

    def execute(self, context):
        n = convert_images()
        self.report({"INFO"}, f"Converted {n} NWN DDS texture(s)")
        return {"FINISHED"}


def menu_func(self, context):
    """Helper to register a Menu element."""
    self.layout.operator(NVB_OT_dds_convert.bl_idname)


def register():
    """Register the handlers. The operator is in neverblender_classes."""
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.load_post):
        if _on_update not in handlers:
            handlers.append(_on_update)


def unregister():
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.load_post):
        if _on_update in handlers:
            handlers.remove(_on_update)
