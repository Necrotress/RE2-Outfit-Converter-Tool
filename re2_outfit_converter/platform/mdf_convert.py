"""RT mdf2.21 → classic mdf2.10.

Paired Schoolgirl materials differ in header layout and size (mdfVersion 3 vs 1
per Noesis). Safe structural rewrite needs a material serializer.

Note: byte at offset 6 is a material count, not an RT/classic version marker.
"""

from __future__ import annotations

from .reports import FormatConversionError

MDF_MAGIC = b"MDF\x00"


def is_rt_mdf(data: bytes) -> bool:
    """True if buffer looks like an MDF container (versioning is via filename)."""
    return len(data) >= 16 and data[:4] == MDF_MAGIC


def convert_mdf(data: bytes) -> bytes:
    if len(data) < 4 or data[:4] != MDF_MAGIC:
        raise FormatConversionError("Not an MDF file.")
    raise FormatConversionError(
        "mdf2.21 -> mdf2.10 requires a full re-export "
        "(RE Mesh Editor). Binary downgrade is not supported."
    )
