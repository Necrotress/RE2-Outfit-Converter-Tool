"""Read/write Claire costume-select names in RE Engine GMSG (.msg) files."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
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
# in one file). Jacket / Tank Top / Classic Jacket / Classic Tank Top share
# mes_sys_costume + mes_sys_reward (different entries). Convert does not
# rename those four — use the costume name pack tool instead.
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
CLAIRECOS_MSG_STEMS = frozenset(
    stem for stem, meta in _STEM_ENTRY_IDS.items()
    if meta.get("kind") == "clairecos"
)
_COSTUME_SYS_STEMS = frozenset(
    stem for stem, meta in _STEM_ENTRY_IDS.items()
    if meta.get("kind") == "costume_sys"
)

# Shared Fluffy MSG rows in mes_sys_costume / mes_sys_reward.
# Claire Remake+Classic and Leon base outfits share those files — name pack
# writes them together. Convert UI does not rename these slots.
#
# Each slot: Name entry required; Figure optional (Leon Injured has no figure).
_SHARED_COSTUME_ENTRY_IDS: dict[str, dict] = {
    "jacket": {
        "Name": (
            "Mes_Sys_Costume_Name_01_00",
            "9d14e6bb-9377-47c7-90df-3fed8ce71f8f",
            1870534640,
        ),
        "Figure": (
            "Mes_Sys_Reward_figure05",
            "aacefbe4-3344-4a9e-b511-88264e8a5b7f",
            4278327201,
        ),
        "figure_who": "Claire",
    },
    "tanktop": {
        "Name": _STEM_ENTRY_IDS["tanktop"]["Name"],
        "Figure": _STEM_ENTRY_IDS["tanktop"]["Figure"],
        "figure_who": "Claire",
    },
    "classic_jacket": {
        "Name": (
            "Mes_Sys_Costume_Name_01_02",
            "b5535f09-a7d1-47f0-8b39-6069a4f47ffb",
            861153388,
        ),
        "Figure": (
            "Mes_Sys_Reward_figure07",
            "a29972ab-cf93-48fe-a8d7-8f3a49613830",
            2941772288,
        ),
        "figure_who": "Claire",
    },
    "classic_tanktop": {
        "Name": _STEM_ENTRY_IDS["classic_tanktop"]["Name"],
        "Figure": _STEM_ENTRY_IDS["classic_tanktop"]["Figure"],
        "figure_who": "Claire",
    },
    "leon_casual": {
        "Name": (
            "Mes_Sys_Costume_Name_00_00",
            "79685a08-9f29-4ee7-85ca-be5f5cea0c4b",
            2415760035,
        ),
        "Figure": (
            "Mes_Sys_Reward_figure00",
            "06f4e984-b2dd-4b91-b0f0-871497db1021",
            1840678512,
        ),
        "figure_who": "Leon",
    },
    "leon_police": {
        "Name": (
            "Mes_Sys_Costume_Name_00_01",
            "8f75777f-78a5-4ec2-98bf-cec29d67de77",
            1036518072,
        ),
        "Figure": (
            "Mes_Sys_Reward_figure01",
            "e696a97c-c791-4541-9cf3-2b4450ef12e2",
            2942759806,
        ),
        "figure_who": "Leon",
    },
    "leon_police_injured": {
        "Name": (
            "Mes_Sys_Costume_Name_00_02",
            "44f45b97-39b8-48b5-8f39-5f05c2e9fd1b",
            683729378,
        ),
        "Figure": None,
        "figure_who": "Leon",
    },
    "leon_classic_police": {
        "Name": (
            "Mes_Sys_Costume_Name_00_03",
            "b6f10c3d-1e07-4156-a370-8c16e5a7b1f0",
            3548447256,
        ),
        "Figure": (
            "Mes_Sys_Reward_figure02",
            "c446b934-f7d3-4767-8abc-c059eea526e4",
            611718085,
        ),
        "figure_who": "Leon",
    },
    "leon_classic_police_injured": {
        "Name": (
            "Mes_Sys_Costume_Name_00_04",
            "49aac74a-bfbd-48a8-8bc3-31d55b0f9251",
            1154086672,
        ),
        "Figure": None,
        "figure_who": "Leon",
    },
}

SHARED_COSTUME_NAME_VANILLA: dict[str, str] = {
    "jacket": "Jacket",
    "tanktop": "Tank Top",
    "classic_jacket": "Classic Jacket",
    "classic_tanktop": "Classic Tank Top",
    "leon_casual": "Casual",
    "leon_police": "Police",
    "leon_police_injured": "Police (Injured)",
    "leon_classic_police": "Classic Police",
    "leon_classic_police_injured": "Classic Police (Injured)",
}

SHARED_COSTUME_NAME_LABELS: dict[str, str] = {
    "jacket": "Jacket",
    "tanktop": "Tank Top",
    "classic_jacket": "Classic Jacket",
    "classic_tanktop": "Classic Tank Top",
    "leon_casual": "Casual",
    "leon_police": "Police",
    "leon_police_injured": "Police (Injured)",
    "leon_classic_police": "Classic Police",
    "leon_classic_police_injured": "Classic Police (Injured)",
}

CLAIRE_NAME_PACK_KEYS: tuple[str, ...] = (
    "jacket", "tanktop", "classic_jacket", "classic_tanktop",
)
LEON_NAME_PACK_KEYS: tuple[str, ...] = (
    "leon_casual",
    "leon_police",
    "leon_police_injured",
    "leon_classic_police",
    "leon_classic_police_injured",
)
SHARED_COSTUME_NAME_KEYS: tuple[str, ...] = (
    *CLAIRE_NAME_PACK_KEYS, *LEON_NAME_PACK_KEYS,
)

# Convert-UI "shared name pack" hint still means Claire's four Remake slots.
CLAIRE_SHARED_NAME_PACK_KEYS = frozenset(CLAIRE_NAME_PACK_KEYS)


def resolve_shared_costume_names(
    field_values: dict[str, str],
) -> dict[str, str]:
    """Resolve dialog fields to final strings (empty → vanilla).

    Requires at least one field that differs from that slot's vanilla name.
    Resolves every Claire + Leon name-pack slot.
    """
    resolved: dict[str, str] = {}
    changed = False
    for key, vanilla in SHARED_COSTUME_NAME_VANILLA.items():
        text = (field_values.get(key) or "").strip() or vanilla
        resolved[key] = text
        if text != vanilla:
            changed = True
    if not changed:
        raise ValueError(
            "Change at least one name (leave others blank for vanilla)."
        )
    return resolved


def write_shared_costume_names(
    staging: Path,
    names: dict[str, str],
) -> list[str]:
    """Write Claire + Leon shared costume/reward name rows into staging."""
    for key in SHARED_COSTUME_NAME_KEYS:
        if key not in names or not (names[key] or "").strip():
            raise ValueError(f"Missing shared costume name for {key!r}")

    assets = _assets_dir()
    costume_tmpl = assets / "mes_sys_costume.msg.14"
    reward_tmpl = assets / "mes_sys_reward.msg.14"
    if not costume_tmpl.is_file():
        raise FileNotFoundError(f"Missing bundled costume MSG: {costume_tmpl}")
    if not reward_tmpl.is_file():
        raise FileNotFoundError(f"Missing bundled reward MSG: {reward_tmpl}")

    costume = REMSGUtil.importMSG(str(costume_tmpl))
    reward = REMSGUtil.importMSG(str(reward_tmpl))
    ops: list[str] = []

    for key in SHARED_COSTUME_NAME_KEYS:
        text = names[key].strip()
        ids = _SHARED_COSTUME_ENTRY_IDS[key]
        n_name, _n_guid, _n_crc = ids["Name"]
        name_entry = _find_entry_exact(costume, n_name)
        if name_entry is None:
            raise ValueError(f"Costume MSG missing entry {n_name!r}")
        _set_all_langs(name_entry, text)
        ops.append(
            f"set in-game outfit name -> 'mes_sys_costume.msg.14' "
            f"[{n_name}]: {text!r}"
        )
        fig = ids.get("Figure")
        if fig is not None:
            f_name, _f_guid, _f_crc = fig
            figure_entry = _find_entry_exact(reward, f_name)
            if figure_entry is None:
                raise ValueError(f"Reward MSG missing entry {f_name!r}")
            who = ids.get("figure_who") or "Claire"
            figure_text = f"{who} ({text})"
            _set_all_langs(figure_entry, figure_text)
            ops.append(
                f"set in-game figure name -> 'mes_sys_reward.msg.14' "
                f"[{f_name}]: {figure_text!r}"
            )

    costume_dest = staging / MSG_DIR_SYS / "mes_sys_costume.msg.14"
    reward_dest = staging / MSG_DIR_SYS / "mes_sys_reward.msg.14"
    costume_dest.parent.mkdir(parents=True, exist_ok=True)
    REMSGUtil.exportMSG(costume, str(costume_dest))
    REMSGUtil.exportMSG(reward, str(reward_dest))
    return ops


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


def _keep_path_set(keep: Path | Iterable[Path] | None) -> set[Path]:
    if keep is None:
        return set()
    if isinstance(keep, Path):
        return {keep.resolve()}
    return {Path(p).resolve() for p in keep}


def _remove_clairecos_msgs(
    staging: Path,
    keep: Path | Iterable[Path] | None = None,
) -> list[str]:
    ops: list[str] = []
    keep_res = _keep_path_set(keep)
    for path in _iter_clairecos_msgs(staging):
        if path.resolve() in keep_res:
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
    *,
    cleanup: bool = True,
) -> list[str]:
    """Write target costume MSG and optionally remove conflicting clairecos MSGs.

    DLC stems write mes_sys_clairecos_{stem}.msg.14 from a bundled template.
    Tank Top / Classic Tank Top patch bundled mes_sys_costume.msg.14 +
    mes_sys_reward.msg.14 (their own entries).

    Set ``cleanup=False`` when writing several stems in one convert pass, then
    call ``_remove_clairecos_msgs`` once with the full keep set.

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
        if cleanup:
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
    if cleanup:
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

    - Jacket / Tank Top / Classic* targets: strip clairecos and shared
      costume-sys overrides (rename those four via the name pack tool).
    - DLC ``msg_stem`` + explicit ``display_name``: write that clairecos name.
    - DLC ``msg_stem`` and no new name: preserve text from an existing
      clairecos MSG onto the target stem, then remove leftovers.

    For multi-target converts, use ``sync_costume_names_for_targets`` instead so
    sibling clairecos files are not deleted between passes.
    """
    name = (display_name or "").strip() or None
    stem = (target.msg_stem or "").lower() or None

    # Shared mes_sys rows are owned by the costume name pack, not convert.
    if not stem or stem in _COSTUME_SYS_STEMS:
        ops = _remove_clairecos_msgs(staging)
        ops.extend(_remove_costume_sys_msgs(staging))
        return ops

    if name:
        ops = apply_outfit_display_name(staging, stem, name)
        ops.extend(_remove_costume_sys_msgs(staging))
        return ops

    preserved = _preserved_display_name(staging)
    if preserved:
        ops = apply_outfit_display_name(staging, stem, preserved)
        ops.extend(_remove_costume_sys_msgs(staging))
        return ops

    ops = _remove_clairecos_msgs(staging)
    ops.extend(_remove_costume_sys_msgs(staging))
    return ops


def sync_costume_names_for_targets(
    staging: Path,
    targets: Sequence[object],
    *,
    display_name: str | None = None,
    name_target: object | None = None,
    display_names: dict[str, str] | None = None,
) -> list[str]:
    """Write costume-name MSGs for every convert target in one pass.

    Unlike looping ``sync_costume_name_files``, this keeps all target clairecos
    files (Noir + Military, etc.) instead of deleting siblings on each call.

    Shared Jacket/Tank/Classic MSG files are always stripped on convert —
    rename those with the costume name pack tool.

    ``display_names`` maps target outfit key → explicit in-game name. When set,
    those names win per clairecos target; other targets fall back to preserved.
    """
    targets = list(targets)
    if not targets:
        return []

    names_by_key = {
        str(k): (v or "").strip()
        for k, v in (display_names or {}).items()
        if (v or "").strip()
    }
    explicit = (display_name or "").strip() or None

    if (
        len(targets) == 1
        and name_target is None
        and not names_by_key
    ):
        return sync_costume_name_files(staging, targets[0], display_name)

    # Capture before any rewrite so secondary targets share the source name.
    preserved = _preserved_display_name(staging)

    stemmed = [
        t for t in targets
        if (getattr(t, "msg_stem", None) or "")
        and str(t.msg_stem).lower() in CLAIRECOS_MSG_STEMS
    ]
    if not stemmed:
        ops = _remove_clairecos_msgs(staging)
        ops.extend(_remove_costume_sys_msgs(staging))
        return ops

    ops: list[str] = []
    keep_clairecos: list[Path] = []

    for t in stemmed:
        stem = str(t.msg_stem).lower()
        key = getattr(t, "key", None)
        use_name: str | None = None
        if key is not None and key in names_by_key:
            use_name = names_by_key[key]
        elif (
            name_target is not None
            and key == getattr(name_target, "key", None)
            and explicit
        ):
            use_name = explicit
        elif (
            explicit
            and name_target is None
            and not names_by_key
            and t is stemmed[0]
        ):
            use_name = explicit
        else:
            use_name = preserved

        if not use_name:
            continue

        ops.extend(
            apply_outfit_display_name(
                staging, stem, use_name, cleanup=False)
        )
        keep_clairecos.append(
            staging / MSG_DIR_DLC / f"mes_sys_clairecos_{stem}.msg.14"
        )

    ops.extend(_remove_clairecos_msgs(staging, keep=keep_clairecos))
    ops.extend(_remove_costume_sys_msgs(staging))
    return ops
