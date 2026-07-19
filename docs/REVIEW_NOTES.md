# Review notes (checklist)

Use this instead of embedding full source dumps. Read live code under
`re2_outfit_converter/` and the docs below.

## Architecture docs

- [PIPELINE.md](PIPELINE.md) — 16-stage convert order and stage interactions
- [BINARY_PATCHING.md](BINARY_PATCHING.md) — same-length overlays, allowlist, limits

## Entry points

| Entry | Module |
|-------|--------|
| GUI | `python main.py` → `gui.run` |
| CLI | `python -m re2_outfit_converter` → `cli.main` |
| Load path | `session.load_inputs` (shared by GUI + CLI) |
| Convert | `converter.convert` / `convert_batch` |

## Review checklist

- [ ] Pipeline stage order still matches `docs/PIPELINE.md` and the comment in `converter.py`
- [ ] `rename_map` is complete before `path_patch.patch_binaries`
- [ ] Classic UI stash restore runs before remap (`costume_ui`)
- [ ] Contentsholder is deleted, never retargeted (`contentsholder`)
- [ ] AddonFor linking uses `session.link_orphan_addons` (GUI + batch)
- [ ] Packaging uses public APIs (`make_zip`, `update_modinfo`, …)
- [ ] E2E tests in `tests/test_e2e_convert.py` pass
- [ ] CLI `analyze` / `convert` / `list-outfits` work without CustomTkinter
- [ ] Skipped path patches surface as warnings (GUI + CLI)

## Known hard edges

- Same-length binary patches only (see BINARY_PATCHING.md)
- `'98 Classic` is detect-only
- GUI is Windows-primary; CLI is the Steam Deck / Linux path
- `gui.py` still holds layout/event wiring; settings/workers/analysis are split out
