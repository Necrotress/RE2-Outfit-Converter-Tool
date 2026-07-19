"""Batch conversion and AddonFor passthrough packaging."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .analyzer import AnalysisResult
from .hair_prefabs import ensure_isolated_hair_redirect
from .isolation import (
    isolate_claire_face_hair,
    isolate_shared_outfit_textures,
    staging_mesh_ids,
)
from .outfits import CLAIRE_FACE_IDS, CLAIRE_HAIR_MESH_IDS, Outfit
from .packaging import (
    make_folder,
    resolve_tag_marker,
    update_modinfo,
)
from .path_patch import patch_binaries
from .paths import PARTS_DIR, resolve_ci
from .reports import ConversionError, ConversionReport


def passthrough_folder(
    analysis: AnalysisResult,
    target: Outfit,
    output_dir: Path,
    folder_name: str,
    tag_output: bool = True,
    tag_marker: str | None = None,
    strip_tag_markers: list[str] | None = None,
) -> ConversionReport:
    """Copy a mod into the batch staging folder without outfit remapping.

    Face/hair isolation still runs when those mesh folders exist. Face/hair
    PFBs are dropped when this package has no local face/hair meshes, so a
    texture-only AddonFor cannot overwrite the main mod's isolated prefabs.
    """
    if analysis.root is None:
        raise ConversionError("Analysis has no mod root.")
    report = ConversionReport()
    staging_tmp = tempfile.TemporaryDirectory(prefix="re2oc_pass_")
    staging = Path(staging_tmp.name)
    try:
        shutil.copytree(analysis.root, staging, dirs_exist_ok=True)
        rename_map: dict[str, str] = {}
        outfit = analysis.claire_outfits[0] if analysis.claire_outfits else target
        face_priv, hair_priv = isolate_claire_face_hair(
            staging, analysis, outfit, target, rename_map, report)
        ensure_isolated_hair_redirect(
            staging, analysis, target, hair_priv, rename_map, report)
        isolate_shared_outfit_textures(
            staging, face_priv, rename_map, report)
        drop_orphan_part_pfbs(staging, report)
        if rename_map:
            patch_binaries(staging, rename_map, report)
        marker = resolve_tag_marker(target, tag_marker)
        modinfo_warn = update_modinfo(
            staging, target, tag_output=tag_output, tag_marker=marker,
            strip_tag_markers=strip_tag_markers)
        if modinfo_warn:
            report.warnings.append(modinfo_warn)
        report.output_folder = make_folder(
            staging, analysis, target, output_dir, folder_name,
            tag_output=tag_output, tag_marker=marker,
            strip_tag_markers=strip_tag_markers)
    finally:
        staging_tmp.cleanup()
    return report
def drop_orphan_part_pfbs(staging: Path, report: ConversionReport) -> None:
    """Remove face/hair PFBs when this package ships no face/hair mesh folders.

    Shared pl1050/pl1070 folders count; private pl18xx folders from isolation
    also count. Texture-only addons typically only carry a hair redirect PFB
    that would undo the main mod's private-ID redirect.
    """
    present = staging_mesh_ids(staging)
    face_hair_ids = CLAIRE_FACE_IDS | CLAIRE_HAIR_MESH_IDS
    has_face_hair_mesh = bool(present & face_hair_ids) or any(
        pid.startswith("pl18") for pid in present
    )
    if has_face_hair_mesh:
        return
    target_dir = resolve_ci(staging, PARTS_DIR)
    if target_dir is None:
        return
    for part in ("face", "hair"):
        for path in sorted(target_dir.glob(f"pl1000_{part}_*.pfb*")):
            if not path.is_file():
                continue
            rel = path.relative_to(staging).as_posix()
            path.unlink()
            report.removed_ops.append(rel)
            report.warnings.append(
                f"Dropped {path.name} from addon package (no local face/hair "
                "mesh — main mod's isolated prefab is kept)."
            )
