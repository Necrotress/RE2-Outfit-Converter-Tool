"""Military face mode detection and clean-texture seeding."""

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo, PfbSlot
from re2_outfit_converter.military_face import (
    FACE_CLEAN,
    FACE_DIRTY,
    FACE_MOD,
    analysis_has_face_rewrite,
    apply_military_face_mode,
    resolve_military_face_mode,
)
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.reports import ConversionReport


def test_detects_face_pfb():
    analysis = AnalysisResult(
        claire_pfbs=[PfbSlot("face", "costume_c", "natives/x64/x.pfb.16")],
    )
    assert analysis_has_face_rewrite(analysis)


def test_detects_military_pl1050_04():
    analysis = AnalysisResult(
        natives_files=[
            "natives/x64/sectionroot/character/player/pl1000/pl1050/"
            "pl1050_04/pl1050_04_face_albm.tex.10",
        ],
    )
    assert analysis_has_face_rewrite(analysis)


def test_ignores_partial_pl1050_without_04():
    """Body mods often ship pl1050_01/02/03 — that is not Military face data."""
    analysis = AnalysisResult(
        natives_files=[
            "natives/x64/sectionroot/character/player/pl1000/pl1050/pl1050.mesh.1",
            "natives/x64/sectionroot/character/player/pl1000/pl1050/"
            "pl1050_01/pl1050_01_face_albm.tex.10",
            "natives/x64/sectionroot/character/player/pl1000/pl1050/"
            "pl1050_02/pl1050_02_face_albm.tex.10",
        ],
    )
    analysis._mesh_id_set = {"pl1050"}
    assert not analysis_has_face_rewrite(analysis)


def test_resolve_locks_mod_face_data():
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    military = CLAIRE_OUTFIT_BY_KEY["military"]
    analysis = AnalysisResult(
        claire_pfbs=[PfbSlot("face", "costume_c", "natives/x64/x.pfb.16")],
    )
    assert resolve_military_face_mode(
        military, analysis, [elza], FACE_CLEAN) == FACE_MOD


def test_resolve_clean_when_only_partial_face_textures():
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    military = CLAIRE_OUTFIT_BY_KEY["military"]
    analysis = AnalysisResult(
        natives_files=[
            "natives/x64/sectionroot/character/player/pl1000/pl1050/"
            "pl1050_01/pl1050_01_face_albm.tex.10",
        ],
    )
    analysis._mesh_id_set = {"pl1050"}
    assert resolve_military_face_mode(
        military, analysis, [elza], FACE_CLEAN) == FACE_CLEAN


def test_resolve_clean_when_no_face():
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    military = CLAIRE_OUTFIT_BY_KEY["military"]
    analysis = AnalysisResult(modinfo=ModInfo(name="BodyOnly"))
    assert resolve_military_face_mode(
        military, analysis, [elza], FACE_CLEAN) == FACE_CLEAN
    assert resolve_military_face_mode(
        military, analysis, [elza], None) == FACE_DIRTY


def test_resolve_clean_for_any_target():
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    analysis = AnalysisResult()
    assert resolve_military_face_mode(
        noir, analysis, [elza], FACE_CLEAN) == FACE_CLEAN
    assert resolve_military_face_mode(
        noir, analysis, [elza], FACE_DIRTY) == FACE_DIRTY


def test_apply_clean_writes_pl1050_04(tmp_path: Path):
    staging = tmp_path
    report = ConversionReport()
    apply_military_face_mode(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], FACE_CLEAN, report)
    albm = list(staging.rglob("pl1050_04_face_albm.tex*"))
    assert albm
    assert any("default face clean" in op or "military face clean" in op
               for op in report.rename_ops)


def test_apply_clean_for_non_military_target(tmp_path: Path):
    staging = tmp_path
    report = ConversionReport()
    apply_military_face_mode(
        staging, CLAIRE_OUTFIT_BY_KEY["noir"], FACE_CLEAN, report)
    assert list(staging.rglob("pl1050_04_face_albm.tex*"))


def test_apply_dirty_does_not_write_textures(tmp_path: Path):
    staging = tmp_path
    report = ConversionReport()
    apply_military_face_mode(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], FACE_DIRTY, report)
    assert not list(staging.rglob("pl1050_04*"))
