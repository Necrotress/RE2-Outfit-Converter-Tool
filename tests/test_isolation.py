"""Private ID allocation, exclusive-hair, and material alias tests."""

from pathlib import Path
import struct

import pytest

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo
from re2_outfit_converter.isolation import (
    allocate_private_ids,
    isolate_claire_face_hair,
    isolate_shared_outfit_textures,
    register_material_name_aliases,
    rename_entries,
)
from re2_outfit_converter.material_hash import (
    material_name_hash,
    patch_mdf_material_hashes,
)
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.path_patch import patch_binaries
from re2_outfit_converter.paths import MESH_ROOTS
from re2_outfit_converter.reports import ConversionError, ConversionReport


def test_allocate_stable_for_same_seed():
    a = allocate_private_ids("MyMod", set())
    b = allocate_private_ids("MyMod", set())
    assert a == b
    assert a[0] != a[1]
    assert a[0].startswith("pl18") and len(a[0]) == 6


def test_allocate_skips_reserved():
    reserved = {f"pl{1800 + i}" for i in range(98)}
    face, hair = allocate_private_ids("x", set(reserved))
    assert face not in reserved and hair not in reserved
    assert face != hair


def test_allocate_exhaustion():
    reserved = {f"pl{1800 + i}" for i in range(100)}
    with pytest.raises(ConversionError):
        allocate_private_ids("full", set(reserved))


def test_isolate_keeps_exclusive_when_target_is_military(tmp_path: Path):
    staging = tmp_path
    hat = staging / MESH_ROOTS[0] / "pl1071"
    hat.mkdir(parents=True)
    (hat / "pl1071.mesh.1").write_bytes(b"hdr\x00pl1071_Scarf_Mat\x00")
    analysis = AnalysisResult(
        root=staging,
        modinfo=ModInfo(name="STARS"),
        natives_files=[f"{MESH_ROOTS[0]}/pl1071/pl1071.mesh.1"],
    )
    report = ConversionReport()
    _, hair_id = isolate_claire_face_hair(
        staging, analysis,
        CLAIRE_OUTFIT_BY_KEY["military"],
        CLAIRE_OUTFIT_BY_KEY["military"],
        {}, report,
    )
    assert hair_id == "pl1071"
    assert any("kept exclusive hair pl1071" in op for op in report.rename_ops)


def test_disabled_hair_folder_is_used_instead_of_the_face(tmp_path: Path):
    """``_pl1070`` is the mod hair. The face must not be copied onto pl1071."""
    from re2_outfit_converter.exclusive_meshes import ensure_exclusive_part_mesh_hide

    staging = tmp_path
    root = staging / MESH_ROOTS[0]
    face = root / "pl1050"
    face.mkdir(parents=True)
    (face / "pl1060.mesh.1").write_bytes(b"FACE")
    hair = root / "_pl1070"
    hair.mkdir()
    (hair / "pl1070.mesh.1").write_bytes(b"HAIR")
    (hair / "--pl1070.mdf2.10").write_bytes(b"MDF")
    (hair / "pl1070_hair_alba.tex.10").write_bytes(b"TEX")
    analysis = AnalysisResult(
        root=staging, modinfo=ModInfo(name="Patriot"))
    report = ConversionReport()
    face_id, hair_id = isolate_claire_face_hair(
        staging, analysis,
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["military"],
        {}, report,
        keep_exclusive_ids={"pl1071"},
    )
    assert face_id != hair_id
    assert hair_id.startswith("pl18")
    assert (root / hair_id / f"{hair_id}.mesh.1").read_bytes() == b"HAIR"
    assert (root / hair_id / f"{hair_id}.mdf2.10").read_bytes() == b"MDF"
    assert (root / face_id / "pl1060.mesh.1").read_bytes() == b"FACE"
    assert not (root / "_pl1070").exists()

    ensure_exclusive_part_mesh_hide(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], hair_id, report)
    hid = root / "pl1071"
    assert (hid / "pl1071.mesh.1").read_bytes() == b"HAIR"
    assert (hid / "pl1071.mdf2.10").read_bytes() == b"MDF"
    assert not any("pl1060" in p.name.lower() for p in hid.iterdir())


