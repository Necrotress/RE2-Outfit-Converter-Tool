from __future__ import annotations

import json
from pathlib import Path

from re2_outfit_converter.platform.blender_batch import (
    BlenderBatchResult,
    BlenderJob,
    apply_blender_result_to_report,
    collect_mesh_mdf_jobs,
    collect_shipped_mmtr,
    stock_shader_overrides,
    parse_result,
    write_manifest,
)
from re2_outfit_converter.platform.blender_detect import blender_script_dir, find_blender
from re2_outfit_converter.platform.reports import ConversionReport


def test_blender_script_bundled():
    script = blender_script_dir() / "batch_rt_to_re2.py"
    assert script.is_file()


def test_collect_jobs(tmp_path: Path):
    mesh = (
        tmp_path / "natives" / "stm" / "sectionroot" / "a.mesh.2109108288"
    )
    mdf = tmp_path / "natives" / "stm" / "sectionroot" / "a.mdf2.21"
    mesh.parent.mkdir(parents=True)
    mesh.write_bytes(b"MESH")
    mdf.write_bytes(b"MDF\x00")
    jobs = collect_mesh_mdf_jobs(tmp_path)
    assert len(jobs) == 2
    kinds = {j.kind for j in jobs}
    assert kinds == {"mesh", "mdf2"}
    mesh_job = next(j for j in jobs if j.kind == "mesh")
    assert mesh_job.dst.name.endswith(".mesh.1808312334")
    assert [j.kind for j in jobs] == ["mesh", "mdf2"]


def test_manifest_roundtrip(tmp_path: Path):
    src = tmp_path / "pl.mesh.2109108288"
    dst = tmp_path / "pl.mesh.1808312334"
    src.write_bytes(b"x")
    jobs = [BlenderJob("mesh", src, dst)]
    man = tmp_path / "manifest.json"
    write_manifest(jobs, man, ["record_player_cloth_re3.mmtr.1808160001"])
    data = json.loads(man.read_text(encoding="utf-8"))
    assert data["jobs"][0]["kind"] == "mesh"
    assert Path(data["jobs"][0]["src"]).name == src.name
    assert data["shipped_mmtr"] == ["record_player_cloth_re3.mmtr.1808160001"]


def test_collect_shipped_mmtr(tmp_path: Path):
    master = tmp_path / "natives" / "x64" / "mastermaterial" / "master"
    master.mkdir(parents=True)
    (master / "record_player_cloth_re3.mmtr.1808160001").write_bytes(b"x")
    (master / "env_alpha_re3.mmtr.1808160001").write_bytes(b"x")
    (master / "notes.txt").write_bytes(b"x")
    assert collect_shipped_mmtr(tmp_path) == [
        "env_alpha_re3.mmtr.1808160001",
        "record_player_cloth_re3.mmtr.1808160001",
    ]


def test_stock_shader_overrides_are_singled_out(tmp_path: Path):
    """A mod's copy of a stock shader shadows it; a new name does not."""
    master = tmp_path / "natives" / "x64" / "mastermaterial" / "master"
    master.mkdir(parents=True)
    for name in (
        "record_player_hair.mmtr.1808160001",
        "record_player_cloth_re3.mmtr.1808160001",
        "hair_dither.mmtr.1808160001",
    ):
        (master / name).write_bytes(b"MMTR")

    hits = {p.name for p in stock_shader_overrides(tmp_path)}
    assert hits == {
        "record_player_hair.mmtr.1808160001",
        "hair_dither.mmtr.1808160001",
    }


def test_retargets_reach_the_report(tmp_path: Path):
    batch = BlenderBatchResult(material_notes=[
        "retarget: pl2000_Body_Mat: record_player_cloth_re3.mmtr has no RT "
        "build, rebuilt on Character.json",
        "pl1000_Body_Mat: flags 152 -> 134217880",
    ])
    report = ConversionReport()
    apply_blender_result_to_report(tmp_path, batch, report)
    assert any("re-aimed at a stock shader" in w for w in report.warnings)
    assert any("pl2000_Body_Mat" in w for w in report.warnings)
    assert not any("flags 152" in w for w in report.warnings)


def test_broken_property_table_notes_reach_the_report(tmp_path: Path):
    batch = BlenderBatchResult(material_notes=[
        "pl1004.mdf2.10: pl1000_Body_Mat: broken property table, "
        "rebuilt on Character.json (props 34 -> 37)",
    ])
    report = ConversionReport()
    apply_blender_result_to_report(tmp_path, batch, report)
    assert any("truncated property table" in w for w in report.warnings)
    assert any("pl1000_Body_Mat" in w for w in report.warnings)


def test_parse_result(tmp_path: Path):
    path = tmp_path / "result.json"
    path.write_text(
        json.dumps({
            "results": [
                {"ok": True, "src": "a.mesh", "dst": "b.mesh", "error": ""},
                {"ok": False, "src": "c.mdf2", "error": "boom"},
            ]
        }),
        encoding="utf-8",
    )
    rows = parse_result(path)
    assert rows[0]["ok"] is True
    assert rows[1]["ok"] is False


def test_find_blender_tolerates_missing():
    # Should not raise; may return None on this machine.
    find_blender(r"C:\definitely\not\blender.exe")
