"""RT pfb.17 → classic pfb.16 (and chain.46 → chain.21 stub).

Paired Schoolgirl prefabs differ in size and internal layout, not only paths.
"""

from __future__ import annotations

from .reports import FormatConversionError

PFB_MAGIC = b"PFB\x00"
CHAIN_MAGIC_PREFIXES = (b"CHN\x00", b"CHAIN")


def is_rt_pfb(data: bytes) -> bool:
    return len(data) >= 4 and data[:4] == PFB_MAGIC


def convert_pfb(data: bytes) -> bytes:
    if len(data) < 4 or data[:4] != PFB_MAGIC:
        raise FormatConversionError("Not a PFB file.")
    raise FormatConversionError(
        "pfb.17 -> pfb.16 requires a full re-export or a dual-pack that "
        "already includes natives/x64 prefabs. Binary downgrade is not "
        "supported."
    )


def convert_chain(data: bytes) -> bytes:
    raise FormatConversionError(
        "chain.46 -> chain.21 binary downgrade is not supported. "
        "Re-export with RE Mesh Editor or use a dual-pack classic tree."
    )
