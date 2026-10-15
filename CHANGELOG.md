# Changelog

All notable changes to **RE2 Remake Outfit Converter** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/).

## [1.3.1] — 2026-10-14

The main window is restyled. Convert behavior is unchanged from 1.3.0.

### Changed

- The main window is two cards: the loaded mod, then convert. Costume names is a tag icon, and that dialog scrolls when the window is short.
- Convert menus show either the outfit name or its tag. Settings, under Skip completion dialog, chooses which.

### Removed

- The old checkboxes that showed both the outfit name and its tag in convert menus.

## [1.3.0] — 2026-10-14

Classic and ray tracing in one window, including mods that are not a Claire or Leon outfit.

### Added

- A mod with no Claire or Leon outfit converts between Classic and ray tracing on its own. The outfit line names who it affects, such as Sherry.
- Costume names has a color row. Every color, including red and blue, inserts ``<COLOR FF4040>Name</COLOR>``. Named tags like ``<COL RED>`` and comma RGB are ignored by the costume menu.

### Changed

- Analysis shows Classic, Ray tracing, or both. Convert to has a Game build menu that starts on the detected build. Choosing the other build runs the ray-tracing conversion around the outfit stages.
- Settings can point at Blender 4.3 and RE Mesh Editor. Mesh and material conversion stops if that work is required and Blender is not ready. Texture conversion stays in Python. Prefabs and physics chains are copied.
- ``[RTX]`` / ``[Non-RTX]`` zip and modinfo Description tags are added only when a convert changes the game build.
- A custom Claire face left on the shared head (``pl1050``) is kept on the destination costume, so other outfits keep the pak head and neck.
- Ray-tracing cloth is published when the classic body prefab matches a jacket template (default, costume 1, costume 2, costume 8, costume 9). Other bodies are not given a new chain.
- A local rebuild keeps only the runnable app. PyInstaller scratch folders are removed when the copy finishes.

### Removed

- Skip conversion confirmation.
- Add outfit tag to modinfo Name. That tag collided with AddonFor packs.

### Fixed

- Add outfit tag to modinfo Name now writes ``Name=`` (inserts the line when missing, and still matches BOM / spaced keys).
- Leon Noir / Arklay Sheriff costume-select preview copies shared hair onto ``pl0074`` / ``pl0075`` under ``pl0000`` (same hide as Claire Noir/Military).
- A UTF-8 BOM on ``modinfo.ini`` no longer drops the mod name on load.
- Legacy ``tag_output`` still controls zip tagging when only the Description flag was saved.
- Shared-hair redirects no longer pick up another slot's exclusive hat materials or chain when both kits are isolated in the same convert.
- Costume Name Pack detection still matches ``modinfo.ini`` when the Name line has a UTF-8 BOM or spaces around ``=``.

## [1.2.0] — 2026-08-14

Leon convert, costume-name pack editing, Settings polish, and several
convert edge cases.

### Added

- **Leon outfit convert**: same pipeline as Claire, targeting Leon slots
  under `pl0000` (Casual / Police / Injured / Classic* / Noir / Arklay
  Sheriff). From/To menus filter by detected character; mixed Claire+Leon
  ops in one convert are rejected. Leon `'98` stays detect-only.
- **Leon DLC in-game names on Convert**: Noir / Arklay Sheriff write
  `mes_sys_leoncos_*.msg` (same pattern as Claire clairecos).

### Changed

- **Costume names** opens the existing pack in the output folder (if any),
  fills in the saved names, and Save overwrites that pack. It no longer
  writes a second file such as `Costume Name Pack.zip (2)`. The dialog
  remembers its window position. Esc closes it.
- **Settings**: Outfit tags is its own collapsible section (Claire / Leon
  lists nested inside). The window is a fixed size and scrolls the lists;
  collapse / expand no longer resizes it. Position is remembered (not
  height). Header control is a gear icon. Esc closes Settings. Tagging is
  split into three checkboxes — zip / folder name and modinfo Description
  (on by default), modinfo Name (off). Older ``tag_output`` settings
  migrate to zip + Description.
- `rebuild.bat` / `pack-windows.bat` / `pack-linux.bat` write under in-repo
  `build/` and `release/` (clone-friendly). Optional `RE2OC_BUILD_DIR` /
  `RE2OC_RELEASE_DIR` overrides. Docs updated.

### Fixed

