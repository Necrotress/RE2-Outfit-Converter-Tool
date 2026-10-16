"""Ray tracing body prefabs keep the chain the classic prefab named."""

import struct
from pathlib import Path

from re2_outfit_converter.platform.body_prefab import (
    publish_classic_body_prefabs,
    publish_rt_body_prefabs,
)


class Report:
    def __init__(self) -> None:
        self.warnings: list[str] = []


def _u16_has(data: bytes, text: str) -> bool:
    return text.encode("utf-16le") in data


def _staging(tmp_path: Path) -> tuple[Path, Path]:
    player = (
        tmp_path / "natives" / "stm" / "sectionroot" / "character"
        / "player" / "pl1000"
    )
    prefab = (
        tmp_path / "natives" / "stm" / "objectroot" / "prefab"
        / "character" / "survivor" / "parts" / "pl1000"
    )
    player.mkdir(parents=True)
    prefab.mkdir(parents=True)
    return player, prefab


def _edited_default() -> bytes:
    from re2_outfit_converter.paths import assets_dir

    raw = (assets_dir() / "body_prefab" / "pl1000_body_default.pfb.16").read_bytes()
    chain_old = "SectionRoot/Character/Player/pl1000/pl1000.chain".encode("utf-16le")
    chain_new = "SectionRoot/Character/Player/pl1000/pl1004.chain".encode("utf-16le")
    assert len(chain_old) == len(chain_new)
    raw = raw.replace(chain_old, chain_new)
    mat_old = "pl1000_Chain_Mat".encode("utf-16le") + b"\x00\x00"
    mat_new = ("Dress_Mat".encode("utf-16le") + b"\x00\x00").ljust(len(mat_old), b"\x00")
    assert mat_old in raw
    return raw.replace(mat_old, mat_new)


def test_elza_body_prefab_names_the_mod_chain(tmp_path: Path):
    player, prefab = _staging(tmp_path)
    (player / "pl1004.chain.46").write_bytes(b"CHAIN")
    (prefab / "pl1000_body_costume_c.pfb.16").write_bytes(_edited_default())

    report = Report()
    publish_rt_body_prefabs(tmp_path, report)

    rt = prefab / "pl1000_body_costume_c.pfb.17"
    assert rt.is_file()
    data = rt.read_bytes()
    assert _u16_has(data, "pl1000/pl1004.chain")
    assert _u16_has(data, "Dress_Mat")
    assert not _u16_has(data, "pl1000/pl1000.chain")
    assert not _u16_has(data, "pl1000_Chain_Mat")
    assert any("pl1004.chain" in note for note in report.warnings)


def test_a_rain_rate_float_is_published_with_the_chain(tmp_path: Path):
    player, prefab = _staging(tmp_path)
    (player / "pl1004.chain.46").write_bytes(b"CHAIN")
    edited = bytearray(_edited_default())
    rate = struct.pack("<f", 1.0)
    edited[5688:5692] = rate
    (prefab / "pl1000_body_costume_c.pfb.16").write_bytes(edited)

    publish_rt_body_prefabs(tmp_path, Report())

    rt = prefab / "pl1000_body_costume_c.pfb.17"
    assert rt.is_file()
    data = rt.read_bytes()
    assert _u16_has(data, "pl1000/pl1004.chain")
    assert data[5688:5692] == rate


def test_ray_tracing_prefab_derives_back_to_classic(tmp_path: Path):
    player, prefab = _staging(tmp_path)
    (player / "pl1004.chain.46").write_bytes(b"CHAIN")
    edited = bytearray(_edited_default())
    rate = struct.pack("<f", 1.0)
    edited[5688:5692] = rate
    classic = prefab / "pl1000_body_costume_c.pfb.16"
    classic.write_bytes(edited)
    publish_rt_body_prefabs(tmp_path, Report())
    classic.unlink()

    publish_classic_body_prefabs(tmp_path, Report())

    data = classic.read_bytes()
    assert _u16_has(data, "pl1000/pl1004.chain")
    assert data[5688:5692] == rate


def test_unedited_body_prefab_does_not_replace_the_pak_file(tmp_path: Path):
    from re2_outfit_converter.paths import assets_dir

    _player, prefab = _staging(tmp_path)
    classic = (assets_dir() / "body_prefab" / "pl1000_body_default.pfb.16").read_bytes()
    (prefab / "pl1000_body_costume_c.pfb.16").write_bytes(classic)

    publish_rt_body_prefabs(tmp_path, Report())

    assert not (prefab / "pl1000_body_costume_c.pfb.17").exists()


def test_missing_private_chain_does_not_write_a_prefab(tmp_path: Path):
    _player, prefab = _staging(tmp_path)
    (prefab / "pl1000_body_costume_c.pfb.16").write_bytes(_edited_default())

    report = Report()
    publish_rt_body_prefabs(tmp_path, report)

    assert not (prefab / "pl1000_body_costume_c.pfb.17").exists()
    assert any("pl1004.chain" in note for note in report.warnings)


