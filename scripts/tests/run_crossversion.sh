#!/bin/bash
# Export meshes made in Blender in several Blender versions and check the
# MDLs are byte-identical (all but the header comment, which names the
# Blender version and the date). The meshes are crossversion.py's own and
# those in fixtures/; extra mesh.json files can be given.
#   scripts/tests/run_crossversion.sh OUT_DIR "BLENDER1 BLENDER2 ..." [mesh.json]...
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
ADDON=$(cd "${NVB_ADDON:-$HERE/../../neverblender}" && pwd)  # NVB_ADDON: another add-on to test
OUT=$1
BLENDERS=$2
shift 2
mkdir -p "$OUT/scripts/addons" "$OUT/config"
ln -sfn "$ADDON" "$OUT/scripts/addons/neverblender"
status=0
first=
for b in $BLENDERS; do
    v=$("$b" -b --factory-startup --version 2>/dev/null | head -1 | awk '{print $2}')
    BLENDER_USER_SCRIPTS="$OUT/scripts" BLENDER_USER_CONFIG="$OUT/config" \
        "$b" -b --factory-startup --python "$HERE/crossversion.py" -- "$OUT/$v" "$@" > "$OUT/$v.log" 2>&1 || status=1
    echo "$v: exported $(grep -c '^CROSSVERSION exported' "$OUT/$v.log")"
    if [ -z "$first" ]; then first=$v; continue; fi
    for f in "$OUT/$first"/*.mdl; do
        g="$OUT/$v/$(basename "$f")"
        if ! cmp -s <(grep -v '^# NeverBlender ' "$f") <(grep -v '^# NeverBlender ' "$g"); then
            echo "differs: $(basename "$f") ($first vs $v)"; status=1
        fi
    done
done
[ $status = 0 ] && echo "CROSSVERSION identical"
exit $status
