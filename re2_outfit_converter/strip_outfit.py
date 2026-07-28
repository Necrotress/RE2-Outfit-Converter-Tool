"""Strip a Claire outfit slot from a staged mod (Delete action)."""

from __future__ import annotations

import shutil
from pathlib import Path

from .costume_ui import UI_ROOT, _iter_ui_files
from .msg_name import MSG_DIR_DLC
from .outfits import Outfit
from .paths import MESH_ROOTS, PARTS_DIR, resolve_ci
from .reports import ConversionReport


def strip_outfit_slot(
    staging: Path,
    outfit: Outfit,
    report: ConversionReport,
) -> None:
    """Remove PFB / body mesh / costume UI / outfit MSG for ``outfit``."""
    _strip_pfbs(staging, outfit, report)
    _strip_body_meshes(staging, outfit, report)
    _strip_costume_ui(staging, outfit, report)
    _strip_outfit_msg(staging, outfit, report)
    report.removed_ops.append(f"stripped outfit slot {outfit.key} ({outfit.name})")


def _strip_pfbs(staging: Path, outfit: Outfit, report: ConversionReport) -> None:
    parts = resolve_ci(staging, PARTS_DIR)
    if parts is None or not parts.is_dir():
        return
    for slot in outfit.all_slots:
        for part in ("body", "face", "hair"):
            for path in list(parts.glob(f"pl1000_{part}_{slot}.pfb*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(staging).as_posix()
                path.unlink(missing_ok=True)
                report.removed_ops.append(rel)


def _strip_body_meshes(
    staging: Path, outfit: Outfit, report: ConversionReport,
) -> None:
    body_id = outfit.body_id.lower()
    for root in MESH_ROOTS:
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


def _strip_costume_ui(
    staging: Path, outfit: Outfit, report: ConversionReport,
) -> None:
    ui_root = resolve_ci(staging, UI_ROOT)
    if ui_root is None or not ui_root.is_dir():
        return
    for path in _iter_ui_files(ui_root, outfit.ui_id):
        rel = path.relative_to(staging).as_posix()
        path.unlink(missing_ok=True)
        report.removed_ops.append(rel)


def _strip_outfit_msg(
    staging: Path, outfit: Outfit, report: ConversionReport,
) -> None:
    stem = outfit.msg_stem
    if not stem:
        return
    # Only strip DLC clairecos files. Tank/Classic Tank share mes_sys_costume
    # + reward — removing them would fight sibling slots still in the pack.
    if stem not in ("elza", "noir", "military", "original"):
        return
    parent = resolve_ci(staging, MSG_DIR_DLC)
    if parent is None or not parent.is_dir():
        return
    for path in parent.glob(f"mes_sys_clairecos_{stem}.msg*"):
        if not path.is_file():
            continue
        rel = path.relative_to(staging).as_posix()
        path.unlink(missing_ok=True)
        report.removed_ops.append(rel)
