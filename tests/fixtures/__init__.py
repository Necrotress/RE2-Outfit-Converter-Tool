"""Synthetic Fluffy mod trees for end-to-end conversion tests."""

from __future__ import annotations

from pathlib import Path

from re2_outfit_converter.msg_name import MSG_DIR_DLC, write_outfit_name, _template_path
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR

PARTS = PARTS_DIR
MESH = MESH_ROOTS[0]
UI_ROOT = "natives/x64/sectionroot/ui/ui0600"
HOLDER_DIR = "natives/x64/objectroot/scene/contents/extra"


def _u16(s: str) -> bytes:
    return s.encode("utf-16-le")


def elza_contentsholder_bytes() -> bytes:
    strings = [
        "Costume_E",
        "DLC_E",
        "Extra_Costume_E",
        "DLC_Costume_E",
        "ObjectRoot/Prefab/Character/Survivor/Parts/pl1000/pl1000_body_costume_c.pfb",
        "SectionRoot/Message/Mes_Other_DLC/Mes_Sys_ClaireCos_Elza.msg",
        "SectionRoot/UI/ui0600/Prefab/ui0601_01_08.pfb",
    ]
    return b"SCN\x00" + b"\x00\x00".join(_u16(s) for s in strings)


def write_modinfo(root: Path, **fields: str) -> None:
    lines = [f"{k}={v}" for k, v in fields.items()]
    (root / "modinfo.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plant_engine_path_binary(
    root: Path,
    rel: str,
    engine_path: str,
) -> Path:
    """Write a tiny patchable binary containing an engine path (ASCII + UTF-16)."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    ascii_p = engine_path.encode("ascii")
    u16_p = _u16(engine_path)
    path.write_bytes(b"BIN\x00" + ascii_p + b"\x00" + u16_p + b"\x00END")
    return path


def build_elza_full(tmp_path: Path, name: str = "E2E Elza Full") -> Path:
    """Elza PFBs + body mesh + face/hair + UI + MSG + contentsholder + plant binary."""
    root = tmp_path / "elza_full"
    parts = root / PARTS
    parts.mkdir(parents=True)
    (parts / "pl1000_body_costume_c.pfb.16").write_bytes(b"body")
    (parts / "pl1000_face_costume_c.pfb.16").write_bytes(b"face")
    (parts / "pl1000_hair_costume_c.pfb.16").write_bytes(b"hair")

    mesh = root / MESH
    for pid, payload in (
        ("pl1004", b"body"),
        ("pl1050", b"face"),
        ("pl1070", b"hair"),
    ):
        (mesh / pid).mkdir(parents=True)
        (mesh / pid / f"{pid}.mdf2.10").write_bytes(payload + b"-mdf")
        (mesh / pid / f"{pid}.mesh.1").write_bytes(payload + b"-mesh")

    msg_dir = root / MSG_DIR_DLC
    msg_dir.mkdir(parents=True)
    write_outfit_name(
        _template_path("elza"),
        msg_dir / "mes_sys_clairecos_elza.msg.14",
        "E2E Rich Girl",
        "elza",
    )

    ui = root / UI_ROOT
    (ui / "prefab").mkdir(parents=True)
    (ui / "tex").mkdir(parents=True)
    ui_raw = _u16("ui0601_01_08")
    (ui / "prefab" / "ui0601_01_08.pfb.16").write_bytes(b"PFB" + ui_raw)
    (ui / "tex" / "ui0601_01_08_iam.tex.10").write_bytes(b"tex")
    (ui / "tex" / "ui0601_01_08.uvs.7").write_bytes(b"uvs")

    holder = root / HOLDER_DIR
    holder.mkdir(parents=True)
    (holder / "contentsholder_dlc_costume_e.scn.19").write_bytes(
        elza_contentsholder_bytes()
    )

    # Same-length path that convert Elza→Noir remaps (pl1004 → pl1005).
    plant_engine_path_binary(
        root,
        "natives/x64/objectroot/prefab/character/survivor/parts/pl1000/"
        "ref_pl1004.mdf2.10",
        "sectionroot/character/player/pl1000/pl1004/pl1004.mdf2",
    )

    write_modinfo(root, Name=name, Description="E2E fixture")
    return root


def build_nurse_style(tmp_path: Path, name: str = "E2E Nurse") -> Path:
    """Elza PFBs + stub pl1004 + custom body under pl1000/pl1008."""
    root = tmp_path / "nurse_style"
    parts = root / PARTS
    parts.mkdir(parents=True)
    (parts / "pl1000_body_costume_c.pfb.16").write_bytes(
        b"PFB" + _u16("sectionroot/character/player/pl1000/pl1008/pl1008.mdf2")
    )
    (parts / "pl1000_face_costume_c.pfb.16").write_bytes(b"face")
    (parts / "pl1000_hair_costume_c.pfb.16").write_bytes(b"hair")

    mesh = root / MESH
    (mesh / "pl1004").mkdir(parents=True)
    (mesh / "pl1004" / "pl1004.mdf2.10").write_bytes(b"elza-mdf")
    (mesh / "pl1004" / "pl1004.mesh.1").write_bytes(b"elza-mesh")
    (mesh / "pl1000").mkdir(parents=True)
    (mesh / "pl1000" / "pl1008.mdf2.10").write_bytes(b"custom-mdf")
    (mesh / "pl1000" / "pl1008.mesh.1").write_bytes(b"custom-mesh")

    ui = root / UI_ROOT
    (ui / "prefab").mkdir(parents=True)
    (ui / "tex").mkdir(parents=True)
    (ui / "prefab" / "ui0601_01_08.pfb.16").write_bytes(b"uipfb")
    (ui / "tex" / "ui0601_01_08_iam.tex.10").write_bytes(b"uitex")

    write_modinfo(root, Name=name, Description="Nurse-style redirect")
    return root


def build_face_addon(tmp_path: Path, name: str = "E2E Face Addon") -> Path:
    root = tmp_path / "face_addon"
    face = root / MESH / "pl1050"
    face.mkdir(parents=True)
    (face / "pl1050.mesh.1").write_bytes(b"face-mesh")
    write_modinfo(root, name=name, version="1.0", description="Face addon")
    return root


def build_elza_main(tmp_path: Path, name: str = "E2E Main Elza") -> Path:
    root = tmp_path / "elza_main"
    parts = root / PARTS
    parts.mkdir(parents=True)
    (parts / "pl1000_body_costume_c.pfb.16").write_bytes(b"pfb")
    body = root / MESH / "pl1004"
    body.mkdir(parents=True)
    (body / "pl1004.mesh.1").write_bytes(b"mesh")
    write_modinfo(root, name=name, version="1.0")
    return root
