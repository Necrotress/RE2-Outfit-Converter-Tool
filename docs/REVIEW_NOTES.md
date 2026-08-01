# Review notes (checklist)

Use this instead of embedding full source dumps. Read live code under
`re2_outfit_converter/` and the docs below.

## Architecture docs

- [PIPELINE.md](PIPELINE.md) — convert stage order and stage interactions
- [BINARY_PATCHING.md](BINARY_PATCHING.md) — same-length overlays, allowlist, limits

## Entry points

| Entry | Module |
|-------|--------|
| GUI | `python main.py` → `gui.run` |
| Load path | `session.load_inputs` |
| Convert | `converter.convert` / `convert_batch` |

## Review checklist

- [ ] Pipeline stage order still matches `docs/PIPELINE.md` and the comment in `converter.py`
- [ ] `rename_map` is complete before `path_patch.patch_binaries`
- [ ] Classic UI stash restore runs before remap (`costume_ui`)
- [ ] Contentsholder is deleted, never retargeted (`contentsholder`)
- [ ] AddonFor linking uses `session.link_orphan_addons` (GUI + batch)
- [ ] Packaging uses public APIs (`make_zip`, `update_modinfo`, …)
- [ ] E2E tests in `tests/test_e2e_convert.py` pass
- [ ] Skipped path patches surface as warnings
- [ ] Converted packs have no author `figurescene_pl1000_*` / `figure_pl1000_*`
      (ids 10–13); Records viewer relies on vanilla scene + remapped body
- [ ] Multi-target converts keep all target `mes_sys_clairecos_*.msg` files
      (`sync_costume_names_for_targets`, not last-wins)

## Known hard edges

- Same-length binary patches only (see BINARY_PATCHING.md)
- `'98 Classic` is detect-only
- Author figure gallery scenes are stripped on convert (not retargeted) to
  prevent cross-outfit model-viewer bleed; gallery shows remapped body via
  the game's vanilla DLC figure scene
- Delete-only runs still isolate shared face/hair and remove DLC contentsholders
  (remaining unticked slots are not fully "untouched" at the shared-asset layer)
- Linux package runs the same CustomTkinter GUI via `./run.sh` (source + venv)
- `gui.py` still holds layout/event wiring; settings/workers/analysis are split out
- Pack Linux zip with `pack-linux.bat`
