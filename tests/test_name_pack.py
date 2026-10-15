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
    PACK_TITLE,
    build_costume_name_pack,
    find_existing_name_pack,
    name_pack_description,
    name_pack_game_build,
    read_name_pack_fields,
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


def test_build_costume_name_pack_folder(tmp_path: Path):
    out = build_costume_name_pack(
        tmp_path, {
            "classic_jacket": "Old School",
            "leon_police": "Rookie",
        })
    assert out.is_dir()
    assert out.name == "Costume Name Pack"
    assert (out / "modinfo.ini").is_file()
    assert (out / MSG_DIR_SYS / "mes_sys_costume.msg.14").is_file()
    assert (out / MSG_DIR_SYS / "mes_sys_reward.msg.14").is_file()
    info = (out / "modinfo.ini").read_text(encoding="utf-8")
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


def test_find_and_read_existing_name_pack(tmp_path: Path):
    out = build_costume_name_pack(
        tmp_path, {
            "jacket": "Bare Essentials",
            "leon_casual": "Streetwear",
        })
    found = find_existing_name_pack(tmp_path)
    assert found == out
    fields = read_name_pack_fields(found)
    assert fields["jacket"] == "Bare Essentials"
    assert fields["leon_casual"] == "Streetwear"
    assert fields["tanktop"] == ""
    assert fields["leon_police"] == ""


def test_overwrite_keeps_the_same_folder(tmp_path: Path):
    first = build_costume_name_pack(tmp_path, {"jacket": "First Name"})
    marker = first / "screenshot.png"
    marker.write_bytes(b"PNG")
    second = build_costume_name_pack(
        tmp_path, {"jacket": "Second Name"}, dest=first)
    assert second == first
    assert [path.name for path in tmp_path.iterdir()] == ["Costume Name Pack"]
    assert marker.read_bytes() == b"PNG"
    fields = read_name_pack_fields(second)
    assert fields["jacket"] == "Second Name"
    info = (second / "modinfo.ini").read_text(encoding="utf-8")
    assert "Name=Costume Name Pack" in info
    assert "[Jacket] -> Second Name" in info
    assert "First Name" not in info


def test_save_removes_old_zip_packs(tmp_path: Path):
    def _zip(path: Path, title: str) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("modinfo.ini", f"Name={title}\n")
            zf.writestr(f"{MSG_DIR_SYS}/mes_sys_costume.msg.14", b"x")

    old = tmp_path / "Costume Name Pack.zip"
    numbered = tmp_path / "Costume Name Pack (2).zip"
    other = tmp_path / "Some Outfit [Noir].zip"
    _zip(old, "Costume Name Pack")
    _zip(numbered, "Costume Name Pack")
    _zip(other, "Some Outfit")
    out = build_costume_name_pack(
        tmp_path, {"jacket": "Bare Essentials"}, dest=old)
    assert out.is_dir()
    assert out.name == "Costume Name Pack"
    assert not old.exists()
    assert not numbered.exists()
    assert other.is_file()
    assert read_name_pack_fields(out)["jacket"] == "Bare Essentials"


def test_find_prefers_folder_over_zip(tmp_path: Path):
    folder = build_costume_name_pack(tmp_path, {"jacket": "Canonical"})
    zpath = tmp_path / "Costume Name Pack.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("modinfo.ini", "Name=Costume Name Pack\n")
        zf.writestr(f"{MSG_DIR_SYS}/mes_sys_costume.msg.14", b"x")
    zpath.touch()
    assert find_existing_name_pack(tmp_path) == folder


def test_find_ignores_unrelated_zip(tmp_path: Path):
    other = tmp_path / "Some Outfit [Noir].zip"
    with zipfile.ZipFile(other, "w") as zf:
        zf.writestr("modinfo.ini", "Name=Some Outfit\n")
        zf.writestr(f"{MSG_DIR_SYS}/mes_sys_costume.msg.14", b"not-a-msg")
    assert find_existing_name_pack(tmp_path) is None


