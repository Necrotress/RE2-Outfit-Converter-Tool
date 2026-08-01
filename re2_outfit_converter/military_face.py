"""Auto-seed / strip Claire face textures for Military and Tank Top.

Military's vanilla look uses dirty ``pl1050_04`` face textures. Body-only mods
that land on Military without their own face data get Claire's clean default
face seeded onto the active ``*_04`` face folder (private id after isolation,
or vanilla ``pl1050_04``).

Tank Top does not use the Military ``*_04`` face variant. Leftover ``*_04``
face textures (often identical to our clean seed, but still the wrong slot)
are removed so the game falls back to Claire's default face. Face PFBs are
left alone.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .analyzer import AnalysisResult
from .outfits import Outfit
from .paths import MESH_ROOTS, PARTS_DIR, assets_dir, ensure_dir_ci, resolve_ci
from .reports import ConversionReport

_CLEAN_TEMPLATE = "military_face_clean"
# Clean Claire face textures live on the Military dirty-face path (pl1050_04).
_CLEAN_DEST = {
    "sectionroot": (
        "natives/x64/sectionroot/character/player/pl1000/pl1050/pl1050_04"
    ),
    "streaming": (
        "natives/x64/streaming/sectionroot/character/player/pl1000/"
        "pl1050/pl1050_04"
    ),
}
_SEED_TARGETS = frozenset({"military", "tanktop"})


def analysis_has_custom_face(analysis: AnalysisResult) -> bool:
    """True if the *original* analysis lists face PFB or ``pl1050_04`` files.

    Prefer :func:`staging_has_custom_face` after Delete/strip — analysis can
    still list face PFBs that were removed from staging.
    """
    if any(p.part == "face" for p in analysis.claire_pfbs):
        return True
    for rel in analysis.natives_files:
        low = rel.lower().replace("\\", "/")
        if "/pl1050/pl1050_04/" in low or "/pl1050/pl1050_04." in low:
            return True
    return False


def staging_has_face_pfb(staging: Path) -> bool:
    """True if staging still has Claire face PFB overrides."""
    parts = resolve_ci(staging, PARTS_DIR)
    if parts is not None and parts.is_dir():
        return any(parts.glob("pl1000_face_*.pfb*"))
    return False


def _face04_dirs(staging: Path) -> list[tuple[str, Path]]:
    """Return ``(mesh_id, plXXXX_04_dir)`` for each face-04 folder in staging.

    Matches vanilla ``pl1050/pl1050_04`` and isolated ``pl18xx/pl18xx_04``.
    """
    found: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for root in MESH_ROOTS:
        root_dir = resolve_ci(staging, root)
        if root_dir is None or not root_dir.is_dir():
            continue
        for path in root_dir.rglob("*"):
            if not path.is_dir():
                continue
            name = path.name.lower()
            parent = path.parent.name.lower()
            if (
                len(name) == 9
                and name.startswith("pl")
                and name.endswith("_04")
                and parent == name[:6]
            ):
                key = str(path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append((parent, path))
    return found


def staging_has_custom_face(staging: Path) -> bool:
    """True if staging still has face PFBs or any ``plXXXX_04`` face textures."""
    if staging_has_face_pfb(staging):
        return True
    return bool(_face04_dirs(staging))


def _strip_face04_dirs(staging: Path, report: ConversionReport) -> int:
    """Remove Military ``*_04`` face texture folders. Returns dirs removed."""
    removed = 0
    for _mesh_id, dest_dir in _face04_dirs(staging):
        rel = dest_dir.relative_to(staging).as_posix()
        shutil.rmtree(dest_dir, ignore_errors=True)
        # Drop empty parent face folder (e.g. pl1813/) when it only held _04.
        parent = dest_dir.parent
        try:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                report.removed_ops.append(
                    f"removed empty face folder "
                    f"{parent.relative_to(staging).as_posix()}/"
                )
        except OSError:
            pass
        report.removed_ops.append(
            f"removed Military face textures {rel}/ "
            f"(Tank Top uses Claire default face)"
        )
        removed += 1
    return removed


def _seed_clean_vanilla(
    staging: Path,
    target: Outfit,
    report: ConversionReport,
) -> int:
    """Create vanilla ``pl1050/pl1050_04`` clean textures (body-only Military)."""
    template = assets_dir() / _CLEAN_TEMPLATE
    wrote = 0
    for key, dest_rel in _CLEAN_DEST.items():
        src_dir = template / key
        if not src_dir.is_dir():
            continue
        dest_dir = ensure_dir_ci(staging, dest_rel)
        for src in sorted(src_dir.iterdir()):
            if not src.is_file():
                continue
            dest = dest_dir / src.name
            shutil.copy2(src, dest)
            wrote += 1
            report.rename_ops.append(
                f"{target.name} clean face: {src.name}  ->  "
                f"{dest.relative_to(staging).as_posix()}"
            )
    return wrote


def ensure_military_clean_face(
    staging: Path,
    target: Outfit,
    analysis: AnalysisResult,
    report: ConversionReport,
) -> None:
    """Fix face textures for Military / Tank Top converts.

    Military: seed Claire default onto active ``*_04`` face folders when the
    mod has no face PFBs and no ``*_04`` textures yet. If ``*_04`` already
    exists, keep it (intentional Military / mod face).

    Tank Top: when there are no face PFBs, remove leftover ``*_04`` Military
    face texture folders so Claire's default face is used. Do not seed
    ``*_04`` onto Tank Top.
    """
    _ = analysis
    if target.key not in _SEED_TARGETS:
        return

    if staging_has_face_pfb(staging):
        report.rename_ops.append(
            f"face: kept mod face data ({target.name} clean-face seed skipped)"
        )
        return

    if target.key == "tanktop":
        removed = _strip_face04_dirs(staging, report)
        if removed:
            report.rename_ops.append(
                f"face: stripped Military *_04 face textures for {target.name} "
                f"({removed} folder(s); Claire default face)"
            )
        return

    # Military — keep existing *_04; only seed when absent.
    existing = _face04_dirs(staging)
    if existing:
        report.rename_ops.append(
            f"face: kept mod face data ({target.name} clean-face seed skipped)"
        )
        return

    template = assets_dir() / _CLEAN_TEMPLATE
    if not template.is_dir():
        report.warnings.append(
            f"{target.name} convert needs default face textures but the "
            f"bundled template is missing ({_CLEAN_TEMPLATE})."
        )
        return

    wrote = _seed_clean_vanilla(staging, target, report)
    if wrote <= 0:
        report.warnings.append(
            f"{target.name} convert needed default face textures but no "
            "template files were found."
        )
    else:
        report.rename_ops.append(
            f"face: seeded Claire default face for {target.name} "
            "(mod had no custom face data)"
        )
