"""chain.21 → chain.46. Retail pairs must match; hand-tuned RTX edits are listed."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from re2_outfit_converter.platform.chain_convert import convert_chain_to_rt
from re2_outfit_converter.platform.converter import _convert_textures_and_unsupported
from re2_outfit_converter.platform.reports import ConversionReport, FormatConversionError

_CLASSIC = Path(
    r"O:\Libraries\CL2\Re2\References\RE2 Non-RTX Unpak\natives\x64"
)
_RTX = Path(r"O:\Libraries\CL2\Re2\References\RE2 RTX Unpak\natives\stm")

# Ray-tracing builds of these files were edited by hand (damping, a bone
# angle, a header byte). The upgrade keeps the classic values.
_HAND_TUNED = frozenset({
    "sm73_429_liftkey01a.chain.21",
    "em0000_body00.chain.21",
    "em0000_shirt00.chain.21",
    "em0000_shirt01.chain.21",
    "em0000_shirt02.chain.21",
    "em0000_shirt06.chain.21",
    "em0000_shirt11.chain.21",
    "em0100_body00.chain.21",
    "em0100_shirt00.chain.21",
    "em0200_body00.chain.21",
    "em0200_shirt01.chain.21",
    "pl5001.chain.21",
})


def _minimal_chain() -> bytes:
    name = "a".encode("utf-16le") + b"\x00\x00"
    setting = bytes(128)
    group = bytearray(48)
    struct.pack_into("<Q", group, 0, 304)
    struct.pack_into("<Q", group, 8, 320)
    group[20] = 1
    body = bytearray(112)
    body += setting
    body += b"\x00" * (256 - len(body))
    body += group
    body += name
    body += b"\x00" * (320 - len(body))
    body += bytes(64)
    struct.pack_into("<I", body, 0, 21)
    body[4:8] = b"chan"
    struct.pack_into("<Q", body, 0x18, 256)
    struct.pack_into("<Q", body, 0x28, 256)
    struct.pack_into("<Q", body, 0x38, 112)
    struct.pack_into("<Q", body, 0x40, len(body))
    body[0x48] = 1
    body[0x49] = 1
    return bytes(body)


def test_classic_chain_grows_into_version_46():
    out = convert_chain_to_rt(_minimal_chain())
    assert struct.unpack_from("<I", out, 0)[0] == 46
    assert out[4:8] == b"chan"
    assert len(out) > 384
    assert "a".encode("utf-16le") + b"\x00\x00" in out
    assert struct.pack("<i", -1) in out


def test_upgrade_renames_the_chain_file(tmp_path: Path):
    natives = tmp_path / "natives" / "x64"
    natives.mkdir(parents=True)
    (natives / "pl1000.chain.21").write_bytes(_minimal_chain())
    (natives / "note.chain.21").write_bytes(b"not-a-chain")
    report = ConversionReport()
    _convert_textures_and_unsupported(
        tmp_path, report, lambda _msg: None, to_rt=True,
    )
    upgraded = natives / "pl1000.chain.46"
    assert upgraded.is_file()
    assert not (natives / "pl1000.chain.21").exists()
    assert struct.unpack_from("<I", upgraded.read_bytes(), 0)[0] == 46
    assert (natives / "note.chain.21").read_bytes() == b"not-a-chain"
    assert any(op.startswith("chain:") for op in report.converted_ops)
    assert any(op.startswith("chain:") for op in report.passthrough_ops)


def test_garbage_is_rejected():
    with pytest.raises(FormatConversionError):
        convert_chain_to_rt(b"chan-but-short")


def test_vanilla_chains_match_the_ray_tracing_build():
    if not _CLASSIC.is_dir() or not _RTX.is_dir():
        pytest.skip("RE2 chain dumps are not on this machine")
    pairs = list(_CLASSIC.rglob("*.chain.21"))
    assert pairs
    seen_hand_tuned = set()
    for path in pairs:
        vanilla = (_RTX / path.relative_to(_CLASSIC)).with_name(path.name[:-2] + "46")
        assert vanilla.is_file(), path.name
        upgraded = convert_chain_to_rt(path.read_bytes())
        retail = vanilla.read_bytes()
        if path.name in _HAND_TUNED:
            seen_hand_tuned.add(path.name)
            assert len(upgraded) == len(retail)
            continue
        assert upgraded == retail, path.name
    assert seen_hand_tuned == _HAND_TUNED
