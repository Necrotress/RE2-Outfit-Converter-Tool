"""A bone link that names no bone is cleared so the mesh editor can import."""

from __future__ import annotations

import struct
import sys

from re2_outfit_converter.platform.blender_detect import blender_script_dir

sys.path.insert(0, str(blender_script_dir()))

import mesh_bones  # noqa: E402


class _Bone:
    def __init__(self, index, parent, sibling=-1, child=-1, sym=-1):
        self.boneIndex = index
        self.boneParent = parent
        self.boneSibling = sibling
        self.boneChild = child
        self.boneSymmetric = sym
        self.useSecondaryWeight = 0
        self.padding0 = 0
        self.padding1 = 0


class _Header:
    def __init__(self, bones):
        self.boneInfoList = bones


class _Mesh:
    def __init__(self, bones):
        self.skeletonHeader = _Header(bones)


class _Api:
    def __init__(self, bones):
        self.bones = bones

    def readREMesh(self, path):
        del path
        return _Mesh(self.bones)


def test_orphan_root_parent_is_cleared(tmp_path):
    bones = [
        _Bone(1, 0, sibling=1),
        _Bone(0, 16256),
    ]
    blob = b"".join(mesh_bones._pack_bone(bone) for bone in bones)
    path = tmp_path / "body.mesh.1808312334"
    path.write_bytes(b"MESH" + blob + b"TAIL")

    changed = mesh_bones.relax_orphan_bone_links(str(path), _Api(bones))

    data = path.read_bytes()
    assert changed == 1
    parent = struct.unpack_from("<h", data, 4 + 16 + 2)[0]
    assert parent == -1
    assert data.endswith(b"TAIL")
