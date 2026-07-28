"""Custom private hair folders (pl1605) must be detected for Noir preview."""

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo
from re2_outfit_converter.isolation import isolate_claire_face_hair
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS
from re2_outfit_converter.reports import ConversionReport


def test_isolate_keeps_custom_hair_pl1605(tmp_path: Path):
    staging = tmp_path
    face = staging / MESH_ROOTS[0] / "pl1050"
    face.mkdir(parents=True)
    (face / "pl1060.mesh.1").write_bytes(b"face")
    hair = staging / MESH_ROOTS[0] / "pl1605"
    hair.mkdir(parents=True)
    (hair / "pl1678.mesh.1").write_bytes(b"hair")
    (hair / "pl1678_hair_alba.tex.10").write_bytes(b"tex")
    analysis = AnalysisResult(
        root=staging,
        modinfo=ModInfo(name="CustomHair"),
        claire_custom_ids=["pl1605"],
        natives_files=[
            f"{MESH_ROOTS[0]}/pl1050/pl1060.mesh.1",
            f"{MESH_ROOTS[0]}/pl1605/pl1678.mesh.1",
        ],
    )
    report = ConversionReport()
    face_id, hair_id = isolate_claire_face_hair(
        staging,
        analysis,
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        {},
        report,
    )
    assert hair_id == "pl1605"
    assert (staging / MESH_ROOTS[0] / "pl1605" / "pl1678.mesh.1").is_file()
    assert any("kept custom hair pl1605" in op for op in report.rename_ops)
    assert face_id.startswith("pl18")
