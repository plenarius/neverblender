"""PLT Autoreload functionality for NeverBlender.

Automatically reloads PLT files when changes are detected on disk.
"""

import bpy
import os

from . import nvb_plt

# Dictionary to track PLT files and their modification times
# Key: filepath, Value: (modification_time, base_name)
_plt_file_tracker = {}

# Timer interval in seconds
PLT_CHECK_INTERVAL = 5.0

# Debug mode - set to True to see console output
DEBUG = False


def debug_print(msg):
    """Print debug message if DEBUG is enabled."""
    if DEBUG:
        print(f"NeverBlender PLT Autoreload: {msg}")


def get_addon_preferences():
    """Get NeverBlender addon preferences."""
    addon = bpy.context.preferences.addons.get(__package__)
    return getattr(addon, "preferences", None)


def is_autoreload_enabled():
    """Check if PLT autoreload is enabled in preferences."""
    prefs = get_addon_preferences()
    if prefs:
        return prefs.plt_autoreload_enabled
    return False


def register_plt_file(filepath, base_name):
    """Register a PLT file for autoreload tracking.
    
    Call this after importing a PLT file.
    
    Args:
        filepath: Absolute path to the PLT file
        base_name: Base name used for the imported images (e.g., 'mytexture')
    """
    # Ensure absolute path
    filepath = os.path.abspath(bpy.path.abspath(filepath))
    
    if not filepath or not os.path.isfile(filepath):
        debug_print(f"Cannot track - file not found: {filepath}")
        return
    
    try:
        modtime = os.path.getmtime(filepath)
        _plt_file_tracker[filepath] = (modtime, base_name)
        debug_print(f"Now tracking: {filepath} (base: {base_name}, modtime: {modtime})")
    except OSError as e:
        debug_print(f"Error getting modtime for {filepath}: {e}")


def unregister_plt_file(filepath):
    """Stop tracking a PLT file.
    
    Args:
        filepath: Absolute path to the PLT file
    """
    if filepath in _plt_file_tracker:
        del _plt_file_tracker[filepath]


def get_tracked_plt_files():
    """Get list of tracked PLT files.
    
    Returns:
        Dictionary of filepath -> (modtime, base_name)
    """
    return _plt_file_tracker.copy()


def reload_plt_file(filepath, base_name):
    """Reload a single PLT file.
    
    Args:
        filepath: Absolute path to the PLT file
        base_name: Base name for the layer images
    """
    if not os.path.isfile(filepath):
        debug_print(f"File not found: {filepath}")
        return False
    
    debug_print(f"Reloading PLT: {filepath}")
    
    try:
        import struct
        
        PLT_HEADER_SIGNATURE = b"PLT V1  "
        PLT_HEADER_SIZE = 24
        
        with open(filepath, "rb") as f:
            data = f.read()
        
        if len(data) < PLT_HEADER_SIZE:
            debug_print(f"File too small: {filepath}")
            return False
        
        signature = data[0:8]
        if signature != PLT_HEADER_SIGNATURE:
            debug_print(f"Invalid PLT signature: {filepath}")
            return False
        
        width = struct.unpack_from("<I", data, 16)[0]
        height = struct.unpack_from("<I", data, 20)[0]
        
        # Check for combined image (from model import)
        # Could be named "{base_name}_plt" or just "{base_name}"
        combined_name = f"{base_name}_plt"
        updated_any = False
        
        # Try different naming conventions
        possible_names = [
            combined_name,           # {base_name}_plt
            base_name,               # {base_name}
            f"{base_name}.001",      # {base_name}.001 (Blender duplicate)
        ]
        
        for img_name in possible_names:
            if img_name in bpy.data.images:
                img = bpy.data.images[img_name]
                debug_print(f"Found image: {img_name}, size: {img.size[0]}x{img.size[1]}")
                
                # Build combined grayscale pixels
                pixels = [0.0] * (width * height * 4)
                for y in range(height):
                    for x in range(width):
                        plt_offset = PLT_HEADER_SIZE + (y * width + x) * 2
                        if plt_offset + 1 >= len(data):
                            continue
                        gray_value = data[plt_offset]
                        pixel_idx = (y * width + x) * 4
                        gray_float = gray_value / 255.0
                        pixels[pixel_idx] = gray_float      # R
                        pixels[pixel_idx + 1] = gray_float  # G
                        pixels[pixel_idx + 2] = gray_float  # B
                        pixels[pixel_idx + 3] = 1.0         # A
                
                # Update pixels directly (works even on packed images)
                img.pixels[:] = pixels
                
                # Force GPU texture cache to update
                img.gl_free()
                
                # Mark image as updated
                img.update()
                updated_any = True
                debug_print(f"Updated image pixels: {img_name}")
        
        # Also check for layered images (from PLT import: {base_name}_{layer})
        layer_names = ["skin", "hair", "metal1", "metal2", "cloth1", "cloth2", 
                       "leather1", "leather2", "tattoo1", "tattoo2"]
        for layer_idx, layer_name in enumerate(layer_names):
            image_name = f"{base_name}_{layer_name}"
            if image_name in bpy.data.images:
                img = bpy.data.images[image_name]
                
                pixels = [0.0] * (width * height * 4)
                for y in range(height):
                    for x in range(width):
                        plt_offset = PLT_HEADER_SIZE + (y * width + x) * 2
                        if plt_offset + 1 >= len(data):
                            continue
                        gray_value = data[plt_offset]
                        pixel_layer = data[plt_offset + 1]
                        pixel_idx = (y * width + x) * 4
                        
                        if pixel_layer == layer_idx:
                            gray_float = gray_value / 255.0
                            pixels[pixel_idx] = gray_float
                            pixels[pixel_idx + 1] = gray_float
                            pixels[pixel_idx + 2] = gray_float
                            pixels[pixel_idx + 3] = 1.0
                        else:
                            pixels[pixel_idx] = 0.0
                            pixels[pixel_idx + 1] = 0.0
                            pixels[pixel_idx + 2] = 0.0
                            pixels[pixel_idx + 3] = 0.0
                
                img.pixels[:] = pixels
                img.update()
                updated_any = True
                debug_print(f"Updated layer image: {image_name}")
        
        if not updated_any:
            debug_print(f"Warning: No images found to update for base_name: {base_name}")
        
        # Force viewport updates
        update_viewports()
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        
        debug_print(f"Successfully reloaded: {filepath}")
        return True
        
    except Exception as e:
        debug_print(f"Error reloading {filepath}: {e}")
        import traceback
        traceback.print_exc()
    
    return False