def test_ray_tracing_noir_slot_overrides_the_pak_prefabs(tmp_path: Path):
    from re2_outfit_converter.analyzer import AnalysisResult
    from re2_outfit_converter.hair_prefabs import ensure_exclusive_hair_override
    from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
    from re2_outfit_converter.paths import assets_dir, mesh_roots, parts_dir, use_natives_platform
    from re2_outfit_converter.platform.body_prefab import (
        _prefab_mat_names,
        publish_rt_jacket_body_prefab,
    )
    from re2_outfit_converter.reports import ConversionReport

    template = (assets_dir() / "body_prefab" / "pl1000_body_default.pfb.17").read_bytes()
    with use_natives_platform("stm"):
        mesh_dir = tmp_path / mesh_roots()[0] / "pl1005"
        mesh_dir.mkdir(parents=True)
        names = [
            name.replace("pl1000", "pl1005", 1)
            for name in _prefab_mat_names(template)
        ]
        (mesh_dir / "pl1005.mesh.2109108288").write_bytes(
            b"\n".join(name.encode("ascii") for name in names)
        )
        report = ConversionReport()
        ensure_exclusive_hair_override(
            tmp_path, AnalysisResult(root=tmp_path),
            CLAIRE_OUTFIT_BY_KEY["jacket"],
            CLAIRE_OUTFIT_BY_KEY["noir"],
            [], report,
        )
        publish_rt_jacket_body_prefab(tmp_path, report, "pl1005", "costume_a")
        folder = tmp_path / parts_dir()
        hair = (folder / "pl1000_hair_costume_a.pfb.17").read_bytes()
        body = (folder / "pl1000_body_costume_a.pfb.17").read_bytes()

    assert _u16_has(hair, "pl1070/pl1070.mesh")
    assert _u16_has(hair, "pl1070.chain")
    assert not _u16_has(hair, "pl1075")
    assert _u16_has(body, "pl1000/pl1005/pl1005.mesh")
    assert _u16_has(body, "pl1000/pl1005/pl1005.mdf2")
    assert not _u16_has(body, "pl1000/pl1000/pl1000.mdf2")
    assert not _u16_has(body, "pl1000/pl1000/pl1005")
    assert _u16_has(body, "pl1000_body_default")
    assert _u16_has(body, "pl1005_Jacket_Mat")
    assert _u16_has(body, "pl1000.chain")
    assert not _u16_has(body, "pl1005.chain")
    assert not list(tmp_path.rglob("pl1075.mesh*"))


def test_elza_mesh_on_the_military_slot_keeps_elza_materials(tmp_path: Path):
    from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
    from re2_outfit_converter.paths import mesh_roots, parts_dir, use_natives_platform
    from re2_outfit_converter.platform.body_prefab import publish_rt_slot_body_prefab
    from re2_outfit_converter.reports import ConversionReport

    with use_natives_platform("stm"):
        mesh_dir = tmp_path / mesh_roots()[0] / "pl1006"
        mesh_dir.mkdir(parents=True)
        (mesh_dir / "pl1006.mesh.2109108288").write_bytes(
            b"pl1006_Body_Mat\npl1006_Props_Mat"
        )
        publish_rt_slot_body_prefab(
            tmp_path, ConversionReport(),
            CLAIRE_OUTFIT_BY_KEY["elza"], "pl1006", "costume_b",
        )
        body = (tmp_path / parts_dir() / "pl1000_body_costume_b.pfb.17").read_bytes()

    assert _u16_has(body, "pl1000/pl1006/pl1006.mesh")
    assert _u16_has(body, "pl1006_Body_Mat")
    assert _u16_has(body, "pl1006_Props_Mat")
    assert _u16_has(body, "pl1000_body_costume_b")
    assert not _u16_has(body, "pl1006_Skin_Mat")
    assert not _u16_has(body, "pl1005.chain")
    assert not _u16_has(body, ".chain")


