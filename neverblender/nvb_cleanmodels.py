"""Optional cleanmodels integration.

Neverblender works without cleanmodels. When it finds a cleanmodels command
line tool (version 4.5.1 or later) it uses it to:
- import any model: binary models are decompiled (skinned body parts get
  their bone names from the creature skeleton, found in the model's folder or
  the game install), and ASCII models are rewritten in cleanmodels' canonical
  form, which absorbs malformed or hand-edited input;
- check exported models and list the findings (Scene properties);
- optionally compile exported models to binary;
- make a robe's, cloak's or armour part's versions for other races and
  phenotypes (cleanmodels 4.7.0 or later; Scene properties).
Anything that goes wrong here falls back to Neverblender's own behaviour.

Without the program, Neverblender's copy of cleanmodels' Python port
(neverblender/cleanmodels) decompiles binary models on import (nvb_mdl) and
compiles exported ones (compile_bundled), with the same results.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

MIN_VERSION = (4, 5, 1)
VARIANTS_VERSION = (4, 7, 0)
DRY_RUN_VERSION = (4, 8, 0)  # variants --dry-run; learnedFrom and adjusts
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


def to_ascii(path, mdl_path, game_dir="", warnings=None):
    """Return the model at mdl_path as cleanmodels' canonical ASCII, or None.

    The model is read where it is, so its own folder is searched for
    supermodels, skeletons and capart.2da. Its decompile and parse warnings,
    and why it could not be read, are added to warnings (a list) as text.
    """
    name = os.path.basename(mdl_path)
    tmp_dir = tempfile.mkdtemp(prefix="nvb_cm_")
    try:
        out_path = os.path.join(tmp_dir, name)
        args = ["decompile", "--json-lines", "--overwrite"]
        if game_dir:
            args += ["--game-dir", game_dir]
        result = _run(path, args + [mdl_path, out_path])
        error = ""
        for line in result.stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") != "done":
                continue
            res = ev.get("result", {})
            error = res.get("error", "")
            for w in res.get("warnings") or []:
                node = w.get("node", "")
                _warn(warnings, name + ": " + (node + ": " if node else "") + w.get("message", ""))
            for w in res.get("parse_warnings") or []:
                _warn(warnings, name + ": " + w)
        if result.returncode != 0 or not os.path.isfile(out_path):
            print("Neverblender: cleanmodels could not read " + mdl_path + ": " +
                  (error or result.stderr or result.stdout).strip()[:300])
            return None
        with open(out_path, "r", encoding="latin-1") as f:
            return f.read()
    except (OSError, subprocess.SubprocessError) as e:
        print("Neverblender: cleanmodels failed on " + mdl_path + ": " + str(e))
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _warn(warnings, text):
    print("Neverblender: " + text)
    if warnings is not None:
        warnings.append(text)


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
    """Compile ascii_path to a binary model at out_path with the cleanmodels
    program. Returns (error, warnings): error is "" if it compiled, warnings
    are its parse and compile warnings as text."""
    args = ["compile", "--json-lines", "--overwrite"]
    if game_dir:
        args += ["--game-dir", game_dir]
    try:
        result = _run(path, args + [ascii_path, out_path])
    except (OSError, subprocess.SubprocessError) as e:
        return str(e) or "cleanmodels failed", []
    error, warnings = "", []
    for line in result.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "error":
            error = ev.get("message", "")
        elif ev.get("type") == "done":
            res = ev.get("result", {})
            error = res.get("error", "") or error
            warnings += res.get("parse_warnings") or []
            for w in res.get("warnings") or []:
                node = w.get("node", "")
                warnings.append((node + ": " if node else "") + w.get("message", ""))
    if result.returncode != 0 or not os.path.isfile(out_path):
        error = error or (result.stderr or result.stdout).strip()[:500] or "cleanmodels failed"
    return error.strip(), warnings


def compile_bundled(ascii_path, out_path, game_dir=""):
    """Compile ascii_path to a binary model at out_path with Neverblender's
    copy of cleanmodels' compiler (neverblender/cleanmodels): the same bytes
    the cleanmodels program writes. Returns (error, warnings) as compile_to."""
    from . import cleanmodels
    try:
        with open(os.fsencode(ascii_path), "rb") as f:
            res = cleanmodels.parse(f.read())
        res.model.file_type = "ascii"
        warnings = [str(e) for e in res.errors]
        # Supermodels, skeletons and materials: the model's folder, then the game
        dirs = cleanmodels.lookup_dirs(ascii_path, game_dir=game_dir)
        data = cleanmodels.compile(res.model, dirs, dirs, warnings.append)
    except (cleanmodels.NotModelError, cleanmodels.CompileError, OSError) as e:
        return str(e) or type(e).__name__, []
    with open(os.fsencode(out_path), "wb") as f:
        f.write(data)
    return "", warnings


def _resource_args(game_dir="", resource_dirs=()):
    args = []
    if game_dir:
        args += ["--game-dir", game_dir]
    for resource_dir in resource_dirs:
        args += ["--resource-dir", resource_dir]
    return args


def list_bodies(path, mdl_path=None, game_dir="", resource_dirs=()):
    """Return (bodies, error): as dicts from cleanmodels variants --list-bodies
    --json, the bodies mdl_path would get variants for (its own has
    "source": true), or without mdl_path every body in the game install and
    resource_dirs; or None and the reason."""
    args = ["variants", "--list-bodies", "--json"] + _resource_args(game_dir, resource_dirs)
    try:
        result = _run(path, args + ([mdl_path] if mdl_path else []))
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)
    if result.returncode != 0:
        return None, _strip_prefix(result.stderr or result.stdout, mdl_path)
    try:
        return json.loads(result.stdout), ""
    except ValueError:
        return None, _strip_prefix(result.stderr or result.stdout, mdl_path)


def _strip_prefix(text, mdl_path):
    """Shorten "cleanmodels: /tmp/.../x.mdl: message" to "message"."""
    text = text.strip().splitlines()[-1] if text.strip() else "cleanmodels failed"
    for prefix in ("cleanmodels: ", (mdl_path or "") + ": "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text


def _variants_args(bodies=(), width=1.0, length=1.0, shape="", compile_binary=False,
                   overwrite=False, game_dir="", resource_dirs=()):
    args = _resource_args(game_dir, resource_dirs)
    if bodies:
        args += ["--to", ",".join(bodies)]
    if abs(width - 1.0) > 1e-6:
        args += ["--width", "{:g}".format(width)]
    if abs(length - 1.0) > 1e-6:
        args += ["--length", "{:g}".format(length)]
    if shape:
        args += ["--shape", shape]
    if compile_binary:
        args.append("--compile")
    if overwrite:
        args.append("--overwrite")
    return args


def start_variants(path, mdl_path, out_dir, bodies=(), width=1.0, length=1.0, shape="",
                   compile_binary=False, overwrite=False, preview_dir="",
                   game_dir="", resource_dirs=()):
    """Start cleanmodels variants and return the process. Its stdout is NDJSON:
    one "source" event, then "start" and "done" per variant (done carries
    output, and preview/body when preview_dir is given; from 4.8.0 also
    learnedFrom and adjusts), "error" for a variant that was not made, then
    "summary"."""
    args = ["variants", "--json-lines"] + _variants_args(
        bodies, width, length, shape, compile_binary, overwrite, game_dir, resource_dirs)
    if preview_dir:
        args += ["--preview-dir", preview_dir]
    return subprocess.Popen([path] + args + [mdl_path, out_dir], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def dry_run(path, mdl_path, out_dir, overwrite=False, game_dir="", resource_dirs=()):
    """cleanmodels variants --dry-run (4.8.0 or later). Returns (variants, error):
    per variant a dict with target, file, action ("write", "replace" or
    "skip", with the reason in reason), adjusts (the fit settings that change it) and
    learnedFrom (existing pairs its fit was learned from; absent when measured)."""
    args = ["variants", "--dry-run", "--json"] + _variants_args(
        overwrite=overwrite, game_dir=game_dir, resource_dirs=resource_dirs)
    try:
        result = _run(path, args + [mdl_path, out_dir])
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)
    try:
        return json.loads(result.stdout), ""
    except ValueError:
        return None, _strip_prefix(result.stderr or result.stdout, mdl_path)
