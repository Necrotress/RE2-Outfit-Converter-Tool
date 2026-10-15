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
- [ ] Converted packs retarget figure gallery to the target frame (DLC id or
      base Claire/Leon paths); leftover non-target extras (ids 10–13) are stripped
- [ ] Multi-target converts keep all target `mes_sys_clairecos_*.msg` files
      (`sync_costume_names_for_targets`, not last-wins)

## Known hard edges

- Same-length binary patches only (see BINARY_PATCHING.md)
- `'98 Classic` is detect-only
- Author figure gallery scenes are retargeted on convert (DLC frame or base
  Claire paths) so Bonuses can load isolated face/hair; non-target extras are
  still stripped. Leaky shared mannequin scenes may still affect other Records
  viewers — re-test Dimitrescu-style packs after figure changes.
- Delete-only runs still isolate shared face/hair and remove DLC contentsholders
  (remaining unticked slots are not fully "untouched" at the shared-asset layer)
- Linux package runs the same CustomTkinter GUI via `./run.sh` (source + venv)
- `gui.py` still holds layout/event wiring; settings/workers/analysis are split out
- Pack Linux zip with `pack-linux.bat`