- Convert adds `Description=[Outfit]` to `modinfo.ini` when the source mod
  had no Description line, so the outfit tag is not skipped.
- Leon convert into Noir / Arklay Sheriff no longer injects a Claire
  ``pl1070`` hair redirect under ``pl0000`` (missing chain froze on outfit
  switch and cutscenes). Hide-exclusive uses Leon shared ``pl0070``.
- Leon hair isolation / hide-exclusive now scans ``pl0000`` mesh roots
  (not Claire ``pl1000``), so exclusive hats are seen and redirects are
  not skipped.
- Leon mesh packs with leftover Claire textures (e.g. Marston Sheriff +
  ``pl1000`` chain tex) are detected as Leon instead of tying to Claire Jacket.
- Settings no longer flashes at the original map location when closing.

## [1.1.8] — 2026-08-01

Leon convert, costume-name pack editing, Settings polish, and several
convert edge cases.

### Added

- **Leon outfit convert**: same pipeline as Claire, targeting Leon slots
  under `pl0000` (Casual / Police / Injured / Classic* / Noir / Arklay
  Sheriff). From/To menus filter by detected character; mixed Claire+Leon
  ops in one convert are rejected. Leon `'98` stays detect-only.
- **Leon DLC in-game names on Convert**: Noir / Arklay Sheriff write
  `mes_sys_leoncos_*.msg` (same pattern as Claire clairecos).

### Changed

- **Costume names** opens the existing pack in the output folder (if any),
  fills in the saved names, and Save overwrites that pack. It no longer
  writes a second file such as `Costume Name Pack.zip (2)`.
- **Settings**: Outfit tags is its own collapsible section (Claire / Leon
  lists nested inside). The window remembers position and which sections
  are expanded. Tagging is split into three checkboxes — zip / folder name
  and modinfo Description (on by default), modinfo Name (off). Older
  ``tag_output`` settings migrate to zip + Description.
- `rebuild.bat` / `pack-windows.bat` / `pack-linux.bat` write under in-repo
  `build/` and `release/` (clone-friendly). Optional `RE2OC_BUILD_DIR` /
  `RE2OC_RELEASE_DIR` overrides. Docs updated.

### Fixed

- Convert adds `Description=[Outfit]` to `modinfo.ini` when the source mod
  had no Description line, so the outfit tag is not skipped.
- Leon convert into Noir / Arklay Sheriff no longer injects a Claire
  ``pl1070`` hair redirect under ``pl0000`` (missing chain froze on outfit
  switch and cutscenes). Hide-exclusive uses Leon shared ``pl0070``.
- Leon mesh packs with leftover Claire textures (e.g. Marston Sheriff +
  ``pl1000`` chain tex) are detected as Leon instead of tying to Claire Jacket.
- Settings no longer flashes at the original map location when closing.

## [1.1.8] — 2026-08-01

Public release since **1.1.0**. Includes pipeline, GUI, and packaging work that
landed after that release (formerly tracked as 1.1.5 / 1.1.6 / unreleased).

### Added

- **Costume names** button: builds a small Fluffy pack that sets Claire
  (Jacket / Tank Top / Classic Jacket / Classic Tank Top) and Leon
  (Casual / Police / Classic Police, including Injured) costume-menu names
  together. Those rows share one game MSG file — one pack can set either or
  both so they do not overwrite each other. Blank fields keep vanilla; at
  least one edit is required. Claire / Leon tabs in the dialog.
- Multi-slot convert ops in the GUI: Convert-from checkboxes, Delete on
  multi-outfit packs, ▸ focus marker, per-row Convert-to.
- Incomplete-slot detection (textures/mdf without `.mesh`), with load-set
  filtering so AddonFor overlays do not warn when a main mod already has
  the mesh.
- Exclusive hat/headband hide + bundled exclusive `.mdf2` seeding so
  costume-select 3D preview matches gameplay hair redirects.
- Material-hash patching for remapped `*_Mat` names in `.mdf2` files.
- Figure-gallery isolation: author `figurescene_pl1000_*` / `figure_pl1000_*`
  extras are stripped so Records viewers use the vanilla scene + remapped
  body (prevents cross-outfit bleed).
- Convert log: Settings option (on by default) embeds `convert.log` in the
  output with From→To ops, file changes, and warnings.
- Linux GUI package (`pack-linux.bat`, `./run.sh`).

### Changed

