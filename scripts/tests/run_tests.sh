#!/bin/sh
# Run the export tests in one Blender version.
#   scripts/tests/run_tests.sh /path/to/blender [ADDON_DIR] [OUT_DIR]
# ADDON_DIR is the neverblender package to test (default: this checkout's).
# The add-on is enabled from a scratch user scripts folder, so your own
# Blender settings are not touched. Exits non-zero if a test fails.
set -eu
BLENDER=$1
HERE=$(cd "$(dirname "$0")" && pwd)
ADDON=$(cd "${2:-$HERE/../../neverblender}" && pwd)
OUT=${3:-$(mktemp -d "${TMPDIR:-/tmp}/nvbtest.XXXXXX")}
mkdir -p "$OUT/scripts/addons" "$OUT/config" "$OUT/syspath"
ln -sfn "$ADDON" "$OUT/scripts/addons/neverblender"
ln -sfn "$ADDON" "$OUT/syspath/neverblender"
export BLENDER_USER_SCRIPTS="$OUT/scripts" BLENDER_USER_CONFIG="$OUT/config"
status=0
"$BLENDER" -b --factory-startup --python-exit-code 1 --python "$HERE/test_export.py" -- "$OUT/export" || status=1
# The add-on loaded from sys.path, not from an add-ons folder
BLENDER_USER_SCRIPTS="$OUT/config" "$BLENDER" -b --factory-startup --python-exit-code 1 \
    --python "$HERE/test_syspath.py" -- "$OUT/syspath" || status=1
echo "output in $OUT"
exit $status
