"""Bone links the mesh editor can import.

RE Mesh Editor looks a parent index up in the bone list and aborts when that
index is not a bone. A classic file can store that as a large integer on a
root bone. Clearing it to "no parent" lets the import finish.

Rewriting bone order, bind matrices, or cull boxes after export was tried
against an invisible body and did not change what the game drew. Those
passes are not part of the convert.
"""

from __future__ import annotations

import struct


def _pack_bone(bone) -> bytes:
    return struct.pack(
        "<Hhhhhhhh",
        int(bone.boneIndex),
        int(bone.boneParent),
        int(bone.boneSibling),
        int(bone.boneChild),
        int(bone.boneSymmetric),
        int(bone.useSecondaryWeight),
        int(bone.padding0),
        int(bone.padding1),
    )


def _in_range(value: int, count: int) -> bool:
    return value == -1 or 0 <= value < count


def relax_orphan_bone_links(path: str, file_re_mesh) -> int:
    """Rewrite bone links that name no bone so they mean no link.

    Returns how many fields changed. The file is left untouched when the
    bone table cannot be found as one block.
    """
    re_mesh = file_re_mesh.readREMesh(path)
    header = getattr(re_mesh, "skeletonHeader", None)
    bones = list(getattr(header, "boneInfoList", None) or [])
    if not bones:
        return 0
    count = len(bones)
    original = b"".join(_pack_bone(bone) for bone in bones)
    changed = 0
    for bone in bones:
        for attr in ("boneParent", "boneSibling", "boneChild", "boneSymmetric"):
            value = int(getattr(bone, attr))
            if _in_range(value, count):
                continue
            setattr(bone, attr, -1)
            changed += 1
    if not changed:
        return 0
    patched = b"".join(_pack_bone(bone) for bone in bones)
    with open(path, "rb") as handle:
        data = handle.read()
    at = data.find(original)
    if at < 0:
        return 0
    with open(path, "wb") as handle:
        handle.write(data[:at] + patched + data[at + len(original):])
    return changed
