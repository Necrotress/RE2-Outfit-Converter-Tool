# Changelog

All notable changes to **RE2 Remake Outfit Converter** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/).

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
- Repo layout: `Source/` is the git root; sibling `Build/` is the local
  test exe; `Production/` is pack output. `rebuild.bat` /
  `pack-windows.bat` build into `Build/` work dirs.
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

[1.1.8]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.1.8
[1.1.0]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.1.0
[1.0.0]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.0.0