def test_tank_material_names_are_what_the_military_prefab_lists(tmp_path: Path):
    from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
    from re2_outfit_converter.paths import mesh_roots, parts_dir, use_natives_platform
    from re2_outfit_converter.platform.body_prefab import publish_rt_slot_body_prefab
    from re2_outfit_converter.reports import ConversionReport

    with use_natives_platform("stm"):
        mesh_dir = tmp_path / mesh_roots()[0] / "pl1006"
        mesh_dir.mkdir(parents=True)
        (mesh_dir / "pl1006.mesh.2109108288").write_bytes(
            b"Outfit_Mat\x00pl1006_Body_Mat\x00pl1006_Radio_Mat"
        )
        publish_rt_slot_body_prefab(
            tmp_path, ConversionReport(),
            CLAIRE_OUTFIT_BY_KEY["tanktop"], "pl1006", "costume_b",
        )
        body = (tmp_path / parts_dir() / "pl1000_body_costume_b.pfb.17").read_bytes()

    assert _u16_has(body, "pl1000/pl1006/pl1006.mesh")
    assert _u16_has(body, "pl1000.chain")
    assert not _u16_has(body, "pl1005.chain")
    assert _u16_has(body, "pl1006_Body_Mat")
    assert _u16_has(body, "pl1006_Boots_Mat")
    assert not _u16_has(body, "Outfit_Mat")
    boots = "pl1006_Boots_Mat".encode("utf-16le")
    idx = body.find(boots)
    assert body[idx - 4:idx] == struct.pack("<I", len("pl1006_Boots_Mat") + 1)


def test_classic_jacket_on_elza_keeps_the_source_material_slots(tmp_path: Path):
    from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
    from re2_outfit_converter.paths import mesh_roots, parts_dir, use_natives_platform
    from re2_outfit_converter.platform.body_prefab import publish_rt_slot_body_prefab
    from re2_outfit_converter.reports import ConversionReport

    with use_natives_platform("stm"):
        mesh_dir = tmp_path / mesh_roots()[0] / "pl1004"
        mesh_dir.mkdir(parents=True)
        (mesh_dir / "pl1004.mesh.2109108288").write_bytes(
            b"Swim_Mat\x00pl1001_Holster_Mat\x00pl1001_Gun_Mat"
        )
        publish_rt_slot_body_prefab(
            tmp_path, ConversionReport(),
            CLAIRE_OUTFIT_BY_KEY["classic_jacket"], "pl1004", "costume_c",
        )
        body = (tmp_path / parts_dir() / "pl1000_body_costume_c.pfb.17").read_bytes()

    assert _u16_has(body, "pl1000/pl1004/pl1004.mesh")
    assert _u16_has(body, "pl1000.chain")
    assert _u16_has(body, "pl1004_Body_Mat")
    assert _u16_has(body, "pl1004_Props_Mat")
    assert not _u16_has(body, "Swim_Mat")
    assert not _u16_has(body, "pl1001_Holster_Mat")


def test_elza_to_noir_hair_hide_overwrites_the_copied_prefab(tmp_path: Path):
    from re2_outfit_converter.hair_prefabs import publish_rt_hair_hide
    from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
    from re2_outfit_converter.paths import parts_dir, use_natives_platform
    from re2_outfit_converter.reports import ConversionReport

    with use_natives_platform("stm"):
        folder = tmp_path / parts_dir()
        folder.mkdir(parents=True)
        (folder / "pl1000_hair_costume_a.pfb.17").write_bytes(
            "SectionRoot/Character/Player/pl1000/pl1075/pl1075.mesh".encode("utf-16le")
        )
        publish_rt_hair_hide(
            tmp_path, ConversionReport(),
            CLAIRE_OUTFIT_BY_KEY["noir"], "costume_a",
        )
        hair = (folder / "pl1000_hair_costume_a.pfb.17").read_bytes()

    assert _u16_has(hair, "pl1070/pl1070.mesh")
    assert _u16_has(hair, "pl1070.chain")
    assert not _u16_has(hair, "pl1075")
    assert not list(tmp_path.rglob("pl1075.mesh*"))


def test_unrelated_body_prefab_is_left_alone(tmp_path: Path):
    _player, prefab = _staging(tmp_path)
    (prefab / "pl1000_body_costume_c.pfb.16").write_bytes(b"PFB\x00not-a-body-prefab")

    publish_rt_body_prefabs(tmp_path, Report())

    assert not (prefab / "pl1000_body_costume_c.pfb.17").exists()


