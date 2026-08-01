"""Shared Claire / Leon costume name pack (mes_sys MSG files)."""

from pathlib import Path
import zipfile

import pytest

from re2_outfit_converter import msg_name
from re2_outfit_converter.msg_name import (
    MSG_DIR_SYS,
    SHARED_COSTUME_NAME_VANILLA,
    resolve_shared_costume_names,
    write_shared_costume_names,
)
from re2_outfit_converter.name_pack import (
    build_costume_name_pack,
    name_pack_description,
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


def test_resolve_requires_one_real_edit():
    with pytest.raises(ValueError, match="at least one"):
        resolve_shared_costume_names({})
    with pytest.raises(ValueError, match="at least one"):
        resolve_shared_costume_names(dict(SHARED_COSTUME_NAME_VANILLA))

    resolved = resolve_shared_costume_names({"tanktop": "Beach Fluff"})
    assert resolved["tanktop"] == "Beach Fluff"
    assert resolved["jacket"] == "Jacket"
    assert resolved["leon_casual"] == "Casual"


def test_write_shared_includes_claire_and_leon(tmp_path: Path):
    names = resolve_shared_costume_names({
        "jacket": "Bare Essentials",
        "leon_casual": "Streetwear",
        "leon_police_injured": "Hurt Cop",
    })
    write_shared_costume_names(tmp_path, names)
    costume = tmp_path / MSG_DIR_SYS / "mes_sys_costume.msg.14"
    reward = tmp_path / MSG_DIR_SYS / "mes_sys_reward.msg.14"
    cmsg = _import_msg(costume)
    rmsg = _import_msg(reward)

    assert _english(next(
        e for e in cmsg.entrys if e.name == "Mes_Sys_Costume_Name_01_00"
    )) == "Bare Essentials"
    assert _english(next(
        e for e in cmsg.entrys if e.name == "Mes_Sys_Costume_Name_00_00"
    )) == "Streetwear"
    assert _english(next(
        e for e in cmsg.entrys if e.name == "Mes_Sys_Costume_Name_00_02"
    )) == "Hurt Cop"
    # Injured has no figure row — Casual figure updated.
    assert _english(next(
        e for e in rmsg.entrys if e.name == "Mes_Sys_Reward_figure00"
    )) == "Leon (Streetwear)"
    assert _english(next(
        e for e in rmsg.entrys if e.name == "Mes_Sys_Reward_figure05"
    )) == "Claire (Bare Essentials)"


def test_build_costume_name_pack_zip(tmp_path: Path):
    out = build_costume_name_pack(
        tmp_path, {
            "classic_jacket": "Old School",
            "leon_police": "Rookie",
        })
    assert out.is_file() and out.suffix == ".zip"
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert "modinfo.ini" in names
        assert f"{MSG_DIR_SYS}/mes_sys_costume.msg.14" in names
        assert f"{MSG_DIR_SYS}/mes_sys_reward.msg.14" in names
        info = zf.read("modinfo.ini").decode("utf-8")
    assert "Name=Costume Name Pack" in info
    desc = name_pack_description(
        resolve_shared_costume_names({
            "classic_jacket": "Old School",
            "leon_police": "Rookie",
        }))
    assert desc.startswith("Costume menu names:")
    assert "Claire:" in desc
    assert "[Classic Jacket] -> Old School" in desc
    assert "Leon:" in desc
    assert "[Police] -> Rookie" in desc
    assert "[Jacket]" not in desc
    assert "\\n" in desc
