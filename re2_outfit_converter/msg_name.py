"""Read/write Claire costume-select names in RE Engine GMSG (.msg) files."""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent / "vendor" / "remsg"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

import REMSGUtil  # noqa: E402

ENGLISH_LANG = 1  # REMSGUtil.SHORT_LANG_LU["en"]

MSG_DIR_DLC = "natives/x64/sectionroot/message/mes_other_dlc"
MSG_DIR_SYS = "natives/x64/sectionroot/message/mes_sys"

# Vanilla identity for Name / Figure rows. The game looks these up by entry
# name + GUID, not by the filename alone.
#
# DLC outfits use mes_other_dlc/mes_sys_clairecos_{stem}.msg.14 (Name+Figure
# in one file). Tank Top / Classic Tank Top patch shared mes_sys_costume +
# mes_sys_reward (different entries). Jacket / Classic Jacket are left alone
# so those renames do not fight over the same shared files in Fluffy.
_STEM_ENTRY_IDS: dict[str, dict] = {
    "military": {
        "kind": "clairecos",
        "Name": (
            "Mes_Sys_ClaireCos_Military_Name",
            "bbba3f41-539a-4933-9cb2-f9efdbdfa2b3",
            382569364,
        ),
        "Figure": (
            "Mes_Sys_ClaireCos_Military_Figure",
            "d500d96d-8eff-4118-8417-f61240dce114",
            1451028727,
        ),
    },
    "noir": {
        "kind": "clairecos",
        "Name": (
            "Mes_Sys_ClaireCos_Noir_Name",
            "9dee6487-2d3a-4a69-b4c2-560d1b762b71",
            2766408969,
        ),
        "Figure": (
            "Mes_Sys_ClaireCos_Noir_Figure",
            "77486c6e-d5bc-4c63-9e9b-9e281523fb91",
            2463474735,
        ),
    },
    "elza": {
        "kind": "clairecos",
        "Name": (
            "Mes_Sys_ClaireCos_Elza_Name",
            "8d937081-3f23-4d11-9653-169d68fe9c1f",
            848860402,
        ),
        "Figure": (
            "Mes_Sys_ClaireCos_Elza_Figure",
            "cd747350-8268-4385-920b-95878965ff52",
            2377749407,
        ),
    },
    "original": {
        "kind": "clairecos",
        "Name": (
            "Mes_Sys_ClaireCos_Original_Name",
            "74b11ee0-efaa-4218-acbb-f6d355aa3478",
            1670659039,
        ),
        "Figure": (
            "Mes_Sys_ClaireCos_Original_Figure",
            "38b660f2-d64e-4b14-b315-37d45dfd94ec",
            3087125640,
        ),
    },
    "tanktop": {
        "kind": "costume_sys",
        "Name": (
            "Mes_Sys_Costume_Name_01_01",
            "1fbdf2eb-96e2-441e-bf09-af7ffc6b0686",
            1342691026,
        ),
        "Figure": (
            "Mes_Sys_Reward_figure06",
            "048f2d42-772d-4c34-a94c-dacba2c67749",
            2479866802,
        ),
    },
    "classic_tanktop": {
        "kind": "costume_sys",
        "Name": (
            "Mes_Sys_Costume_Name_01_03",
            "173ebd7b-67f5-49b7-bc1e-19eaa2de4292",
            1040998475,
        ),
        "Figure": (
            "Mes_Sys_Reward_figure08",
            "a8eec18a-a721-42cf-a6ea-cec4b879826b",
            1594369853,
        ),
    },
}

SUPPORTED_NAME_STEMS = tuple(sorted(_STEM_ENTRY_IDS))
_COSTUME_SYS_STEMS = frozenset(
    stem for stem, meta in _STEM_ENTRY_IDS.items()
    if meta.get("kind") == "costume_sys"
)


def _assets_dir() -> Path:
    from .paths import assets_dir
    return assets_dir()


def _template_path(msg_stem: str | None = None) -> Path:
    assets = _assets_dir()
    if msg_stem:
        stem_path = assets / f"mes_sys_clairecos_{msg_stem}.msg.14"
        if stem_path.is_file():
            return stem_path
    return assets / "mes_sys_clairecos_template.msg.14"


def read_english_name(path: Path | str) -> str | None:
    """Return the English string from the Name entry, if present."""
    try:
        msg = REMSGUtil.importMSG(str(path))
    except Exception:
        return None
    if not msg.entrys:
        return None
    entry = _find_entry(msg, "_Name") or msg.entrys[0]
    if not entry.langs:
        return None
    idx = ENGLISH_LANG if ENGLISH_LANG < len(entry.langs) else 0
    text = (entry.langs[idx] or "").replace("\r\n", " ").replace("\n", " ").strip()
    return text or None


def _find_entry(msg, suffix: str):
    suffix_l = suffix.lower()
    for entry in msg.entrys:
        if (entry.name or "").lower().endswith(suffix_l):
            return entry
    return None


