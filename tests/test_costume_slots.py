"""Claire costume hair is copied onto the mesh RTX loads. The shared face is not."""

import struct
from pathlib import Path

import pytest

from re2_outfit_converter.material_hash import material_name_hash
from re2_outfit_converter.platform.costume_slots import mount_claire_costume_parts


class Report:
    def __init__(self) -> None:
        self.warnings: list[str] = []


def _u16(text: str) -> bytes:
    return text.encode("utf-16le") + b"\x00\x00"


def test_elza_hair_mounts_and_the_shared_face_stays(tmp_path: Path):
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    face = player / "pl1050"
    hair = player / "pl1605"
    face.mkdir(parents=True)
    hair.mkdir()
    (face / "pl1060.mesh.2109108288").write_bytes(b"FACE")
    (face / "pl1060.mdf2.21").write_bytes(b"FACEMDF")
    (hair / "pl1678.mesh.2109108288").write_bytes(b"HAIR")
    (hair / "pl1678.mdf2.21").write_bytes(b"HAIRMDF")
    (player / "pl1605.chain.21").write_bytes(b"CHAIN")
    prefab = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    prefab.mkdir(parents=True)
    (prefab / "pl1000_face_costume_c.pfb.16").write_bytes(
        _u16("SectionRoot/Character/Player/pl1000/pl1050/pl1050_Blend.mesh")
        + _u16("SectionRoot/Character/Player/pl1000/pl1050/pl1060.mesh")
        + _u16("SectionRoot/Character/Player/pl1000/pl1050/pl1060.mdf2")
    )
    (prefab / "pl1000_hair_costume_c.pfb.16").write_bytes(
        _u16("SectionRoot/Character/Player/pl1000/pl1605/pl1678.mesh")
        + _u16("SectionRoot/Character/Player/pl1000/pl1605/pl1678.mdf2")
        + _u16("SectionRoot/Character/Player/pl1000/pl1605.chain")
    )

    report = Report()
    mount_claire_costume_parts(tmp_path, report)

    assert not (face / "pl1050.mesh.2109108288").exists()
    assert not (face / "pl1050.mdf2.21").exists()
    assert (face / "pl1060.mesh.2109108288").read_bytes() == b"FACE"
    hair_slot = player / "pl1070"
    assert (hair_slot / "pl1070.mesh.2109108288").read_bytes() == b"HAIR"
    assert (hair_slot / "pl1070.mdf2.21").read_bytes() == b"HAIRMDF"
    assert (player / "pl1070.chain.21").read_bytes() == b"CHAIN"
    assert any("left shared pl1050.mesh" in note for note in report.warnings)
    assert any("pl1678.mesh" in note for note in report.warnings)
    assert (prefab / "pl1000_face_costume_c.pfb.17").is_file()
    assert not (prefab / "pl1000_hair_costume_c.pfb.17").exists()


def test_a_no_hood_addon_without_a_prefab_still_mounts_hair(tmp_path: Path):
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    face = player / "pl1050"
    hair = player / "pl1605"
    face.mkdir(parents=True)
    hair.mkdir()
    (face / "pl1060.mesh.2109108288").write_bytes(b"FACE")
    (face / "pl1060.mdf2.21").write_bytes(b"FACEMDF")
    (hair / "pl1678.mesh.2109108288").write_bytes(b"HAIR")
    (hair / "pl1678.mdf2.21").write_bytes(b"HAIRMDF")
    (player / "pl1605.chain.21").write_bytes(b"CHAIN")

    report = Report()
    mount_claire_costume_parts(tmp_path, report)

    assert not (face / "pl1050.mesh.2109108288").exists()
    assert not (face / "pl1050.mdf2.21").exists()
    assert (face / "pl1060.mesh.2109108288").read_bytes() == b"FACE"
    assert (player / "pl1070" / "pl1070.mesh.2109108288").read_bytes() == b"HAIR"
    assert (player / "pl1070" / "pl1070.mdf2.21").read_bytes() == b"HAIRMDF"
    assert (player / "pl1070.chain.21").read_bytes() == b"CHAIN"
    assert any("pl1678.mesh" in note for note in report.warnings)
    assert any("left shared pl1050.mesh" in note for note in report.warnings)