def test_isolate_moves_exclusive_away_from_military(tmp_path: Path):
    """Converting Military→Elza must clear pl1071 so Military stays vanilla."""
    staging = tmp_path
    hat = staging / MESH_ROOTS[0] / "pl1071"
    hat.mkdir(parents=True)
    (hat / "pl1071.mesh.1").write_bytes(b"hdr\x00pl1071_Scarf_Mat\x00")
    (hat / "pl1071_scarf_albm.tex.10").write_bytes(b"tex")
    analysis = AnalysisResult(
        root=staging,
        modinfo=ModInfo(name="STARS"),
        natives_files=[
            f"{MESH_ROOTS[0]}/pl1071/pl1071.mesh.1",
            f"{MESH_ROOTS[0]}/pl1071/pl1071_scarf_albm.tex.10",
        ],
    )
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    _, hair_id = isolate_claire_face_hair(
        staging, analysis,
        CLAIRE_OUTFIT_BY_KEY["military"],
        CLAIRE_OUTFIT_BY_KEY["elza"],
        rename_map, report,
    )
    assert hair_id.startswith("pl18")
    assert not (staging / MESH_ROOTS[0] / "pl1071").exists()
    assert (staging / MESH_ROOTS[0] / hair_id / f"{hair_id}.mesh.1").is_file()
    # Materials stay on pl1071; bundled private mdf binds renamed textures.
    mesh = (staging / MESH_ROOTS[0] / hair_id / f"{hair_id}.mesh.1").read_bytes()
    assert b"pl1071_Scarf_Mat" in mesh
    assert "pl1071_Scarf_Mat" not in rename_map
    mdfs = list((staging / MESH_ROOTS[0] / hair_id).glob(f"{hair_id}.mdf2*"))
    assert mdfs, "bundled exclusive mdf should be seeded into private folder"
    assert any("bundled exclusive mdf" in op for op in report.rename_ops)
    assert any("isolated exclusive hair pl1071" in op for op in report.rename_ops)


def _u16(s: str) -> bytes:
    return b"".join(bytes([ord(c), 0]) for c in s)