def _find_entry_exact(msg, name: str):
    want = name.lower()
    for entry in msg.entrys:
        if (entry.name or "").lower() == want:
            return entry
    return None


def _set_entry_identity(entry, name: str, guid: str, crc: int) -> None:
    import uuid

    entry.name = name
    entry.guid = uuid.UUID(guid)
    entry.crc = crc


def _set_all_langs(entry, text: str) -> None:
    entry.langs = [text] * len(entry.langs)


def write_outfit_name(
    template_path: Path | str,
    dest_path: Path | str,
    name: str,
    msg_stem: str,
) -> None:
    """Clone a clairecos GMSG template and write Name/Figure text for `msg_stem`."""
    text = name.strip()
    if not text:
        raise ValueError("Outfit display name is empty.")
    ids = _STEM_ENTRY_IDS.get(msg_stem.lower())
    if not ids or ids.get("kind") != "clairecos":
        raise ValueError(
            f"Unsupported clairecos costume name stem {msg_stem!r} "
            f"(expected one of: "
            f"{', '.join(s for s, v in _STEM_ENTRY_IDS.items() if v.get('kind') == 'clairecos')})."
        )

    msg = REMSGUtil.importMSG(str(template_path))
    if not msg.entrys:
        raise ValueError("Costume name template has no entries.")

    name_entry = _find_entry(msg, "_Name") or msg.entrys[0]
    figure_entry = _find_entry(msg, "_Figure")
    if figure_entry is None and len(msg.entrys) > 1:
        figure_entry = msg.entrys[1]

    n_name, n_guid, n_crc = ids["Name"]
    _set_entry_identity(name_entry, n_name, n_guid, n_crc)
    _set_all_langs(name_entry, text)

    if figure_entry is not None:
        f_name, f_guid, f_crc = ids["Figure"]
        _set_entry_identity(figure_entry, f_name, f_guid, f_crc)
        _set_all_langs(figure_entry, f"Claire ({text})")

    # Drop leftover rows from a different costume (e.g. Noir popups) so a
    # Military/Elza file never re-registers foreign GUIDs.
    keep = {id(name_entry)}
    if figure_entry is not None:
        keep.add(id(figure_entry))
    msg.entrys = [e for e in msg.entrys if id(e) in keep]
    for i, entry in enumerate(msg.entrys):
        entry.index = i

    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    REMSGUtil.exportMSG(msg, str(dest))


def _write_costume_sys_name(staging: Path, msg_stem: str, display_name: str) -> list[str]:
    """Patch shared mes_sys_costume + mes_sys_reward for Tank / Classic Tank."""
    text = display_name.strip()
    if not text:
        raise ValueError("Outfit display name is empty.")
    ids = _STEM_ENTRY_IDS[msg_stem]
    assets = _assets_dir()
    costume_tmpl = assets / "mes_sys_costume.msg.14"
    reward_tmpl = assets / "mes_sys_reward.msg.14"
    if not costume_tmpl.is_file():
        raise FileNotFoundError(f"Missing bundled costume MSG: {costume_tmpl}")
    if not reward_tmpl.is_file():
        raise FileNotFoundError(f"Missing bundled reward MSG: {reward_tmpl}")

    n_name, _n_guid, _n_crc = ids["Name"]
    f_name, _f_guid, _f_crc = ids["Figure"]
    ops: list[str] = []

    costume = REMSGUtil.importMSG(str(costume_tmpl))
    name_entry = _find_entry_exact(costume, n_name)
    if name_entry is None:
        raise ValueError(f"Costume MSG missing entry {n_name!r}")
    _set_all_langs(name_entry, text)
    costume_dest = staging / MSG_DIR_SYS / "mes_sys_costume.msg.14"
    costume_dest.parent.mkdir(parents=True, exist_ok=True)
    REMSGUtil.exportMSG(costume, str(costume_dest))
    ops.append(
        f"set in-game outfit name -> {costume_dest.name!r} "
        f"[{n_name}]: {text!r}"
    )

    reward = REMSGUtil.importMSG(str(reward_tmpl))
    figure_entry = _find_entry_exact(reward, f_name)
    if figure_entry is None:
        raise ValueError(f"Reward MSG missing entry {f_name!r}")
    figure_text = f"Claire ({text})"
    _set_all_langs(figure_entry, figure_text)
    reward_dest = staging / MSG_DIR_SYS / "mes_sys_reward.msg.14"
    REMSGUtil.exportMSG(reward, str(reward_dest))
    ops.append(
        f"set in-game figure name -> {reward_dest.name!r} "
        f"[{f_name}]: {figure_text!r}"
    )
    return ops


