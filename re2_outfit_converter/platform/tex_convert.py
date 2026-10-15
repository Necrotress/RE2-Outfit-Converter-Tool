"""Convert RE Engine tex.34 (RT) to tex.10 (classic RE2) and back.

Reverse of FluffyQuack's RT patch texture upgrade, matching the Noesis
fmt_RE_MESH TEX layouts. Which layout a file uses is decided from its mip
table, not the version field: RE Engine also stamps date-style versions
(RE3 writes 190820018) on classic-layout textures.
"""

from __future__ import annotations

import struct

from .reports import FormatConversionError

TEX_MAGIC = b"TEX\x00"
RT_VERSION = 34
CLASSIC_VERSION = 10
# RE3 writes this date on classic-layout textures. Their unkn04 is already
# a real flag (Punisher suit ALBM is 1280). RE2 classic files leave it 0
# and get the dual-pack table instead.
RE3_TEX_VERSION = 190820018


LAYOUT_CLASSIC = "classic"
LAYOUT_RT = "rt"


def _classic_header_size(data: bytes) -> int | None:
    """Header size if this parses as classic (mipCount, numImages, no pad)."""
    mip_count, num_images = data[14], data[15]
    if mip_count <= 0 or num_images <= 0:
        return None
    size = 32 + num_images * mip_count * 16
    if len(data) < size:
        return None
    return size if struct.unpack_from("<Q", data, 32)[0] == size else None


