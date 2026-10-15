# Runs INSIDE Blender (--background --python).
# Converts RT mesh/mdf2 files to classic RE2 via RE Mesh Editor APIs.
#
# MDF: does NOT use Blender scene import/export. RE Mesh Editor's default
# writer inflates string tables (~2x) and that classic-RE2 layout is wrong for
# gameplay (crashes). We read with the addon's parser and rewrite .mdf2.10 with
# a compact shared string table + correct v10 sizes.
#
# Args after -- :
#   --manifest PATH.json
#   --result PATH.json

from __future__ import annotations

import json
import os
import sys
import traceback


# Classic RE2 mesh file header version field (little-endian u32 after "MESH").
RE2_MESH_INTERNAL_VERSION = 386270720  # 0x17060600
# RE2/3 RT mesh header version (file suffix .mesh.2109108288).
RE2RT_MESH_INTERNAL_VERSION = 21041600


def _parse_args(argv: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--manifest", "--result") and i + 1 < len(argv):
            out[a[2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    return out


def _find_re_mesh_editor_module():
    import addon_utils

    for mod in addon_utils.modules():
        info = getattr(mod, "bl_info", {}) or {}
        name = str(info.get("name", ""))
        if "RE Mesh Editor" in name:
            try:
                addon_utils.enable(mod.__name__, default_set=True)
            except Exception:
                pass
            return mod.__name__
    return None


def _load_api(package: str):
    import importlib

    mesh = importlib.import_module(f"{package}.modules.mesh.blender_re_mesh")
    mdf_file = importlib.import_module(f"{package}.modules.mdf.file_re_mdf")
    file_re_mesh = importlib.import_module(f"{package}.modules.mesh.file_re_mesh")
    return mesh, mdf_file, file_re_mesh


def _clear_scene():
    import bpy

    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for block in (
        bpy.data.objects,
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.node_groups,
    ):
        for item in list(block):
            try:
                block.remove(item)
            except Exception:
                pass


def _mesh_import_options(*, clear_scene: bool = True) -> dict:
    return {
        "clearScene": clear_scene,
        "createCollections": True,
        # loadMDFData=True is required so import creates a proper RE mesh collection
        "loadMDFData": True,
        "loadMaterials": False,
        "loadShellFur": False,
        "loadUnusedTextures": False,
        "loadUnusedProps": False,
        "useBackfaceCulling": False,
        "reloadCachedTextures": False,
        "mdfPath": "",
        "importAllLODs": True,
        "importBlendShapes": True,
        "rotate90": True,
        "mergeArmature": "",
        "importArmatureOnly": False,
        "mergeGroups": False,
        "importShadowMeshes": True,
        "importOcclusionMeshes": False,
        "importBoundingBoxes": False,
    }


def _mesh_export_options(target_collection: str) -> dict:
    return {
        "targetCollection": target_collection,
        "selectedOnly": False,
        "exportAllLODs": True,
        "exportBlendShapes": True,
        "rotate90": True,
        "useBlenderMaterialName": False,
        "preserveBoneMatrices": True,
        "exportBoundingBoxes": False,
        "autoSolveRepeatedUVs": True,
        "preserveSharpEdges": True,
    }


def _find_mesh_collection(preferred: str = "") -> str:
    import bpy

    if preferred and preferred in bpy.data.collections:
        return preferred
    last = bpy.context.scene.get("REMeshLastImportedCollection", "")
    if last and last in bpy.data.collections:
        return last
    for col in bpy.data.collections:
        if col.get("~TYPE") == "RE_MESH_COLLECTION" or col.name.endswith(".mesh"):
            return col.name
    return ""


_TO_CLASSIC_TOKENS = (
    ("natives/stm/", "natives/x64/"),
    ("natives\\stm\\", "natives\\x64\\"),
    ("natives/STM/", "natives/x64/"),
    ("natives\\STM\\", "natives\\x64\\"),
    ("/stm/", "/x64/"),
    ("\\stm\\", "\\x64\\"),
    ("/STM/", "/x64/"),
    ("\\STM\\", "\\x64\\"),
    (".tex.34", ".tex.10"),
    (".TEX.34", ".tex.10"),
)

_TO_RT_TOKENS = (
    ("natives/x64/", "natives/stm/"),
    ("natives\\x64\\", "natives\\stm\\"),
    ("natives/X64/", "natives/stm/"),
    ("natives\\X64\\", "natives\\stm\\"),
    ("/x64/", "/stm/"),
    ("\\x64\\", "\\stm\\"),
    ("/X64/", "/stm/"),
    ("\\X64\\", "\\stm\\"),
    (".tex.10", ".tex.34"),
    (".TEX.10", ".tex.34"),
)

# Which way the writer rewrites paths. Set per job, since one batch can hold
# both directions only if each job sets it before writing.
_WRITE_TOKENS = _TO_CLASSIC_TOKENS

# Compact string tables are a classic-only workaround (stock write ~2x and
# crashes RE2). Vanilla RT MDFs keep the stock duplicate string table.
# Face "working" after convert is not proof the compact RT write is fine:
# we do not overlay vanilla pl1050.mdf2.21, so the head still uses the
# game's MDF. The body uses our pl1004.mdf2.21.
_STOCK_RECALC = None
_COMPACT_RECALC = None


def _remap_engine_path(path: str) -> str:
    """stm/x64 + tex version tokens inside MDF texture / mmtr-style paths."""
    if not path:
        return path
    out = path
    for old, new in _WRITE_TOKENS:
        out = out.replace(old, new)
    return out


def _install_compact_mdf_writer(file_re_mdf) -> None:
    """Replace RE Mesh Editor string-table builder with a compact shared table.

    Stock writer re-emits every string even when reusing offsets, roughly
    doubling MDF size. Combined with RT→classic structural differences that
    produces files that crash classic RE2.
    """
    hash_utf8 = file_re_mdf.hashUTF8
    hash_utf16 = file_re_mdf.hashUTF16

    def recalculate_compact(self, version):
        self.Header.materialCount = len(self.materialList)
        self.sizeData = file_re_mdf.SIZEDATA(version)
        # Upstream bug: TEXTURE_ENTRY_SIZE = 24 is assigned without self.
        if version < 13:
            self.sizeData.TEXTURE_ENTRY_SIZE = 24
        if version < 19:
            self.sizeData.MATERIAL_ENTRY_SIZE = 64

        material_entries_size = (
            self.sizeData.MATERIAL_ENTRY_SIZE * len(self.materialList)
        )
        texture_entries_size = 0
        property_entries_size = 0
        prop_data_block_offsets: list[int] = []
        prop_header_offsets: list[int] = []
        tex_header_offsets: list[int] = []
        current_prop_data_block = 0
        current_prop_header = 0
        current_tex_header = 0

        for material in self.materialList:
            material.gpbfBufferNameList = []
            material.gpbfBufferPathList = []
            material.GPBFBufferNameCount = 0
            material.GPBFBufferPathCount = 0
            material.GPUBufferOffset = 0
            material.mmtrsData = None
            material.mmtrsDataOffset = 0

            texture_entries_size += (
                len(material.textureList) * self.sizeData.TEXTURE_ENTRY_SIZE
            )
            property_entries_size += (
                len(material.propertyList) * self.sizeData.PROPERTY_ENTRY_SIZE
            )
            if material.hideInGame:
                material.matNameHash = 0
            else:
                material.matNameHash = hash_utf16(material.materialName)

            material.textureCount = len(material.textureList)
            material.propertyCount = len(material.propertyList)
            prop_header_offsets.append(current_prop_header)
            current_prop_header += (
                material.propertyCount * self.sizeData.PROPERTY_ENTRY_SIZE
            )
            tex_header_offsets.append(current_tex_header)
            current_tex_header += (
                material.textureCount * self.sizeData.TEXTURE_ENTRY_SIZE
            )

            current_prop_offset = 0
            if material.propertyList:
                current_prop_offset += int(
                    getattr(material.propertyList[0], "frontPadding", 0) or 0
                )
            for prop in material.propertyList:
                # Keep tail padding: RT Record_Player's last parameter is
                # 8 bytes short without it. Classic presets use 0.
                prop.frontPadding = 0
                prop.paramCount = len(list(prop.propValue))
                prop.propDataOffset = current_prop_offset
                current_prop_offset += (
                    prop.paramCount * self.sizeData.PROPERTY_VALUE_SIZE
                    + int(getattr(prop, "padding", 0) or 0)
                )
                prop.asciiMMH3Hash = hash_utf8(prop.propName)
                prop.unicodeMMH3Hash = hash_utf16(prop.propName)
            material.propBlockSize = current_prop_offset
            prop_data_block_offsets.append(current_prop_data_block)
            current_prop_data_block += material.propBlockSize

            for texture in material.textureList:
                texture.asciiMMH3Hash = hash_utf8(texture.textureType)
                texture.unicodeMMH3Hash = hash_utf16(texture.textureType)
                texture.texturePath = _remap_engine_path(texture.texturePath)

            material.mmtrPath = _remap_engine_path(material.mmtrPath)

        material_entry_start = self.sizeData.HEADER_SIZE
        texture_entry_start = material_entry_start + material_entries_size
        property_entry_start = texture_entry_start + texture_entries_size
        string_table_start = property_entry_start + property_entries_size

        current_string = string_table_start
        self.stringList = []
        string_offsets: dict[str, int] = {}

        def intern(s: str) -> int:
            nonlocal current_string
            if s in string_offsets:
                return string_offsets[s]
            string_offsets[s] = current_string
            self.stringList.append(s)
            current_string += len(s) * 2 + 2
            return string_offsets[s]

        for material in self.materialList:
            material.matNameOffset = intern(material.materialName)
            material.mmtrPathOffset = intern(material.mmtrPath)
        for material in self.materialList:
            for texture in material.textureList:
                texture.textureTypeOffset = intern(texture.textureType)
                texture.texturePathOffset = intern(texture.texturePath)
        for material in self.materialList:
            for prop in material.propertyList:
                prop.propNameOffset = intern(prop.propName)

        prop_data_start = current_string
        for index, material in enumerate(self.materialList):
            material.propHeadersOffset = (
                property_entry_start + prop_header_offsets[index]
            )
            material.texHeadersOffset = (
                texture_entry_start + tex_header_offsets[index]
            )
            material.GPUBufferOffset = string_table_start
            material.propDataOffset = (
                prop_data_start + prop_data_block_offsets[index]
            )

    global _STOCK_RECALC, _COMPACT_RECALC
    _STOCK_RECALC = file_re_mdf.MDFFile.recalculateHashesAndOffsets
    _COMPACT_RECALC = recalculate_compact
    file_re_mdf.MDFFile.recalculateHashesAndOffsets = recalculate_compact


def _use_mdf_writer(file_re_mdf, *, compact: bool) -> None:
    writer = _COMPACT_RECALC if compact else _STOCK_RECALC
    if writer is not None:
        file_re_mdf.MDFFile.recalculateHashesAndOffsets = writer


def _print_notes(notes, src: str) -> None:
    """Emit material notes, naming the file so a pack's log stays readable."""
    import mdf_presets  # noqa: WPS433 — Blender script sibling

    name = os.path.basename(src)
    prefix = mdf_presets.RETARGET_PREFIX
    for note in notes:
        if note.startswith(prefix):
            note = f"{prefix}{name}: {note[len(prefix):]}"
        else:
            note = f"{name}: {note}"
        print(f"RE2RTX_MDF: {note}")


def _validate_mesh(path: str, expected: int, label: str) -> None:
    with open(path, "rb") as f:
        data = f.read(8)
    if len(data) < 8 or data[:4] != b"MESH":
        raise RuntimeError(f"Exported mesh missing MESH magic: {path}")
    version = int.from_bytes(data[4:8], "little")
    if version != expected:
        raise RuntimeError(
            f"Exported mesh is not {label} (internal version "
            f"{version}, expected {expected}): {path}"
        )


def _validate_classic_mesh(path: str) -> None:
    _validate_mesh(path, RE2_MESH_INTERNAL_VERSION, "classic RE2")


def _validate_rt_mdf(dst: str) -> None:
    with open(dst, "rb") as f:
        magic = f.read(4)
    if magic != b"MDF\x00":
        raise RuntimeError(f"Exported mdf missing MDF magic: {dst}")


def _validate_classic_mdf(src: str, dst: str) -> None:
    src_size = os.path.getsize(src)
    dst_size = os.path.getsize(dst)
    with open(dst, "rb") as f:
        magic = f.read(4)
    if magic != b"MDF\x00":
        raise RuntimeError(f"Exported mdf missing MDF magic: {dst}")
    # Compact classic rewrite should be near source size (usually slightly
    # smaller). Stock Blender export was ~2x and crashed in-game.
    limit = max(int(src_size * 1.35), src_size + 8192)
    if dst_size > limit:
        raise RuntimeError(
            f"Exported mdf suspiciously large ({dst_size} bytes vs source "
            f"{src_size}); refusing to ship a likely-corrupt classic mdf."
        )


def _restore_material_order(src: str, dst: str, file_re_mesh) -> None:
    import mesh_material_order  # noqa: WPS433 — Blender script sibling

    note = mesh_material_order.restore_mesh_material_order(src, dst, file_re_mesh)
    if note:
        print(f"RE2RTX_MESH: {note}")


def _relax_bone_links(src: str, file_re_mesh) -> None:
    import mesh_bones  # noqa: WPS433 — Blender script sibling

    changed = mesh_bones.relax_orphan_bone_links(src, file_re_mesh)
    if changed:
        print(
            f"RE2RTX_MESH: cleared {changed} bone link(s) that named no bone"
        )


def convert_mesh(src: str, dst: str, mesh_api, file_re_mesh) -> None:
    _relax_bone_links(src, file_re_mesh)
    _clear_scene()
    ok = mesh_api.importREMeshFile(src, _mesh_import_options(clear_scene=False))
    if ok is False:
        raise RuntimeError("importREMeshFile returned False")
    collection = _find_mesh_collection()
    if not collection:
        raise RuntimeError("No RE mesh collection after import")
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    # Destination path extension selects classic RE2 mesh version.
    ok = mesh_api.exportREMeshFile(dst, _mesh_export_options(collection))
    if ok is False:
        raise RuntimeError("exportREMeshFile returned False")
    if not os.path.isfile(dst):
        raise RuntimeError(f"Export did not create file: {dst}")
    _restore_material_order(src, dst, file_re_mesh)
    _validate_classic_mesh(dst)


def convert_mesh_to_rt(src: str, dst: str, mesh_api, file_re_mesh) -> None:
    """Classic mesh → RE2/3 Ray Tracing. Destination suffix selects the version."""
    _relax_bone_links(src, file_re_mesh)
    _clear_scene()
    ok = mesh_api.importREMeshFile(src, _mesh_import_options(clear_scene=False))
    if ok is False:
        raise RuntimeError("importREMeshFile returned False")
    collection = _find_mesh_collection()
    if not collection:
        raise RuntimeError("No RE mesh collection after import")
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    ok = mesh_api.exportREMeshFile(dst, _mesh_export_options(collection))
    if ok is False:
        raise RuntimeError("exportREMeshFile returned False")
    if not os.path.isfile(dst):
        raise RuntimeError(f"Export did not create file: {dst}")
    _restore_material_order(src, dst, file_re_mesh)
    _validate_mesh(dst, RE2RT_MESH_INTERNAL_VERSION, "RE2 RT")


def _align_mdf_to_sibling_mesh(
    src: str, mdf, file_re_mesh, prefer_suffix: str | None = None
) -> list[str]:
    import mesh_material_order  # noqa: WPS433 — Blender script sibling

    loaded_path = mesh_material_order.mesh_path_for_mdf(src, prefer_suffix)
    if not loaded_path:
        return []
    loaded = file_re_mesh.readREMesh(loaded_path)
    names = mesh_material_order.material_names(loaded)
    used = mesh_material_order.used_material_names(loaded)
    rank = mesh_material_order.albedo_rank_in_folder(os.path.dirname(src))
    return mesh_material_order.align_mdf_names_to_mesh(
        mdf, names, used, albedo_rank=rank,
    )


def convert_mdf_to_rt(
    src: str,
    dst: str,
    file_re_mdf,
    shipped_mmtr=None,
    re3_player_dest=None,
    file_re_mesh=None,
) -> None:
    """Classic mdf2.10 → mdf2.21 via RT material pass + stock RT writer."""
    global _WRITE_TOKENS

    import mdf_rtxify  # noqa: WPS433 — Blender script sibling

    _WRITE_TOKENS = _TO_RT_TOKENS
    _use_mdf_writer(file_re_mdf, compact=False)
    try:
        mdf = file_re_mdf.readMDF(src)
        notes = mdf_rtxify.rtxify_mdf(
            mdf, file_re_mdf, shipped_mmtr, re3_player_dest=re3_player_dest
        )
        if file_re_mesh is not None:
            notes.extend(
                _align_mdf_to_sibling_mesh(
                    src, mdf, file_re_mesh, "mesh.2109108288"
                )
            )
        _print_notes(notes, src)
        mdf.fileVersion = 21
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        file_re_mdf.writeMDF(mdf, dst)
    finally:
        _WRITE_TOKENS = _TO_CLASSIC_TOKENS
        _use_mdf_writer(file_re_mdf, compact=True)
    if not os.path.isfile(dst):
        raise RuntimeError(f"MDF write did not create file: {dst}")
    _validate_rt_mdf(dst)
    check = file_re_mdf.readMDF(dst)
    if not check.materialList:
        raise RuntimeError(f"RT mdf has no materials: {dst}")


def convert_mdf(
    src: str, dst: str, file_re_mdf, shipped_mmtr=None, file_re_mesh=None
) -> None:
    """RT mdf2.21 → classic mdf2.10 via rematerialize + compact rewrite."""
    import mdf_classicize  # noqa: WPS433 — Blender script sibling

    mdf = file_re_mdf.readMDF(src)
    notes = mdf_classicize.classicize_mdf(mdf, file_re_mdf, shipped_mmtr)
    if file_re_mesh is not None:
        notes.extend(
            _align_mdf_to_sibling_mesh(
                src, mdf, file_re_mesh, "mesh.1808312334"
            )
        )
    _print_notes(notes, src)
    mdf.fileVersion = 10
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    # writeMDF picks version from destination extension (.10).
    file_re_mdf.writeMDF(mdf, dst)
    if not os.path.isfile(dst):
        raise RuntimeError(f"MDF write did not create file: {dst}")
    _validate_classic_mdf(src, dst)
    # Round-trip read to ensure classic parser accepts the file.
    check = file_re_mdf.readMDF(dst)
    if not check.materialList:
        raise RuntimeError(f"Classic mdf has no materials: {dst}")
    # Sanity: RT SSSProfileUsed bit should be gone on rematerialized mats.
    for mat in check.materialList:
        if int(mat.flags.asInt32) & 0x08000000:
            raise RuntimeError(
                f"Classic mdf still has SSSProfileUsed flag on "
                f"{mat.materialName}"
            )


def main() -> int:
    args = _parse_args(sys.argv)
    manifest_path = args.get("manifest", "")
    result_path = args.get("result", "")
    if not manifest_path or not result_path:
        print("RE2RTX_BATCH: missing --manifest / --result")
        return 2

    # Sibling helpers (mdf_classicize, mdf_rtxify, mdf_presets) live here.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    results: list[dict] = []
    try:
        with open(manifest_path, encoding="utf-8-sig") as f:
            manifest = json.load(f)
    except Exception as e:
        _write_result(result_path, [{"ok": False, "error": f"Bad manifest: {e}"}])
        return 1

    package = _find_re_mesh_editor_module()
    if not package:
        _write_result(
            result_path,
            [{
                "ok": False,
                "src": "",
                "error": "RE Mesh Editor addon not found/enabled",
            }],
        )
        return 1

    try:
        mesh_api, file_re_mdf, file_re_mesh = _load_api(package)
        _install_compact_mdf_writer(file_re_mdf)
    except Exception as e:
        _write_result(
            result_path,
            [{"ok": False, "src": "", "error": f"Failed loading RE Mesh Editor API: {e}"}],
        )
        return 1

    jobs = manifest.get("jobs") or []
    # Mesh export can drop empty slots. The MDF has to be aligned to that
    # mesh, so the mesh job has to finish before the material job.
    jobs.sort(key=lambda job: 0 if str(job.get("kind", "")).startswith("mesh") else 1)
    shipped_mmtr = manifest.get("shipped_mmtr") or []
    re3_player_dest = manifest.get("re3_player_dest") or None
    for job in jobs:
        kind = job.get("kind", "")
        src = job.get("src", "")
        dst = job.get("dst", "")
        entry = {"kind": kind, "src": src, "dst": dst, "ok": False, "error": ""}
        try:
            if not os.path.isfile(src):
                raise FileNotFoundError(src)
            if kind == "mesh":
                convert_mesh(src, dst, mesh_api, file_re_mesh)
            elif kind == "mesh_rt":
                convert_mesh_to_rt(src, dst, mesh_api, file_re_mesh)
            elif kind == "mdf2":
                convert_mdf(src, dst, file_re_mdf, shipped_mmtr, file_re_mesh)
            elif kind == "mdf2_rt":
                convert_mdf_to_rt(
                    src,
                    dst,
                    file_re_mdf,
                    shipped_mmtr,
                    re3_player_dest,
                    file_re_mesh,
                )
            else:
                raise ValueError(f"Unsupported kind: {kind}")
            entry["ok"] = True
            print(f"RE2RTX_BATCH_OK: {kind} {src}")
        except Exception as e:
            entry["error"] = f"{e}\n{traceback.format_exc()}"
            print(f"RE2RTX_BATCH_FAIL: {kind} {src}: {e}")
            if dst and os.path.isfile(dst):
                try:
                    os.remove(dst)
                except OSError:
                    pass
        results.append(entry)

    _write_result(result_path, results)
    return 0 if all(r.get("ok") for r in results) else 1


def _write_result(path: str, results: list[dict]) -> None:
    payload = {"results": results}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
