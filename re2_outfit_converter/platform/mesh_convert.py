"""RT mesh.2109108288 → classic mesh.1808312334.

Schoolgirl paired samples differ across nearly the entire file (different
meshVersion / meshMagic serialization). A safe byte-level downgrade is not
possible without a full RE Engine mesh re-serializer (RE Mesh Editor / Noesis).
"""

from __future__ import annotations

import struct

from .reports import FormatConversionError

MESH_MAGIC = b"MESH"
# Noesis formats table: RERT meshMagic=21041600, RE2 meshMagic=386270720
MESH_MAGIC_RT = 21041600
MESH_MAGIC_CLASSIC = 386270720


def is_rt_mesh(data: bytes) -> bool:
    if len(data) < 8 or data[:4] != MESH_MAGIC:
        return False
    return struct.unpack_from("<I", data, 4)[0] == MESH_MAGIC_RT


def convert_mesh(data: bytes) -> bytes:
    if len(data) < 8 or data[:4] != MESH_MAGIC:
        raise FormatConversionError("Not a MESH file.")
    magic = struct.unpack_from("<I", data, 4)[0]
    if magic == MESH_MAGIC_CLASSIC:
        raise FormatConversionError("Mesh is already classic RE2.")
    if magic != MESH_MAGIC_RT:
        raise FormatConversionError(
            f"Unsupported mesh magic {magic} (expected RT {MESH_MAGIC_RT})."
        )
    raise FormatConversionError(
        "mesh.2109108288 -> mesh.1808312334 requires a full re-export "
        "(RE Mesh Editor / Noesis). Binary downgrade is not supported."
    )