def test_short_hair_on_another_player_is_not_replaced_by_the_ponytail(tmp_path: Path):
    """SB Back to Raccoon City keeps pl207H short hair, not Claire's pl1070."""
    players = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character" / "player"
    )
    claire = players / "pl1000"
    short = players / "pl2000" / "pl207H"
    claire.mkdir(parents=True)
    short.mkdir(parents=True)
    (claire / "pl1070").mkdir()
    (claire / "pl1070" / "pl1070_hair_alba.tex.34").write_bytes(b"BLONDE")
    (short / "pl2070.mesh.2109108288").write_bytes(b"SHORT")
    brown = "SectionRoot/Character/Player/pl1000/pl1004/pl2005_Hair_ALBM.tex"
    blonde = "SectionRoot/Character/Player/pl1000/pl1070/pl1070_hair_alba.tex"
    assert len(brown) == len(blonde)
    (short / "pl2070.mdf2.21").write_bytes(_u16(brown))
    (players / "pl2000" / "pl2071.chain.21").write_bytes(b"CHAIN")
    prefab = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    prefab.mkdir(parents=True)
    (prefab / "pl1000_hair_costume_c.pfb.16").write_bytes(
        _u16("SectionRoot/Character/Player/pl2000/pl207H/pl2070.mesh")
        + _u16("SectionRoot/Character/Player/pl2000/pl207H/pl2070.mdf2")
        + _u16("SectionRoot/Character/Player/pl2000/pl2071.chain")
        + _u16("pl2070_Hair_Mat")
    )

    report = Report()
    mount_claire_costume_parts(tmp_path, report)

    assert not (claire / "pl1070" / "pl1070.mesh.2109108288").exists()
    rt = prefab / "pl1000_hair_costume_c.pfb.17"
    assert rt.is_file()
    assert _u16_has(rt.read_bytes(), "pl2000/pl207H/pl2070.mesh")
    assert _u16_has(rt.read_bytes(), "pl2000/pl207H/pl2070.mdf2")
    assert _u16_has(rt.read_bytes(), "pl2000/pl2071.chain")
    assert _u16_has(rt.read_bytes(), "pl2070_Hair_Mat")
    assert not _u16_has(rt.read_bytes(), "pl1000/pl1070/pl1070.mesh")
    assert any("pl2000/pl207H/pl2070.mesh" in note for note in report.warnings)
    mdf = (short / "pl2070.mdf2.21").read_bytes()
    assert _u16_has(mdf, blonde)
    assert not _u16_has(mdf, "pl2005_Hair_ALBM")
    assert (claire / "pl1070" / "pl1070_hair_alba.tex.34").read_bytes() == b"BLONDE"


def test_a_shared_head_is_kept_on_the_destination_costume_only(tmp_path: Path):
    """A face shipped as pl1050.mesh must not stay the head every outfit uses."""
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000" / "pl1050"
    )
    player.mkdir(parents=True)
    (player / "pl1050.mesh.2109108288").write_bytes(b"SAME")
    (player / "pl1050_face_nrmr.tex.34").write_bytes(b"NECK")
    prefab = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    prefab.mkdir(parents=True)
    (prefab / "pl1000_face_costume_b.pfb.16").write_bytes(
        _u16("SectionRoot/Character/Player/pl1000/pl1050/pl1050.mesh")
    )
    report = Report()
    mount_claire_costume_parts(tmp_path, report)
    names = {path.name for path in player.iterdir()}
    assert "pl1050.mesh.2109108288" not in names
    assert "pl1050_face_nrmr.tex.34" not in names
    assert (player / "pl1060.mesh.2109108288").read_bytes() == b"SAME"
    assert (player / "pl1060_face_nrmr.tex.34").read_bytes() == b"NECK"
    rt = prefab / "pl1000_face_costume_b.pfb.17"
    assert rt.is_file()
    data = rt.read_bytes()
    assert _u16_has(data, "pl1050/pl1060.mesh")
    assert not _u16_has(data, "pl1050/pl1050.mesh")
    assert _u16_has(data, "pl1050/pl1050.mdf2")


