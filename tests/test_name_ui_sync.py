"""Costume name + preview cleanup/retarget on convert."""

from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.converter import convert
from re2_outfit_converter.msg_name import (
    MSG_DIR_DLC,
    read_english_name,
    write_outfit_name,
    _template_path,
)
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR


def _u16(s: str) -> bytes:
    return s.encode("utf-16-le")


def _elza_contentsholder_bytes() -> bytes:
    """Minimal holder mirroring Nurse Claire / Rich Girl Elza DLC register."""
    strings = [
        "Costume_E",
        "DLC_E",
        "Extra_Costume_E",
        "DLC_Costume_E",
        "ObjectRoot/Prefab/Character/Survivor/Parts/pl1000/pl1000_body_costume_c.pfb",
        "SectionRoot/Message/Mes_Other_DLC/Mes_Sys_ClaireCos_Elza.msg",
        "SectionRoot/UI/ui0600/Prefab/ui0601_01_08.pfb",
        "assets:/SectionRoot/UserData/Costume/pl1000Costume_CostumeC.user.json",
    ]
    return b"SCN\x00" + b"\x00\x00".join(_u16(s) for s in strings)


def _rich_girl_shaped(tmp_path: Path) -> Path:
    """Minimal Elza mod with custom name + costume preview (Rich Girl style)."""
    root = tmp_path / "RichGirl"
    parts = root / PARTS_DIR
    parts.mkdir(parents=True)
    (parts / "pl1000_body_costume_c.pfb.16").write_bytes(b"body")
    (parts / "pl1000_face_costume_c.pfb.16").write_bytes(b"face")
    mesh = root / MESH_ROOTS[0]
    (mesh / "pl1004").mkdir(parents=True)
    (mesh / "pl1004" / "pl1004.mdf2.10").write_bytes(b"mdf")
    (mesh / "pl1004" / "pl1004.mesh.1").write_bytes(b"mesh")

    msg_dir = root / MSG_DIR_DLC
    msg_dir.mkdir(parents=True)
    write_outfit_name(
        _template_path("elza"),
        msg_dir / "mes_sys_clairecos_elza.msg.14",
        "Rich Girl",
        "elza",
    )

    ui = root / "natives/x64/sectionroot/ui/ui0600"
    (ui / "prefab").mkdir(parents=True)
    (ui / "tex").mkdir(parents=True)
    ui_name = "ui0601_01_08"
    ui_raw = _u16(ui_name)
    (ui / "prefab" / "ui0601_01_08.pfb.16").write_bytes(b"PFB" + ui_raw)
    (ui / "tex" / "ui0601_01_08_iam.tex.10").write_bytes(b"tex")
    (ui / "tex" / "ui0601_01_08.uvs.7").write_bytes(b"uvs")

    holder_dir = root / "natives/x64/objectroot/scene/contents/extra"
    holder_dir.mkdir(parents=True)
    (holder_dir / "contentsholder_dlc_costume_e.scn.19").write_bytes(
        _elza_contentsholder_bytes()
    )

    (root / "modinfo.ini").write_text("Name=Rich Girl\n", encoding="utf-8")
    return root


def test_elza_to_jacket_strips_name_and_remaps_preview(tmp_path: Path):
    root = _rich_girl_shaped(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    report = convert(
        analyze(root),
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["jacket"],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="JacketOut",
    )
    folder = report.output_folder
    assert folder is not None
    assert not list(folder.rglob("mes_sys_clairecos_*"))
    assert not list(folder.rglob("ui0601_01_08*"))
    assert list(folder.rglob("ui0601_01_00_iam.tex*"))
    ui_pfb = next(folder.rglob("ui0601_01_00.pfb*"))
    assert "ui0601_01_00".encode("utf-16-le") in ui_pfb.read_bytes()


def test_elza_to_noir_retargets_name_and_preview(tmp_path: Path):
    root = _rich_girl_shaped(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    report = convert(
        analyze(root),
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="NoirOut",
    )
    folder = report.output_folder
    assert folder is not None
    msg = folder / MSG_DIR_DLC / "mes_sys_clairecos_noir.msg.14"
    assert msg.is_file()
    assert read_english_name(msg) == "Rich Girl"
    assert not list(folder.rglob("mes_sys_clairecos_elza*"))
    assert list(folder.rglob("ui0601_01_07_iam.tex*"))
    assert not list(folder.rglob("ui0601_01_08*"))
    # Contentsholder cannot be safely retargeted — strip so Elza doesn't keep
    # the preview and Noir's vanilla DLC register isn't overridden.
    assert not list(folder.rglob("contentsholder_dlc*"))


def test_elza_to_jacket_removes_dlc_contentsholder(tmp_path: Path):
    root = _rich_girl_shaped(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    report = convert(
        analyze(root),
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["jacket"],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="JacketHolder",
    )
    folder = report.output_folder
    assert folder is not None
    assert not list(folder.rglob("contentsholder_dlc*"))


def test_elza_to_classic_stashes_preview(tmp_path: Path):
    root = _rich_girl_shaped(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    report = convert(
        analyze(root),
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["classic_jacket"],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="ClassicOut",
    )
    folder = report.output_folder
    assert folder is not None
    assert not list(folder.rglob("mes_sys_clairecos_*"))
    stash = list(folder.rglob("_re2oc_ui_stash/ui0601_01_08*"))
    assert stash
    # Not left on Classic ui id 01 or live Elza 08 paths outside stash.
    live_08 = [
        p for p in folder.rglob("ui0601_01_08*")
        if "_re2oc_ui_stash" not in p.as_posix().replace("\\", "/")
    ]
    assert not live_08
    assert not list(folder.rglob("ui0601_01_01*"))


def test_classic_stash_restores_to_elza(tmp_path: Path):
    root = _rich_girl_shaped(tmp_path)
    mid = tmp_path / "mid"
    mid.mkdir()
    classic = convert(
        analyze(root),
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["classic_jacket"],
        mid,
        tag_output=False,
        as_folder=True,
        folder_name="ClassicMid",
    ).output_folder
    assert classic is not None

    out = tmp_path / "out"
    out.mkdir()
    report = convert(
        analyze(classic),
        CLAIRE_OUTFIT_BY_KEY["classic_jacket"],
        CLAIRE_OUTFIT_BY_KEY["elza"],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="ElzaBack",
    )
    folder = report.output_folder
    assert folder is not None
    assert list(folder.rglob("ui0601_01_08_iam.tex*"))
    assert not list(folder.rglob("_re2oc_ui_stash/**"))