- **GUI-only product:** CLI module, `python -m` entry, `convert.sh` /
  `menu.sh`, and CLI docs/tests removed. Windows and Linux ship the
  CustomTkinter GUI only.
- Repo layout documented for local packaging; pack scripts later moved to
  in-repo `build/` + `release/` (see 1.2.0).
- Convert-time "Set in-game outfit name" is **Elza / Noir / Military** only.
  Jacket / Tank / Classic* hint to use **Costume names** instead; convert
  no longer ships the shared costume MSG renames.
- ANALYSIS panel: short outfit names only (no PFB slots / mesh IDs / file
  counts). Characters row removed; non-Claire content is a brief note.
  Window default/minimum height reduced so Convert controls get more space.
- Military face is automatic: converting **to Military** seeds Claire's
  clean default face when the mod has no custom face data. Dirty/clean
  toggle removed. Other targets never seed face textures.
- Tank Top converts strip leftover Military `*_04` face texture folders
  **before** face isolation so Claire's default face is used.
- Costume-select preview: when remapping onto a slot that already has
  preview art, the Convert-from art replaces the existing target preview.
- In-game name UI keeps a fixed layout so Convert-to switches do not resize
  the window.
- Convert log: single Changes section with counts; empty categories noted
  in a footer; Name / Face / Military face one-liners under Operations.
- Costume MSG sync writes all clairecos convert targets in one pass so
  multi-target converts keep every `mes_sys_clairecos_*.msg`.

### Fixed

- Tank Top dirty-face leftover: mods that only ship Military `pl1050_04`
  face textures no longer keep those textures after convert.
- Dual-slot dress packs: promote deleted-slot body textures onto the
  convert source before strip; AddonFor Delete remaps to the batch target
  when needed.
- Hair redirects use real mesh/mdf stems inside custom hair folders;
  isolate all hair kits; per-target redirects; Delete strips exclusive hats.
- Records model-viewer bleed when remapping author figure scenes onto
  another DLC frame; figure strip also runs on delete-only paths.

## [1.1.0] — 2026-07-28

### Added

- Multi-slot convert ops: `--map SRC:DST` / `--delete KEY` (GUI From checkboxes
  + CLI) for packs that ship more than one Claire outfit.
- Incomplete-slot detection when a body folder has textures/mdf but no `.mesh`,
  with load-set filtering so AddonFor texture overlays do not warn when a main
  mod already supplies the mesh.
- Exclusive hat/headband mesh hide + bundled exclusive `.mdf2` seeding so
  costume-select 3D preview matches gameplay hair redirects.
- Material-hash patching for remapped `*_Mat` names in `.mdf2` files.
- Linux GUI package (`pack-linux.bat`, `./run.sh`, `./menu.sh`) alongside CLI.
- Figure-gallery isolation: author `figurescene_pl1000_*` / `figure_pl1000_*`
  extras (ids 10–13) are stripped so Records viewers use the vanilla scene +
  remapped body (prevents cross-outfit bleed).
- Convert log: Settings option (on by default) embeds `convert.log` inside
  the output zip/folder with From→To ops, file changes, and warnings.
- Clearer multi-slot Convert-from focus (▸ marker) and in-game name tied to
  the focused row’s Convert-to target (per-target names on convert).

### Changed

- Costume MSG sync writes all convert targets in one pass so multi-target
  converts keep every `mes_sys_clairecos_*.msg` (no last-wins wipe).
- Stronger `.gitignore` for builds, archives, local mods, and debug trees.
- Docs / user guide updated for the 1.1 pipeline.

### Fixed

- Records model-viewer bleed when remapping author figure scenes onto another
  DLC frame (e.g. Dimitrescu-style packs showing in Noir and Military).
- Figure strip also runs on delete-only paths so leftover gallery files cannot
  linger after slot removal.

## [1.0.0] — 2026-07-27

### Added

- Initial public release: Windows GUI (CustomTkinter) + CLI convert/analyze.
- Claire outfit remapping (Jacket, Tank Top, Classic, Noir, Military, Elza).
- Face/hair isolation onto private mesh IDs; AddonFor batch packaging.
- Same-length binary path patching; Fluffy-ready zip/folder output.

[1.3.1]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.3.1
[1.3.0]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.3.0
[1.2.0]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.2.0
[1.1.8]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.1.8
[1.1.0]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.1.0
[1.0.0]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.0.0
