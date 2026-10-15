"""Ray tracing body prefabs keep the chain the classic prefab named."""

from pathlib import Path

from re2_outfit_converter.platform.body_prefab import publish_rt_body_prefabs


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


def test_unrelated_body_prefab_is_left_alone(tmp_path: Path):
    _player, prefab = _staging(tmp_path)
    (prefab / "pl1000_body_costume_c.pfb.16").write_bytes(b"PFB\x00not-a-body-prefab")

    publish_rt_body_prefabs(tmp_path, Report())

    assert not (prefab / "pl1000_body_costume_c.pfb.17").exists()