def test_an_rt_face_prefab_that_names_the_shared_mesh_is_rewritten(tmp_path: Path):
    """A .pfb.17 that still loads pl1050.mesh must follow the private head."""
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000" / "pl1050"
    )
    player.mkdir(parents=True)
    (player / "pl1050.mesh.2109108288").write_bytes(b"SAME")
    prefab = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    prefab.mkdir(parents=True)
    (prefab / "pl1000_face_costume_b.pfb.17").write_bytes(
        _u16("SectionRoot/Character/Player/pl1000/pl1050/pl1050.mesh")
    )
    report = Report()
    mount_claire_costume_parts(tmp_path, report)
    assert not (player / "pl1050.mesh.2109108288").exists()
    assert (player / "pl1060.mesh.2109108288").read_bytes() == b"SAME"
    rt = prefab / "pl1000_face_costume_b.pfb.17"
    data = rt.read_bytes()
    assert _u16_has(data, "pl1050/pl1060.mesh")
    assert not _u16_has(data, "pl1050/pl1050.mesh")


def test_face_only_mount_leaves_loose_hair_off_the_shared_ponytail(tmp_path: Path):
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    face = player / "pl1050"
    hair = player / "pl1605"
    face.mkdir(parents=True)
    hair.mkdir()
    (face / "pl1050.mesh.2109108288").write_bytes(b"FACE")
    (hair / "pl1678.mesh.2109108288").write_bytes(b"HAIR")
    (player / "pl1605.chain.21").write_bytes(b"CHAIN")
    report = Report()
    mount_claire_costume_parts(tmp_path, report, face_slot="b", hair=False)
    assert (face / "pl1060.mesh.2109108288").read_bytes() == b"FACE"
    assert not (player / "pl1070").exists()
    assert not (player / "pl1070.chain.21").exists()
    assert (hair / "pl1678.mesh.2109108288").read_bytes() == b"HAIR"


def test_a_non_claire_player_is_left_alone(tmp_path: Path):
    sherry = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl3000"
    )
    sherry.mkdir(parents=True)
    mesh = sherry / "pl3000.mesh.2109108288"
    mesh.write_bytes(b"SHERRY")
    report = Report()
    mount_claire_costume_parts(tmp_path, report, face_slot="b")
    assert mesh.read_bytes() == b"SHERRY"
    assert not (tmp_path / "natives" / "stm" / "sectionroot" / "character" / "player" / "pl1000").exists()
    assert report.warnings == []


def test_an_addon_face_without_a_prefab_follows_the_destination_slot(tmp_path: Path):
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000" / "pl1050"
    )
    player.mkdir(parents=True)
    (player / "pl1050.mesh.2109108288").write_bytes(b"GAG")
    report = Report()
    mount_claire_costume_parts(tmp_path, report, face_slot="b")
    assert not (player / "pl1050.mesh.2109108288").exists()
    assert (player / "pl1060.mesh.2109108288").read_bytes() == b"GAG"
    rt = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
        / "pl1000_face_costume_b.pfb.17"
    )
    assert rt.is_file()
    assert _u16_has(rt.read_bytes(), "pl1050/pl1060.mesh")
    assert not (rt.parent / "pl1000_face_costume_c.pfb.17").exists()


