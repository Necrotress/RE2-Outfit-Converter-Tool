"""Costume-select UI preview remapping (ui0601_01_XX)."""

from __future__ import annotations

import re
from pathlib import Path

from .isolation import add_rename
from .outfits import Outfit
from .paths import ensure_dir_ci, resolve_ci
from .reports import ConversionReport

UI_ROOT = "natives/x64/sectionroot/ui/ui0600"
UI_STASH = f"{UI_ROOT}/_re2oc_ui_stash"
_UI_FILE_RE = re.compile(
    r"ui0601_01_(\d{2})(?:_iam)?\.(?:tex|uvs|pfb)(?:\.\d+)?$",
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


def _iter_ui_files(ui_root: Path, ui_id: str | None = None) -> list[Path]:
    hits: list[Path] = []
    for path in ui_root.rglob("*"):
        if not path.is_file():
            continue
        # Never treat stash contents as live overrides.
        if "_re2oc_ui_stash" in path.as_posix().replace("\\", "/").lower():
            continue
        m = _UI_FILE_RE.match(path.name)
        if not m:
            continue
        if ui_id is not None and m.group(1) != ui_id:
            continue
        hits.append(path)
    return hits


def _restore_ui_stash(staging: Path, report: ConversionReport) -> None:
    """Move stashed preview files back into live ui0600 tex/prefab folders."""
    stash = resolve_ci(staging, UI_STASH)
    if stash is None or not stash.is_dir():
        return
    ui_root = ensure_dir_ci(staging, UI_ROOT)
    for path in sorted(stash.rglob("*")):
        if not path.is_file():
            continue
        if not _UI_FILE_RE.match(path.name):
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
    # Clean empty stash dirs.
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
) -> None:
    if old_id == new_id:
        return
    old_token = f"ui0601_01_{old_id}"
    new_token = f"ui0601_01_{new_id}"
    rename_map[old_token] = new_token

    matches = _iter_ui_files(ui_root, old_id)
    for path in sorted(matches):
        m = _UI_FILE_RE.match(path.name)
        if m is None:
            continue
        dest = path.with_name(
            path.name[:m.start(1)] + new_id + path.name[m.end(1):]
        )
        if dest.exists() and dest.resolve() != path.resolve():
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
) -> None:
    """Remap costume-select previews, or stash them for Classic targets.

    Supported targets (Jacket / Tank / DLC): rename ``ui0601_01_XX`` to the
    target id and register bare-token patches. Classic targets cannot host
    reliable overrides — previews are moved under ``_re2oc_ui_stash`` so the
    game ignores them, then restored on a later convert to a supported slot.
    """
    # Pull any previously stashed previews back before remapping/stashing.
    _restore_ui_stash(staging, report)

    ui_root = resolve_ci(staging, UI_ROOT)
    if ui_root is None:
        return

    if not target.supports_costume_ui:
        to_stash: list[Path] = []
        for source in sources:
            to_stash.extend(_iter_ui_files(ui_root, source.ui_id))
        # Also stash any other live ui0601 previews so Classic converts never
        # leave DLC art on the wrong slot.
        if not to_stash:
            to_stash = _iter_ui_files(ui_root)
        # Dedupe
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
            source, target, rename_map, report,
        )

    # After restore, stashed files may still carry a prior DLC id that differs
    # from the From outfit (e.g. Classic From after Elza→Classic stash of 08).
    # Remap any remaining live preview ids onto the target.
    for path in list(_iter_ui_files(ui_root)):
        m = _UI_FILE_RE.match(path.name)
        if not m:
            continue
        old_id = m.group(1)
        if old_id == target.ui_id:
            continue
        # Synthetic source for messaging only.
        fake = Outfit(
            key=f"_ui_{old_id}",
            name=f"UI {old_id}",
            tag=old_id,
            primary_slot="_",
            variant_slots=(),
            body_id="pl1000",
            hair_id="pl1070",
            head_id="pl1050",
            ui_id=old_id,
        )
        _remap_ui_id(
            staging, ui_root, old_id, target.ui_id,
            fake, target, rename_map, report,
        )
