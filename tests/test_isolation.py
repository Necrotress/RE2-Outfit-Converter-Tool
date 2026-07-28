"""Private ID allocation, exclusive-hair, and material alias tests."""

from pathlib import Path
import struct

import pytest

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo
from re2_outfit_converter.isolation import (
    allocate_private_ids,
    isolate_claire_face_hair,
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