def test_find_name_pack_with_bom_and_spaced_name(tmp_path: Path):
    zpath = tmp_path / "Costume Name Pack.zip"
    ini = "\ufeffName = Costume Name Pack\nDescription=Hi\n"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("modinfo.ini", ini.encode("utf-8-sig"))
        zf.writestr(f"{MSG_DIR_SYS}/mes_sys_costume.msg.14", b"x")
    assert find_existing_name_pack(tmp_path) == zpath


def test_apply_col_tag_replaces_leading_tag():
    from re2_outfit_converter.gui_name_pack import apply_col_tag, preview_hex_for_name

    assert apply_col_tag("Jacket", "FF4040") == "<COLOR FF4040>Jacket</COLOR>"
    assert apply_col_tag("<COL BLUE>Jacket", "FF4040") == "<COLOR FF4040>Jacket</COLOR>"
    assert apply_col_tag("<COL PINK>Tank", "FF7EB3") == "<COLOR FF7EB3>Tank</COLOR>"
    assert apply_col_tag("<COLOR FFFF80>Name</COLOR>", "F2F2F2") == "<COLOR F2F2F2>Name</COLOR>"
    assert apply_col_tag("", "FFFFFF") == "<COLOR FFFFFF>"
    assert preview_hex_for_name("<COL RED>Jacket") == "#ff4040"
    assert preview_hex_for_name("<COLOR FF4040>Jacket</COLOR>") == "#ff4040"
    assert preview_hex_for_name("<COLOR FFFF80>Name</COLOR>") == "#ffff80"
    assert preview_hex_for_name("Jacket") is None


def test_read_folder_name_pack(tmp_path: Path):
    folder = build_costume_name_pack(
        tmp_path, {"leon_police": "Rookie"}, as_folder=True)
    assert folder.is_dir()
    assert find_existing_name_pack(tmp_path) == folder
    fields = read_name_pack_fields(folder)
    assert fields["leon_police"] == "Rookie"
    updated = build_costume_name_pack(
        tmp_path, {"leon_police": "Veteran"}, dest=folder)
    assert updated == folder
    assert read_name_pack_fields(folder)["leon_police"] == "Veteran"


def test_ray_tracing_name_pack_uses_current_msg(tmp_path: Path):
    out = build_costume_name_pack(
        tmp_path, {"jacket": "Bare Essentials"}, game_build="Ray tracing")
    rel = (
        out / "natives" / "stm" / "sectionroot" / "message"
        / "mes_sys" / "mes_sys_costume.msg.50397457"
    )
    reward = rel.with_name("mes_sys_reward.msg.50397457")
    assert rel.is_file()
    assert reward.is_file()
    assert not (out / "natives" / "x64").exists()
    data = rel.read_bytes()
    assert int.from_bytes(data[:4], "little") == 50397457
    assert name_pack_game_build(out) == "Ray tracing"
    fields = read_name_pack_fields(out)
    assert fields["jacket"] == "Bare Essentials"
    assert fields["tanktop"] == ""


def test_switching_build_replaces_message_tree(tmp_path: Path):
    folder = build_costume_name_pack(
        tmp_path, {"jacket": "Bare Essentials"}, as_folder=True)
    updated = build_costume_name_pack(
        tmp_path, {"jacket": "Bare Essentials"},
        dest=folder, game_build="Ray tracing")
    assert updated == folder
    assert name_pack_game_build(folder) == "Ray tracing"
    assert not (folder / "natives" / "x64").exists()
    msg = (
        folder / "natives" / "stm" / "sectionroot" / "message"
        / "mes_sys" / "mes_sys_costume.msg.50397457"
    )
    assert int.from_bytes(msg.read_bytes()[:4], "little") == 50397457
    assert read_name_pack_fields(folder)["jacket"] == "Bare Essentials"


def test_read_shared_costume_names_roundtrip(tmp_path: Path):
    names = resolve_shared_costume_names({"classic_tanktop": "Beach"})
    write_shared_costume_names(tmp_path, names)
    costume = tmp_path / MSG_DIR_SYS / "mes_sys_costume.msg.14"
    read_back = msg_name.read_shared_costume_names(costume)
    assert read_back["classic_tanktop"] == "Beach"
    assert read_back["jacket"] == "Jacket"
    assert PACK_TITLE == "Costume Name Pack"
