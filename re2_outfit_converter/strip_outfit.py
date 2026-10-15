"""Strip an outfit slot from a staged mod (Delete action)."""

from __future__ import annotations

import shutil
from pathlib import Path

from .costume_ui import UI_ROOT, _iter_ui_files
from .msg_name import DLC_COS_MSG_STEMS, MSG_DIR_DLC, _cos_dest_name
from .outfits import EXCLUSIVE_PART_IDS, Outfit
from .paths import mesh_roots, parts_dir, resolve_ci
from .reports import ConversionReport


def strip_outfit_slot(
    staging: Path,
    outfit: Outfit,
    report: ConversionReport,
    *,
    keep_exclusive_ids: set[str] | None = None,
) -> None:
    """Remove PFB / body mesh / costume UI / outfit MSG for ``outfit``."""
    _strip_pfbs(staging, outfit, report)
    _strip_body_meshes(staging, outfit, report)
    _strip_exclusive_hair(
        staging, outfit, report, keep_exclusive_ids=keep_exclusive_ids)
    _strip_costume_ui(staging, outfit, report)
    _strip_outfit_msg(staging, outfit, report)
    report.removed_ops.append(f"stripped outfit slot {outfit.key} ({outfit.name})")


def _strip_pfbs(staging: Path, outfit: Outfit, report: ConversionReport) -> None:
    profile = outfit.profile
    parts = resolve_ci(staging, parts_dir(profile))
    if parts is None or not parts.is_dir():
        return
    root = profile.player_root
    for slot in outfit.all_slots:
        for part in ("body", "face", "hair"):
            for path in list(parts.glob(f"{root}_{part}_{slot}.pfb*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(staging).as_posix()
                path.unlink(missing_ok=True)
                report.removed_ops.append(rel)


def _strip_body_meshes(
    staging: Path, outfit: Outfit, report: ConversionReport,
) -> None:
    body_id = outfit.body_id.lower()
    for root in mesh_roots(outfit.profile):
        root_dir = resolve_ci(staging, root)
        if root_dir is None or not root_dir.is_dir():
            continue
        for entry in list(root_dir.iterdir()):
            name_low = entry.name.lower()
            if not (
                name_low == body_id
                or name_low.startswith(body_id + ".")
                or name_low.startswith(body_id + "_")
            ):
                continue
            rel = entry.relative_to(staging).as_posix()
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
            report.removed_ops.append(rel)


def _strip_exclusive_hair(
    staging: Path,
    outfit: Outfit,
    report: ConversionReport,
    *,
    keep_exclusive_ids: set[str] | None = None,
) -> None:
    """Remove this outfit's exclusive hat/headband mesh if not kept by converts."""
    hair_id = outfit.hair_id.lower()
    if hair_id not in EXCLUSIVE_PART_IDS:
        return
    keep = {x.lower() for x in (keep_exclusive_ids or set())}
    if hair_id in keep:
        return
    for root in mesh_roots(outfit.profile):
        root_dir = resolve_ci(staging, root)
        if root_dir is None or not root_dir.is_dir():
            continue
        for entry in list(root_dir.iterdir()):
            name_low = entry.name.lower()
            if not (
                name_low == hair_id
                or name_low.startswith(hair_id + ".")
                or name_low.startswith(hair_id + "_")
            ):
                continue
            rel = entry.relative_to(staging).as_posix()
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
            report.removed_ops.append(rel)
            report.rename_ops.append(
                f"stripped exclusive hair {entry.name} with {outfit.name}"
            )


def _strip_costume_ui(
    staging: Path, outfit: Outfit, report: ConversionReport,
) -> None:
    ui_root = resolve_ci(staging, UI_ROOT)
    if ui_root is None or not ui_root.is_dir():
        return
    for path in _iter_ui_files(
        ui_root, outfit.ui_id, ui_row=outfit.profile.ui_row,
    ):
        rel = path.relative_to(staging).as_posix()
        path.unlink(missing_ok=True)
        report.removed_ops.append(rel)


def _strip_outfit_msg(
    staging: Path, outfit: Outfit, report: ConversionReport,
) -> None:
    stem = outfit.msg_stem
    if not stem:
        return
    # Only strip DLC clairecos/leoncos files. Base slots use the name pack.
    if stem not in DLC_COS_MSG_STEMS:
        return
    parent = resolve_ci(staging, MSG_DIR_DLC)
    if parent is None or not parent.is_dir():
        return
    dest = _cos_dest_name(stem)
    base = dest.split(".msg")[0].lower()
    for path in parent.iterdir():
        if not path.is_file():
            continue
        if not path.name.lower().startswith(base):
            continue
        rel = path.relative_to(staging).as_posix()
        path.unlink(missing_ok=True)
        report.removed_ops.append(rel)
