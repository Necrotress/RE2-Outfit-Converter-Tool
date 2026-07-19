# Binary path patching

After filesystem renames, the converter rewrites **same-length** engine path
strings inside selected binaries so PFBs / materials still find the new files.

Implementation: [`re2_outfit_converter/path_patch.py`](../re2_outfit_converter/path_patch.py).

## What we patch

- **ASCII** path bytes (case-insensitive match, overlay preserves unchanged casing)
- **UTF-16LE** ASCII runs stored as `(byte, 0)` pairs (common in RE Engine)

Only pairs from `rename_map` where `len(old) == len(new)` are applied. Private
face/hair IDs (`pl1050` → `pl18xx`) and body IDs are the same length by design.

## What we skip

| Skip reason | Behavior |
|-------------|----------|
| Length mismatch | Warning; that rename is not patched in binaries |
| Non-allowlisted extension | File not opened (textures, MSG, ini, images, …) |
| File larger than 32 MiB | Warning; not scanned |

Allowlisted types live in `outfits.PATCHABLE_TYPES` (`pfb`, `mdf2`, `chain`,
`mesh`, `scn`, …). This replaced an older denylist of “everything except
textures” so convert time on huge CR-AW packs stays reasonable.

## Assumptions / limitations

1. Paths in binaries match the engine-relative form produced by
   `paths.engine_path` (e.g. `sectionroot/.../pl1004.mdf2`), not always the
   full `natives/x64/...` on-disk path.
2. We do **not** parse RE Engine structures — only string overlays. False
   positives are possible but rare for these path patterns.
3. If a mod embeds a path that changes length under rename, that reference
   stays on the old ID. Check completion warnings for “length mismatch” /
   “Binary path patch skips”.
4. Injected hair redirect PFBs rely on `rename_map` aliases registered
   **before** this stage (see [PIPELINE.md](PIPELINE.md)).

## Not a full serializer

A proper RE Engine file rewriter would be more correct and more expensive.
Same-length overlays are the pragmatic approach used by this tool and many
community converters; treat unusual failures as “inspect the warning list,
then check in-game.”
