"""Optional cleanmodels integration.

Neverblender works without cleanmodels. When it finds a cleanmodels command
line tool (version 4.5.1 or later) it uses it to:
- import any model: binary models are decompiled (skinned body parts get
  their bone names from the creature skeleton, found in the model's folder or
  the game install), and ASCII models are rewritten in cleanmodels' canonical
  form, which absorbs malformed or hand-edited input;
- check exported models and list the findings (Scene properties);
- optionally compile exported models to binary.
Anything that goes wrong here falls back to Neverblender's own behaviour.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

MIN_VERSION = (4, 5, 1)
_TIMEOUT = 300  # seconds per call; whole folders of models take a few seconds
_VERSION_RE = re.compile(r"cleanmodels v(\d+)\.(\d+)\.(\d+)")
_cache = {}  # path -> (mtime, version tuple or None)

# Names cleanmodels is shipped under (release archives and the Qt app).
_NAMES = ("cleanmodels", "cleanmodels-cli",
          "cleanmodels-linux-amd64", "cleanmodels-linux-arm64",
          "cleanmodels-darwin-amd64", "cleanmodels-darwin-arm64",
          "cleanmodels-windows-amd64.exe", "cleanmodels.exe")


def version_of(path):
    """Return the (major, minor, patch) of the cleanmodels at path, or None."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    version = None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
        m = _VERSION_RE.search(out.stdout + out.stderr)
        if m:
            version = tuple(int(x) for x in m.groups())
    except (OSError, subprocess.SubprocessError):
        version = None
    _cache[path] = (mtime, version)
    return version


def find(preferred=("",)):
    """Return (path, version) of a usable cleanmodels, or (None, None).

    preferred: paths to try first (the add-on preferences); then the PATH.
    """
    candidates = [p for p in preferred if p]
    # Every match on the PATH, not just the first: an old cleanmodels earlier
    # on the PATH must not hide a newer one later on.
    for d in os.get_exec_path():
        for name in _NAMES:
            p = os.path.join(d, name)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                candidates.append(p)
    for p in candidates:
        p = os.path.abspath(os.path.expanduser(p))
        if not os.path.isfile(p) or "cleanmodels" not in os.path.basename(p).lower():
            continue
        v = version_of(p)
        if v and v >= MIN_VERSION:
            return p, v
    return None, None


def find_from_prefs(addon_prefs):
    """find() with the paths set in Neverblender's preferences."""
    return find((getattr(addon_prefs, "cleanmodels_path", ""),
                 getattr(addon_prefs, "import_compiler_path", "")))


def _run(path, args):
    return subprocess.run([path] + args, capture_output=True, text=True, timeout=_TIMEOUT)


def to_ascii(path, mdl_path, game_dir=""):
    """Return the model at mdl_path as cleanmodels' canonical ASCII, or None.

    The model is read where it is, so its own folder is searched for
    supermodels, skeletons and capart.2da.
    """
    tmp_dir = tempfile.mkdtemp(prefix="nvb_cm_")
    try:
        out_path = os.path.join(tmp_dir, os.path.basename(mdl_path))
        args = ["decompile", "--quiet", "--overwrite"]
        if game_dir:
            args += ["--game-dir", game_dir]
        result = _run(path, args + [mdl_path, out_path])
        if result.returncode != 0 or not os.path.isfile(out_path):
            print("Neverblender: cleanmodels could not read " + mdl_path + ": " + (result.stderr or result.stdout).strip()[:300])
            return None
        with open(out_path, "r", encoding="latin-1") as f:
            return f.read()
    except (OSError, subprocess.SubprocessError) as e:
        print("Neverblender: cleanmodels failed on " + mdl_path + ": " + str(e))
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def check(path, mdl_path, game_dir=""):
    """Run cleanmodels' checks on a model. Returns a list of findings:
    dicts with file, check, node, severity (info, warning, error, fatal) and
    message. Parse and decompile warnings are included as warnings."""
    args = ["check", "--json-lines", "--verbose"]
    if game_dir:
        args += ["--game-dir", game_dir]
    try:
        result = _run(path, args + [mdl_path])
    except (OSError, subprocess.SubprocessError) as e:
        return [dict(file=mdl_path, check="cleanmodels", node="", severity="error", message=str(e))]
    findings = []
    for line in result.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") != "done":
            continue
        res = ev.get("result", {})
        f = res.get("file", mdl_path)
        if res.get("error"):
            findings.append(dict(file=f, check="cleanmodels", node="", severity="error", message=res["error"]))
        for c in res.get("checks") or []:
            findings.append(dict(file=f, check=c.get("check", ""), node=c.get("node", ""),
                                 severity=c.get("severity", "info"), message=c.get("message", "")))
        for w in res.get("warnings") or []:
            findings.append(dict(file=f, check="decompile", node=w.get("node", ""),
                                 severity="warning", message=w.get("message", "")))
        for w in res.get("parse_warnings") or []:
            findings.append(dict(file=f, check="parse", node="", severity="warning", message=w))
    return findings


def compile_to(path, ascii_path, out_path, game_dir=""):
    """Compile ascii_path to a binary model at out_path. Returns (ok, messages)."""
    args = ["compile", "--overwrite"]
    if game_dir:
        args += ["--game-dir", game_dir]
    try:
        result = _run(path, args + [ascii_path, out_path])
    except (OSError, subprocess.SubprocessError) as e:
        return False, [str(e)]
    lines = [ln.strip() for ln in (result.stdout + result.stderr).splitlines() if ln.strip()]
    return result.returncode == 0 and os.path.isfile(out_path), lines
