"""Costume-select UI preview remapping (ui0601_{row}_XX)."""

from __future__ import annotations

import re
from pathlib import Path

from .character import CLAIRE_PROFILE, CharacterProfile
from .isolation import add_rename
from .outfits import (
    CLAIRE_OUTFIT_BY_UI_ID,
    LEON_OUTFIT_BY_UI_ID,
    Outfit,
)
from .paths import ensure_dir_ci, resolve_ci
from .reports import ConversionReport

UI_ROOT = "natives/x64/sectionroot/ui/ui0600"
UI_STASH = f"{UI_ROOT}/_re2oc_ui_stash"


def _ui_file_re(ui_row: str) -> re.Pattern[str]:
    return re.compile(
        rf"ui0601_{re.escape(ui_row)}_(\d{{2}})(?:_iam)?\.(?:tex|uvs|pfb)(?:\.\d+)?$",
        re.IGNORECASE,
    )


def _live_ui_dir_for(ui_root: Path, filename: str) -> Path:
    """prefab/ for .pfb*, tex/ for textures/uvs."""
    low = filename.lower()
    if ".pfb" in low:
        dest_dir = ui_root / "prefab"
    else:
        dest_dir = ui_root / "tex"
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir


def _iter_ui_files(
    ui_root: Path,
    ui_id: str | None = None,
    *,
    ui_row: str = "01",
) -> list[Path]:
    file_re = _ui_file_re(ui_row)
    hits: list[Path] = []
    for path in ui_root.rglob("*"):
        if not path.is_file():
            continue
        if "_re2oc_ui_stash" in path.as_posix().replace("\\", "/").lower():
            continue
        m = file_re.match(path.name)
        if not m:
            continue
        if ui_id is not None and m.group(1) != ui_id:
            continue
        hits.append(path)
    return hits


def _restore_ui_stash(
    staging: Path,
    report: ConversionReport,
    *,
    ui_row: str = "01",
) -> None:
    """Move stashed preview files back into live ui0600 tex/prefab folders."""
    stash = resolve_ci(staging, UI_STASH)
    if stash is None or not stash.is_dir():
        return
    ui_root = ensure_dir_ci(staging, UI_ROOT)
    file_re = _ui_file_re(ui_row)
    # Also accept the other character row so Classic stash restore works across.
    alt_re = _ui_file_re("00" if ui_row == "01" else "01")
    for path in sorted(stash.rglob("*")):
        if not path.is_file():
            continue
        if not (file_re.match(path.name) or alt_re.match(path.name)):
            continue
        dest_dir = _live_ui_dir_for(ui_root, path.name)
        dest = dest_dir / path.name
        if dest.exists() and dest.resolve() != path.resolve():
            dest.unlink()
        old_rel = path.relative_to(staging).as_posix()
        path.rename(dest)
        report.rename_ops.append(
            f"{old_rel}  ->  {dest.relative_to(staging).as_posix()} "
            "(restored UI stash)"
        )
    try:
        for sub in sorted(stash.rglob("*"), reverse=True):
            if sub.is_dir():
                try:
                    sub.rmdir()
                except OSError:
                    pass
        stash.rmdir()
    except OSError:
        pass


def _stash_ui_files(
    staging: Path,
    paths: list[Path],
    report: ConversionReport,
) -> None:
    if not paths:
        return
    stash = ensure_dir_ci(staging, UI_STASH)
    for path in sorted(paths):
        if not path.is_file():
            continue
        dest = stash / path.name
        if dest.exists() and dest.resolve() != path.resolve():
            dest.unlink()
        old_rel = path.relative_to(staging).as_posix()
        path.rename(dest)
        report.rename_ops.append(
            f"{old_rel}  ->  {dest.relative_to(staging).as_posix()} "
            "(stashed UI; Classic has no reliable preview slot)"
        )