def update_viewports():
    """Force update of 3D viewports in rendered mode."""
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D' and space.shading.type == 'RENDERED':
                            # Toggle shading to force refresh
                            space.shading.type = 'SOLID'
                            space.shading.type = 'RENDERED'
    except Exception:
        pass


def check_and_reload_plt_files():
    """Check all tracked PLT files for changes and reload if modified."""
    files_to_update = []
    
    debug_print(f"Checking {len(_plt_file_tracker)} tracked files...")
    
    for filepath, (old_modtime, base_name) in list(_plt_file_tracker.items()):
        if not os.path.isfile(filepath):
            debug_print(f"File no longer exists: {filepath}")
            continue
        
        try:
            current_modtime = os.path.getmtime(filepath)
            if current_modtime != old_modtime:
                debug_print(f"Change detected: {filepath} (old: {old_modtime}, new: {current_modtime})")
                files_to_update.append((filepath, base_name, current_modtime))
        except OSError as e:
            debug_print(f"Error checking {filepath}: {e}")
            continue
    
    # Reload modified files
    for filepath, base_name, new_modtime in files_to_update:
        if reload_plt_file(filepath, base_name):
            _plt_file_tracker[filepath] = (new_modtime, base_name)


def plt_autoreload_timer():
    """Timer callback for PLT autoreload.
    
    Returns the interval for the next check, or None to stop the timer.
    """
    if not is_autoreload_enabled():
        # Still return interval to keep timer running (user might re-enable)
        return PLT_CHECK_INTERVAL
    
    if not _plt_file_tracker:
        # No files to track, but keep timer running
        return PLT_CHECK_INTERVAL
    
    try:
        check_and_reload_plt_files()
    except Exception as e:
        debug_print(f"Timer error: {e}")
    
    return PLT_CHECK_INTERVAL


# Timer registration state
_timer_registered = False


def register():
    """Register the PLT autoreload timer."""
    global _timer_registered
    if not _timer_registered:
        bpy.app.timers.register(plt_autoreload_timer, persistent=True)
        _timer_registered = True
        print("NeverBlender PLT Autoreload: Timer registered")


def unregister():
    """Unregister the PLT autoreload timer."""
    global _timer_registered
    if _timer_registered:
        try:
            bpy.app.timers.unregister(plt_autoreload_timer)
        except ValueError:
            pass  # Timer wasn't registered
        _timer_registered = False
    _plt_file_tracker.clear()
