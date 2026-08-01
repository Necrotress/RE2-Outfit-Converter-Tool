"""End-user analysis panel text helpers."""

from __future__ import annotations

from types import SimpleNamespace

from re2_outfit_converter.analyzer import AnalysisResult
from re2_outfit_converter.gui_analysis import (
    format_multi_outfit_row,
    format_outfit_row,
)
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY


def _analysis(**kwargs) -> AnalysisResult:
    result = AnalysisResult()
    for key, value in kwargs.items():
        setattr(result, key, value)
    return result


def test_outfit_row_short_names_only():
    analysis = _analysis(
        claire_outfits=[CLAIRE_OUTFIT_BY_KEY["tanktop"]],
        claire_body_ids={"pl1001"},
        claire_pfbs=[],
        characters={"Claire": 12},
    )
    text, ok = format_outfit_row(analysis)
    assert ok
    assert text == "Tank Top"
    assert "PFB" not in text
    assert "pl1001" not in text
    assert "mesh" not in text


def test_outfit_row_notes_non_claire_without_file_counts():
    analysis = _analysis(
        claire_outfits=[CLAIRE_OUTFIT_BY_KEY["elza"]],
        characters={"Claire": 20, "Leon": 3, "Ada": 1},
    )
    text, ok = format_outfit_row(analysis)
    assert ok
    assert text.startswith("Elza Walker")
    assert "also has Ada, Leon" in text
    assert "files" not in text


def test_outfit_row_ignores_analysis_warnings():
    analysis = _analysis(
        claire_outfits=[CLAIRE_OUTFIT_BY_KEY["noir"]],
        characters={"Claire": 5},
        warnings=["No Claire files detected - this mod targets: Leon"],
    )
    text, ok = format_outfit_row(analysis)
    assert ok
    assert text == "Noir"
    assert "!" not in text
    assert "Leon" not in text


def test_outfit_row_addon_short():
    analysis = _analysis(characters={"Claire": 1})
    analysis.modinfo.addonfor = "Main Pack"
    text, ok = format_outfit_row(analysis)
    assert ok
    assert "Addon for Main Pack" in text
    assert "load with the main mod" in text
    assert "batch" not in text.lower()


def test_multi_outfit_row():
    tank = _analysis(
        claire_outfits=[CLAIRE_OUTFIT_BY_KEY["tanktop"]],
        characters={"Claire": 4},
    )
    addon = _analysis(claire_outfits=[], characters={"Claire": 2})
    loaded = [
        SimpleNamespace(analysis=tank),
        SimpleNamespace(analysis=addon),
    ]
    text, ok = format_multi_outfit_row(loaded)
    assert ok
    assert text.startswith("Tank Top")
    assert "1 addon" in text
