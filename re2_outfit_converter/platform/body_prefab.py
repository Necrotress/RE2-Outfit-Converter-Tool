"""Write the ray-tracing body prefab the game actually loads.

RTX ignores ``.pfb.16``. Elza, Military, and '98 ship a ``.pfb.17`` with
no chain, so a converted ``pl1004.chain.46`` never runs and the vest,
cardigan, and breasts stay still. Jacket's ``.pfb.17`` already names
``pl1000.chain``, which is why an in-place chain file is enough there.

A mod body prefab is usually a vanilla classic body prefab with in-place
string edits (mesh, material, chain). The matching ray-tracing prefab is
that same edit applied to the RT twin, so the offset table stays valid.
"""

from __future__ import annotations

from pathlib import Path

from ..paths import assets_dir

# Body chains the ray-tracing pak already has. A private chain such as
# pl1004.chain has to be in the mod or the prefab must not name it.
_PAK_CHAINS = frozenset({
    "pl1000.chain",
    "pl1005.chain",
    "pl1057.chain",
    "pl1070.chain",
    "pl1071.chain",
    "pl1075.chain",
})
_TEMPLATE_DIR = "body_prefab"


def publish_rt_body_prefabs(staging: Path, report) -> None:
    """Add a ``.pfb.17`` next to a classic body prefab RTX would ignore."""
    natives = staging / "natives"
    if not natives.is_dir():
        return
    pairs = _template_pairs()
    if not pairs:
        return
    shipped = _chain_stems(natives)
    for prefab in natives.rglob("pl1000_body_*.pfb.16"):
        if not prefab.is_file():
            continue
        dest = prefab.with_name(prefab.name.split(".", 1)[0] + ".pfb.17")
        if dest.is_file():
            continue
        try:
            mod = prefab.read_bytes()
        except OSError as exc:
            report.warnings.append(f"{prefab.name}: {exc}")
            continue
        derived = _derive(mod, pairs)
        if derived is None:
            if _custom_chains(mod):
                report.warnings.append(
                    f"{prefab.name}: body chain was not attached to a ray "
                    "tracing prefab, so those parts stay on the vanilla rig."
                )
            continue
        missing = [
            stem for stem in _custom_chains(derived)
            if stem not in shipped
        ]
        if missing:
            report.warnings.append(
                f"{prefab.name}: ray tracing prefab was not written because "
                f"{', '.join(missing)} is not in the mod."
            )
            continue
        dest.write_bytes(derived)
        chains = ", ".join(sorted(_chain_stems_in(derived))) or "its chain"
        report.warnings.append(
            f"{prefab.name}: ray tracing body prefab loads {chains}."
        )


def _template_pairs() -> list[tuple[bytes, bytes]]:
    folder = assets_dir() / _TEMPLATE_DIR
    if not folder.is_dir():
        return []
    pairs: list[tuple[bytes, bytes]] = []
    for classic in sorted(folder.glob("*.pfb.16")):
        rt = classic.with_name(classic.name.replace(".pfb.16", ".pfb.17"))
        if rt.is_file():
            pairs.append((classic.read_bytes(), rt.read_bytes()))
    return pairs


def _derive(mod: bytes, pairs: list[tuple[bytes, bytes]]) -> bytes | None:
    found: list[tuple[int, int, bytes]] = []
    for classic, rt in pairs:
        parsed = _edits(classic, mod)
        if parsed is None:
            continue
        edits, zeros = parsed
        if not edits:
            continue
        applied = _apply(rt, edits, zeros)
        if applied is None:
            continue
        found.append((len(edits), len(zeros), applied))
    if not found:
        return None
    found.sort(key=lambda item: (item[0], item[1]))
    best = found[0]
    tied = [item for item in found if item[0] == best[0] and item[1] == best[1]]
    if len({item[2] for item in tied}) > 1:
        return None
    return best[2]


def _edits(template: bytes, mod: bytes) -> tuple[list[tuple[str, str]], list[bytes]] | None:
    """In-place string swaps, plus dwords the mod cleared."""
    if len(template) != len(mod):
        return None
    covered = bytearray(len(template))
    edits: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(template):
        slot = _wstring_at(template, i)
        if slot is None:
            i += 2
            continue
        text, end = slot
        covered[i:end] = b"\x01" * (end - i)
        if template[i:end] != mod[i:end]:
            parsed = _wstring_at(mod, i)
            if parsed is None:
                return None
            new_text, new_end = parsed
            if new_end > end or len(new_text) > len(text):
                return None
            if mod[new_end:end] != b"\x00" * (end - new_end):
                return None
            edits.append((text, new_text))
        i = end if end % 2 == 0 else end + 1
    zeros: list[bytes] = []
    i = 0
    while i < len(template):
        if template[i] == mod[i] or covered[i]:
            i += 1
            continue
        if (
            i % 4 == 0
            and i + 4 <= len(template)
            and not any(covered[i:i + 4])
            and mod[i:i + 4] == b"\x00\x00\x00\x00"
        ):
            zeros.append(template[i:i + 4])
            i += 4
            continue
        return None
    return edits, zeros


def _apply(
    rt: bytes,
    edits: list[tuple[str, str]],
    zeros: list[bytes],
) -> bytes | None:
    data = bytearray(rt)
    by_old: dict[str, str] = {}
    for old, new in edits:
        if old in by_old and by_old[old] != new:
            return None
        by_old[old] = new
    ordered = sorted(by_old.items(), key=lambda pair: len(pair[0]), reverse=True)
    for old, new in ordered:
        old_b = old.encode("utf-16le") + b"\x00\x00"
        if old_b not in data:
            return None
        new_b = (new.encode("utf-16le") + b"\x00\x00").ljust(len(old_b), b"\x00")
        if len(new_b) != len(old_b):
            return None
        data = bytearray(bytes(data).replace(old_b, new_b))
    for dword in zeros:
        start = 0
        hits: list[int] = []
        while True:
            idx = data.find(dword, start)
            if idx < 0:
                break
            hits.append(idx)
            start = idx + 1
        if len(hits) == 1:
            at = hits[0]
            data[at:at + 4] = b"\x00\x00\x00\x00"
    return bytes(data)


def _wstring_at(data: bytes, pos: int) -> tuple[str, int] | None:
    if pos % 2 or pos + 5 >= len(data):
        return None
    if data[pos + 1] != 0 or not (32 <= data[pos] < 127):
        return None
    chars: list[str] = []
    j = pos
    while j + 1 < len(data) and data[j + 1] == 0 and 32 <= data[j] < 127:
        chars.append(chr(data[j]))
        j += 2
    if len(chars) < 2 or j + 1 >= len(data) or data[j] != 0 or data[j + 1] != 0:
        return None
    return "".join(chars), j + 2


def _chain_stems(natives: Path) -> set[str]:
    found: set[str] = set()
    for path in natives.rglob("*"):
        if not path.is_file():
            continue
        low = path.name.lower()
        if ".chain." not in low:
            continue
        found.add(low.split(".chain.", 1)[0] + ".chain")
    return found


def _chain_stems_in(data: bytes) -> set[str]:
    stems: set[str] = set()
    i = 0
    while i + 1 < len(data):
        slot = _wstring_at(data, i)
        if slot is None:
            i += 2
            continue
        text, end = slot
        if text.lower().endswith(".chain"):
            stems.add(text.replace("\\", "/").rsplit("/", 1)[-1].lower())
        i = end if end % 2 == 0 else end + 1
    return stems


def _custom_chains(data: bytes) -> list[str]:
    return sorted(stem for stem in _chain_stems_in(data) if stem not in _PAK_CHAINS)
