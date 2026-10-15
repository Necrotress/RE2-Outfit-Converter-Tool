"""Multi-slot From focus and per-target in-game name helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.converter import convert_with_ops
from re2_outfit_converter.msg_name import (
    MSG_DIR_DLC,
    read_english_name,
    write_outfit_name,
    _template_path,
)
from re2_outfit_converter.name_ui import (
    active_convert_name_target,
    collect_display_names_by_target,
    from_checkbox_label,
    other_namable_hint,
)
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY

from tests.fixtures import MESH, PARTS, write_modinfo


def test_from_checkbox_label_focus_and_incomplete():
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    assert from_checkbox_label(
        jacket, incomplete=False, focused=True, base_label="Jacket",
    ) == "▸ Jacket"
    assert from_checkbox_label(
        jacket, incomplete=True, focused=True, base_label="Jacket",
    ) == "▸ ⚠ Jacket"
    assert from_checkbox_label(
        jacket, incomplete=True, focused=False, base_label="Jacket",
    ) == "⚠ Jacket"


def test_active_convert_name_target_classic_vs_noir():
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    classic = CLAIRE_OUTFIT_BY_KEY["classic_jacket"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]

    def resolve(choice: str):
        for o in (classic, noir, tank):
            if o.name in choice or o.key in choice.lower():
                return o
        if "Classic" in choice:
            return classic
        if "Noir" in choice:
            return noir
        if "Tank" in choice:
            return tank
        return None

    assert active_convert_name_target(
        jacket, "Classic (Jacket)", resolve_target=lambda c: classic,
    ) is None
    assert active_convert_name_target(
        jacket, "Tank Top", resolve_target=lambda c: tank,
    ) is None
    assert active_convert_name_target(
        jacket, "Noir", resolve_target=lambda c: noir,
    ) is noir
    assert active_convert_name_target(
        jacket, "Delete 🗑", resolve_target=lambda c: None,
    ) is None


def test_other_namable_hint():
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    classic = CLAIRE_OUTFIT_BY_KEY["classic_jacket"]

    def choice_for(o):
        return "Classic" if o.key == "jacket" else "Noir"

    def resolve(choice: str):
        return classic if "Classic" in choice else noir

    hint = other_namable_hint(
        [jacket, tank],
        choice_for=choice_for,
        resolve_target=resolve,
        skip_key="jacket",
    )
    assert hint is not None
    assert "Tank Top" in hint
    assert "Noir" in hint


def test_collect_display_names_by_target():
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]
    classic = CLAIRE_OUTFIT_BY_KEY["classic_jacket"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    ops = [
        OutfitOp(source=jacket, target=classic),
        OutfitOp(source=tank, target=noir),
    ]
    names = collect_display_names_by_target(
        ops, {"jacket": "Ignored", "tanktop": "Beach Noir"})
    assert names == {"noir": "Beach Noir"}


def _dual_slot_mod(tmp_path: Path) -> Path:
    root = tmp_path / "dual"
    parts = root / PARTS
    parts.mkdir(parents=True)
    (parts / "pl1000_body_default.pfb.16").write_bytes(b"j")
    (parts / "pl1000_body_costume_3.pfb.16").write_bytes(b"t")
    mesh = root / MESH
    for pid in ("pl1000", "pl1001"):
        d = mesh / pid
        d.mkdir(parents=True)
        (d / f"{pid}.mesh.1").write_bytes(b"m")
        (d / f"{pid}.mdf2.10").write_bytes(b"d")
    msg = root / MSG_DIR_DLC
    msg.mkdir(parents=True)
    write_outfit_name(
        _template_path("elza"),
        msg / "mes_sys_clairecos_elza.msg.14",
        "Source Name",
        "elza",
    )
    write_modinfo(root, Name="Dual Slot")
    return root


def test_convert_to_tanktop_strips_shared_name_msgs(tmp_path: Path):
    """Convert must not ship shared costume MSG renames (use name pack)."""
    from re2_outfit_converter.msg_name import MSG_DIR_SYS
    from re2_outfit_converter.reports import ConversionError

    root = _dual_slot_mod(tmp_path)
    out = tmp_path / "out_tank"
    out.mkdir()
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]

    with pytest.raises(ConversionError, match="Costume names"):
        convert_with_ops(
            analyze(root),
            [OutfitOp(source=jacket, target=tank)],
            out,
            as_folder=True,
            folder_name="ToTankNamed",
            tag_output=False,
            write_log=False,
            outfit_display_name="ShouldNotWrite",
        )

    report = convert_with_ops(
        analyze(root),
        [OutfitOp(source=jacket, target=tank)],
        out,
        as_folder=True,
        folder_name="ToTank",
        tag_output=False,
        write_log=False,
    )
    folder = report.output_folder
    assert folder is not None
    assert not (folder / MSG_DIR_SYS / "mes_sys_costume.msg.14").exists()
    assert not (folder / MSG_DIR_SYS / "mes_sys_reward.msg.14").exists()


def test_convert_per_target_name_noir_only(tmp_path: Path):
    root = _dual_slot_mod(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]
    classic = CLAIRE_OUTFIT_BY_KEY["classic_jacket"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    report = convert_with_ops(
        analyze(root),
        [
            OutfitOp(source=jacket, target=classic),
            OutfitOp(source=tank, target=noir),
        ],
        out,
        as_folder=True,
        folder_name="DualNamed",
        tag_output=False,
        write_log=False,
        outfit_display_names={"noir": "Named Noir"},
    )
    folder = report.output_folder
    assert folder is not None
    noir_msg = folder / MSG_DIR_DLC / "mes_sys_clairecos_noir.msg.14"
    assert noir_msg.is_file()
    assert read_english_name(noir_msg) == "Named Noir"


def _elza_root(tmp_path: Path, platform: str, mesh_suffix: str) -> Path:
    root = tmp_path / f"elza_{platform}"
    body = (
        root / "natives" / platform / "sectionroot" / "character"
        / "player" / "pl1000" / "pl1004"
    )
    body.mkdir(parents=True)
    (body / f"pl1004.mesh.{mesh_suffix}").write_bytes(b"mesh")
    write_modinfo(root, Name="Elza Same Slot")
    return root


def test_same_slot_ray_tracing_writes_the_colored_name(tmp_path, monkeypatch):
    """Elza → Elza on ray tracing skips outfit stages but still ships the name."""
    from re2_outfit_converter.platform.path_remap import move_tree_to_rt
    from re2_outfit_converter.platform.reports import ConversionReport as Plat

    def _upgrade(staging, **_kwargs):
        plat = Plat()
        move_tree_to_rt(staging, plat)
        return plat

    monkeypatch.setattr("re2_outfit_converter.converter.upgrade_to_rt", _upgrade)
    root = _elza_root(tmp_path, "x64", "1808312334")
    out = tmp_path / "out"
    out.mkdir()
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    colored = "<COLOR FF7EB3>Bunny Boom</COLOR>"
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(source=elza, target=elza)],
        out,
        as_folder=True,
        folder_name="ElzaNamed",
        tag_output=False,
        write_log=False,
        game_build="Ray tracing",
        outfit_display_names={"elza": colored},
    )
    folder = report.output_folder
    assert folder is not None
    msg = (
        folder / "natives" / "stm" / "sectionroot" / "message"
        / "mes_other_dlc" / "mes_sys_clairecos_elza.msg.50397457"
    )
    assert msg.is_file()
    assert int.from_bytes(msg.read_bytes()[:4], "little") == 50397457
    assert read_english_name(msg) == colored


def test_same_slot_classic_name_stays_on_x64(tmp_path, monkeypatch):
    """A typed name must not move an RT→Classic same-slot pack back to stm."""
    from re2_outfit_converter.platform.path_remap import move_tree_to_classic
    from re2_outfit_converter.platform.reports import ConversionReport as Plat

    def _prepare(staging, **_kwargs):
        plat = Plat()
        move_tree_to_classic(staging, plat)
        return plat

    monkeypatch.setattr(
        "re2_outfit_converter.converter.prepare_classic", _prepare)
    root = _elza_root(tmp_path, "stm", "2109108288")
    out = tmp_path / "out_classic"
    out.mkdir()
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(source=elza, target=elza)],
        out,
        as_folder=True,
        folder_name="ElzaClassic",
        tag_output=False,
        write_log=False,
        game_build="Classic",
        outfit_display_names={"elza": "Walker"},
    )
    folder = report.output_folder
    assert folder is not None
    assert (
        folder / "natives" / "x64" / "sectionroot" / "character"
        / "player" / "pl1000" / "pl1004" / "pl1004.mesh.1808312334"
    ).is_file()
    msg = (
        folder / "natives" / "x64" / "sectionroot" / "message"
        / "mes_other_dlc" / "mes_sys_clairecos_elza.msg.14"
    )
    assert msg.is_file()
    assert read_english_name(msg) == "Walker"
    assert not (folder / "natives" / "stm").exists()


def test_two_dlc_names_stay_on_their_sources(tmp_path: Path):
    from re2_outfit_converter.msg_name import (
        sync_costume_names_for_targets,
        write_outfit_name,
        _template_path,
    )

    root = tmp_path / "stage"
    msg = root / MSG_DIR_DLC
    msg.mkdir(parents=True)
    write_outfit_name(
        _template_path("elza"), msg / "mes_sys_clairecos_elza.msg.14",
        "Rich Girl", "elza")
    write_outfit_name(
        _template_path("noir"), msg / "mes_sys_clairecos_noir.msg.14",
        "Agent", "noir")
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    military = CLAIRE_OUTFIT_BY_KEY["military"]
    sync_costume_names_for_targets(
        root,
        [noir, military],
        source_msg_stem_by_target={"noir": "elza", "military": "noir"},
    )
    assert read_english_name(
        msg / "mes_sys_clairecos_noir.msg.14") == "Rich Girl"
    assert read_english_name(
        msg / "mes_sys_clairecos_military.msg.14") == "Agent"
    assert not (msg / "mes_sys_clairecos_elza.msg.14").exists()


def test_leon_costume_name_is_only_leon_noir(tmp_path: Path):
    root = tmp_path / "leon"
    (root / "natives").mkdir(parents=True)
    msg = root / MSG_DIR_DLC
    msg.mkdir(parents=True)
    write_outfit_name(
        _template_path("leon_noir"),
        msg / "mes_sys_leoncos_noir.msg.14",
        "Private Eye",
        "leon_noir",
    )
    write_modinfo(root, Name="Cool Leon")
    analysis = analyze(root)
    assert analysis.english_names_by_outfit_key() == {
        "leon_noir": "Private Eye",
    }
    assert analysis.suggested_outfit_display_name("fallback") == "Private Eye"


def test_rt_shared_costume_names_are_stripped(tmp_path: Path):
    from re2_outfit_converter.msg_name import _remove_costume_sys_msgs

    parent = tmp_path / "natives" / "stm" / "sectionroot" / "message" / "mes_sys"
    parent.mkdir(parents=True)
    costume = parent / "mes_sys_costume.msg.50397457"
    reward = parent / "mes_sys_reward.msg.50397457"
    costume.write_bytes(b"c")
    reward.write_bytes(b"r")
    ops = _remove_costume_sys_msgs(tmp_path)
    assert not costume.exists()
    assert not reward.exists()
    assert len(ops) == 2


def test_already_ray_tracing_same_slot_writes_the_name(tmp_path: Path):
    root = _elza_root(tmp_path, "stm", "2109108288")
    out = tmp_path / "out_rt"
    out.mkdir()
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(source=elza, target=elza)],
        out,
        as_folder=True,
        folder_name="ElzaRtNamed",
        tag_output=False,
        write_log=False,
        game_build="Ray tracing",
        outfit_display_names={"elza": "Walker"},
    )
    folder = report.output_folder
    assert folder is not None
    msg = (
        folder / "natives" / "stm" / "sectionroot" / "message"
        / "mes_other_dlc" / "mes_sys_clairecos_elza.msg.50397457"
    )
    assert msg.is_file()
    assert read_english_name(msg) == "Walker"
