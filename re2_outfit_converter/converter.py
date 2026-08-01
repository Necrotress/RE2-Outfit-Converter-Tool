"""Converts a Claire mod from one outfit slot to another.

Pipeline orchestration only — helpers live in focused sibling modules.

Stage order in ``convert_with_ops`` (see also docs/PIPELINE.md):

1. Copy mod to staging
1b. Promote deleted-slot body assets → convert source; strip deleted outfits
2. PFB outfit slots (per convert op)
3. Body mesh IDs
4. Purge leftover source bodies
5. Retarget redirect bodies
6. Costume-select UI
7. Streaming / sectionroot sync
8. Exclusive hair override
9. Isolate face/hair
10. Isolated hair redirect PFB
11. Exclusive mesh hide for preview
12. Military clean face (auto-seed when target is Military and staging has no face)
13. Shared outfit textures
14. Costume MSG (all targets, one pass)
14b. Strip author figure gallery (convert + delete-only)
15. Delete DLC contentsholder
16. Binary path patch + material hashes
17. Update modinfo
18. Zip or folder output
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Sequence

from .analyzer import AnalysisResult
from .batch import passthrough_folder
from .contentsholder import sync_dlc_contentsholder
from .convert_log import (
    ConvertLogContext,
    context_from_analysis,
    write_batch_log_to_staging,
    write_convert_log_to_staging,
)
from .costume_ui import convert_costume_ui
from .exclusive_meshes import ensure_exclusive_part_mesh_hide
from .figure_scenes import strip_claire_extra_figures
from .hair_prefabs import (
    ensure_exclusive_hair_override,
    ensure_isolated_hair_redirect,
)

from .isolation import (
    isolate_claire_face_hair,
    isolate_shared_outfit_textures,
    resolve_hair_id_for_target,
)
from .meshes import (
    convert_mesh_ids,
    has_mesh_entry,
    purge_source_body_meshes,
    retarget_redirect_bodies,
    sync_streaming_meshes,
)
from .military_face import ensure_military_clean_face
from .msg_name import CLAIRECOS_MSG_STEMS, sync_costume_names_for_targets
from .outfit_ops import (
    OutfitOp,
    adapt_ops_for_package,
    convert_ops as filter_convert_ops,
    delete_ops as filter_delete_ops,
    normalize_ops,
    ops_from_source_target,
    primary_convert_source,
    primary_convert_target,
)
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
from .material_hash import patch_mdf_material_hashes
from .prefabs import convert_pfb_slots
from .promote_body import promote_deleted_body_assets
from .reports import (
    BatchItem,
    BatchReport,
    ConversionError,
    ConversionReport,
    NothingToConvertError,
)
from .session import link_orphan_addons
from .strip_outfit import strip_outfit_slot


def _absorb_msg_lines(report: ConversionReport, lines: list[str]) -> None:
    for line in lines:
        if line.startswith("removed "):
            report.removed_ops.append(line)
        else:
            report.rename_ops.append(line)


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
    source_name: str | None = None,
    write_log: bool = True,
    outfit_display_names: dict[str, str] | None = None,
) -> ConversionReport:
    """Legacy single-target API — wraps :func:`convert_with_ops`."""
    return convert_with_ops(
        analysis,
        ops_from_source_target(source, target),
        output_dir,
        progress=progress,
        as_folder=as_folder,
        folder_name=folder_name,
        outfit_display_name=outfit_display_name,
        tag_output=tag_output,
        tag_marker=tag_marker,
        strip_tag_markers=strip_tag_markers,
        source_name=source_name,
        write_log=write_log,
        outfit_display_names=outfit_display_names,
    )


def convert_with_ops(
    analysis: AnalysisResult,
    ops: Sequence[OutfitOp],
    output_dir: Path,
    progress=None,
    as_folder: bool = False,
    folder_name: str | None = None,
    outfit_display_name: str | None = None,
    tag_output: bool = True,
    tag_marker: str | None = None,
    strip_tag_markers: list[str] | None = None,
    source_name: str | None = None,
    write_log: bool = True,
    outfit_display_names: dict[str, str] | None = None,
) -> ConversionReport:
    if analysis.root is None:
        raise ConversionError("Analysis has no mod root.")

    # Per-package: drop From ops this pack lacks; rewrite Delete-only body
    # AddonFors into convert→target so textures are not wiped.
    ops = adapt_ops_for_package(analysis, ops)
    converts = filter_convert_ops(ops)
    deletes = filter_delete_ops(ops)
    sources = [op.source for op in converts]
    package_target = primary_convert_target(ops)
    if package_target is None:
        package_target = deletes[0].source
    primary = primary_convert_source(ops) or package_target

    report = ConversionReport()
    _progress = progress

    def notify(msg: str) -> None:
        report.progress_log.append(msg)
        if _progress:
            _progress(msg)

    src_pfbs = [
        p for p in analysis.claire_pfbs
        if any(p.slot in s.all_slots for s in sources)
    ] if sources else []

    display_names = {
        str(k): (v or "").strip()
        for k, v in (outfit_display_names or {}).items()
        if (v or "").strip()
    }
    display_name = (outfit_display_name or "").strip() or None
    msg_target: Outfit | None = None
    if display_names:
        # Multi-target explicit names — validate at least one convert can use them.
        namable = [
            op.target for op in converts
            if op.target is not None
            and (op.target.msg_stem or "").lower() in CLAIRECOS_MSG_STEMS
        ]
        if not namable:
            raise ConversionError(
                f"{package_target.name} has no custom in-game name slot "
                "(supported on Convert: Elza / Noir / Military; "
                "Jacket/Tank/Classic use Costume names)."
            )
    elif display_name:
        msg_target = next(
            (op.target for op in converts
             if op.target is not None
             and (op.target.msg_stem or "").lower() in CLAIRECOS_MSG_STEMS),
            None,
        )
        if msg_target is None:
            raise ConversionError(
                f"{package_target.name} has no custom in-game name slot "
                "(supported on Convert: Elza / Noir / Military; "
                "Jacket/Tank/Classic use Costume names)."
            )

    has_body = any(
        has_mesh_entry(analysis, s.body_id) for s in sources
    ) if sources else False
    has_face_hair = any(
        has_mesh_entry(analysis, pid)
        for pid in (CLAIRE_FACE_IDS | CLAIRE_HAIR_MESH_IDS)
    )
    if (converts and not src_pfbs and not has_body and not has_face_hair
            and not display_name and not display_names):
        names = ", ".join(s.name for s in sources)
        raise NothingToConvertError(
            f"The mod has no PFB prefabs, mesh, or face/hair assets for "
            f"{names} - nothing to convert for that outfit."
        )
    if not converts and not deletes:
        raise ConversionError("No outfit operations selected.")

    # Collision: multiple converts onto the same target.
    by_target: dict[str, list[Outfit]] = {}
    for op in converts:
        assert op.target is not None
        by_target.setdefault(op.target.key, []).append(op.source)
    for target_key, srcs in by_target.items():
        if len(srcs) > 1:
            report.warnings.append(
                f"Multiple outfits map to the same target "
                f"({srcs[0].name}… → {target_key}); later sources win on collision."
            )

    staging_tmp = tempfile.TemporaryDirectory(prefix="re2oc_stage_")
    staging = Path(staging_tmp.name)
    try:
        notify("Copying mod to staging folder...")
        shutil.copytree(analysis.root, staging, dirs_exist_ok=True)

        rename_map: dict[str, str] = {}

        keep_exclusive = {
            op.target.hair_id
            for op in converts
            if op.target is not None and op.target.hair_id in EXCLUSIVE_PART_IDS
        }

        if deletes and converts:
            notify("Promoting deleted-slot body assets into convert source...")
            promote_deleted_body_assets(
                staging, deletes, converts, rename_map, report)

        if deletes:
            notify("Removing deleted outfit slots...")
            for op in deletes:
                strip_outfit_slot(
                    staging, op.source, report,
                    keep_exclusive_ids=keep_exclusive,
                )

        unique_targets: list[Outfit] = []
        seen_t: set[str] = set()
        for op in converts:
            assert op.target is not None
            if op.target.key not in seen_t:
                seen_t.add(op.target.key)
                unique_targets.append(op.target)

        if converts:
            notify("Renaming PFB outfit slots...")
            for op in converts:
                assert op.target is not None
                pfbs = [
                    p for p in analysis.claire_pfbs
                    if p.slot in op.source.all_slots
                ]
                if pfbs:
                    convert_pfb_slots(
                        staging, pfbs, op.source, op.target, report)

            notify("Renaming mesh folders and files...")
            for op in converts:
                assert op.target is not None
                if has_mesh_entry(analysis, op.source.body_id):
                    convert_mesh_ids(
                        staging, analysis, op.source, op.target,
                        rename_map, report)

            notify("Removing leftover source body meshes...")
            for op in converts:
                assert op.target is not None
                purge_source_body_meshes(
                    staging, [op.source], op.target, report)

            notify("Retargeting redirected custom body meshes...")
            for target in unique_targets:
                retarget_redirect_bodies(staging, target, rename_map, report)

            notify("Remapping costume-select preview...")
            for op in converts:
                assert op.target is not None
                convert_costume_ui(
                    staging, [op.source], op.target, rename_map, report)

            notify("Syncing streaming / in-game texture folders...")
            for target in unique_targets:
                sync_streaming_meshes(staging, target, report)

            primary_src = primary
            hair_target = next(
                (t for t in unique_targets
                 if t.hair_id in EXCLUSIVE_PART_IDS),
                unique_targets[0],
            )

            for target in unique_targets:
                ops_for_t = [
                    op for op in converts
                    if op.target is not None and op.target.key == target.key
                ]
                src = ops_for_t[0].source if ops_for_t else primary_src
                pfbs = [
                    p for p in analysis.claire_pfbs
                    if p.slot in src.all_slots
                ]
                notify(f"Ensuring hair / hat slot override ({target.name})...")
                ensure_exclusive_hair_override(
                    staging, analysis, src, target, pfbs, report)

            # Tank Top: strip Military *_04 face leftovers before isolation so
            # they are not moved onto a private face id and path-patched.
            for target in unique_targets:
                if target.key != "tanktop":
                    continue
                notify("Stripping Military face textures for Tank Top...")
                ensure_military_clean_face(
                    staging, target, analysis, report)

            notify("Isolating face/hair...")
            face_priv, hair_priv = isolate_claire_face_hair(
                staging, analysis, primary_src, hair_target,
                rename_map, report, keep_exclusive_ids=keep_exclusive)

            notify("Ensuring private hair prefab...")
            for target in unique_targets:
                hair_for_t = resolve_hair_id_for_target(
                    staging, target, hair_priv)
                if hair_for_t:
                    ensure_isolated_hair_redirect(
                        staging, analysis, target, hair_for_t,
                        rename_map, report)

            for target in unique_targets:
                if target.hair_id not in EXCLUSIVE_PART_IDS:
                    continue
                hair_for_t = resolve_hair_id_for_target(
                    staging, target, hair_priv)
                # Do not seed Military preview from a Noir exclusive (or vice
                # versa); fall back to the bundled hide template.
                hide_src = hair_for_t
                if (
                    hide_src in EXCLUSIVE_PART_IDS
                    and hide_src != target.hair_id
                ):
                    hide_src = ""
                notify(
                    f"Hiding exclusive hat/headband for {target.name}...")
                ensure_exclusive_part_mesh_hide(
                    staging, target, hide_src, report)

            for target in unique_targets:
                if target.key != "military":
                    continue
                notify("Seeding Military clean face if needed...")
                ensure_military_clean_face(
                    staging, target, analysis, report)

            notify("Isolating shared outfit textures...")
            isolate_shared_outfit_textures(
                staging, face_priv, rename_map, report)

            notify("Syncing costume-select name / clearing leftovers...")
            try:
                _absorb_msg_lines(
                    report,
                    sync_costume_names_for_targets(
                        staging,
                        unique_targets,
                        display_name=display_name,
                        name_target=msg_target,
                        display_names=display_names or None,
                    ),
                )
            except Exception as e:
                raise ConversionError(
                    f"Failed to sync in-game outfit name: {e}") from e
        else:
            # Delete-only: isolate face/hair against a remaining slot if any.
            deleted_keys = {op.source.key for op in deletes}
            remaining = [
                o for o in analysis.claire_outfits
                if is_convertible_outfit(o) and o.key not in deleted_keys
            ]
            seed = remaining[0] if remaining else deletes[0].source
            notify("Isolating face/hair...")
            face_priv, hair_priv = isolate_claire_face_hair(
                staging, analysis, seed, seed, rename_map, report,
                keep_exclusive_ids=set(),
            )
            redirect_targets = remaining or [seed]
            notify("Ensuring private hair prefab...")
            for outfit in redirect_targets:
                hair_for_t = resolve_hair_id_for_target(
                    staging, outfit, hair_priv)
                if hair_for_t:
                    ensure_isolated_hair_redirect(
                        staging, analysis, outfit, hair_for_t,
                        rename_map, report)
            notify("Isolating shared outfit textures...")
            isolate_shared_outfit_textures(
                staging, face_priv, rename_map, report)

        # Always strip author figure galleries (convert and delete-only) so
        # leftover SCN/PFBs cannot bleed across DLC Records viewers.
        notify("Isolating figure gallery (strip author scenes)...")
        strip_claire_extra_figures(staging, report)

        notify("Removing DLC contentsholder...")
        sync_dlc_contentsholder(staging, package_target, report)

        if rename_map:
            notify("Patching path strings inside binary files...")
            patch_binaries(staging, rename_map, report)
            patch_mdf_material_hashes(staging, rename_map, report)

        marker = resolve_tag_marker(package_target, tag_marker)
        do_tag = tag_output and bool(converts)
        modinfo_warn = update_modinfo(
            staging, package_target, tag_output=do_tag, tag_marker=marker,
            strip_tag_markers=strip_tag_markers)
        if modinfo_warn:
            report.warnings.append(modinfo_warn)

        if write_log:
            log_ctx = context_from_analysis(
                analysis, list(ops),
                source_name=source_name,
                as_folder=as_folder,
                tag_output=do_tag,
                tag_marker=marker or "",
                display_name=display_name,
                package_name=(
                    f"{'folder' if as_folder else 'zip'} "
                    f"(includes convert.log)"
                ),
            )
            write_convert_log_to_staging(staging, report, log_ctx)

        if as_folder:
            notify("Writing Fluffy-ready mod folder...")
            report.output_folder = make_folder(
                staging, analysis, package_target, output_dir, folder_name,
                tag_output=do_tag, tag_marker=marker,
                strip_tag_markers=strip_tag_markers,
                source_name=source_name)
        else:
            notify("Creating Fluffy-ready zip...")
            report.output_zip = make_zip(
                staging, analysis, package_target, output_dir,
                tag_output=do_tag,
                tag_marker=marker, strip_tag_markers=strip_tag_markers,
                source_name=source_name)
    finally:
        staging_tmp.cleanup()

    for op in converts:
        assert op.target is not None
        src, target = op.source, op.target
        if src.hair_id == target.hair_id:
            continue
        injected = any("injected hair redirect" in x for x in report.pfb_ops)
        isolated = any("isolat" in x.lower() for x in report.rename_ops)
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
    ops: Sequence[OutfitOp] | None = None,
    write_log: bool = True,
    outfit_display_names: dict[str, str] | None = None,
) -> BatchReport:
    """Convert several mods into one Fluffy-ready multi-mod ZIP."""
    if not items:
        raise ConversionError("Batch is empty.")

    use_ops = list(ops) if ops is not None else ops_from_source_target(
        source, target)
    use_ops = normalize_ops(use_ops)
    package_target = primary_convert_target(use_ops) or use_ops[0].source

    report = BatchReport()
    _progress = progress

    def notify(msg: str) -> None:
        report.progress_log.append(msg)
        if _progress:
            _progress(msg)

    output_dir.mkdir(parents=True, exist_ok=True)

    marker = resolve_tag_marker(package_target, tag_marker)
    safe_bundle = safe_name(bundle_name.strip() or "Converted Batch")
    do_tag = tag_output and any(op.target is not None for op in use_ops)
    if do_tag and marker:
        zip_name = f"{safe_name(f'{safe_bundle} {marker}')}.zip"
    else:
        zip_name = f"{safe_bundle}.zip"
    zip_path = unique_path(output_dir / zip_name)

    used_names: set[str] = set()
    folder_names: list[str] = []
    item_contexts: list[ConvertLogContext] = []
    staging_tmp = tempfile.TemporaryDirectory(prefix="re2oc_batch_")
    staging_root = Path(staging_tmp.name)

    link_orphan_addons([item.analysis for item in items])

    try:
        for i, item in enumerate(items, start=1):
            root = item.analysis.root
            preferred = (
                (root.name if root is not None else "")
                or item.label
                or item.analysis.modinfo.name
                or f"mod {i}"
            )
            folder_name = unique_folder_name(
                item.analysis, used_names, preferred=preferred,
                strip_tag_markers=strip_tag_markers,
                strip_tags=root is None,
            )
            notify(f"[{i}/{len(items)}] Converting {folder_name}...")
            try:
                item_report = convert_with_ops(
                    item.analysis, use_ops, staging_root,
                    progress=None,
                    as_folder=True,
                    folder_name=folder_name,
                    outfit_display_name=outfit_display_name,
                    tag_output=tag_output,
                    tag_marker=marker,
                    strip_tag_markers=strip_tag_markers,
                    write_log=False,
                    outfit_display_names=outfit_display_names,
                )
            except NothingToConvertError:
                if item.analysis.root is None:
                    report.warnings.append(
                        f"{folder_name}: Analysis has no mod root.")
                    continue
                notify(
                    f"[{i}/{len(items)}] No outfit remap for {folder_name} — "
                    "packaging as-is...")
                try:
                    item_report = passthrough_folder(
                        item.analysis, package_target, staging_root,
                        folder_name,
                        tag_output=do_tag, tag_marker=marker,
                        strip_tag_markers=strip_tag_markers,
                        write_log=False,
                        source_name=folder_name,
                        ops=use_ops,
                    )
                    src_names = ", ".join(
                        op.source.name for op in use_ops if op.target)
                    item_report.warnings.append(
                        f"{folder_name}: no {src_names or 'selected'} assets "
                        "to remap; packaged as-is.")
                except (ConversionError, OSError) as e2:
                    report.warnings.append(f"{folder_name}: {e2}")
                    continue
            except ConversionError as e:
                report.warnings.append(f"{folder_name}: {e}")
                continue
            used_names.add(folder_name.lower())
            report.items.append(item_report)
            folder_names.append(folder_name)
            display = ""
            if outfit_display_names:
                for op in use_ops:
                    if op.target is None:
                        continue
                    display = (
                        outfit_display_names.get(op.target.key) or ""
                    ).strip()
                    if display:
                        break
            display = display or (outfit_display_name or "").strip()
            item_contexts.append(context_from_analysis(
                item.analysis, use_ops,
                source_name=folder_name,
                as_folder=True,
                tag_output=do_tag,
                tag_marker=marker or "",
                display_name=display,
                label=folder_name,
                package_name=(
                    f"folder {folder_name}/ (see bundle convert.log)"
                ),
            ))

        if not report.items:
            raise ConversionError(
                "No mods converted successfully.\n"
                + "\n".join(report.warnings))

        if write_log:
            write_batch_log_to_staging(
                staging_root, report,
                folder_names=folder_names,
                item_contexts=item_contexts,
                bundle_name=safe_bundle,
            )

        notify("Creating Fluffy-ready multi-mod zip...")
        zip_directory(staging_root, zip_path)
        report.output_zip = zip_path
    finally:
        staging_tmp.cleanup()

    return report
