#!/bin/sh
# vendor_cleanmodels.sh [REF]: copy cleanmodels' Python port (python/cleanmodels in
# github.com/plenarius/cleanmodels) at REF (a tag or commit; default: origin/main) into
# neverblender/cleanmodels/, and record where it came from in neverblender/cleanmodels/VENDORED.
# Never edit the copy by hand: change cleanmodels, then run this again.
set -eu
REF=${1:-origin/main}
REPO=${CLEANMODELS_REPO:-https://github.com/plenarius/cleanmodels.git}
DEST=$(cd "$(dirname "$0")/.." && pwd)/neverblender/cleanmodels
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git clone -q --filter=blob:none --no-checkout "$REPO" "$TMP/cm"
git -C "$TMP/cm" checkout -q "$REF" -- python/cleanmodels
COMMIT=$(git -C "$TMP/cm" rev-parse "$REF^{commit}")  # the commit, also for an annotated tag
DESC=$(git -C "$TMP/cm" describe --tags --always "$COMMIT")
rm -rf "$DEST"
cp -r "$TMP/cm/python/cleanmodels" "$DEST"
rm -f "$DEST/__main__.py"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +
printf 'Copied by scripts/vendor_cleanmodels.sh from github.com/plenarius/cleanmodels python/cleanmodels.\nDo not edit: change cleanmodels and run the script again.\ncommit %s\ndescribe %s\n' "$COMMIT" "$DESC" > "$DEST/VENDORED"
echo "vendored cleanmodels $DESC ($COMMIT) into $DEST"
