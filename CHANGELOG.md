# Changelog

All notable changes to **RE2 Remake Outfit Converter** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-07-28

### Added

- Multi-slot convert ops: `--map SRC:DST` / `--delete KEY` (GUI From checkboxes
  + CLI) for packs that ship more than one Claire outfit.
- Incomplete-slot detection when a body folder has textures/mdf but no `.mesh`,
  with load-set filtering so AddonFor texture overlays do not warn when a main
  mod already supplies the mesh.
- Military / default face mode (`dirty` / `clean`) when converting into slots
  that need a seeded face.
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

[1.1.0]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.1.0
[1.0.0]: https://github.com/Necrotress/RE2-Outfit-Converter-Tool/releases/tag/v1.0.0