def _rt_header_size(data: bytes) -> int | None:
    """Header size if this parses as RT (numImages, mipCount*16, 8-byte pad)."""
    num_images, mip_header = data[14], data[15]
    if num_images <= 0 or mip_header <= 0 or mip_header % 16:
        return None
    size = 40 + num_images * (mip_header // 16) * 16
    if len(data) < size:
        return None
    return size if struct.unpack_from("<Q", data, 40)[0] == size else None


def tex_layout(data: bytes) -> str | None:
    """Which TEX header layout this buffer uses, or None if it is not a TEX.

    Decided by the mip table rather than the version field: RE Engine also
    stamps date-style versions (e.g. RE3's 190820018) on classic-layout
    textures, so a numeric threshold misclassifies them.
    """
    if len(data) < 40 or data[:4] != TEX_MAGIC:
        return None
    classic = _classic_header_size(data)
    rt = _rt_header_size(data)
    if classic is not None and rt is None:
        return LAYOUT_CLASSIC
    if rt is not None and classic is None:
        return LAYOUT_RT
    if classic is not None and rt is not None:
        version = struct.unpack_from("<I", data, 4)[0]
        return LAYOUT_RT if version == RT_VERSION else LAYOUT_CLASSIC
    return None


def is_rt_tex(data: bytes) -> bool:
    return tex_layout(data) == LAYOUT_RT


def tex34_to_tex10(data: bytes) -> bytes:
    """Downgrade an RT-layout TEX buffer to tex.10."""
    if len(data) < 40 or data[:4] != TEX_MAGIC:
        raise FormatConversionError("Not a TEX file.")
    version = struct.unpack_from("<I", data, 4)[0]
    layout = tex_layout(data)
    if layout is None:
        raise FormatConversionError(
            f"Unrecognised TEX header (version {version})."
        )
    if layout == LAYOUT_CLASSIC:
        raise FormatConversionError(
            f"TEX version {version} already uses the classic layout."
        )

    width, height, unk00 = struct.unpack_from("<HHH", data, 8)
    num_images = data[14]
    one_img_mip_hdr = data[15]
    if one_img_mip_hdr % 16 != 0:
        raise FormatConversionError(
            f"Invalid RT mip header size byte: {one_img_mip_hdr}"
        )
    mip_count = one_img_mip_hdr // 16
    if mip_count <= 0 or num_images <= 0:
        raise FormatConversionError(
            f"Invalid image/mip counts: images={num_images} mips={mip_count}"
        )

    fmt, unk02, unk03, _unk04 = struct.unpack_from("<IIII", data, 16)
    # RT inserts 8 padding bytes after the 32-byte base header.
    off = 40
    need = off + num_images * mip_count * 16
    if len(data) < need:
        raise FormatConversionError(
            f"TEX truncated: need {need} header bytes, have {len(data)}"
        )

    mips: list[tuple[int, int, int]] = []
    for _ in range(num_images):
        for _m in range(mip_count):
            mip_off, pitch, size = struct.unpack_from("<QII", data, off)
            if mip_off < 8:
                raise FormatConversionError(
                    f"Mip offset {mip_off} too small to subtract RT header pad."
                )
            mips.append((mip_off - 8, pitch, size))
            off += 16

    payload = data[off:]
    out = bytearray()
    out += TEX_MAGIC
    out += struct.pack("<I", CLASSIC_VERSION)
    out += struct.pack("<HHH", width, height, unk00)
    # Classic stores mipCount then numImages (swapped vs RT).
    out += bytes((mip_count & 0xFF, num_images & 0xFF))
    # Classic unk04 is 0 for RE2 samples; do not copy RT's value.
    out += struct.pack("<IIII", fmt, unk02, unk03, 0)
    for mip_off, pitch, size in mips:
        out += struct.pack("<QII", mip_off, pitch, size)
    out += payload

    expected_hdr = 32 + num_images * mip_count * 16
    if len(out) - len(payload) != expected_hdr:
        raise FormatConversionError("Internal TEX header size mismatch.")
    first = struct.unpack_from("<Q", out, 32)[0]
    if first != expected_hdr:
        raise FormatConversionError(
            f"First mip offset {first} != classic header size {expected_hdr}."
        )
    return bytes(out)


def convert_tex_file(src: bytes) -> bytes:
    """Public entry: convert RT TEX bytes to classic tex.10 bytes."""
    return tex34_to_tex10(src)


# RT header dword at offset 28. SkinDetail (a small fmt-98 detail map) uses
# 384; player ALBM/NRMR/ATOS in a real RT/non-RT dual pack use other values
# keyed off the texture kind, not a single constant.
_RT_UNK04 = 384


def rt_unk04_for(name: str = "", fmt: int = 0) -> int:
    """RT ``unkn04/unkn05`` packed dword for files we upgrade from classic.

    Classic always stores 0. A working dual-pack pair (Bare Essentials
    torso ALBM/NRMR/ATOS) is byte-identical to this converter except this
    dword: ALBM 1408, NRMR 1536, ATOS 1152, ALBA 256, detail 384.
    Vanilla dump player maps are those values plus one (1409/…); those are
    Capcom-authored files, not a tex.10 upgrade. Stamping the dump values
    on a converted 2K/4K body made Sportsuit checkerboard while the same
    pixels shipped as 1408 in the dual pack. Engine nulls in
    systems/rendering use another set (NullWhite 128, not 384). Inverse:
    classic always writes 0.
    """
    n = (name or "").lower()
    if not n:
        return _RT_UNK04
    stem = n.replace("\\", "/").rsplit("/", 1)[-1].split(".tex")[0]
    if "cubemap" in stem:
        return 1792
    if stem in {"nullwhite", "nullblack", "nullgray"}:
        return 128
    if "atos" in n:
        return 1152
    if "nrmr" in n or "nullnormalroughness" in stem:
        return 1536
    if "alba" in n and "albm" not in n:
        return 256
    if "albm" in n or "_iam" in n or n.endswith("iam"):
        return 1408
    if "dtl" in n or "detail" in n:
        return 384
    return {71: 1152, 99: 1408, 98: 1536}.get(fmt, _RT_UNK04)


def tex10_to_tex34(data: bytes, *, name: str = "") -> bytes:
    """Upgrade a tex.10 buffer to tex.34 (8-byte header pad, swapped counts)."""
    if len(data) < 32 or data[:4] != TEX_MAGIC:
        raise FormatConversionError("Not a TEX file.")
    version = struct.unpack_from("<I", data, 4)[0]
    layout = tex_layout(data)
    if layout is None:
        raise FormatConversionError(
            f"Unrecognised TEX header (version {version})."
        )
    if layout == LAYOUT_RT:
        raise FormatConversionError(
            f"TEX version {version} already uses the RT layout."
        )

    width, height, unk00 = struct.unpack_from("<HHH", data, 8)
    mip_count = data[14]
    num_images = data[15]
    if mip_count <= 0 or num_images <= 0:
        raise FormatConversionError(
            f"Invalid image/mip counts: images={num_images} mips={mip_count}"
        )
    fmt, unk02, unk03, classic_unk04 = struct.unpack_from("<IIII", data, 16)
    # RE2 classic stores 0 here, so those files take the dual-pack table
    # (ALBM 1408, …). An RE3 texture already has its own flag. Replacing
    # that with 1408 left Sportsuit and Punisher checkerboarded the same
    # way 1280 did, while Moto draws at 1280. Keep the authored flag.
    # Classic downgrade still writes 0.
    if version == RE3_TEX_VERSION and classic_unk04:
        unk04 = classic_unk04
    else:
        unk04 = rt_unk04_for(name, fmt)
    off = 32
    need = off + num_images * mip_count * 16
    if len(data) < need:
        raise FormatConversionError(
            f"TEX truncated: need {need} header bytes, have {len(data)}"
        )

    mips: list[tuple[int, int, int]] = []
    for _ in range(num_images):
        for _m in range(mip_count):
            mip_off, pitch, size = struct.unpack_from("<QII", data, off)
            mips.append((mip_off + 8, pitch, size))
            off += 16

    payload = data[off:]
    out = bytearray()
    out += TEX_MAGIC
    out += struct.pack("<I", RT_VERSION)
    out += struct.pack("<HHH", width, height, unk00)
    # RT stores numImages then mipCount*16 (swapped vs classic).
    out += bytes((num_images & 0xFF, (mip_count * 16) & 0xFF))
    out += struct.pack("<IIII", fmt, unk02, unk03, unk04)
    out += b"\x00" * 8
    for mip_off, pitch, size in mips:
        out += struct.pack("<QII", mip_off, pitch, size)
    out += payload
    return bytes(out)


def convert_tex_to_rt(src: bytes, name: str = "") -> bytes:
    """Public entry: convert classic TEX bytes to RT tex.34 bytes."""
    return tex10_to_tex34(src, name=name)