def test_ballgag_does_not_replace_every_outfit_head_or_neck(tmp_path: Path):
    """A private pl1060 face must not leave pl1050.mesh or pl1050_face_* loose.

    Those loose files replace the head and the neck on every Claire outfit.
    The converted costume keeps the gag through pl1060.
    """
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000" / "pl1050"
    )
    player.mkdir(parents=True)
    (player / "pl1050.mesh.2109108288").write_bytes(b"GAG")
    (player / "pl1060.mesh.2109108288").write_bytes(b"GAG")
    (player / "pl1050_face_nrmr.tex.34").write_bytes(b"NECK")
    (player / "pl1050_face_atos.tex.34").write_bytes(b"SPEC")
    (player / "pl1050_face_albm.tex.34").write_bytes(b"SHARED")
    (player / "pl1060_face_albm.tex.34").write_bytes(b"PRIVATE")
    mdf = (
        _u16("SectionRoot/Character/Player/pl1000/pl1050/pl1050_Face_NRMR.tex")
        + _u16("SectionRoot/Character/Player/pl1000/pl1050/pl1050_Face_ATOS.tex")
        + _u16("SectionRoot/Character/Player/pl1000/pl1050/pl1060_Face_ALBM.tex")
        + _u16("SectionRoot/Character/Player/pl1000/pl1050/pl1050_Face_Blend_NRMR.tex")
        + _u16("pl1050_Face_Mat")
    )
    (player / "pl1060.mdf2.21").write_bytes(mdf)

    report = Report()
    mount_claire_costume_parts(tmp_path, report)

    names = {path.name for path in player.iterdir()}
    assert "pl1050.mesh.2109108288" not in names
    assert (player / "pl1060.mesh.2109108288").read_bytes() == b"GAG"
    assert "pl1050_face_nrmr.tex.34" not in names
    assert "pl1050_face_atos.tex.34" not in names
    assert "pl1050_face_albm.tex.34" not in names
    assert (player / "pl1060_face_nrmr.tex.34").read_bytes() == b"NECK"
    assert (player / "pl1060_face_atos.tex.34").read_bytes() == b"SPEC"
    assert (player / "pl1060_face_albm.tex.34").read_bytes() == b"PRIVATE"
    patched = (player / "pl1060.mdf2.21").read_bytes()
    assert _u16_has(patched, "pl1050/pl1060_Face_NRMR.tex")
    assert _u16_has(patched, "pl1050/pl1060_Face_ATOS.tex")
    assert _u16_has(patched, "pl1060_Face_ALBM.tex")
    assert _u16_has(patched, "pl1050_Face_Blend_NRMR.tex")
    assert _u16_has(patched, "pl1050_Face_Mat")
    assert not _u16_has(patched, "pl1050_Face_NRMR")
    assert not _u16_has(patched, "pl1050_Face_ATOS")


def _u16_has(data: bytes, text: str) -> bool:
    return text.encode("utf-16le") in data