def test_private_chain_is_attached_for_every_claire_slot(tmp_path: Path):
    """A classic body that matches no vanilla twin still has to carry its chain.

    Jacket, Tank, both Classics, and Noir already name a chain. Military and
    Elza do not, so those slots borrow Noir's prefab and keep the mod chain.
    """
    player, prefab = _staging(tmp_path)
    chain_dir = player.parent / "pl5300" / "ples47"
    chain_dir.mkdir(parents=True)
    (player.parent / "pl5300" / "pl5300.chain.46").write_bytes(b"CHAIN")
    (player.parent / "pl5300" / "pl5300.jcns.11").write_bytes(b"JCNS")
    (chain_dir / "pl5300.mesh.2109108288").write_bytes(b"MESH")
    (chain_dir / "pl5300.mdf2.21").write_bytes(b"MDF")
    text = (
        "SectionRoot/Character/Player/pl5300/ples47/pl5300.mesh\x00"
        "SectionRoot/Character/Player/pl5300/ples47/pl5300.mdf2\x00"
        "SectionRoot/Character/Player/pl5300/pl5300.jcns\x00"
        "SectionRoot/Character/Player/pl5300/pl5300.chain\x00"
        "pl5300_Body_Mat\x00"
        "pl5300_Body2_Mat\x00"
    )
    blob = b"XXXX" + text.encode("utf-16le") + b"unmatched-body"
    slots = (
        "default",
        "costume_3",
        "costume_5",
        "costume_8",
        "costume_a",
        "costume_b",
        "costume_c",
    )
    for slot in slots:
        (prefab / f"pl1000_body_{slot}.pfb.16").write_bytes(blob)

    publish_rt_body_prefabs(tmp_path, Report())

    for slot in slots:
        data = (prefab / f"pl1000_body_{slot}.pfb.17").read_bytes()
        assert _u16_has(data, "pl5300/ples47/pl5300.mesh"), slot
        assert _u16_has(data, "pl5300/ples47/pl5300.mdf2"), slot
        assert _u16_has(data, "pl5300/pl5300.chain"), slot
        assert _u16_has(data, "pl1000/pl1000.jcns"), slot
        assert not _u16_has(data, "pl5300/pl5300.jcns"), slot
        assert _u16_has(data, "pl5300_Body_Mat"), slot
        assert not _u16_has(data, "pl5300_Body2_Mat"), slot
        assert _u16_has(data, f"pl1000_body_{slot}"), slot
        assert not _u16_has(data, "pl1005.chain"), slot


def test_slot_publish_keeps_a_shipped_private_chain(tmp_path: Path):
    from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
    from re2_outfit_converter.paths import mesh_roots, parts_dir, use_natives_platform
    from re2_outfit_converter.platform.body_prefab import publish_rt_slot_body_prefab
    from re2_outfit_converter.reports import ConversionReport

    slots = {
        "default": "pl1000",
        "costume_3": "pl1001",
        "costume_5": "pl1002",
        "costume_8": "pl1003",
        "costume_a": "pl1005",
        "costume_b": "pl1006",
        "costume_c": "pl1004",
    }
    chain = "SectionRoot/Character/Player/pl5300/pl5300.chain\x00".encode("utf-16le")
    payload = chain + b"KEEP-CHAIN"
    with use_natives_platform("stm"):
        (tmp_path / "natives" / "stm" / "sectionroot" / "character" / "player" / "pl5300").mkdir(parents=True)
        (
            tmp_path / "natives" / "stm" / "sectionroot" / "character"
            / "player" / "pl5300" / "pl5300.chain.46"
        ).write_bytes(b"CHAIN")
        folder = tmp_path / parts_dir()
        folder.mkdir(parents=True)
        for slot, body_id in slots.items():
            mesh_dir = tmp_path / mesh_roots()[0] / body_id
            mesh_dir.mkdir(parents=True)
            (mesh_dir / f"{body_id}.mesh.2109108288").write_bytes(b"MESH")
            (folder / f"pl1000_body_{slot}.pfb.17").write_bytes(payload)
            publish_rt_slot_body_prefab(
                tmp_path, ConversionReport(),
                CLAIRE_OUTFIT_BY_KEY["elza"], body_id, slot,
            )
            written = (folder / f"pl1000_body_{slot}.pfb.17").read_bytes()
            assert written == payload, slot


def test_hair_hide_leaves_a_shipped_private_mesh(tmp_path: Path):
    from re2_outfit_converter.hair_prefabs import publish_rt_hair_hide
    from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
    from re2_outfit_converter.paths import mesh_roots, parts_dir, use_natives_platform
    from re2_outfit_converter.reports import ConversionReport

    targets = (
        (CLAIRE_OUTFIT_BY_KEY["noir"], "costume_a"),
        (CLAIRE_OUTFIT_BY_KEY["military"], "costume_b"),
    )
    payload = (
        "SectionRoot/Character/Player/pl1000/pl1841/pl1841.mesh\x00"
        "SectionRoot/Character/Player/pl1000/pl1841/pl1841.mdf2\x00"
    ).encode("utf-16le") + b"KEEP-HAIR"
    with use_natives_platform("stm"):
        mesh_dir = tmp_path / mesh_roots()[0] / "pl1841"
        mesh_dir.mkdir(parents=True)
        (mesh_dir / "pl1841.mesh.2109108288").write_bytes(b"MESH")
        (mesh_dir / "pl1841.mdf2.21").write_bytes(b"MDF")
        folder = tmp_path / parts_dir()
        folder.mkdir(parents=True)
        for target, slot in targets:
            dest = folder / f"pl1000_hair_{slot}.pfb.17"
            dest.write_bytes(payload)
            publish_rt_hair_hide(tmp_path, ConversionReport(), target, slot)
            assert dest.read_bytes() == payload, slot
