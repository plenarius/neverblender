Neverblender
============

A Blender add-on to import, edit and export Neverwinter Nights models (Aurora
engine `.mdl`, walkmeshes and `.set` files), for Blender 3.3 through 5.2.

This is a maintained continuation of Neverblender by Attila Györkös
(Symmetric on the Neverwinter Vault), with SpacePope's Blender 5.0 work and
tools, and further fixes. See [Credits](#credits).

Install
-------

1. Download `neverblender-<version>.zip` from the
   [releases](https://github.com/plenarius/neverblender/releases). Do not
   unzip it.
2. In Blender: *Edit > Preferences > Add-ons*, then *Install...* (Blender
   3.3 to 4.1) or the *v* menu, *Install from Disk...* (Blender 4.2 and
   later), and pick the zip.
3. Enable *Import-Export: Neverblender*.

If you have another Neverblender installed, remove it first (*Remove* in the
add-on's entry, then restart Blender).

Models are imported and exported from *File > Import / Export > Aurora Model
(.mdl)*.

Supported Blender versions
--------------------------

One release works on all of these; each release is tested on:

| Blender | |
|---|---|
| 3.3 LTS, 3.6 LTS | supported |
| 4.0, 4.5 LTS | supported |
| 5.2 LTS | supported |

The test round-trips models (a skinned and animated creature, a placeable with
an emitter, a tile with its walkmesh, ...) through import and export in each
version and compares the results, and exercises the tools below. Binary models
must import exactly as the cleanmodels program reads them. Exports from
3.6, 4.x and 5.x are identical; 3.3's differ only in the last decimals of some
rotations.

What's in it
------------

Everything in Neverblender 4.0 (the last Neverwinter Vault release), plus:

- **Blender 3.3 to 5.2** in one add-on (the 4.0 release ran on Blender 4.0
  only).
- **Smoothing groups are kept.** Neverblender used to rebuild them from
  sharp edges on export, which changed how unedited models shade in game.
  Imported smoothing groups now go back out as they came in; faces made by
  extruding or subdividing take the group of the face they came from.
- **Positions with 7 decimals** instead of 5: thin, two-sided meshes no
  longer shade differently after a round trip.
- **Binary models import directly**, with cleanmodels' decompiler built in:
  the same model the cleanmodels program reads, emitters, animated meshes and
  skinned body parts included, with or without cleanmodels installed.
- **Import warnings are shown** in Blender (a popup and the Info editor), not
  only in the system console: what the decompiler warns about (a skin whose
  vertices have no bone weights, a skeleton that isn't found, ...), and a
  model or walkmesh that can't be read.
- **Animated meshes (animmesh)** import whole: every sample, whatever the
  animation length. Vertex samples are shape keys, as before; UV samples are
  mesh attributes named `animtverts.<animation>.<sample>` (face corner,
  vector: u, v, 0; *Object Data properties > Attributes*), so there is no
  limit of 8 as with UV maps. Files saved by older versions, which have them as
  UV maps, still export. Each animation's sample period is kept on the mesh
  (custom property `sampleperiod.<animation>`) and written back unless its
  shape key samples were moved.
- **PLT textures**: *File > Import / Export > NWN PLT Texture (.plt)*, and
  *Image > Setup PLT Layer Images* in the image editor; an optional autoreload
  of PLT files changed on disk (add-on preferences).
- **NWN DDS textures show up.** The game's own DDS format (no `DDS ` magic)
  is converted to PNG on import and cached in `~/.cache/nwn-dds`; the image
  keeps the texture's name, so exports still write the right bitmap. Turn it
  off in the add-on preferences; *Image > Convert NWN DDS textures* converts
  on demand.
- **Export Phenotypes**: *File > Export > Aurora Phenotypes (.mdl)* exports a
  model scaled for each race and gender.
- Armature tools: *Update Animation*, hook skinmeshes, world coordinates.
- Fixes: importing a model a second time in one session no longer fails;
  the external decompiler setting works with cleanmodels 4; models with stray
  `node` lines, empty emitter values or a face that uses a vertex twice import
  (checked on the game's own models); MTR files with accented characters
  import on Linux and macOS.

cleanmodels (optional)
----------------------

Neverblender works on its own. If it finds
[cleanmodels](https://github.com/plenarius/cleanmodels) 4.5.1 or later (the
path in the add-on preferences, or anywhere on your `PATH`), it also:

- **imports every model through cleanmodels.** Binary models are decompiled
  with skinned body parts bound to the right skeleton bones (found next to the
  model or in your game install, set *Game folder* in the preferences if it is
  not found), and hand-edited or malformed ASCII is read in a clean form.
  Turn off *Import through cleanmodels* in the preferences to use
  Neverblender's own reader;
- **checks exported models** (*Check with cleanmodels* in the export options,
  on by default) and lists the findings in *Scene properties > cleanmodels*,
  with a button that selects the object each finding is about;
- **compiles exported models** to game-ready binaries (*Compile with
  cleanmodels*, off by default; walkmeshes stay ASCII).
- **makes variants** (cleanmodels 4.7.0 or later): *Scene properties >
  cleanmodels Variants* fits the selected robe, cloak or armour part
  (named for its body, like `pmh0_robe003` or `pfe0_chest050`) to the other
  races and phenotypes of its gender and writes `pmd0_robe003.mdl` and so on
  to the output folder. *Find Bodies* lists the bodies so you can pick some;
  *Fit* loosens, lengthens or reshapes the fit by region; *Show on Bodies*
  imports each variant on its body into a *Variants* collection, races side
  by side and one row per phenotype, to check the fit before using the files. With cleanmodels 4.8.0 or
  later, *Find Bodies* also shows how each variant will be fitted (learned
  from the existing race versions of that part, or measured) and which files
  already exist, and greys out the *Fit* settings that would not change the
  chosen variants.
  Custom bodies come from *Resources*: add each race's hak (or folder) and the
  hak with `racialtypes.2da` and `phenotype.2da` for their names. *All
  Bodies* lists every body in the game install and the resources, without
  selecting a model, and marks the ones only the resources have.

Without cleanmodels, binary models are read by a copy of cleanmodels'
decompiler that ships with Neverblender (`neverblender/cleanmodels`, from the
cleanmodels repository, where CI checks it gives the same output as the
cleanmodels program). Skinned body parts (`pmh0_neck001` and the like) get their
bone names from the creature skeleton: next to the model, or in the game folder
(*Game folder* in the preferences, or the usual install locations).

Reporting problems
------------------

Open an issue here: https://github.com/plenarius/neverblender/issues. Attach
the model if you can share it, and say which Blender version you use. Please
don't send Neverblender issues to the original authors; they no longer
maintain it.

Credits
-------

- **Attila Györkös** (gyoerkaa, Symmetric on the Neverwinter Vault) wrote
  Neverblender. The history here is his
  [mdltools](https://github.com/gyoerkaa/mdltools) repository up to 2.8.48,
  then his Vault releases 2.8.51 and 4.0 (code he did not push to GitHub),
  each imported unchanged. He agreed to it being continued here.
- **SpacePope** ported it to Blender 5.0 and added a built-in decompiler (since
  replaced by cleanmodels'),
  the PLT tools, Export Phenotypes and the armature tool changes, imported
  unchanged from the version they shared. Used with their permission; they
  do not support it, so report problems here.
- **plenarius** maintains this repository: Blender 3.3 to 5.2, smoothing
  groups, precision, the cleanmodels integration, NWN DDS textures and fixes.

License
-------

GPL-3.0-or-later, see [neverblender/COPYING](neverblender/COPYING).
