"""Costume parking helpers and the outfit pipeline's game-build direction."""

from __future__ import annotations

import struct
from pathlib import Path
from types import SimpleNamespace

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.converter import convert_with_ops
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.platform.converter import (
    _bundle_costume_prefix,
    _find_claire_costume_dir,
    _find_claire_costume_tex_dir,
    _move_unmounted_textures_to,
    _park_bundle_addon_textures,
)


def _classic_tex() -> bytes:
    payload = b"PX"
    header = 48
    buf = bytearray(header + len(payload))
    buf[0:4] = b"TEX\x00"
    struct.pack_into("<I", buf, 4, 10)
    struct.pack_into("<HHH", buf, 8, 4, 4, 0)
    buf[14] = 1
    buf[15] = 1
    struct.pack_into("<IIII", buf, 16, 98, 0, 0, 0)
    struct.pack_into("<QII", buf, 32, header, 16, len(payload))
    buf[header:] = payload
    return bytes(buf)


def _mod(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    (root / "modinfo.ini").write_text("name=Mod\n", encoding="utf-8")


def test_military_face_textures_are_not_a_costume_dir(tmp_path: Path):
    section = tmp_path / "sectionroot"
    player = section / "character" / "player" / "pl1000"
    face = player / "pl1050" / "pl1050_04"
    face.mkdir(parents=True)
    (face / "pl1050_04_face_albm.tex.10").write_bytes(b"F")
    body = player / "pl1004"
    body.mkdir()
    (body / "pl2900_body_albm.tex.10").write_bytes(b"B")
    assert _find_claire_costume_tex_dir(section) == body


def test_parked_classic_texture_is_upgraded_on_stm(tmp_path: Path):
    dest = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000" / "pl1004"
    )
    dest.mkdir(parents=True)
    src = (
        tmp_path / "natives" / "x64" / "sectionroot" / "character"
        / "player" / "wap100"
    )
    src.mkdir(parents=True)
    (src / "pl2900_body_albm.tex.10").write_bytes(_classic_tex())
    assert _move_unmounted_textures_to(tmp_path, dest) == 1
    assert (dest / "pl2900_body_albm.tex.34").is_file()
    assert not (src / "pl2900_body_albm.tex.10").exists()


def test_face_only_mesh_is_not_a_costume_dir(tmp_path: Path):
    section = tmp_path / "sectionroot"
    face = section / "character" / "player" / "pl1000" / "pl1050"
    face.mkdir(parents=True)
    (face / "pl1060.mesh.1808312334").write_bytes(b"F")
    assert _find_claire_costume_dir(section) is None


def test_body_folder_wins_over_an_earlier_face_mesh(tmp_path: Path):
    section = tmp_path / "sectionroot"
    player = section / "character" / "player" / "pl1000"
    (player / "pl1050").mkdir(parents=True)
    (player / "pl1004").mkdir()
    (player / "pl1050" / "face.mesh.1808312334").write_bytes(b"F")
    (player / "pl1004" / "body.mesh.1808312334").write_bytes(b"B")
    assert _find_claire_costume_dir(section) == player / "pl1004"


def test_bundle_prefix_skips_a_face_only_package(tmp_path: Path):
    body = (
        tmp_path / "Base" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "pl1000" / "pl1004"
    )
    body.mkdir(parents=True)
    (body / "pl1004.mesh.1808312334").write_bytes(b"B")
    face = (
        tmp_path / "Ears" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "pl1000" / "pl1050"
    )
    face.mkdir(parents=True)
    (face / "pl1060.mesh.1808312334").write_bytes(b"F")
    prefix = _bundle_costume_prefix([
        (SimpleNamespace(root=tmp_path / "Base"), "Base"),
        (SimpleNamespace(root=tmp_path / "Ears"), "Ears"),
    ])
    assert prefix == "SectionRoot/Character/Player/pl1000/pl1004"