def _remap_ui_id(
    staging: Path,
    ui_root: Path,
    old_id: str,
    new_id: str,
    source: Outfit,
    target: Outfit,
    rename_map: dict[str, str],
    report: ConversionReport,
    *,
    ui_row: str = "01",
    prefer_incoming: bool = True,
) -> None:
    if old_id == new_id:
        return
    file_re = _ui_file_re(ui_row)
    old_token = f"ui0601_{ui_row}_{old_id}"
    new_token = f"ui0601_{ui_row}_{new_id}"
    rename_map[old_token] = new_token

    matches = _iter_ui_files(ui_root, old_id, ui_row=ui_row)
    for path in sorted(matches):
        m = file_re.match(path.name)
        if m is None:
            continue
        dest = path.with_name(
            path.name[:m.start(1)] + new_id + path.name[m.end(1):]
        )
        if dest.exists() and dest.resolve() != path.resolve():
            if prefer_incoming:
                dest_rel = dest.relative_to(staging).as_posix()
                dest.unlink()
                report.removed_ops.append(dest_rel)
                report.warnings.append(
                    f"Replaced existing costume preview {dest.name} with "
                    f"{source.name} art ({source.name} → {target.name})."
                )
            else:
                rel = path.relative_to(staging).as_posix()
                path.unlink()
                report.removed_ops.append(rel)
                report.warnings.append(
                    f"Removed leftover costume preview {path.name} "
                    f"({source.name} → {target.name}; "
                    "target preview already present)."
                )
                continue
        old_rel = path.relative_to(staging).as_posix()
        path.rename(dest)
        new_rel = dest.relative_to(staging).as_posix()
        add_rename(rename_map, old_rel, new_rel)
        report.rename_ops.append(f"{path.name}  ->  {dest.name}")


def convert_costume_ui(
    staging: Path,
    sources: list[Outfit],
    target: Outfit,
    rename_map: dict[str, str],
    report: ConversionReport,
    *,
    profile: CharacterProfile | None = None,
) -> None:
    """Remap costume-select previews, or stash them for Classic targets."""
    profile = profile or target.profile or CLAIRE_PROFILE
    ui_row = profile.ui_row
    _restore_ui_stash(staging, report, ui_row=ui_row)

    ui_root = resolve_ci(staging, UI_ROOT)
    if ui_root is None:
        return

    if not target.supports_costume_ui:
        to_stash: list[Path] = []
        for source in sources:
            to_stash.extend(
                _iter_ui_files(ui_root, source.ui_id, ui_row=ui_row))
        if not to_stash:
            # The source preview id is absent. Do not stash a preview that
            # another convert in this batch just placed on a live costume id.
            if ui_row == "01":
                by_ui = CLAIRE_OUTFIT_BY_UI_ID
            elif ui_row == "00":
                by_ui = LEON_OUTFIT_BY_UI_ID
            else:
                by_ui = {}
            source_ids = {s.ui_id for s in sources}
            file_re = _ui_file_re(ui_row)
            for path in _iter_ui_files(ui_root, ui_row=ui_row):
                match = file_re.match(path.name)
                if match is not None:
                    uid = match.group(1)
                    owner = by_ui.get(uid)
                    if (
                        owner is not None
                        and owner.supports_costume_ui
                        and uid not in source_ids
                    ):
                        continue
                to_stash.append(path)
        seen: set[Path] = set()
        unique: list[Path] = []
        for p in to_stash:
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                unique.append(p)
        _stash_ui_files(staging, unique, report)
        return

    for source in sources:
        _remap_ui_id(
            staging, ui_root, source.ui_id, target.ui_id,
            source, target, rename_map, report, ui_row=ui_row,
        )

    file_re = _ui_file_re(ui_row)
    for path in list(_iter_ui_files(ui_root, ui_row=ui_row)):
        m = file_re.match(path.name)
        if not m:
            continue
        old_id = m.group(1)
        if old_id == target.ui_id:
            continue
        fake = Outfit(
            key=f"_ui_{old_id}",
            name=f"UI {old_id}",
            tag=old_id,
            primary_slot="_",
            variant_slots=(),
            body_id=profile.player_root,
            hair_id=profile.default_hair_id,
            head_id=next(iter(profile.face_ids)),
            ui_id=old_id,
            character=profile.key,
        )
        _remap_ui_id(
            staging, ui_root, old_id, target.ui_id,
            fake, target, rename_map, report,
            ui_row=ui_row,
            prefer_incoming=False,
        )