def test_body_rename_remaps_materials_and_hashes(tmp_path: Path):
    """Wet needs material IDs + Murmur hashes updated with the body slot."""
    staging = tmp_path
    root = (
        staging / "natives" / "x64" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    body = root / "pl1006"
    body.mkdir(parents=True)
    (body / "pl1006.mesh.1").write_bytes(
        b"hdr\x00pl1006_Body_Mat\x00pl1006_Chain_Mat\x00")
    wet = "SectionRoot/Character/Player/pl1000/pl1006/pl1006_wetMask_MSK1.tex"
    old_hash = struct.pack("<I", material_name_hash("pl1006_Body_Mat"))
    new_hash = struct.pack("<I", material_name_hash("pl1004_Body_Mat"))
    (body / "pl1006.mdf2.10").write_bytes(
        old_hash + _u16("pl1006_Body_Mat") + b"\x00\x00" + _u16(wet) + b"\x00\x00"
    )
    (body / "pl1006_body_albm.tex.10").write_bytes(b"tex")
    (body / "pl1006_wetmask_msk1.tex.10").write_bytes(b"wet")

    rename_map: dict[str, str] = {}
    report = ConversionReport()
    rename_entries(root, staging, "pl1006", "pl1004", rename_map, report)
    assert rename_map.get("pl1006_Body_Mat") == "pl1004_Body_Mat"
    assert rename_map.get("pl1006_Chain_Mat") == "pl1004_Chain_Mat"

    patch_binaries(staging, rename_map, report)
    patch_mdf_material_hashes(staging, rename_map, report)

    mesh = next(staging.rglob("pl1004.mesh*")).read_bytes()
    assert b"pl1004_Body_Mat" in mesh

    mdf = next(staging.rglob("pl1004.mdf2*")).read_bytes()
    assert _u16("pl1004_Body_Mat") in mdf
    assert old_hash not in mdf
    assert new_hash in mdf
    assert _u16("pl1004/pl1004_wetMask_MSK1.tex") in mdf


def test_register_material_name_aliases_helper(tmp_path: Path):
    folder = tmp_path / "pl1006"
    folder.mkdir()
    (folder / "pl1006.mesh.1").write_bytes(b"pl1006_Body_Mat")
    rename_map: dict[str, str] = {}
    assert register_material_name_aliases(
        folder, "pl1006", "pl1004", rename_map) == 1
    assert rename_map == {"pl1006_Body_Mat": "pl1004_Body_Mat"}


def test_material_name_hash_known_value():
    assert material_name_hash("pl1006_Body_Mat") == 0xE36A92E1


def test_two_hop_rename_patches_the_final_material_hash(tmp_path: Path):
    """Promote then convert leaves the last name and the first id's hash."""
    staging = tmp_path / "natives" / "x64"
    staging.mkdir(parents=True)
    cases = (
        ("pl1001_Body_Mat", "pl1000_Body_Mat", "pl1004_Body_Mat"),
        ("pl0001_Body_Mat", "pl0000_Body_Mat", "pl0004_Body_Mat"),
    )
    for start, mid, final in cases:
        folder = staging / final[:6]
        folder.mkdir()
        (folder / f"{final[:6]}.mdf2.21").write_bytes(
            struct.pack("<I", material_name_hash(start))
            + _u16(final)
            + b"\x00\x00"
        )
        patch_mdf_material_hashes(
            tmp_path,
            {start: mid, mid: final},
            ConversionReport(),
        )
        data = (folder / f"{final[:6]}.mdf2.21").read_bytes()
        assert struct.pack("<I", material_name_hash(final)) in data, final
        assert struct.pack("<I", material_name_hash(start)) not in data, final


def test_shared_texture_aliases_patch_addon_mdf_without_textures_folder(
    tmp_path: Path,
):
    """Apocalypse-style AddonFor: Pl2020 dirt tex, no Textures/ — still Tex_*.

    Main isolates Escape/Character/Textures → Tex_XXXX. Addon body .mdf2 must
    get the same remap or Fluffy overwrites Main's binds (invisible body).
    """
    staging = tmp_path
    pl2020 = (
        staging / "natives/x64/escape/character/player/wap100/Pl2020/mesh"
    )
    pl2020.mkdir(parents=True)
    (pl2020 / "pl2900_body_albm.tex.10").write_bytes(b"tex")
    body = staging / MESH_ROOTS[0] / "pl1006"
    body.mkdir(parents=True)
    mdf = body / "pl1006.mdf2.10"
    # Minimal UTF-16LE payload with both Escape roots (same as real body mdf).
    payload = (
        "Escape/Character/Player/wap100/Pl2020/Mesh/pl2900_Body_ALBM.tex\0"
        "Escape/Character/Textures/Cover_ALBM.tex\0"
    )
    mdf.write_bytes(payload.encode("utf-16-le"))

    rename_map: dict[str, str] = {}
    report = ConversionReport()
    isolate_shared_outfit_textures(staging, "pl1856", rename_map, report)
    assert rename_map.get("Escape/Character/Textures") == (
        "Escape/Character/Tex_1856"
    )
    assert rename_map.get("Escape/Character/Player/wap100/Pl2020") == (
        "Escape/Character/Player/wap100/Pl1856"
    )
    patch_binaries(staging, rename_map, report)
    data = mdf.read_bytes()
    assert _u16("Escape/Character/Tex_1856/Cover_ALBM.tex") in data
    assert _u16("Escape/Character/Textures/Cover_ALBM.tex") not in data
    assert _u16(
        "Escape/Character/Player/wap100/Pl1856/Mesh/pl2900_Body_ALBM.tex"
    ) in data


def test_body_folder_prefix_patches_mdf_only_addon(tmp_path: Path):
    """Black Patch ships only the body MDF. Texture paths still have to move."""
    staging = tmp_path
    root = (
        staging / "natives" / "x64" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    body = root / "pl1005"
    body.mkdir(parents=True)
    tex = "SectionRoot/Character/Player/pl1000/pl1005/props_1.tex"
    detail = "SectionRoot/Character/Player/pl1000/pl1005/Leather_Detail_NRM.tex"
    (body / "pl1005.mdf2.10").write_bytes(
        _u16(tex) + b"\x00\x00" + _u16(detail) + b"\x00\x00"
    )

    rename_map: dict[str, str] = {}
    report = ConversionReport()
    rename_entries(
        root, staging, "pl1005", "pl1006", rename_map, report,
        register_dir_prefix=True,
    )
    assert "sectionroot/character/player/pl1000/pl1005" not in rename_map

    patch_binaries(staging, rename_map, report)
    data = next(staging.rglob("pl1006.mdf2*")).read_bytes()
    assert _u16("pl1006/props_1.tex") in data
    assert _u16("pl1005/props_1.tex") not in data
    assert _u16("pl1005/Leather_Detail_NRM.tex") in data
    assert _u16("pl1006/Leather_Detail_NRM.tex") not in data


def test_shared_face_mesh_is_isolated_off_pl1050(tmp_path: Path):
    """Elite's pl1050.mesh is a shortened neck. It must not replace every costume."""
    staging = tmp_path
    face = staging / MESH_ROOTS[0] / "pl1050"
    face.mkdir(parents=True)
    (face / "pl1050.mesh.1").write_bytes(b"neck")
    analysis = AnalysisResult(
        root=staging, modinfo=ModInfo(name="Elite"),
    )
    report = ConversionReport()
    face_id, _ = isolate_claire_face_hair(
        staging, analysis,
        CLAIRE_OUTFIT_BY_KEY["noir"],
        CLAIRE_OUTFIT_BY_KEY["military"],
        {}, report,
    )
    assert face_id.startswith("pl18")
    assert not (staging / MESH_ROOTS[0] / "pl1050").exists()
    assert (staging / MESH_ROOTS[0] / face_id / f"{face_id}.mesh.1").is_file()
    assert any("isolated face pl1050" in op for op in report.rename_ops)


def test_other_stem_in_face_folder_is_still_isolated(tmp_path: Path):
    staging = tmp_path
    face = staging / MESH_ROOTS[0] / "pl1050"
    face.mkdir(parents=True)
    (face / "pl1060.mesh.1").write_bytes(b"custom")
    analysis = AnalysisResult(
        root=staging, modinfo=ModInfo(name="BSAA"),
    )
    report = ConversionReport()
    face_id, _ = isolate_claire_face_hair(
        staging, analysis,
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        {}, report,
    )
    assert face_id.startswith("pl18")
    assert not (staging / MESH_ROOTS[0] / "pl1050").exists()
    assert (staging / MESH_ROOTS[0] / face_id / "pl1060.mesh.1").is_file()


def test_face_prefab_still_isolates_shared_mesh(tmp_path: Path):
    staging = tmp_path
    face = staging / MESH_ROOTS[0] / "pl1050"
    face.mkdir(parents=True)
    (face / "pl1050.mesh.1").write_bytes(b"face")
    parts = staging / (
        "natives/x64/objectroot/prefab/character/survivor/parts/pl1000"
    )
    parts.mkdir(parents=True)
    (parts / "pl1000_face_costume_c.pfb.16").write_bytes(b"pfb")
    analysis = AnalysisResult(
        root=staging, modinfo=ModInfo(name="Elza"),
    )
    report = ConversionReport()
    face_id, _ = isolate_claire_face_hair(
        staging, analysis,
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        {}, report,
    )
    assert face_id.startswith("pl18")
    assert not (staging / MESH_ROOTS[0] / "pl1050").exists()
    assert any("isolated face pl1050" in op for op in report.rename_ops)


def test_hair_rename_keeps_pak_textures_and_the_vanilla_chain(tmp_path: Path):
    """Only files the mod ships move. Pak normals and pl1070.chain stay put."""
    staging = tmp_path
    root = (
        staging / "natives" / "x64" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    hair = root / "pl1070"
    hair.mkdir(parents=True)
    (hair / "pl1070.mesh.1").write_bytes(b"mesh")
    (hair / "pl1070_hair_alba.tex.10").write_bytes(b"alb")
    nrm = "SectionRoot/Character/Player/pl1000/pl1070/pl1070_Hair_NRMR.tex"
    chain = "SectionRoot/Character/Player/pl1000/pl1070.chain"
    alba = "SectionRoot/Character/Player/pl1000/pl1070/pl1070_Hair_ALBA.tex"
    (hair / "pl1070.mdf2.10").write_bytes(
        _u16(nrm) + b"\x00\x00" + _u16(chain) + b"\x00\x00" + _u16(alba)
    )

    rename_map: dict[str, str] = {}
    report = ConversionReport()
    rename_entries(root, staging, "pl1070", "pl1890", rename_map, report)
    assert "sectionroot/character/player/pl1000/pl1070" not in rename_map

    patch_binaries(staging, rename_map, report)
    data = next(staging.rglob("pl1890.mdf2*")).read_bytes()
    assert _u16("pl1070/pl1070_Hair_NRMR.tex") in data
    assert _u16("pl1070.chain") in data
    assert _u16("pl1890/pl1890_Hair_ALBA.tex") in data
    assert _u16("pl1890.chain") not in data