def test_color_addon_parks_beside_the_one_costume(tmp_path: Path):
    body = (
        tmp_path / "Base" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "pl1000" / "pl1004"
    )
    body.mkdir(parents=True)
    (body / "pl1004.mesh.1808312334").write_bytes(b"B")
    gold = (
        tmp_path / "Gold" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "wap100"
    )
    gold.mkdir(parents=True)
    (gold / "pl2900_body_albm.tex.10").write_bytes(b"GOLD")
    warnings: list[str] = []
    _park_bundle_addon_textures(tmp_path, warnings)
    parked = body.parents[4]  # Base
    dest = (
        tmp_path / "Gold" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "pl1000" / "pl1004"
        / "pl2900_body_albm.tex.10"
    )
    assert dest.is_file()
    assert dest.read_bytes() == b"GOLD"
    assert not (gold / "pl2900_body_albm.tex.10").exists()
    assert parked.is_dir()
    assert warnings


def test_ears_package_does_not_block_the_gold_textures(tmp_path: Path):
    """pl1810/pl1060 and pl1075 are face and hair, not a second costume."""
    body = (
        tmp_path / "Base" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "pl1000" / "pl1005"
    )
    body.mkdir(parents=True)
    (body / "pl1005.mesh.1808312334").write_bytes(b"B")
    ears_face = (
        tmp_path / "Ears" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "pl1000" / "pl1810"
    )
    ears_face.mkdir(parents=True)
    (ears_face / "pl1060.mesh.1808312334").write_bytes(b"F")
    ears_hair = (
        tmp_path / "Ears" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "pl1000" / "pl1075"
    )
    ears_hair.mkdir(parents=True)
    (ears_hair / "pl1075.mesh.1808312334").write_bytes(b"H")
    gold = (
        tmp_path / "Gold" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "wap100" / "Pl1810" / "mesh"
    )
    gold.mkdir(parents=True)
    (gold / "pl2900_body_albm.tex.34").write_bytes(b"GOLD")
    warnings: list[str] = []
    _park_bundle_addon_textures(tmp_path, warnings)
    dest = (
        tmp_path / "Gold" / "natives" / "x64" / "sectionroot"
        / "character" / "player" / "pl1000" / "pl1005"
        / "pl2900_body_albm.tex.34"
    )
    assert dest.is_file()
    assert dest.read_bytes() == b"GOLD"
    assert not any("more than one costume" in note for note in warnings)


def test_classic_tree_upgrades_when_game_build_is_ray_tracing(tmp_path: Path):
    root = tmp_path / "mod"
    _mod(
        root,
        "natives/x64/sectionroot/character/player/pl1000/pl1000/body.tex.10",
        _classic_tex(),
    )
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    out = tmp_path / "out"
    out.mkdir()
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(source=jacket, target=jacket)],
        out,
        as_folder=True,
        tag_output=False,
        tag_modinfo_description=False,
        tag_build_zip_name=True,
        tag_build_modinfo_description=True,
        game_build="Ray tracing",
    )
    assert report.output_folder is not None
    assert report.output_folder.name.endswith("[RTX]")
    files = [
        p.relative_to(report.output_folder).as_posix()
        for p in report.output_folder.rglob("*") if p.is_file()
    ]
    assert any(n.startswith("natives/stm/") and n.endswith(".tex.34") for n in files)
    assert not any(n.startswith("natives/x64/") and n.endswith(".tex.10") for n in files)
    ini = (report.output_folder / "modinfo.ini").read_text(encoding="utf-8")
    assert "[RTX]" in ini
    assert "[Non-RTX]" not in ini


def test_ray_tracing_tree_comes_down_when_game_build_is_classic(tmp_path: Path):
    root = tmp_path / "mod"
    classic = _classic_tex()
    from re2_outfit_converter.platform.tex_convert import convert_tex_to_rt
    _mod(
        root,
        "natives/stm/sectionroot/character/player/pl1000/pl1000/body.tex.34",
        convert_tex_to_rt(classic),
    )
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    out = tmp_path / "out"
    out.mkdir()
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(source=jacket, target=jacket)],
        out,
        as_folder=True,
        tag_output=False,
        tag_modinfo_description=False,
        game_build="Classic",
    )
    assert report.output_folder is not None
    assert "[Non-RTX]" in report.output_folder.name
    files = [
        p.relative_to(report.output_folder).as_posix()
        for p in report.output_folder.rglob("*") if p.is_file()
    ]
    assert any(n.startswith("natives/x64/") and n.endswith(".tex.10") for n in files)
    assert not any("/stm/" in n for n in files)
