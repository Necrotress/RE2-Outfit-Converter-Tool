"""Convert log embedding and settings default."""

from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.convert_log import (
    CONVERT_LOG_NAME,
    ConvertLogContext,
    format_convert_log,
    write_convert_log_to_staging,
)
from re2_outfit_converter.converter import BatchItem, convert_batch, convert_with_ops
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.reports import ConversionReport
from re2_outfit_converter.session import package_label
from re2_outfit_converter.settings import normalize_settings

from tests.fixtures import build_elza_main, build_face_addon


def test_write_convert_log_default_on():
    assert normalize_settings({})["write_convert_log"] is True


def test_format_and_write_staging_log(tmp_path: Path):
    report = ConversionReport()
    report.rename_ops.append("pl1004/ -> pl1005/")
    report.removed_ops.append("stripped leftover")
    report.progress_log.append("Renaming mesh folders and files...")
    ctx = ConvertLogContext(
        mod_name="Cooling Suit",
        source_basename="CoolingSuit.zip",
        outfits="Elza Walker",
        characters="Claire",
        op_lines=["From Elza Walker → To Noir"],
        as_folder=False,
        tag_output=True,
        tag_marker="[Noir]",
        package_name="Cooling Suit [Noir].zip",
    )
    text = format_convert_log(report, ctx)
    assert "Cooling Suit" in text
    assert "Source:" not in text
    assert "=== Options ===" not in text
    assert "=== Progress ===" not in text
    assert "=== Prefab ops ===" not in text
    assert "=== Renames / isolation ===" not in text
    assert "=== Removals ===" not in text
    assert "=== Changes (2 — 1 rename, 1 removal) ===" in text
    assert "rename: pl1004/ -> pl1005/" in text
    assert "removal: stripped leftover" in text
    assert "No prefab or patch changes." in text
    assert "O:\\" not in text and "O:/" not in text
    assert "From Elza Walker → To Noir" in text
    assert "Military face:" not in text
    assert "Written:" not in text
    assert "Renaming mesh folders" not in text

    staging = tmp_path / "stage"
    staging.mkdir()
    path = write_convert_log_to_staging(staging, report, ctx)
    assert path is not None
    assert path.name == CONVERT_LOG_NAME
    assert path.is_file()
    assert "From Elza Walker" in path.read_text(encoding="utf-8")


def test_format_omits_empty_changes_and_warnings():
    report = ConversionReport()
    ctx = ConvertLogContext(
        mod_name="Empty",
        outfits="Jacket",
        characters="Claire",
        op_lines=["From Jacket → To Noir"],
        package_name="Empty.zip",
    )
    text = format_convert_log(report, ctx)
    assert "=== Changes" not in text
    assert "No file changes." in text
    assert "=== Warnings ===" not in text
    assert "=== Operations ===" in text
    assert "=== Output ===" in text


def test_format_empty_category_footer_three_items():
    report = ConversionReport()
    report.rename_ops.append("pl1004/ -> pl1005/")
    ctx = ConvertLogContext(
        mod_name="Suit",
        outfits="Elza Walker",
        characters="Claire",
        op_lines=["From Elza Walker → To Noir"],
        package_name="Suit.zip",
    )
    text = format_convert_log(report, ctx)
    assert "=== Changes (1 — 1 rename) ===" in text
    assert "No prefab, removal, or patch changes." in text
    assert "No file changes." not in text


def test_format_operation_extras_name_face_military():
    report = ConversionReport()
    report.rename_ops.extend([
        "isolated face pl1050  ->  pl1801",
        "face: seeded Claire default face for Military "
        "(mod had no custom face data)",
        "Military clean face: a.tex  ->  pl1050_04/a.tex",
        "set in-game outfit name -> 'mes_sys_clairecos_military.msg.14': "
        "'Beach Claire'",
    ])
    report.pfb_ops.append("body.pfb  ->  body_costume.pfb")
    ctx = ConvertLogContext(
        mod_name="Suit",
        outfits="Elza Walker",
        characters="Claire",
        op_lines=["From Elza Walker → To Military"],
        display_name="Beach Claire",
        package_name="Suit.zip",
    )
    text = format_convert_log(report, ctx)
    assert "Name: 'Beach Claire'" in text
    assert "Face: pl1050  ->  pl1801" in text
    assert "Default face (Military): seeded Claire default" in text
    assert "=== Changes (5 — 1 prefab, 4 renames) ===" in text
    assert "No removal or patch changes." in text
    # Name appears once under Operations (ctx + rename_ops deduped)
    assert text.count("Name: 'Beach Claire'") == 1


