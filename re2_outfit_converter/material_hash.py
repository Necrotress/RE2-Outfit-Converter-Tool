"""Murmur3 material-name hashes used inside RE Engine .mdf2 files."""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .reports import ConversionReport

_MAT_NAME_RE = re.compile(r"^pl1\d{3}_[A-Za-z0-9_]+_Mat$")


def murmur3_32(data: bytes, seed: int = 0xFFFFFFFF) -> int:
    """32-bit MurmurHash3 (x86) — matches RE Engine material name hashes."""
    c1 = 0xCC9E2D51
    c2 = 0x1B873593
    length = len(data)
    h = seed & 0xFFFFFFFF
    i = 0
    while i + 4 <= length:
        k = struct.unpack_from("<I", data, i)[0]
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
        i += 4
    k = 0
    rem = data[i:]
    if len(rem) >= 3:
        k ^= rem[2] << 16
    if len(rem) >= 2:
        k ^= rem[1] << 8
    if len(rem) >= 1:
        k ^= rem[0]
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
    h ^= length
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h


def material_name_hash(name: str) -> int:
    """Hash of the UTF-16LE material name (no null terminator)."""
    return murmur3_32(name.encode("utf-16-le"))


def is_material_name(token: str) -> bool:
    return bool(_MAT_NAME_RE.match(token))


def patch_mdf_material_hashes(
    staging: Path,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    """Update .mdf2 Murmur hashes after material name string overlays.

    RE Engine stores both the UTF-16 material name and its Murmur3 hash.
    Overlaying only the name (e.g. pl1006_Body_Mat → pl1004_Body_Mat) leaves
    a stale hash and the body fails to bind (invisible outfit). Rain/wet also
    depends on materials resolving correctly after a body-ID retarget.
    """
    pairs = [
        (old, new) for old, new in rename_map.items()
        if is_material_name(old) and is_material_name(new) and len(old) == len(new)
    ]
    if not pairs:
        return

    hash_pairs = [
        (struct.pack("<I", material_name_hash(old)),
         struct.pack("<I", material_name_hash(new)),
         old, new)
        for old, new in pairs
    ]

    for f in staging.rglob("*"):
        if not f.is_file() or ".mdf2" not in f.name.lower():
            continue
        try:
            data = f.read_bytes()
        except OSError as e:
            report.warnings.append(
                f"Skipped material hash patch for "
                f"{f.relative_to(staging).as_posix()}: {e}")
            continue
        out = bytearray(data)
        total = 0
        for old_h, new_h, old, new in hash_pairs:
            if old_h == new_h:
                continue
            # Only rewrite hashes in files that carry the material name
            # (old or new — path_patch may already have overlaid the string).
            # Avoids blind 4-byte collisions with unrelated dwords.
            if (old.encode("utf-16-le") not in data
                    and new.encode("utf-16-le") not in data):
                continue
            start = 0
            while True:
                idx = out.find(old_h, start)
                if idx < 0:
                    break
                out[idx:idx + 4] = new_h
                total += 1
                start = idx + 4
        if total:
            f.write_bytes(bytes(out))
            report.patch_ops.append(
                f"{f.relative_to(staging).as_posix()}  "
                f"({total} material hash(es))"
            )
