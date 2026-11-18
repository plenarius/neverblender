#!/bin/bash
# Export models with two versions of the add-on and compare the results.
#   scripts/tests/run_roundtrip.sh /path/to/blender BASE_ADDON_DIR OUT_DIR model.mdl...
# BASE_ADDON_DIR is the neverblender package to compare with (e.g. from
# `git archive origin/main neverblender | tar -x -C DIR`); the other is this
# checkout's. Lines that differ only in the header comment (version, date)
# are ignored. Exits non-zero if an export fails or the outputs differ.
set -eu
BLENDER=$1
HERE=$(cd "$(dirname "$0")" && pwd)
BASE=$(cd "$2" && pwd)
NEW=$(cd "$HERE/../../neverblender" && pwd)
OUT=$3
shift 3
status=0
for side in base new; do
    if [ $side = base ]; then addon=$BASE; else addon=$NEW; fi
    mkdir -p "$OUT/$side/scripts/addons" "$OUT/$side/config"
    ln -sfn "$addon" "$OUT/$side/scripts/addons/neverblender"
    BLENDER_USER_SCRIPTS="$OUT/$side/scripts" BLENDER_USER_CONFIG="$OUT/$side/config" \
        "$BLENDER" -b --factory-startup --python "$HERE/roundtrip.py" -- "$OUT/$side/export" "$@" \
        > "$OUT/$side.log" 2>&1 || status=1
    grep -c '^ROUNDTRIP ok' "$OUT/$side.log" | sed "s/^/$side: exported /"
    grep '^ROUNDTRIP FAILED' "$OUT/$side.log" || true
done
for f in "$OUT/base/export"/*; do
    g="$OUT/new/export/$(basename "$f")"
    if [ ! -f "$g" ]; then echo "only in base: $(basename "$f")"; status=1; continue; fi
    if ! diff -q <(grep -v '^# NeverBlender ' "$f") <(grep -v '^# NeverBlender ' "$g") >/dev/null 2>&1; then
        echo "differs: $(basename "$f")"; status=1
    fi
done
for g in "$OUT/new/export"/*; do
    [ -f "$OUT/base/export/$(basename "$g")" ] || { echo "only in new: $(basename "$g")"; status=1; }
done
[ $status = 0 ] && echo "ROUNDTRIP identical"
exit $status
