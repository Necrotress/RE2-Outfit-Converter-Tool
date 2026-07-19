"""Same-length ASCII / UTF-16LE engine path overlays in binaries."""

from __future__ import annotations

from pathlib import Path

from .outfits import patchable
from .reports import ConversionReport

# Skip reading/scanning files larger than this (bytes). Huge assets are almost
# never path carriers and dominate convert time on texture-heavy packs.
MAX_PATCH_FILE_BYTES = 32 * 1024 * 1024


def patch_binaries(staging: Path, rename_map: dict[str, str],
                    report: ConversionReport) -> None:
    """Rewrite same-length engine paths inside patchable binaries.

    Hot path for large mods: allowlisted extensions only, size-capped reads,
    lower-case once per file, cheap ``find`` before overlays (ASCII + UTF-16LE).
    """
    patterns: list[tuple[str, str, bytes, bytes]] = []
    length_skips = 0
    for old, new in sorted(rename_map.items(), key=lambda kv: -len(kv[0])):
        if len(old) != len(new):
            length_skips += 1
            report.warnings.append(
                f"Skipped path patch {old!r} -> {new!r}: length mismatch.")
            continue
        old_l = old.lower().encode("ascii")
        u16_l = b"".join(bytes([c, 0]) for c in old_l)
        patterns.append((old, new, old_l, u16_l))
    if length_skips:
        report.warnings.append(
            f"Binary path patch: {length_skips} rename(s) skipped "
            "(same-length paths only — see docs/BINARY_PATCHING.md).")
    if not patterns:
        return

    size_skips = 0
    for f in staging.rglob("*"):
        if not f.is_file() or not patchable(f.name):
            continue
        try:
            size = f.stat().st_size
        except OSError as e:
            report.warnings.append(
                f"Skipped binary patch for "
                f"{f.relative_to(staging).as_posix()}: {e}")
            continue
        if size > MAX_PATCH_FILE_BYTES:
            size_skips += 1
            report.warnings.append(
                f"Skipped binary patch for "
                f"{f.relative_to(staging).as_posix()}: "
                f"too large ({size} bytes > {MAX_PATCH_FILE_BYTES}).")
            continue
        try:
            data = f.read_bytes()
        except OSError as e:
            report.warnings.append(
                f"Skipped binary patch for "
                f"{f.relative_to(staging).as_posix()}: {e}")
            continue

        data_l = data.lower()
        u16_l_view = utf16_ascii_lower(data)
        if not any(old_l in data_l or u16_l in u16_l_view
                   for _, _, old_l, u16_l in patterns):
            continue

        total = 0
        for old, new, old_l, u16_l in patterns:
            if old_l in data_l:
                data, n = patch_ascii_ci(data, data_l, old, new, old_l)
                if n:
                    total += n
                    # ASCII overlays don't touch UTF-16 pairs.
                    data_l = data.lower()
            if u16_l in u16_l_view:
                data, n = patch_utf16_ci(data, u16_l_view, old, new, u16_l)
                if n:
                    total += n
                    u16_l_view = utf16_ascii_lower(data)
                    data_l = data.lower()

        if total:
            f.write_bytes(data)
            report.patch_ops.append(
                f"{f.relative_to(staging).as_posix()}  "
                f"({total} path reference(s))"
            )
    if size_skips:
        report.warnings.append(
            f"Binary path patch: skipped {size_skips} file(s) over size cap.")

def utf16_ascii_lower(data: bytes) -> bytes:
    """Lowercase ASCII letters stored as UTF-16LE (byte, 0) pairs."""
    out = bytearray(data)
    i = 0
    last = len(out) - 1
    while i < last:
        if out[i + 1] == 0 and 65 <= out[i] <= 90:  # A-Z
            out[i] += 32
            i += 2
        else:
            i += 1
    return bytes(out)

def patch_ascii_ci(
    data: bytes, data_lower: bytes, old: str, new: str, needle: bytes,
) -> tuple[bytes, int]:
    count = 0
    nlen = len(needle)
    start = 0
    # In-place via bytearray when hits exist.
    idx = data_lower.find(needle, start)
    if idx < 0:
        return data, 0
    out = bytearray(data)
    while idx >= 0:
        matched = bytes(out[idx:idx + nlen])
        out[idx:idx + nlen] = overlay(matched, old, new, 1)
        count += 1
        start = idx + nlen
        idx = data_lower.find(needle, start)
    return bytes(out), count

def patch_utf16_ci(
    data: bytes, data_u16_lower: bytes, old: str, new: str, needle: bytes,
) -> tuple[bytes, int]:
    count = 0
    nlen = len(needle)
    start = 0
    idx = data_u16_lower.find(needle, start)
    if idx < 0:
        return data, 0
    out = bytearray(data)
    while idx >= 0:
        matched = bytes(out[idx:idx + nlen])
        out[idx:idx + nlen] = overlay(matched, old, new, 2)
        count += 1
        start = idx + nlen
        idx = data_u16_lower.find(needle, start)
    return bytes(out), count

def overlay(matched: bytes, old: str, new: str, step: int) -> bytes:
    out = bytearray(matched)
    for i, (o, n) in enumerate(zip(old, new)):
        if o.lower() != n.lower():
            out[i * step] = ord(n)
    return bytes(out)
