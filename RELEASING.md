Releasing
=========

`main` is protected: every change, the version bump included, goes through
a pull request. Release tags (`v*`) cannot be moved or deleted once pushed.

1. In `neverblender/__init__.py`, set `bl_info["version"]` to the new
   version and read the rest of `bl_info`: `location`, `tracker_url` (bug
   reports must come here) and `wiki_url` must still be right; Blender shows
   them in the add-on list. Settle anything left over for this release first.
   Open a pull request for it and merge it.
2. Run the release check on Blender 3.3, 3.6, 4.0, 4.5 and 5.2 (every model
   round-trips, exports match across versions, the tools work). It must pass.
3. Tag the merged commit and push the tag:
   `git fetch origin && git tag -a vX.Y.Z -m vX.Y.Z origin/main && git push origin vX.Y.Z`.
   The release workflow checks the tag against `bl_info`, builds
   `neverblender-X.Y.Z.zip` and publishes the release. A suffix
   (`vX.Y.Z-rc1`) makes a pre-release.
4. Replace the generated notes with real ones:
   `gh release edit vX.Y.Z --notes-file notes.md`. Say which Blender versions
   were tested.
5. Download the zip and install it in Blender (*Install...* / *Install from
   Disk...*) to make sure the published file works.