def test_convert_embeds_log_in_folder(tmp_path: Path):
    root = build_elza_main(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(
            source=CLAIRE_OUTFIT_BY_KEY["elza"],
            target=CLAIRE_OUTFIT_BY_KEY["noir"],
        )],
        out,
        as_folder=True,
        folder_name="ElzaToNoir",
        tag_output=False,
        source_name="elza_main",
        write_log=True,
    )
    folder = report.output_folder
    assert folder is not None
    log = folder / CONVERT_LOG_NAME
    assert log.is_file()
    body = log.read_text(encoding="utf-8")
    assert "From Elza Walker → To Noir" in body
    assert "=== Options ===" not in body
    assert "=== Progress ===" not in body
    assert "Source:" not in body
    assert "Mod name:" in body
    assert "=== Changes (" in body


def test_convert_skips_log_when_disabled(tmp_path: Path):
    root = build_elza_main(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(
            source=CLAIRE_OUTFIT_BY_KEY["elza"],
            target=CLAIRE_OUTFIT_BY_KEY["noir"],
        )],
        out,
        as_folder=True,
        folder_name="NoLog",
        tag_output=False,
        write_log=False,
    )
    folder = report.output_folder
    assert folder is not None
    assert not (folder / CONVERT_LOG_NAME).exists()


def test_package_label_uses_nested_folder_name(tmp_path: Path):
    extract = tmp_path / "extract"
    nested = extract / "Cooling Suit Main"
    nested.mkdir(parents=True)
    analysis = SimpleNamespace(
        root=nested,
        modinfo=SimpleNamespace(name="Ignored Modinfo Name"),
    )
    source = SimpleNamespace(
        original=tmp_path / "CoolingSuit.zip",
        folder=extract,
    )
    assert package_label(analysis, source) == "Cooling Suit Main"


def test_package_label_uses_archive_stem_for_top_level(tmp_path: Path):
    extract = tmp_path / "CoolingSuit"
    extract.mkdir()
    analysis = SimpleNamespace(
        root=extract,
        modinfo=SimpleNamespace(name="Modinfo Name"),
    )
    source = SimpleNamespace(
        original=tmp_path / "CoolingSuit.zip",
        folder=extract,
    )
    assert package_label(analysis, source) == "CoolingSuit"


def test_batch_root_convert_log_preserves_folder_names(tmp_path: Path):
    main = analyze(build_elza_main(tmp_path))
    addon = analyze(build_face_addon(tmp_path))
    out = tmp_path / "out"
    out.mkdir()
    report = convert_batch(
        [
            BatchItem(analysis=main, label="OuterZipName"),
            BatchItem(analysis=addon, label="OuterZipName"),
        ],
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        out,
        "Cooling Suit",
        tag_output=False,
        write_log=True,
    )
    assert report.output_zip is not None
    with zipfile.ZipFile(report.output_zip) as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
        assert CONVERT_LOG_NAME in names
        assert "convert_batch.log" not in names
        nested_logs = [
            n for n in names
            if n.lower().endswith("convert.log") and "/" in n
        ]
        assert nested_logs == []
        assert any(n.startswith("elza_main/") for n in names)
        assert any(n.startswith("face_addon/") for n in names)
        assert not any(n.startswith("OuterZipName") for n in names)
        log = zf.read(CONVERT_LOG_NAME).decode("utf-8")
    assert "=== Bundle ===" in log
    assert "# Package: elza_main" in log
    assert "# Package: face_addon" in log
    assert "From Elza Walker → To Noir" in log
    assert "=== Changes (" in log or "rename:" in log
