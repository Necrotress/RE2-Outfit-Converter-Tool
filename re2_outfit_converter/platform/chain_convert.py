"""Upgrade a classic chain.21 (cloth / hair physics) to ray-tracing chain.46.

The record sizes come from the RE Engine chain template (v21 vs v46). The
bytes inserted for a new field are the values the retail ray-tracing chains
actually store: an identity rotation, a full turn of end-rotation, collision
lerp 0.1, and collision flags -1. Renaming the file is not enough — the
ray-tracing build reads chain.46 only, and a chain whose offsets are wrong
freezes outfit changes.

Downgrade (chain.46 → chain.21) is still unsupported.
"""

from __future__ import annotations

import math
import struct

from .reports import FormatConversionError

CHAIN_MAGIC = b"chan"
HEADER_SIZE = 112
VERSION_CLASSIC = 21
VERSION_RT = 46

_SETTING_V21 = 128
_SETTING_V46 = 168
_COLLISION_V21 = 56
_COLLISION_V46 = 80
_GROUP_V21 = 48
_GROUP_V46 = 88
_NODE_V21 = 64
_NODE_V46 = 80
_SUB_V21 = 32
_SUB_V46 = 56
_WIND_SIZE = 184
_LINK_SIZE = 32

# float32(4π). The decimal 12.56637 packs one ulp lower than the retail files.
_END_ROT = struct.pack("<f", 4 * math.pi)
_IDENTITY_W = struct.pack("<ffff", 0.0, 0.0, 0.0, 1.0)
_ONE = struct.pack("<f", 1.0)
_TENTH = struct.pack("<f", 0.1)
_NEG_ONE = struct.pack("<i", -1)


