from __future__ import annotations

from pathlib import Path

from re2_outfit_converter.platform.formats import (
    classic_suffix_for,
    is_rt_suffix,
    parse_versioned_name,
    patchable,
    platform_from_rel,
    remap_rel_to_classic,
    remap_rel_to_rt,
)


def test_parse_versioned_name():
    p = parse_versioned_name("pl3000.mesh.2109108288")
    assert p is not None
    assert p.kind == "mesh"
    assert p.suffix == "mesh.2109108288"
    assert is_rt_suffix(p.suffix)
    assert classic_suffix_for(p.suffix) == "mesh.1808312334"


def test_remap_rel():
    rel = "natives/STM/Sectionroot/Character/Player/Pl3000/pl3000/Dress.tex.34"
    out = remap_rel_to_classic(rel)
    assert out.lower().startswith("natives/x64/")
    assert out.endswith("Dress.tex.10")


def test_remap_rel_to_rt():
    rel = "natives/x64/Sectionroot/Character/Player/Pl3000/Dress.tex.10"
    out = remap_rel_to_rt(rel)
    assert out.lower().startswith("natives/stm/")
    assert out.endswith("Dress.tex.34")


def test_mmtr_suffix_is_not_remapped():
    rel = "natives/stm/a/mat.mmtr.2109101635"
    assert remap_rel_to_classic(rel).endswith("mat.mmtr.2109101635")


def test_msg_suffix_follows_platform():
    classic = "natives/x64/sectionroot/message/mes_sys/mes_sys_costume.msg.14"
    rt = remap_rel_to_rt(classic)
    assert rt == (
        "natives/stm/sectionroot/message/mes_sys/mes_sys_costume.msg.50397457"
    )
    assert remap_rel_to_classic(rt) == classic


def test_versioned_user_is_patchable():
    assert patchable("a.user.2")
    assert patchable("a.scn.20")
    assert parse_versioned_name("a.user.2") is not None


def test_platform_from_rel():
    assert platform_from_rel("natives/stm/foo.tex.34") == "stm"
    assert platform_from_rel("natives/x64/foo.tex.10") == "x64"
    assert platform_from_rel("modinfo.ini") is None


def test_move_tree_rewrites_msg_for_current_rt(tmp_path: Path):
    from re2_outfit_converter.msg_name import apply_outfit_display_name, import_msg
    from re2_outfit_converter.platform.formats import MSG_VERSION_RT
    from re2_outfit_converter.platform.path_remap import (
        move_tree_to_classic,
        move_tree_to_rt,
    )
    from re2_outfit_converter.platform.reports import ConversionReport

    apply_outfit_display_name(tmp_path, "military", "ELITE Xpecial Ops")
    src = (
        tmp_path / "natives" / "x64" / "sectionroot" / "message"
        / "mes_other_dlc" / "mes_sys_clairecos_military.msg.14"
    )
    assert src.is_file()
    move_tree_to_rt(tmp_path, ConversionReport())
    dest = (
        tmp_path / "natives" / "stm" / "sectionroot" / "message"
        / "mes_other_dlc" / "mes_sys_clairecos_military.msg.50397457"
    )
    assert dest.is_file()
    assert not src.exists()
    msg = import_msg(dest)
    assert msg.version == MSG_VERSION_RT
    assert len(msg.languages) == 33
    assert msg.entrys[0].langs[1] == "ELITE Xpecial Ops"

    move_tree_to_classic(tmp_path, ConversionReport())
    assert src.is_file()
    assert not dest.exists()
    classic = import_msg(src)
    assert classic.version == 14
    assert classic.entrys[0].langs[1] == "ELITE Xpecial Ops"
