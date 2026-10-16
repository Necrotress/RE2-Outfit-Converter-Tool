"""Face textures for Military and Tank Top.

Military loads ``pl1050_04``. Tank Top loads ``pl1050_02`` (costume 3) and
``pl1050_03`` (costume 4). Those converts copy the bundled Claire face
onto those folders when the mod has no face of its own. A classic face
prefab is not face-texture data: ray tracing ignores it, so it does not
block the copy. An authored slot folder, or any face albedo such as
``pl1060_face_albm``, is left as shipped. The shared ``pl1050`` head is
never written.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .analyzer import AnalysisResult
from .outfits import Outfit
from .paths import (
    MESH_ROOTS,
    PARTS_DIR,
    assets_dir,
    ensure_dir_ci,
    natives_platform,
    resolve_ci,
)
from .reports import ConversionReport

_CLEAN_TEMPLATE = "military_face_clean"
_TEMPLATE_SUFFIX = "04"
_SEED_TARGETS = frozenset({"military", "tanktop"})
# Folders the game actually samples for that outfit. Not a private face id.
_SLOT_SUFFIXES = {
    "military": ("04",),
    "tanktop": ("02", "03"),
}


def _search_roots() -> list[str]:
    """Claire mesh roots on classic and ray tracing."""
    roots: list[str] = []
    for root in MESH_ROOTS:
        roots.append(root)
        stm = root.replace("natives/x64/", "natives/stm/", 1)
        if stm not in roots:
            roots.append(stm)
    return roots


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


def analysis_ships_slot_face(analysis: AnalysisResult, target_key: str) -> bool:
    """True when the package already contains that outfit's face textures.

    Military is ``pl1050/pl1050_04``. Tank Top is ``pl1050_02`` or
    ``pl1050_03``. A face prefab does not count.
    """
    suffixes = _SLOT_SUFFIXES.get(target_key, ())
    if not suffixes:
        return False
    for rel in analysis.natives_files:
        low = rel.lower().replace("\\", "/")
        for suf in suffixes:
            if (
                f"/pl1050/pl1050_{suf}/" in low
                or f"/pl1050/pl1050_{suf}." in low
            ):
                return True
    return False


def _face04_dirs(staging: Path) -> list[tuple[str, Path]]:
    """Return ``(mesh_id, plXXXX_04_dir)`` for each face-04 folder in staging.

    Matches vanilla ``pl1050/pl1050_04`` and isolated ``pl18xx/pl18xx_04``.
    """
    found: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for root in _search_roots():
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


def _vanilla_slot_dirs(staging: Path, suffix: str) -> list[Path]:
    """``pl1050/pl1050_<suffix>`` folders that still hold files."""
    found: list[Path] = []
    for root in _search_roots():
        path = resolve_ci(staging, f"{root}/pl1050/pl1050_{suffix}")
        if path is None or not path.is_dir():
            continue
        if any(child.is_file() for child in path.rglob("*")):
            found.append(path)
    return found


def _staging_has_face_albedo(staging: Path) -> bool:
    """True when the mod already ships a face color map.

    Slot folders (``pl1050_02`` / ``_03`` / ``_04``) are one case. A custom
    head such as ``pl1060_face_albm`` is another. Seeding Claire's clean
    maps on top of that replaces the mod's lips and makeup.
    """
    natives = staging / "natives"
    if not natives.is_dir():
        return False
    for path in natives.rglob("*"):
        if path.is_file() and "face_alb" in path.name.lower():
            return True
    return False


def _shipped_slot_textures(
    staging: Path,
    analysis: AnalysisResult,
    target: Outfit,
) -> bool:
    if analysis_ships_slot_face(analysis, target.key):
        return True
    return any(
        _vanilla_slot_dirs(staging, suffix)
        for suffix in _SLOT_SUFFIXES.get(target.key, ())
    )


def _seed_clean_slot(
    staging: Path,
    target: Outfit,
    suffix: str,
    report: ConversionReport,
) -> int:
    """Copy the bundled clean face onto ``pl1050/pl1050_<suffix>``.

    Template files are named ``pl1050_04_*``. The suffix in the file name
    is renamed to match the destination folder. Shared ``pl1050`` maps are
    not part of the template and are not written.
    """
    template = assets_dir() / _CLEAN_TEMPLATE
    wrote = 0
    dests = {
        "sectionroot": (
            "natives/x64/sectionroot/character/player/pl1000/"
            f"pl1050/pl1050_{suffix}"
        ),
        "streaming": (
            "natives/x64/streaming/sectionroot/character/player/pl1000/"
            f"pl1050/pl1050_{suffix}"
        ),
    }
    for key, dest_rel in dests.items():
        src_dir = template / key
        if not src_dir.is_dir():
            continue
        dest_dir = ensure_dir_ci(staging, dest_rel)
        for src in sorted(src_dir.iterdir()):
            if not src.is_file():
                continue
            name = src.name.replace(
                f"pl1050_{_TEMPLATE_SUFFIX}", f"pl1050_{suffix}")
            dest = dest_dir / name
            shutil.copy2(src, dest)
            if (
                natives_platform() == "stm"
                and dest.name.lower().endswith(".tex.10")
            ):
                from .platform.tex_convert import convert_tex_to_rt

                rt_dest = dest.with_name(dest.name[:-len("10")] + "34")
                rt_dest.write_bytes(
                    convert_tex_to_rt(dest.read_bytes(), name=dest.name))
                dest.unlink()
                dest = rt_dest
            wrote += 1
            report.rename_ops.append(
                f"{target.name} clean face: {src.name}  ->  "
                f"{dest.relative_to(staging).as_posix()}"
            )
    return wrote


def _note_strip(staging: Path, target: Outfit, report: ConversionReport) -> None:
    removed = _strip_face04_dirs(staging, report)
    if removed:
        report.rename_ops.append(
            f"face: stripped Military *_04 face textures for {target.name} "
            f"({removed} folder(s); Claire default face)"
        )


def strip_tank_military_leftovers(
    staging: Path,
    target: Outfit,
    report: ConversionReport,
) -> None:
    """Remove leftover Military ``*_04`` folders before face isolation."""
    if target.key != "tanktop":
        return
    _note_strip(staging, target, report)


def ensure_military_clean_face(
    staging: Path,
    target: Outfit,
    analysis: AnalysisResult,
    report: ConversionReport,
    strip_leftover_04: bool = True,
) -> None:
    """Seed the bundled Claire face for Military / Tank Top.

    Writes the clean textures onto the folder that outfit loads. Tank Top
    still drops a leftover Military ``*_04`` folder unless Military is also
    being converted (``strip_leftover_04`` false). An AddonFor package is
    never seeded.
    """
    if target.key not in _SEED_TARGETS:
        return

    # An addon overlay would replace the main mod's face when Fluffy
    # enables it. Addons do not get a seeded face of their own.
    if analysis.modinfo.addonfor:
        if target.key == "tanktop" and strip_leftover_04:
            _note_strip(staging, target, report)
        if _shipped_slot_textures(staging, analysis, target):
            report.rename_ops.append(
                f"face: kept mod face data "
                f"({target.name} clean-face seed skipped)"
            )
        else:
            report.rename_ops.append(
                f"face: left {target.name} face alone "
                "(addon has no face of its own)"
            )
        return

    if target.key == "tanktop" and strip_leftover_04:
        _note_strip(staging, target, report)

    if _shipped_slot_textures(staging, analysis, target):
        report.rename_ops.append(
            f"face: kept mod face data ({target.name} clean-face seed skipped)"
        )
        return

    if _staging_has_face_albedo(staging):
        report.rename_ops.append(
            f"face: kept mod face data ({target.name} clean-face seed skipped)"
        )
        return

    suffixes = _SLOT_SUFFIXES[target.key]
    template = assets_dir() / _CLEAN_TEMPLATE
    if not template.is_dir():
        report.warnings.append(
            f"{target.name} convert needs default face textures but the "
            f"bundled template is missing ({_CLEAN_TEMPLATE})."
        )
        return

    wrote = 0
    for suffix in suffixes:
        wrote += _seed_clean_slot(staging, target, suffix, report)
    if wrote <= 0:
        report.warnings.append(
            f"{target.name} convert needed default face textures but no "
            "template files were found."
        )
        return
    slots = ", ".join(f"pl1050_{suffix}" for suffix in suffixes)
    report.rename_ops.append(
        f"face: seeded Claire default face for {target.name} "
        f"({slots}; mod had no custom face data)"
    )