def convert_chain_to_rt(data: bytes) -> bytes:
    """Return chain.46 bytes for a classic chain.21 file."""
    chain = _parse_classic(data)
    out = bytearray(data[:HEADER_SIZE])
    struct.pack_into("<I", out, 0, VERSION_RT)

    setting_at: list[int] = []
    path_at: dict[int, int] = {}
    for setting in chain.settings:
        setting_at.append(len(out))
        out += _expand_setting(setting.raw, 0)
    for setting_index, setting in enumerate(chain.settings):
        if setting.path is None:
            continue
        if setting.path_offset not in path_at:
            path_at[setting.path_offset] = len(out)
            out += setting.path
        struct.pack_into(
            "<Q", out, setting_at[setting_index], path_at[setting.path_offset],
        )

    _align(out, 16)
    collision_at = len(out)
    for collision in chain.collisions:
        out += _expand_collision(collision.raw, 0)
    for index, collision in enumerate(chain.collisions):
        if not collision.subs:
            continue
        _align(out, 16)
        struct.pack_into("<Q", out, collision_at + index * _COLLISION_V46, len(out))
        for sub in collision.subs:
            out += _expand_sub(sub)
        _align(out, 16)

    _align(out, 16)
    group_at = len(out)
    for group in chain.groups:
        out += _expand_group(group.raw)
    _align(out, 16)

    piece_name: list[int] = []
    piece_node: list[int] = []
    for piece in chain.pieces:
        piece_name.append(len(out))
        out += piece.name
        _align(out, 16)
        # An empty node table still records the aligned address after the name.
        piece_node.append(len(out))
        for node in piece.nodes:
            out += _expand_node(node)

    if chain.wind:
        wind_at = len(out)
        out += chain.wind
    else:
        wind_at = 0
    if chain.links:
        _align(out, 16)
        link_at = len(out)
        shift = link_at - chain.classic_link_at
        for index in range(len(chain.links) // _LINK_SIZE):
            rec = bytearray(
                chain.links[index * _LINK_SIZE:(index + 1) * _LINK_SIZE]
            )
            node_tbl = struct.unpack_from("<Q", rec, 0)[0]
            if node_tbl:
                struct.pack_into("<Q", rec, 0, node_tbl + shift)
            out += rec
        tail = bytearray(chain.link_tail)
        tail_at = len(out)
        for index in range(len(chain.links) // _LINK_SIZE):
            rec = out[link_at + index * _LINK_SIZE:link_at + (index + 1) * _LINK_SIZE]
            node_tbl = struct.unpack_from("<Q", rec, 0)[0]
            count = rec[28]
            if not node_tbl or not count:
                continue
            local = node_tbl - tail_at
            for node_index in range(count):
                flag_at = local + node_index * 8 + 4
                if flag_at < 0 or flag_at + 4 > len(tail):
                    raise FormatConversionError(
                        "Chain link nodes point outside the link table."
                    )
                struct.pack_into("<i", tail, flag_at, -1)
        out += tail
    else:
        link_at = 0

    if chain.wind:
        after_pieces = wind_at
    elif chain.links:
        after_pieces = link_at
    else:
        after_pieces = len(out)

    for group in chain.groups:
        base = group_at + group.index * _GROUP_V46
        slot = group.piece
        struct.pack_into("<Q", out, base, piece_name[slot])
        struct.pack_into("<Q", out, base + 8, piece_node[slot])
        nxt = piece_name[slot + 1] if slot + 1 < len(chain.pieces) else after_pieces
        struct.pack_into("<Q", out, base + 80, nxt)

    struct.pack_into("<Q", out, 0x18, collision_at if chain.collisions else group_at)
    struct.pack_into("<Q", out, 0x28, group_at if chain.groups else 0)
    struct.pack_into("<Q", out, 0x30, link_at)
    if chain.settings:
        struct.pack_into("<Q", out, 0x38, HEADER_SIZE)
    if chain.wind:
        struct.pack_into("<Q", out, 0x40, wind_at)
    elif chain.links:
        struct.pack_into("<Q", out, 0x40, link_at)
    else:
        struct.pack_into("<Q", out, 0x40, len(out))
    return bytes(out)


class _Setting:
    def __init__(self, raw: bytes, path: bytes | None, path_offset: int) -> None:
        self.raw = raw
        self.path = path
        self.path_offset = path_offset


class _Collision:
    def __init__(self, raw: bytes, subs: list[bytes]) -> None:
        self.raw = raw
        self.subs = subs


class _Group:
    def __init__(
        self,
        raw: bytes,
        name: bytes,
        nodes: list[bytes],
        name_at: int,
        node_end: int,
        index: int,
    ) -> None:
        self.raw = raw
        self.name = name
        self.nodes = nodes
        self.name_at = name_at
        self.node_end = node_end
        self.index = index
        self.piece = 0


class _Piece:
    """One name-plus-nodes run, in the order the file stores them.

    A group record points at one of these. Runs with no group are subchains:
    classic files tuck them between groups, and chain.46 points ``nextChain``
    at the next run's name.
    """

    def __init__(self, name: bytes, nodes: list[bytes]) -> None:
        self.name = name
        self.nodes = nodes


class _Chain:
    def __init__(self) -> None:
        self.settings: list[_Setting] = []
        self.collisions: list[_Collision] = []
        self.groups: list[_Group] = []
        self.pieces: list[_Piece] = []
        self.wind = b""
        self.links = b""
        self.link_tail = b""
        self.classic_link_at = 0


def _parse_classic(data: bytes) -> _Chain:
    if len(data) < HEADER_SIZE or data[4:8] != CHAIN_MAGIC:
        raise FormatConversionError("Not a chain file.")
    version = struct.unpack_from("<I", data, 0)[0]
    if version != VERSION_CLASSIC:
        raise FormatConversionError(
            f"chain version {version} is not classic chain.21."
        )
    if _u64(data, 0x10) or _u64(data, 0x20):
        raise FormatConversionError(
            "This chain has an extra string table the converter does not read."
        )

    group_count = data[0x48]
    setting_count = data[0x49]
    collision_count = data[0x4A]
    wind_count = data[0x4B]
    link_count = data[0x4C]
    collision_at = _u64(data, 0x18)
    group_at = _u64(data, 0x28)
    link_at = _u64(data, 0x30)
    setting_at = _u64(data, 0x38)
    wind_at = _u64(data, 0x40)

    if setting_count and setting_at != HEADER_SIZE:
        raise FormatConversionError(
            "Chain settings do not start at the classic header."
        )

    chain = _Chain()
    for index in range(setting_count):
        raw = _slice(data, setting_at + index * _SETTING_V21, _SETTING_V21, "setting")
        path_offset = struct.unpack_from("<Q", raw, 0)[0]
        path = _wstring(data, path_offset) if path_offset else None
        chain.settings.append(_Setting(raw, path, path_offset))

    for index in range(collision_count):
        raw = _slice(
            data, collision_at + index * _COLLISION_V21, _COLLISION_V21, "collision",
        )
        sub_at = struct.unpack_from("<Q", raw, 0)[0]
        sub_count = raw[50]
        subs: list[bytes] = []
        if sub_count:
            if not sub_at:
                raise FormatConversionError(
                    "A chain collision names sub-shapes it does not store."
                )
            for sub_index in range(sub_count):
                subs.append(_slice(
                    data, sub_at + sub_index * _SUB_V21, _SUB_V21, "subcollision",
                ))
        chain.collisions.append(_Collision(raw, subs))

    for index in range(group_count):
        raw = _slice(data, group_at + index * _GROUP_V21, _GROUP_V21, "chain group")
        name_at = struct.unpack_from("<Q", raw, 0)[0]
        node_at = struct.unpack_from("<Q", raw, 8)[0]
        node_count = raw[20]
        name = _wstring(data, name_at) if name_at else b"\x00\x00"
        nodes: list[bytes] = []
        if node_count:
            if not node_at:
                raise FormatConversionError(
                    "A chain group names nodes it does not store."
                )
            for node_index in range(node_count):
                nodes.append(_slice(
                    data, node_at + node_index * _NODE_V21, _NODE_V21, "chain node",
                ))
        if node_count:
            node_end = node_at + node_count * _NODE_V21
        else:
            node_end = (name_at + len(name) + 15) & ~15
        chain.groups.append(_Group(raw, name, nodes, name_at, node_end, index))

    _parse_pieces(data, chain, group_at, group_count, wind_count, wind_at, link_count, link_at)

    if wind_count:
        if not wind_at:
            raise FormatConversionError("Chain wind settings are missing.")
        chain.wind = _slice(data, wind_at, wind_count * _WIND_SIZE, "wind")
    if link_count:
        if not link_at:
            raise FormatConversionError("Chain links are missing.")
        chain.classic_link_at = link_at
        chain.links = _slice(data, link_at, link_count * _LINK_SIZE, "link")
        # Some links keep a node-table offset even when the count is 0.
        # Those bytes sit after the link records and move with them.
        tail_at = link_at + link_count * _LINK_SIZE
        if tail_at < len(data):
            chain.link_tail = data[tail_at:]
    return chain


def _parse_pieces(
    data: bytes,
    chain: _Chain,
    group_at: int,
    group_count: int,
    wind_count: int,
    wind_at: int,
    link_count: int,
    link_at: int,
) -> None:
    if not chain.groups:
        return
    limit = len(data)
    if wind_count and wind_at:
        limit = min(limit, wind_at)
    if link_count and link_at:
        limit = min(limit, link_at)
    cursor = group_at + group_count * _GROUP_V21
    spans = sorted(chain.groups, key=lambda group: group.name_at)
    for group in spans:
        if cursor < group.name_at:
            _append_subchains(data, chain, cursor, group.name_at)
        chain.pieces.append(_Piece(group.name, group.nodes))
        group.piece = len(chain.pieces) - 1
        cursor = max(cursor, group.node_end)
    if cursor < limit:
        _append_subchains(data, chain, cursor, limit)


def _append_subchains(data: bytes, chain: _Chain, start: int, limit: int) -> None:
    pos = start
    while pos < limit:
        if not _is_wstring_start(data, pos):
            if data[pos:limit].strip(b"\x00") == b"":
                return
            raise FormatConversionError(
                "Chain data between groups is not a subchain."
            )
        name = _wstring(data, pos)
        pos = (pos + len(name) + 15) & ~15
        nodes: list[bytes] = []
        while pos + _NODE_V21 <= limit and not _is_wstring_start(data, pos):
            nodes.append(data[pos:pos + _NODE_V21])
            pos += _NODE_V21
        chain.pieces.append(_Piece(name, nodes))
    if pos != limit and data[pos:limit].strip(b"\x00") != b"":
        raise FormatConversionError("Chain subchain did not end on the next group.")


def _is_wstring_start(data: bytes, pos: int) -> bool:
    if pos + 5 >= len(data):
        return False
    return (
        data[pos] != 0
        and data[pos + 1] == 0
        and data[pos + 2] != 0
        and data[pos + 3] == 0
        and data[pos + 4] != 0
    )


def _expand_setting(raw: bytes, path_offset: int) -> bytes:
    """v21 setting is 128 bytes; v46 inserts 40 and keeps the authored curves."""
    out = bytearray(_SETTING_V46)
    struct.pack_into("<Q", out, 0, path_offset)
    out[8:68] = raw[8:68]
    # minDamping, secondMinDamping, dampingPow, secondDampingPow, collideMaxVelocity
    out[68:88] = raw[56:64] + _ONE + _ONE + b"\x00" * 4
    out[88:92] = raw[68:72]  # springForce
    out[104:160] = raw[72:128]
    out[164:168] = _TENTH  # ukn1; ukn0 at 160 stays 0
    return bytes(out)


def _expand_collision(raw: bytes, sub_offset: int) -> bytes:
    out = bytearray(_COLLISION_V46)
    struct.pack_into("<Q", out, 0, sub_offset)
    out[8:32] = raw[8:32]
    out[32:48] = _IDENTITY_W
    out[52:64] = raw[32:44]  # joint hashes and radius; classic lerp is dropped
    out[64:68] = _TENTH
    out[72:76] = raw[48:52]  # shape, div, sub count, pad
    out[76:80] = _NEG_ONE
    return bytes(out)


def _expand_sub(raw: bytes) -> bytes:
    out = bytearray(_SUB_V46)
    out[0:24] = raw[0:24]
    out[24:40] = _IDENTITY_W
    out[40:44] = raw[24:28]  # radius
    out[48:52] = raw[28:32]  # id
    return bytes(out)


def _expand_group(raw: bytes) -> bytes:
    out = bytearray(_GROUP_V46)
    out[16:48] = raw[16:48]
    # v46 sets the high attr bit on every group. Retail files all do this.
    flags = struct.unpack_from("<I", out, 28)[0] | 0x8000
    struct.pack_into("<I", out, 28, flags)
    out[72:76] = _END_ROT
    return bytes(out)


def _expand_node(raw: bytes) -> bytes:
    out = bytearray(raw)
    out += b"\x00" * (_NODE_V46 - _NODE_V21)
    struct.pack_into("<i", out, 36, -1)
    struct.pack_into("<f", out, 40, 1.0)
    struct.pack_into("<f", out, 44, 1.0)
    struct.pack_into("<f", out, 72, 1.0)
    return bytes(out)


def _wstring(data: bytes, offset: int) -> bytes:
    if offset <= 0 or offset + 1 >= len(data):
        raise FormatConversionError("Chain string points outside the file.")
    end = offset
    while end + 1 < len(data):
        if data[end] == 0 and data[end + 1] == 0:
            return data[offset:end + 2]
        end += 2
    raise FormatConversionError("Chain string is not terminated.")


def _slice(data: bytes, offset: int, size: int, what: str) -> bytes:
    if offset <= 0 or offset + size > len(data):
        raise FormatConversionError(f"Chain {what} points outside the file.")
    return data[offset:offset + size]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _align(buf: bytearray, boundary: int) -> None:
    pad = (-len(buf)) % boundary
    if pad:
        buf.extend(b"\x00" * pad)
