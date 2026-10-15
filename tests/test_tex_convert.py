"""Texture layout rules, built from a tiny header instead of a game dump."""

from __future__ import annotations

import struct

from re2_outfit_converter.platform.tex_convert import (
    RE3_TEX_VERSION,
    convert_tex_file,
    convert_tex_to_rt,
    is_rt_tex,
    tex_layout,
)


def _classic_tex(*, version: int = 10, unk04: int = 0, payload: bytes = b"PX") -> bytes:
    mip_count, num_images = 1, 1
    header = 32 + num_images * mip_count * 16
    buf = bytearray(header + len(payload))
    buf[0:4] = b"TEX\x00"
    struct.pack_into("<I", buf, 4, version)
    struct.pack_into("<HHH", buf, 8, 4, 4, 0)
    buf[14] = mip_count
    buf[15] = num_images
    struct.pack_into("<IIII", buf, 16, 98, 0, 0, unk04)
    struct.pack_into("<QII", buf, 32, header, 16, len(payload))
    buf[header:] = payload
    return bytes(buf)


def test_classic_round_trip_keeps_the_layout():
    classic = _classic_tex()
    assert tex_layout(classic) == "classic"
    assert not is_rt_tex(classic)
    upgraded = convert_tex_to_rt(classic)
    assert tex_layout(upgraded) == "rt"
    assert struct.unpack_from("<I", upgraded, 4)[0] == 34
    assert convert_tex_file(upgraded) == classic


def test_date_style_version_is_classic_not_rt():
    re3 = _classic_tex(version=RE3_TEX_VERSION)
    assert not is_rt_tex(re3)
    assert tex_layout(re3) == "classic"
    upgraded = convert_tex_to_rt(re3)
    assert struct.unpack_from("<I", upgraded, 4)[0] == 34
    assert tex_layout(upgraded) == "rt"


def test_rt_layout_detected_regardless_of_version():
    rt = convert_tex_to_rt(_classic_tex())
    stamped = rt[:4] + struct.pack("<I", RE3_TEX_VERSION) + rt[8:]
    assert tex_layout(stamped) == "rt"


def test_re3_authored_unk04_is_kept_on_the_way_to_rt():
    classic = _classic_tex(version=RE3_TEX_VERSION, unk04=1280)
    upgraded = convert_tex_to_rt(classic, name="pl2900_dress_albm.tex.10")
    assert struct.unpack_from("<I", upgraded, 4)[0] == 34
    assert struct.unpack_from("<I", upgraded, 28)[0] == 1280


def test_rt_unk04_follows_texture_kind():
    classic = _classic_tex()

    def unk04(name: str) -> int:
        return struct.unpack_from(
            "<I", convert_tex_to_rt(classic, name=name), 28
        )[0]

    assert unk04("torso_albm.tex.10") == 1408
    assert unk04("torso_nrmr.tex.10") == 1536
    assert unk04("torso_atos.tex.10") == 1152
    assert unk04("torso_alba.tex.10") == 256
    assert unk04("suit_detail.tex.10") == 384