# Every Claire slot except '98. Jacket's primary slot is the default prefab.
_CLAIRE_SLOTS = ("default", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c")


def _pak_hair(slot: str) -> str:
    if slot == "a":
        return "pl1075"
    if slot == "b":
        return "pl1071"
    return "pl1070"


def _prefab_name(kind: str, slot: str) -> str:
    if slot == "default":
        return f"pl1000_{kind}_default.pfb.16"
    return f"pl1000_{kind}_costume_{slot}.pfb.16"


@pytest.mark.parametrize("slot", _CLAIRE_SLOTS)
def test_every_costume_keeps_the_mod_face_and_does_not_hide_the_body(tmp_path: Path, slot: str):
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    face = player / "pl1873"
    hair = player / "pl1800"
    body = player / "pl1004"
    face.mkdir(parents=True)
    hair.mkdir()
    body.mkdir()
    mat = "pl1873_Face_Mat".encode("utf-16le")
    (face / "pl1060.mesh.21").write_bytes(b"FACE" + mat)
    (face / "pl1060.mdf2.21").write_bytes(b"MDF" + mat)
    (body / "pl1004.mesh.21").write_bytes(b"BODY")
    hair_names = (
        "pl1800_Hair_Mat",
        "pl1800_Hair2_Mat",
        "pl1800_Hair3_Mat",
    )
    (hair / "pl1800.mdf2.21").write_bytes(b"".join(
        struct.pack("<I", material_name_hash(name)) + name.encode("utf-16le")
        for name in (*hair_names, "pl1800_Hair_ALBA")
    ))
    (hair / "pl1800_hair_alba.tex.34").write_bytes(b"BLONDE")
    prefab = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    prefab.mkdir(parents=True)
    (prefab / _prefab_name("face", slot)).write_bytes(
        _u16("SectionRoot/Character/Player/pl1000/pl1873/pl1060.mesh")
        + _u16("SectionRoot/Character/Player/pl1000/pl1873/pl1060.mdf2")
    )
    (prefab / _prefab_name("hair", slot)).write_bytes(
        _u16("SectionRoot/Character/Player/pl1000/pl1800/pl1800.mesh")
        + _u16("SectionRoot/Character/Player/pl1000/pl1800/pl1800.mdf2")
        + _u16("SectionRoot/Character/Player/pl1000/pl1800.chain")
    )

    report = Report()
    mount_claire_costume_parts(tmp_path, report)

    assert not list(player.rglob("pl1050.mesh*"))
    assert (body / "pl1004.mesh.21").read_bytes() == b"BODY"
    assert (hair / "pl1800_hair_alba.tex.34").read_bytes() == b"BLONDE"
    assert not list(player.rglob("pl1070.mesh*"))
    assert not list(player.rglob("pl1071.mesh*"))
    assert not list(player.rglob("pl1075.mesh*"))
    assert not list(player.rglob("*.chain*"))

    face_pfb = prefab / _prefab_name("face", slot).replace(".pfb.16", ".pfb.17")
    hair_pfb = prefab / _prefab_name("hair", slot).replace(".pfb.16", ".pfb.17")
    face_bytes = face_pfb.read_bytes()
    hair_bytes = hair_pfb.read_bytes()
    pak = _pak_hair(slot)

    assert _u16_has(face_bytes, "pl1873/pl1060.mesh")
    assert _u16_has(face_bytes, "pl1873/pl1060.mdf2")
    assert _u16_has(face_bytes, "pl1873_Face_Mat")
    assert _u16_has(face_bytes, "pl1050/pl1050_Blend.mesh")
    assert not _u16_has(face_bytes, "pl1050/pl1050.mesh")
    assert not _u16_has(face_bytes, "pl1050/pl1050.mdf2")
    assert _u16_has(hair_bytes, f"{pak}/{pak}.mesh")
    assert _u16_has(hair_bytes, f"{pak}.chain")
    assert _u16_has(hair_bytes, "pl1800/pl1800.mdf2")
    assert not _u16_has(hair_bytes, "pl1800/pl1800.mesh")
    assert not _u16_has(hair_bytes, "pl1800.chain")
    mdf = (hair / "pl1800.mdf2.21").read_bytes()
    assert _u16_has(mdf, f"{pak}_Hair_Mat")
    assert _u16_has(mdf, f"{pak}_Hair2_Mat")
    assert _u16_has(mdf, f"{pak}_Hair3_Mat")
    assert _u16_has(mdf, "pl1800_Hair_ALBA")
    assert not _u16_has(mdf, "pl1800_Hair_Mat")
    for old, new in (
        ("pl1800_Hair_Mat", f"{pak}_Hair_Mat"),
        ("pl1800_Hair2_Mat", f"{pak}_Hair2_Mat"),
        ("pl1800_Hair3_Mat", f"{pak}_Hair3_Mat"),
    ):
        assert struct.pack("<I", material_name_hash(new)) in mdf
        assert struct.pack("<I", material_name_hash(old)) not in mdf
    if slot == "default":
        assert _u16_has(face_bytes, "pl1000_face_default")
        assert _u16_has(hair_bytes, "pl1000_hair_default")
        assert not _u16_has(face_bytes, "costume_8")
    else:
        assert _u16_has(face_bytes, f"costume_{slot}")
        assert _u16_has(hair_bytes, f"costume_{slot}")
        if slot != "8":
            assert not _u16_has(face_bytes, "costume_8")
            assert not _u16_has(hair_bytes, "costume_8")


def test_addon_texture_hair_does_not_replace_the_main_hair(tmp_path: Path):
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    hair = player / "pl1800"
    hair.mkdir(parents=True)
    (hair / "pl1800.mdf2.21").write_bytes(b"MDF")
    prefab = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    prefab.mkdir(parents=True)
    (prefab / "pl1000_hair_costume_3.pfb.16").write_bytes(
        _u16("SectionRoot/Character/Player/pl1000/pl1800/pl1800.mesh")
        + _u16("SectionRoot/Character/Player/pl1000/pl1800/pl1800.mdf2")
    )
    (tmp_path / "modinfo.ini").write_text(
        "Name=Gold\nAddonFor=Girl in Red\n", encoding="utf-8",
    )
    report = Report()
    mount_claire_costume_parts(tmp_path, report)
    assert not (prefab / "pl1000_hair_costume_3.pfb.17").exists()
    assert not list(player.rglob("pl1050.mesh*"))
    assert not list(player.rglob("pl1070.mesh*"))


@pytest.mark.parametrize("slot", _CLAIRE_SLOTS)
def test_private_head_named_pl1050_does_not_replace_the_shared_head(tmp_path: Path, slot: str):
    """Fallen Angel stores the custom head at pl1059/pl1050.mesh."""
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    face = player / "pl1059"
    face.mkdir(parents=True)
    mat = "pl1823_Face_Mat"
    (face / "pl1050.mesh.2109108288").write_bytes(b"FACE" + mat.encode("utf-16le"))
    (face / "pl1050.mdf2.21").write_bytes(b"MDF" + mat.encode("utf-16le"))
    (face / "pl1050_Blend.mesh.2109108288").write_bytes(b"BLEND")
    (player / "pl1004").mkdir()
    (player / "pl1004" / "pl1004.mesh.21").write_bytes(b"BODY")
    prefab = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    prefab.mkdir(parents=True)
    (prefab / _prefab_name("face", slot)).write_bytes(
        _u16("SectionRoot/Character/Player/pl1000/pl1059/pl1050_Blend.mesh")
        + _u16("SectionRoot/Character/Player/pl1000/pl1059/pl1050.mesh")
        + _u16("SectionRoot/Character/Player/pl1000/pl1059/pl1050.mdf2")
        + _u16(mat)
    )

    mount_claire_costume_parts(tmp_path, Report())

    assert not (player / "pl1050" / "pl1050.mesh.2109108288").exists()
    assert (face / "pl1050.mesh.2109108288").read_bytes().startswith(b"FACE")
    assert (player / "pl1004" / "pl1004.mesh.21").read_bytes() == b"BODY"
    rt = prefab / _prefab_name("face", slot).replace(".pfb.16", ".pfb.17")
    data = rt.read_bytes()
    assert _u16_has(data, "pl1059/pl1050.mesh")
    assert _u16_has(data, "pl1059/pl1050.mdf2")
    assert _u16_has(data, "pl1059/pl1050_Blend.mesh")
    assert _u16_has(data, mat)
    assert not _u16_has(data, "pl1050/pl1050.mesh")
    assert not _u16_has(data, "pl1050/pl1050_Blend.mesh")


@pytest.mark.parametrize("slot", ("a", "b"))
def test_hair_keeps_the_ponytail_chain_on_hat_slots(tmp_path: Path, slot: str):
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    hair = player / "pl1846"
    hair.mkdir(parents=True)
    (hair / "pl1846.mesh.2109108288").write_bytes(b"HAIR")
    (hair / "pl1846.mdf2.21").write_bytes(
        "pl1846_Hair_Mat".encode("utf-16le")
    )
    prefab = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    prefab.mkdir(parents=True)
    (prefab / _prefab_name("hair", slot)).write_bytes(
        _u16("SectionRoot/Character/Player/pl1000/pl1846/pl1846.mesh")
        + _u16("SectionRoot/Character/Player/pl1000/pl1846/pl1846.mdf2")
        + _u16("SectionRoot/Character/Player/pl1000/pl1070.chain")
        + _u16("pl1846_Hair_Mat")
    )

    mount_claire_costume_parts(tmp_path, Report())

    pak = _pak_hair(slot)
    assert not list(player.rglob(f"{pak}.mesh*"))
    assert (hair / "pl1846.mesh.2109108288").read_bytes() == b"HAIR"
    data = (prefab / _prefab_name("hair", slot).replace(".pfb.16", ".pfb.17")).read_bytes()
    assert _u16_has(data, "pl1846/pl1846.mesh")
    assert _u16_has(data, "pl1846/pl1846.mdf2")
    assert _u16_has(data, "pl1070.chain")
    assert not _u16_has(data, f"{pak}.chain")


def test_face_texture_addon_does_not_take_the_shared_head(tmp_path: Path):
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    face = player / "pl1050"
    body = player / "pl1004"
    face.mkdir(parents=True)
    body.mkdir()
    (face / "pl1050_face_albm.tex.10").write_bytes(b"ALBM")
    (face / "pl1050_face_nrmr.tex.10").write_bytes(b"NRMR")
    (body / "pl1004.mesh.1808312334").write_bytes(b"BODY")
    (tmp_path / "modinfo.ini").write_text(
        '[Mod]\nName=N. S. 2\nAddonFor=The Fallen Angel Mutation II\n',
        encoding="utf-8",
    )

    mount_claire_costume_parts(tmp_path, Report())

    assert not list(player.rglob("pl1050.mesh*"))
    assert not list(player.rglob("*.pfb.17"))
    assert (face / "pl1050_face_albm.tex.10").read_bytes() == b"ALBM"
    assert (body / "pl1004.mesh.1808312334").read_bytes() == b"BODY"