def _remove_clairecos_msgs(staging: Path, keep: Path | None = None) -> list[str]:
    ops: list[str] = []
    keep_res = keep.resolve() if keep is not None else None
    for path in _iter_clairecos_msgs(staging):
        if keep_res is not None and path.resolve() == keep_res:
            continue
        rel = path.relative_to(staging).as_posix()
        path.unlink(missing_ok=True)
        ops.append(f"removed leftover costume name {rel}")
    return ops


def apply_outfit_display_name(
    staging: Path,
    msg_stem: str,
    display_name: str,
    existing_msg_relpaths: list[str] | None = None,
) -> list[str]:
    """Write target costume MSG and remove conflicting clairecos MSG files.

    DLC stems write mes_sys_clairecos_{stem}.msg.14 from a bundled template.
    Tank Top / Classic Tank Top patch bundled mes_sys_costume.msg.14 +
    mes_sys_reward.msg.14 (their own entries).

    Returns a list of human-readable ops for the conversion report.
    """
    del existing_msg_relpaths  # analyzer still passes these; ignored on purpose
    stem = msg_stem.lower()
    ids = _STEM_ENTRY_IDS.get(stem)
    if not ids:
        raise ValueError(
            f"Unsupported costume name stem {stem!r} "
            f"(expected one of: {', '.join(SUPPORTED_NAME_STEMS)})."
        )

    kind = ids.get("kind", "clairecos")
    if kind == "costume_sys":
        ops = _write_costume_sys_name(staging, stem, display_name)
        ops.extend(_remove_clairecos_msgs(staging))
        return ops

    template = _template_path(stem)
    if not template.is_file():
        raise FileNotFoundError(
            f"Missing bundled costume name template: {template}")

    dest_name = f"mes_sys_clairecos_{stem}.msg.14"
    dest = staging / MSG_DIR_DLC / dest_name
    write_outfit_name(template, dest, display_name, stem)
    ops = [f"set in-game outfit name -> {dest_name!r}: {display_name!r}"]
    ops.extend(_remove_clairecos_msgs(staging, keep=dest))
    return ops


def _iter_clairecos_msgs(staging: Path) -> list[Path]:
    return [p for p in staging.rglob("mes_sys_clairecos_*.msg*") if p.is_file()]


def _remove_costume_sys_msgs(staging: Path) -> list[str]:
    """Drop shared mes_sys costume/reward name overrides."""
    ops: list[str] = []
    for rel in (
        f"{MSG_DIR_SYS}/mes_sys_costume.msg.14",
        f"{MSG_DIR_SYS}/mes_sys_reward.msg.14",
    ):
        path = staging / rel
        # Case-insensitive walk if exact path missing.
        if not path.is_file():
            parent = staging / MSG_DIR_SYS
            if parent.is_dir():
                want = Path(rel).name.lower()
                path = next(
                    (c for c in parent.iterdir()
                     if c.is_file() and c.name.lower() == want),
                    path,
                )
        if path.is_file():
            r = path.relative_to(staging).as_posix()
            path.unlink(missing_ok=True)
            ops.append(f"removed leftover costume name {r}")
    return ops


# Back-compat alias for older call sites / tests.
_remove_tanktop_sys_msgs = _remove_costume_sys_msgs


def _preserved_display_name(staging: Path) -> str | None:
    """Best-effort English name from any clairecos MSG still in staging."""
    for path in sorted(_iter_clairecos_msgs(staging), key=lambda p: p.name.lower()):
        text = read_english_name(path)
        if text:
            return text
    return None


def sync_costume_name_files(
    staging: Path,
    target,
    display_name: str | None = None,
) -> list[str]:
    """Retarget or strip costume-name MSG files for the conversion target.

    - Target with no ``msg_stem`` (Jacket / Classic Jacket): remove all
      clairecos and shared costume-sys name overrides.
    - Target with ``msg_stem`` + explicit ``display_name``: write that name.
    - Target with ``msg_stem`` and no new name: preserve text from an existing
      clairecos MSG onto the target stem (via template rewrite), then remove
      leftovers. If nothing readable remains, strip clairecos and leave vanilla.
    """
    name = (display_name or "").strip() or None
    stem = (target.msg_stem or "").lower() or None
    keep_sys = stem in _COSTUME_SYS_STEMS

    if not stem:
        ops = _remove_clairecos_msgs(staging)
        ops.extend(_remove_costume_sys_msgs(staging))
        return ops

    if name:
        ops = apply_outfit_display_name(staging, stem, name)
        if not keep_sys:
            ops.extend(_remove_costume_sys_msgs(staging))
        return ops

    preserved = _preserved_display_name(staging)
    if preserved:
        ops = apply_outfit_display_name(staging, stem, preserved)
        if not keep_sys:
            ops.extend(_remove_costume_sys_msgs(staging))
        return ops

    # No custom name to carry — drop leftover clairecos so source slot is clean.
    # Keep shared costume-sys msgs only when target uses them (already written).
    ops = _remove_clairecos_msgs(staging)
    if not keep_sys:
        ops.extend(_remove_costume_sys_msgs(staging))
    return ops
