"""Convert log embedding and settings default."""

from __future__ import annotations

from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.convert_log import (
    CONVERT_LOG_NAME,
    ConvertLogContext,
    format_convert_log,
    write_convert_log_to_staging,
)
from re2_outfit_converter.converter import convert_with_ops
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.reports import ConversionReport
from re2_outfit_converter.settings import normalize_settings

from tests.fixtures import build_elza_main


def test_write_convert_log_default_on():
    assert normalize_settings({})["write_convert_log"] is True


def test_format_and_write_staging_log(tmp_path: Path):
    report = ConversionReport()
    report.rename_ops.append("pl1004/ -> pl1005/")
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
        military_face="clean",
        package_name="Cooling Suit [Noir].zip",
    )
    text = format_convert_log(report, ctx)
    assert "CoolingSuit.zip" in text
    assert "O:\\" not in text and "O:/" not in text
    assert "From Elza Walker → To Noir" in text
    assert "pl1004/ -> pl1005/" in text
    assert "Written:" not in text

    staging = tmp_path / "stage"
    staging.mkdir()
    path = write_convert_log_to_staging(staging, report, ctx)
    assert path is not None
    assert path.name == CONVERT_LOG_NAME
    assert path.is_file()
    assert "From Elza Walker" in path.read_text(encoding="utf-8")


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
    assert "elza_main" in body


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
