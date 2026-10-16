"""Skip the format pass when the game build stays the same."""

from __future__ import annotations

from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.converter import convert_with_ops
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY


def _pack(root: Path, platform: str, mesh_suffix: str, pfb_suffix: str) -> None:
    body = (
        root / "natives" / platform / "sectionroot" / "character"
        / "player" / "pl1000" / "pl1004"
    )
    body.mkdir(parents=True)
    (body / f"pl1004.mesh.{mesh_suffix}").write_bytes(b"mesh")
    parts = (
        root / "natives" / platform / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    parts.mkdir(parents=True)
    (parts / f"pl1000_body_costume_c.pfb.{pfb_suffix}").write_bytes(b"body")
    (root / "modinfo.ini").write_text("Name=Elza\n", encoding="utf-8")


def _convert(root: Path, out: Path, game_build: str, display_name: str | None = None):
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    military = CLAIRE_OUTFIT_BY_KEY["military"]
    return convert_with_ops(
        analyze(root),
        [OutfitOp(source=elza, target=military)],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="Out",
        write_log=False,
        game_build=game_build,
        outfit_display_name=display_name,
    )


def _files(folder: Path) -> list[str]:
    return [
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    ]


def test_ray_tracing_slot_change_stays_on_stm(tmp_path: Path, monkeypatch):
    jobs: list[bool] = []
    moves: list[str] = []

    def collect(staging, to_rt=False):
        jobs.append(to_rt)
        return []

    def move(staging, report):
        moves.append("move")

    monkeypatch.setattr(
        "re2_outfit_converter.platform.converter.collect_mesh_mdf_jobs",
        collect,
    )
    monkeypatch.setattr(
        "re2_outfit_converter.platform.path_remap.move_tree_to_rt",
        move,
    )
    root = tmp_path / "elza"
    _pack(root, "stm", "2109108288", "17")
    out = tmp_path / "out"
    out.mkdir()
    report = _convert(root, out, "Ray tracing", display_name="Field")
    folder = report.output_folder
    assert folder is not None
    files = _files(folder)
    assert jobs == []
    assert moves == []
    assert not any(name.startswith("natives/x64/") for name in files)
    assert any(
        name.startswith("natives/stm/") and "/pl1006/" in name and name.endswith(".mesh.2109108288")
        for name in files
    )
    assert any(name.endswith("pl1000_body_costume_b.pfb.17") for name in files)
    assert any(
        "pl1050_04" in name and name.endswith(".tex.34") and name.startswith("natives/stm/")
        for name in files
    )
    assert any(
        name.startswith("natives/stm/") and name.endswith(".msg.50397457")
        for name in files
    )
    assert not any(name.endswith(".msg.14") for name in files)


def test_classic_slot_change_skips_both_platform_passes(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def prepare(staging, **_kwargs):
        calls.append("prepare")
        raise AssertionError("prepare_classic")

    def upgrade(staging, **_kwargs):
        calls.append("upgrade")
        raise AssertionError("upgrade_to_rt")

    monkeypatch.setattr("re2_outfit_converter.converter.prepare_classic", prepare)
    monkeypatch.setattr("re2_outfit_converter.converter.upgrade_to_rt", upgrade)
    root = tmp_path / "elza"
    _pack(root, "x64", "1808312334", "16")
    out = tmp_path / "out"
    out.mkdir()
    report = _convert(root, out, "Classic")
    folder = report.output_folder
    assert folder is not None
    files = _files(folder)
    assert calls == []
    assert any("/pl1006/" in name and name.startswith("natives/x64/") for name in files)
    assert not any(name.startswith("natives/stm/") for name in files)


def test_a_real_build_change_still_runs_the_platform_pass(tmp_path: Path, monkeypatch):
    from re2_outfit_converter.platform.reports import ConversionReport as Plat

    calls: list[str] = []

    def prepare(staging, **_kwargs):
        calls.append("prepare")
        return Plat()

    def upgrade(staging, **_kwargs):
        calls.append("upgrade")
        return Plat()

    monkeypatch.setattr("re2_outfit_converter.converter.prepare_classic", prepare)
    monkeypatch.setattr("re2_outfit_converter.converter.upgrade_to_rt", upgrade)

    classic = tmp_path / "classic"
    _pack(classic, "x64", "1808312334", "16")
    out = tmp_path / "up"
    out.mkdir()
    _convert(classic, out, "Ray tracing")
    assert calls == ["upgrade"]

    calls.clear()
    ray = tmp_path / "ray"
    _pack(ray, "stm", "2109108288", "17")
    down = tmp_path / "down"
    down.mkdir()
    _convert(ray, down, "Classic")
    assert calls == ["prepare"]

    calls.clear()
    dual = tmp_path / "dual"
    _pack(dual, "x64", "1808312334", "16")
    _pack(dual, "stm", "2109108288", "17")
    assert analyze(dual).game_label == "Classic and ray tracing"
    both = tmp_path / "both"
    both.mkdir()
    _convert(dual, both, "Ray tracing")
    assert calls == ["prepare", "upgrade"]
