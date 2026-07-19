"""Converts a Claire mod from one outfit slot to another.

Pipeline orchestration only — helpers live in focused sibling modules.

Stage order in ``convert`` (see also docs/PIPELINE.md):

1. Copy mod to staging
2. PFB outfit slots          (prefabs)
3. Body mesh IDs             (meshes)
4. Purge leftover bodies     (meshes)
5. Retarget redirect bodies  (meshes)
6. Costume-select UI         (costume_ui)
7. Streaming / sectionroot   (meshes)
8. Exclusive hair override   (hair_prefabs)
9. Isolate face/hair         (isolation) — builds rename_map
10. Isolated hair redirect   (hair_prefabs) — aliases for patch
11. Shared outfit textures   (isolation)
12. Costume MSG names        (msg_name)
13. Delete DLC contentsholder
14. Binary path patch        (path_patch) — consumes rename_map
15. Update modinfo tags
16. Zip / folder output
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Sequence

from .analyzer import AnalysisResult
from .batch import passthrough_folder
from .hair_prefabs import (
    ensure_exclusive_hair_override,
    ensure_isolated_hair_redirect,
)
from .isolation import isolate_claire_face_hair, isolate_shared_outfit_textures
from .contentsholder import sync_dlc_contentsholder
from .costume_ui import convert_costume_ui
from .meshes import (
    convert_mesh_ids,
    has_mesh_entry,
    purge_source_body_meshes,
    retarget_redirect_bodies,
    sync_streaming_meshes,
)
from .msg_name import sync_costume_name_files
from .outfits import (
    CLAIRE_FACE_IDS,
    CLAIRE_HAIR_MESH_IDS,
    EXCLUSIVE_PART_IDS,
    Outfit,
    is_convertible_outfit,
)
from .packaging import (
    make_folder,
    make_zip,
    resolve_tag_marker,
    safe_name,
    unique_folder_name,
    unique_path,
    update_modinfo,
    zip_directory,
)
from .path_patch import patch_binaries
from .prefabs import convert_pfb_slots
from .reports import (
    BatchItem,
    BatchReport,
    ConversionError,
    ConversionReport,
    NothingToConvertError,
)
from .session import link_orphan_addons


def _normalize_sources(source: Outfit | Sequence[Outfit]) -> list[Outfit]:
    if isinstance(source, Outfit):
        sources = [source]
    else:
        sources = list(source)
    # Preserve order, drop duplicates by key.
    seen: set[str] = set()
    out: list[Outfit] = []
    for o in sources:
        if o.key in seen:
            continue
        seen.add(o.key)
        out.append(o)
    return out


def convert(
    analysis: AnalysisResult,
    source: Outfit | Sequence[Outfit],
    target: Outfit,
    output_dir: Path,
    progress=None,
    as_folder: bool = False,
    folder_name: str | None = None,
    outfit_display_name: str | None = None,
    tag_output: bool = True,
    tag_marker: str | None = None,
    strip_tag_markers: list[str] | None = None,
) -> ConversionReport:
    if analysis.root is None:
        raise ConversionError("Analysis has no mod root.")

    sources = _normalize_sources(source)
    if not sources:
        raise ConversionError("No source outfits selected.")
    if not is_convertible_outfit(target):
        raise ConversionError(
            f"Converting to {target.name} is not supported "
            "(its file layout differs from other Claire outfits)."
        )
    for src in sources:
        if not is_convertible_outfit(src):
            raise ConversionError(
                f"Converting from {src.name} is not supported."
            )

    report = ConversionReport()
    notify = progress or (lambda _msg: None)
    primary = sources[0]

    src_pfbs = [
        p for p in analysis.claire_pfbs
        if any(p.slot in s.all_slots for s in sources)
    ]
    display_name = (outfit_display_name or "").strip() or None
    if display_name and not target.msg_stem:
        raise ConversionError(
            f"{target.name} has no custom in-game name slot "
            "(supported: Tank Top / Classic Tank Top / Elza / Noir / Military)."
        )

    has_body = any(has_mesh_entry(analysis, s.body_id) for s in sources)
    has_face_hair = any(
        has_mesh_entry(analysis, pid)
        for pid in (CLAIRE_FACE_IDS | CLAIRE_HAIR_MESH_IDS)
    )
    if not src_pfbs and not has_body and not has_face_hair and not display_name:
        names = ", ".join(s.name for s in sources)
        raise NothingToConvertError(
            f"The mod has no PFB prefabs, mesh, or face/hair assets for "
            f"{names} - nothing to convert for that outfit."
        )

    staging_tmp = tempfile.TemporaryDirectory(prefix="re2oc_stage_")
    staging = Path(staging_tmp.name)
    try:
        notify("Copying mod to staging folder...")
        shutil.copytree(analysis.root, staging, dirs_exist_ok=True)

        rename_map: dict[str, str] = {}

        notify("Renaming PFB outfit slots...")
        for src in sources:
            pfbs = [p for p in src_pfbs if p.slot in src.all_slots]
            if pfbs:
                convert_pfb_slots(staging, pfbs, src, target, report)

        notify("Renaming mesh folders and files...")
        body_sources = [s for s in sources if has_mesh_entry(analysis, s.body_id)]
        if len({s.body_id for s in body_sources}) > 1:
            report.warnings.append(
                "Multiple source body meshes map to the same target slot — "
                "later sources overwrite earlier ones if they collide."
            )
        for src in body_sources:
            convert_mesh_ids(staging, analysis, src, target, rename_map, report)

        notify("Removing leftover source body meshes...")
        purge_source_body_meshes(staging, sources, target, report)

        notify("Retargeting redirected custom body meshes...")
        retarget_redirect_bodies(staging, target, rename_map, report)

        notify("Remapping costume-select preview...")
        convert_costume_ui(staging, sources, target, rename_map, report)

        notify("Syncing streaming / in-game texture folders...")
        sync_streaming_meshes(staging, target, report)

        notify("Ensuring hair / hat slot override...")
        ensure_exclusive_hair_override(
            staging, analysis, primary, target, src_pfbs, report)

        notify("Isolating face/hair...")
        face_priv, hair_priv = isolate_claire_face_hair(
            staging, analysis, primary, target, rename_map, report)

        notify("Ensuring private hair prefab...")
        ensure_isolated_hair_redirect(
            staging, analysis, target, hair_priv, rename_map, report)

        notify("Isolating shared outfit textures...")
        isolate_shared_outfit_textures(
            staging, face_priv, rename_map, report)

        notify("Syncing costume-select name / clearing leftovers...")
        try:
            for op in sync_costume_name_files(
                    staging, target, display_name):
                if op.startswith("removed "):
                    report.removed_ops.append(op)
                else:
                    report.rename_ops.append(op)
        except Exception as e:
            raise ConversionError(
                f"Failed to sync in-game outfit name: {e}") from e

        notify("Removing DLC contentsholder...")
        sync_dlc_contentsholder(staging, target, report)

        if rename_map:
            notify("Patching path strings inside binary files...")
            patch_binaries(staging, rename_map, report)

        marker = resolve_tag_marker(target, tag_marker)
        modinfo_warn = update_modinfo(
            staging, target, tag_output=tag_output, tag_marker=marker,
            strip_tag_markers=strip_tag_markers)
        if modinfo_warn:
            report.warnings.append(modinfo_warn)

        if as_folder:
            notify("Writing Fluffy-ready mod folder...")
            report.output_folder = make_folder(
                staging, analysis, target, output_dir, folder_name,
                tag_output=tag_output, tag_marker=marker,
                strip_tag_markers=strip_tag_markers)
        else:
            notify("Creating Fluffy-ready zip...")
            report.output_zip = make_zip(
                staging, analysis, target, output_dir, tag_output=tag_output,
                tag_marker=marker, strip_tag_markers=strip_tag_markers)
    finally:
        staging_tmp.cleanup()

    for src in sources:
        if src.hair_id == target.hair_id:
            continue
        injected = any("injected hair redirect" in op for op in report.pfb_ops)
        isolated = any("isolat" in op.lower() for op in report.rename_ops)
        if (not injected and not isolated
                and target.hair_id in EXCLUSIVE_PART_IDS):
            report.warnings.append(
                f"{src.name} and {target.name} use different hair/hat meshes "
                f"({src.hair_id} vs {target.hair_id}) - hair may need in-game checking."
            )
    return report


def convert_batch(
    items: list[BatchItem],
    source: Outfit | Sequence[Outfit],
    target: Outfit,
    output_dir: Path,
    bundle_name: str,
    progress=None,
    outfit_display_name: str | None = None,
    tag_output: bool = True,
    tag_marker: str | None = None,
    strip_tag_markers: list[str] | None = None,
) -> BatchReport:
    """Convert several mods into one Fluffy-ready multi-mod ZIP."""
    if not items:
        raise ConversionError("Batch is empty.")

    sources = _normalize_sources(source)
    if not sources:
        raise ConversionError("No source outfits selected.")

    notify = progress or (lambda _msg: None)
    output_dir.mkdir(parents=True, exist_ok=True)

    marker = resolve_tag_marker(target, tag_marker)
    safe_bundle = safe_name(bundle_name.strip() or "Converted Batch")
    if tag_output and marker:
        zip_name = f"{safe_name(f'{safe_bundle} {marker}')}.zip"
    else:
        zip_name = f"{safe_bundle}.zip"
    zip_path = unique_path(output_dir / zip_name)

    report = BatchReport()
    used_names: set[str] = set()
    staging_tmp = tempfile.TemporaryDirectory(prefix="re2oc_batch_")
    staging_root = Path(staging_tmp.name)

    link_orphan_addons([item.analysis for item in items])

    try:
        for i, item in enumerate(items, start=1):
            label = item.label or item.analysis.modinfo.name or f"mod {i}"
            notify(f"[{i}/{len(items)}] Converting {label}...")
            folder_name = unique_folder_name(
                item.analysis, used_names, preferred=item.label,
                strip_tag_markers=strip_tag_markers)
            try:
                item_report = convert(
                    item.analysis, sources, target, staging_root,
                    progress=None,
                    as_folder=True,
                    folder_name=folder_name,
                    outfit_display_name=outfit_display_name,
                    tag_output=tag_output,
                    tag_marker=marker,
                    strip_tag_markers=strip_tag_markers,
                )
            except NothingToConvertError:
                if item.analysis.root is None:
                    report.warnings.append(
                        f"{label}: Analysis has no mod root.")
                    continue
                notify(
                    f"[{i}/{len(items)}] No outfit remap for {label} — "
                    "packaging as-is...")
                try:
                    item_report = passthrough_folder(
                        item.analysis, target, staging_root, folder_name,
                        tag_output=tag_output, tag_marker=marker,
                        strip_tag_markers=strip_tag_markers,
                    )
                    src_names = ", ".join(s.name for s in sources)
                    item_report.warnings.append(
                        f"{label}: no {src_names} assets to remap; "
                        "packaged as-is.")
                except (ConversionError, OSError) as e2:
                    report.warnings.append(f"{label}: {e2}")
                    continue
            except ConversionError as e:
                report.warnings.append(f"{label}: {e}")
                continue
            used_names.add(folder_name.lower())
            report.items.append(item_report)

        if not report.items:
            raise ConversionError(
                "No mods converted successfully.\n"
                + "\n".join(report.warnings))

        notify("Creating Fluffy-ready multi-mod zip...")
        zip_directory(staging_root, zip_path)
        report.output_zip = zip_path
    finally:
        staging_tmp.cleanup()

    return report
