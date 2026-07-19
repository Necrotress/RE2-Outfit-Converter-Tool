"""Tank Top + DLC in-game outfit name MSG writing."""

from pathlib import Path

from re2_outfit_converter import msg_name
from re2_outfit_converter.msg_name import (
    MSG_DIR_DLC,
    MSG_DIR_SYS,
    apply_outfit_display_name,
    read_english_name,
)


def _import_msg(path: Path):
    import sys

    vendor = Path(msg_name.__file__).resolve().parent / "vendor" / "remsg"
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    import REMSGUtil

    return REMSGUtil.importMSG(str(path))


def _english(entry) -> str:
    langs = entry.langs or []
    idx = 1 if len(langs) > 1 else 0
    return (langs[idx] or "").strip()


def test_tanktop_name_patches_sys_msgs(tmp_path: Path):
    ops = apply_outfit_display_name(tmp_path, "tanktop", "Beach Fluff")
    assert any("mes_sys_costume.msg.14" in op for op in ops)
    assert any("mes_sys_reward.msg.14" in op for op in ops)

    costume = tmp_path / MSG_DIR_SYS / "mes_sys_costume.msg.14"
    reward = tmp_path / MSG_DIR_SYS / "mes_sys_reward.msg.14"
    assert costume.is_file() and costume.stat().st_size > 0
    assert reward.is_file() and reward.stat().st_size > 0

    cmsg = _import_msg(costume)
    rmsg = _import_msg(reward)
    assert len(cmsg.entrys) >= 40
    assert len(rmsg.entrys) >= 100

    name = next(e for e in cmsg.entrys if e.name == "Mes_Sys_Costume_Name_01_01")
    figure = next(e for e in rmsg.entrys if e.name == "Mes_Sys_Reward_figure06")
    assert _english(name) == "Beach Fluff"
    assert _english(figure) == "Claire (Beach Fluff)"

    # Jacket stays vanilla so Tank Top renames don't fight Jacket renames
    jacket = next(e for e in cmsg.entrys if e.name == "Mes_Sys_Costume_Name_01_00")
    assert _english(jacket) == "Jacket"


def test_tanktop_name_removes_leftover_clairecos(tmp_path: Path):
    leftover = tmp_path / MSG_DIR_DLC / "mes_sys_clairecos_elza.msg.14"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(b"junk")
    apply_outfit_display_name(tmp_path, "tanktop", "Renamed")
    assert not leftover.exists()


def test_classic_tanktop_name_patches_sys_msgs(tmp_path: Path):
    ops = apply_outfit_display_name(tmp_path, "classic_tanktop", "Retro Tank")
    assert any("mes_sys_costume.msg.14" in op for op in ops)
    assert any("mes_sys_reward.msg.14" in op for op in ops)

    costume = tmp_path / MSG_DIR_SYS / "mes_sys_costume.msg.14"
    reward = tmp_path / MSG_DIR_SYS / "mes_sys_reward.msg.14"
    cmsg = _import_msg(costume)
    rmsg = _import_msg(reward)

    name = next(e for e in cmsg.entrys if e.name == "Mes_Sys_Costume_Name_01_03")
    figure = next(e for e in rmsg.entrys if e.name == "Mes_Sys_Reward_figure08")
    assert _english(name) == "Retro Tank"
    assert _english(figure) == "Claire (Retro Tank)"

    # Other shared slots stay vanilla in the shipped file.
    tank = next(e for e in cmsg.entrys if e.name == "Mes_Sys_Costume_Name_01_01")
    classic_j = next(e for e in cmsg.entrys if e.name == "Mes_Sys_Costume_Name_01_02")
    jacket = next(e for e in cmsg.entrys if e.name == "Mes_Sys_Costume_Name_01_00")
    assert _english(tank) == "Tank Top"
    assert _english(classic_j) == "Classic Jacket"
    assert _english(jacket) == "Jacket"


def test_name_stem_coverage():
    from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY

    assert CLAIRE_OUTFIT_BY_KEY["jacket"].msg_stem is None
    assert CLAIRE_OUTFIT_BY_KEY["classic_jacket"].msg_stem is None
    assert CLAIRE_OUTFIT_BY_KEY["tanktop"].msg_stem == "tanktop"
    assert CLAIRE_OUTFIT_BY_KEY["classic_tanktop"].msg_stem == "classic_tanktop"
    assert CLAIRE_OUTFIT_BY_KEY["98"].msg_stem == "original"


def test_elza_clairecos_still_works(tmp_path: Path):
    ops = apply_outfit_display_name(tmp_path, "elza", "Custom Elza")
    dest = tmp_path / MSG_DIR_DLC / "mes_sys_clairecos_elza.msg.14"
    assert dest.is_file()
    assert any("mes_sys_clairecos_elza.msg.14" in op for op in ops)
    assert read_english_name(dest) == "Custom Elza"


def test_98_original_clairecos_works(tmp_path: Path):
    ops = apply_outfit_display_name(tmp_path, "original", "Retro Claire")
    dest = tmp_path / MSG_DIR_DLC / "mes_sys_clairecos_original.msg.14"
    assert dest.is_file()
    assert any("mes_sys_clairecos_original.msg.14" in op for op in ops)
    assert read_english_name(dest) == "Retro Claire"
    msg = _import_msg(dest)
    figure = next(e for e in msg.entrys if (e.name or "").endswith("_Figure"))
    assert _english(figure) == "Claire (Retro Claire)"
    assert figure.name == "Mes_Sys_ClaireCos_Original_Figure"
