"""Converts a Claire or Leon mod from one outfit slot to another.

Pipeline orchestration only — helpers live in focused sibling modules.

Stage order in ``convert_with_ops`` (see also docs/PIPELINE.md):

1. Copy mod to staging
1a. Classic-ize a ray-tracing or dual tree when the result is Classic, or the pack is both builds
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
14b. Retarget author figure gallery (convert) / strip (delete-only)
15. Delete DLC contentsholder
16. Binary path patch + material hashes
16b. Upgrade to ray tracing when the pack is not already ray tracing
17. Update modinfo
18. Zip or folder output

Same-slot with a game-build change skips steps 1b–16 except a typed
in-game outfit name, which is still written. A ray-tracing mod that
stays ray tracing skips 1a and 16b even when the outfit slot changes;
those outfit stages read and write natives/stm. Classic to Classic
still runs the outfit stages and skips both platform passes.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import nullcontext
from pathlib import Path
from typing import Sequence

from .analyzer import GAME_BUILDS, AnalysisResult, analyze
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
from .figure_scenes import (
    convert_figure_scenes_for_ops,
    strip_claire_extra_figures,
)
from .hair_prefabs import (
    drop_mesh_only_hair_pfbs,
    ensure_exclusive_hair_override,
    ensure_isolated_hair_redirect,
)

from .isolation import (
    isolate_claire_face_hair,
    isolate_shared_outfit_textures,
    resolve_hair_id_for_target,
)
from .meshes import (
    body_id_on_disk,
    convert_mesh_ids,
    has_mesh_entry,
    purge_source_body_meshes,
    retarget_redirect_bodies,
    sync_streaming_meshes,
)
from .military_face import (
    ensure_military_clean_face,
    strip_tank_military_leftovers,
)
from .msg_name import DLC_COS_MSG_STEMS, sync_costume_names_for_targets
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
from .character import CLAIRE_PROFILE
from .outfits import (
    EXCLUSIVE_PART_IDS,
    Outfit,
    is_convertible_outfit,
)
from .packaging import (
    append_description_marker,
    build_tag_marker,
    make_folder,
    make_zip,
    resolve_convert_tag_flags,
    resolve_tag_marker,
    safe_name,
    strip_converter_tags,
    unique_folder_name,
    unique_path,
    update_modinfo,
    zip_directory,
)
from .path_patch import patch_binaries
from .material_hash import patch_mdf_material_hashes
from .paths import use_natives_platform
from .prefabs import convert_pfb_slots
from .promote_body import promote_deleted_body_assets
from .cancel import raise_if_cancelled
from .reports import (
    BatchItem,
    BatchReport,
    ConversionError,
    ConversionReport,
    NothingToConvertError,
)
from .platform.converter import (
    bundle_costume_hint,
    park_addon_textures,
    prepare_classic,
    upgrade_to_rt,
)
from .platform.reports import ConversionError as PlatformError
from .session import link_orphan_addons
from .strip_outfit import strip_outfit_slot


def _analysis_pfbs(analysis: AnalysisResult):
    return analysis.pfbs or analysis.claire_pfbs


def _analysis_outfits(analysis: AnalysisResult) -> list[Outfit]:
    return analysis.outfits or analysis.claire_outfits


def _same_slot_identity(ops: Sequence[OutfitOp]) -> bool:
    """True when every op converts a slot onto itself and nothing is deleted."""
    converts = [op for op in ops if op.target is not None]
    if not converts or any(op.target is None for op in ops):
        return False
    return all(op.source.key == op.target.key for op in converts)


def _bind_package(analysis: AnalysisResult, requested: Sequence[OutfitOp]):
    """Adapt ops to this package and the fields the outfit stages read."""
    ops = adapt_ops_for_package(analysis, requested)
    converts = filter_convert_ops(ops)
    deletes = filter_delete_ops(ops)
    sources = [op.source for op in converts]
    package_target = primary_convert_target(ops)
    if package_target is None and deletes:
        package_target = deletes[0].source
    primary = primary_convert_source(ops) or package_target
    profile = (
        package_target.profile
        if package_target is not None
        else (analysis.profile or CLAIRE_PROFILE)
    )
    face_hair_ids = profile.face_ids | profile.hair_mesh_ids
    src_pfbs = [
        p for p in _analysis_pfbs(analysis)
        if any(p.slot in s.all_slots for s in sources)
    ] if sources else []
    return (
        ops, converts, deletes, sources, package_target, primary,
        profile, face_hair_ids, src_pfbs,
    )


def _raise_if_nothing(
    analysis: AnalysisResult,
    converts,
    sources,
    src_pfbs,
    face_hair_ids,
    display_name,
    display_names,
) -> None:
    has_body = any(
        has_mesh_entry(analysis, s.body_id) for s in sources
    ) if sources else False
    has_face_hair = any(
        has_mesh_entry(analysis, pid) for pid in face_hair_ids
    )
    if (converts and not src_pfbs and not has_body and not has_face_hair
            and not display_name and not display_names):
        names = ", ".join(s.name for s in sources)
        raise NothingToConvertError(
            f"The mod has no PFB prefabs, mesh, or face/hair assets for "
            f"{names} - nothing to convert for that outfit."
        )


def _merge_platform(report: ConversionReport, plat) -> None:
    report.warnings.extend(plat.warnings)
    report.removed_ops.extend(plat.removed_ops)
    report.rename_ops.extend(plat.converted_ops)
    report.patch_ops.extend(plat.patch_ops)
    if plat.failed_ops:
        report.warnings.extend(plat.failed_ops[:12])


def _source_msg_stems(converts: Sequence) -> dict[str, str]:
    """Target outfit key → source msg stem for name files."""
    out: dict[str, str] = {}
    for op in converts:
        target = getattr(op, "target", None)
        source = getattr(op, "source", None)
        if target is None or source is None:
            continue
        stem = (getattr(source, "msg_stem", None) or "").strip().lower()
        if stem:
            out[target.key] = stem
    return out


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
    tag_modinfo_description: bool | None = None,
    tag_modinfo_name: bool = False,
    game_build: str | None = None,
    tag_build_zip_name: bool = True,
    tag_build_modinfo_description: bool = True,
    settings: dict | None = None,
    costume_dest_hint: str | None = None,
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
        tag_modinfo_description=tag_modinfo_description,
        tag_modinfo_name=tag_modinfo_name,
        game_build=game_build,
        tag_build_zip_name=tag_build_zip_name,
        tag_build_modinfo_description=tag_build_modinfo_description,
        settings=settings,
        costume_dest_hint=costume_dest_hint,
    )


def _apply_face_look(
    staging: Path,
    targets,
    analysis: AnalysisResult,
    report: ConversionReport,
) -> None:
    """Clean face textures for every Military and Tank Top target."""
    seen: set[str] = set()
    unique = []
    for target in targets:
        key = getattr(target, "key", None)
        if key in seen or key is None:
            continue
        seen.add(key)
        unique.append(target)
    military_too = "military" in seen
    for target in unique:
        if getattr(target, "key", None) not in ("military", "tanktop"):
            continue
        ensure_military_clean_face(
            staging, target, analysis, report,
            strip_leftover_04=not military_too,
        )


def _claire_destination_face_slot(converts) -> str | None:
    """Costume letter whose ray-tracing face prefab should load a private head.

    ``'98`` uses ``pl1057`` and is not the shared neck. The first Claire
    target that shares ``pl1050`` is the slot an addon with no prefab of
    its own should follow.
    """
    for op in converts:
        target = op.target
        if target is None or target.head_id != "pl1050":
            continue
        slot = target.primary_slot
        if slot == "default":
            return "default"
        if slot.startswith("costume_"):
            letter = slot[len("costume_"):]
            if letter:
                return letter
    return None


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
    tag_modinfo_description: bool | None = None,
    tag_modinfo_name: bool = False,
    game_build: str | None = None,
    tag_build_zip_name: bool = True,
    tag_build_modinfo_description: bool = True,
    settings: dict | None = None,
    costume_dest_hint: str | None = None,
) -> ConversionReport:
    if analysis.root is None:
        raise ConversionError("Analysis has no mod root.")

    source_analysis = analysis
    requested_ops = list(ops)
    chosen = game_build if game_build in GAME_BUILDS else source_analysis.game_build
    want_rt = chosen == "Ray tracing"
    identity = _same_slot_identity(requested_ops)
    # Already ray tracing, and the menu stays ray tracing: no Blender
    # downgrade or upgrade, even when the outfit slot changes. A dual
    # pack is not already one build. Classic staying Classic never sets
    # want_rt, so both platform passes stay off.
    stay_rt = source_analysis.game_label == "Ray tracing" and want_rt
    round_trip_off = identity and stay_rt
    skip_outfit = identity and (want_rt or source_analysis.has_rt)
    need_prepare = (
        (source_analysis.has_rt or source_analysis.is_dual_pack)
        and not stay_rt
    )
    need_upgrade = want_rt and not stay_rt
    build_marker = build_tag_marker(source_analysis, chosen)

    # Per-package: drop From ops this pack lacks; rewrite Delete-only body
    # AddonFors into convert→target so textures are not wiped.
    (
        ops, converts, deletes, sources, package_target, primary,
        profile, face_hair_ids, src_pfbs,
    ) = _bind_package(analysis, requested_ops)

    op_outfits = [
        *(op.source for op in ops),
        *(op.target for op in converts if op.target is not None),
    ]
    chars = {o.character for o in op_outfits}
    if len(chars) > 1:
        raise ConversionError(
            "Cannot mix Claire and Leon outfit operations in one convert."
        )

    report = ConversionReport()
    _progress = progress

    def notify(msg: str) -> None:
        raise_if_cancelled()
        report.progress_log.append(msg)
        if _progress:
            _progress(msg)

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
            and (op.target.msg_stem or "").lower() in DLC_COS_MSG_STEMS
        ]
        if not namable:
            raise ConversionError(
                f"{package_target.name} has no custom in-game name slot "
                "(supported on Convert: Claire Elza/Noir/Military; "
                "Leon Noir/Arklay Sheriff; "
                "base slots use Costume names)."
            )
    elif display_name:
        msg_target = next(
            (op.target for op in converts
             if op.target is not None
             and (op.target.msg_stem or "").lower() in DLC_COS_MSG_STEMS),
            None,
        )
        if msg_target is None:
            raise ConversionError(
                f"{package_target.name} has no custom in-game name slot "
                "(supported on Convert: Claire Elza/Noir/Military; "
                "Leon Noir/Arklay Sheriff; "
                "base slots use Costume names)."
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

        if need_prepare:
            notify("Preparing a classic tree...")
            try:
                plat = prepare_classic(
                    staging, progress=notify, settings=settings,
                )
            except PlatformError as exc:
                raise ConversionError(str(exc)) from exc
            _merge_platform(report, plat)
            analysis = analyze(staging)
            (
                ops, converts, deletes, sources, package_target, primary,
                profile, face_hair_ids, src_pfbs,
            ) = _bind_package(analysis, requested_ops)
            if not converts and not deletes:
                raise ConversionError("No outfit operations selected.")

        if not skip_outfit:
            _raise_if_nothing(
                analysis, converts, sources, src_pfbs, face_hair_ids,
                display_name, display_names,
            )

        outfit_on_stm = stay_rt and not skip_outfit
        with use_natives_platform("stm") if outfit_on_stm else nullcontext():
            if not skip_outfit:
                all_pfbs = _analysis_pfbs(analysis)
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
                            p for p in all_pfbs
                            if p.slot in op.source.all_slots
                        ]
                        if pfbs:
                            convert_pfb_slots(
                                staging, pfbs, op.source, op.target, report,
                                profile=profile,
                            )

                    notify("Renaming mesh folders and files...")
                    for op in converts:
                        assert op.target is not None
                        if (
                            has_mesh_entry(analysis, op.source.body_id)
                            or body_id_on_disk(staging, op.source)
                        ):
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
                            staging, [op.source], op.target, rename_map, report,
                            profile=profile,
                        )

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
                            p for p in all_pfbs
                            if p.slot in src.all_slots
                        ]
                        notify(f"Ensuring hair / hat slot override ({target.name})...")
                        ensure_exclusive_hair_override(
                            staging, analysis, src, target, pfbs, report)

                    if profile.key == "claire" and not any(
                        t.key == "military" for t in unique_targets
                    ):
                        for target in unique_targets:
                            if target.key != "tanktop":
                                continue
                            notify(
                                "Stripping Military face textures for Tank Top...")
                            strip_tank_military_leftovers(staging, target, report)

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

                    # Costume-select preview still loads exclusive hat meshes
                    # (Claire pl1075/pl1071, Leon pl0074/pl0075). Seed shared hair there.
                    for target in unique_targets:
                        if target.hair_id not in profile.exclusive_part_ids:
                            continue
                        hair_for_t = resolve_hair_id_for_target(
                            staging, target, hair_priv)
                        # Do not seed one exclusive hat from another (Noir vs Military,
                        # or Leon Noir vs Sheriff); fall back to shared / bundled hair.
                        hide_src = hair_for_t
                        if (
                            hide_src in profile.exclusive_part_ids
                            and hide_src != target.hair_id
                        ):
                            hide_src = ""
                        notify(
                            f"Hiding exclusive hat/headband for {target.name}...")
                        ensure_exclusive_part_mesh_hide(
                            staging, target, hide_src, report,
                            allow_template=not analysis.modinfo.addonfor,
                        )

                    # Overlay AddonFor hair PFBs must not stomp Main's redirect
                    # (No Hat mesh-only; Apocalypse-style mesh+mdf without .chain).
                    drop_mesh_only_hair_pfbs(
                        staging, report,
                        is_addon=bool(analysis.modinfo.addonfor),
                        profile=profile,
                    )

                    if profile.key == "claire" and any(
                        t.key in ("military", "tanktop") for t in unique_targets
                    ):
                        notify("Applying Military / Tank Top face textures...")
                        _apply_face_look(
                            staging, unique_targets, analysis, report)

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
                                source_msg_stem_by_target=_source_msg_stems(converts),
                            ),
                        )
                    except Exception as e:
                        raise ConversionError(
                            f"Failed to sync in-game outfit name: {e}") from e
                else:
                    # Delete-only: isolate face/hair against a remaining slot if any.
                    deleted_keys = {op.source.key for op in deletes}
                    remaining = [
                        o for o in _analysis_outfits(analysis)
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
                    drop_mesh_only_hair_pfbs(
                        staging, report,
                        is_addon=bool(analysis.modinfo.addonfor),
                        profile=profile,
                    )
                    notify("Isolating shared outfit textures...")
                    isolate_shared_outfit_textures(
                        staging, face_priv, rename_map, report)

                # Retarget author figure galleries onto the convert target (or base
                # figure/pl paths) so Bonuses keeps custom face/hair after isolation.
                # Delete-only still strips extras.
                if converts:
                    notify("Retargeting figure gallery...")
                    convert_figure_scenes_for_ops(
                        staging,
                        [(op.source, op.target) for op in converts
                         if op.target is not None],
                        rename_map,
                        report,
                    )
                else:
                    notify("Isolating figure gallery (strip author scenes)...")
                    strip_claire_extra_figures(
                        staging, report, figure_prefix=profile.figure_prefix,
                        extra_ids=profile.extra_figure_ids,
                    )

                notify("Removing DLC contentsholder...")
                sync_dlc_contentsholder(staging, package_target, report)

                if rename_map:
                    notify("Patching path strings inside binary files...")
                    patch_binaries(staging, rename_map, report)
                    patch_mdf_material_hashes(staging, rename_map, report)


            if outfit_on_stm and profile.key == "claire":
                from .hair_prefabs import publish_rt_hair_hide
                from .platform.body_prefab import (
                    publish_rt_body_prefabs,
                    publish_rt_slot_body_prefab,
                )
                from .platform.costume_slots import mount_claire_costume_parts

                notify("Publishing ray-tracing costume files...")
                mount_claire_costume_parts(
                    staging, report,
                    face_slot=_claire_destination_face_slot(converts),
                )
                publish_rt_body_prefabs(staging, report)
                for op in converts:
                    if op.target is None:
                        continue
                    for slot in op.target.all_slots:
                        publish_rt_slot_body_prefab(
                            staging, report, op.source, op.target.body_id, slot,
                        )
                        publish_rt_hair_hide(staging, report, op.target, slot)
        face_targets = [
            op.target for op in converts
            if op.target is not None
            and op.target.key in ("military", "tanktop")
        ]
        if skip_outfit and profile.key == "claire" and face_targets:
            # Same-slot ray tracing skips the outfit stages. The clean
            # face still has to land, as classic .tex.10 under x64.
            notify("Applying Military / Tank Top face textures...")
            _apply_face_look(staging, face_targets, analysis, report)

        if skip_outfit and (display_names or display_name):
            # Same-slot ray tracing skips the outfit stages, including the
            # name write. The typed name still has to land in the mod.
            notify("Syncing costume-select name...")
            name_targets: list = []
            seen_keys: set[str] = set()
            for op in converts:
                if op.target is None or op.target.key in seen_keys:
                    continue
                seen_keys.add(op.target.key)
                name_targets.append(op.target)
            try:
                _absorb_msg_lines(
                    report,
                    sync_costume_names_for_targets(
                        staging,
                        name_targets,
                        display_name=display_name,
                        name_target=msg_target,
                        display_names=display_names or None,
                        source_msg_stem_by_target=_source_msg_stems(converts),
                    ),
                )
            except Exception as e:
                raise ConversionError(
                    f"Failed to sync in-game outfit name: {e}") from e
        if skip_outfit and round_trip_off and (
            display_names or display_name
            or any(
                line.startswith("face: seeded Claire default face")
                or " clean face:" in line
                for line in report.rename_ops
            )
        ):
            # Already on natives/stm and staying there. The name file and
            # the new face textures were written under natives/x64 and have
            # to move on their own. A Classic result has already been
            # prepared onto x64; moving the whole tree here would ship
            # ray tracing again.
            from .platform.path_remap import move_tree_to_rt
            from .platform.reports import ConversionReport as PlatformReport

            notify("Moving new files onto the ray-tracing path...")
            plat = PlatformReport()
            move_tree_to_rt(staging, plat)
            _merge_platform(report, plat)

        if round_trip_off and profile.key == "claire":
            # Already ray tracing, so the full upgrade does not run. A face
            # left on pl1050.mesh still replaces the neck on every other outfit.
            from .platform.costume_slots import mount_claire_costume_parts

            notify("Keeping a custom face off the shared head...")
            mount_claire_costume_parts(
                staging, report,
                face_slot=_claire_destination_face_slot(converts),
                hair=False,
            )

        if need_upgrade:
            notify("Upgrading to ray tracing...")
            face_slot = _claire_destination_face_slot(converts)
            try:
                plat = upgrade_to_rt(
                    staging, progress=notify, settings=settings,
                    costume_dest_hint=costume_dest_hint,
                    face_slot=face_slot,
                )
            except PlatformError as exc:
                raise ConversionError(str(exc)) from exc
            _merge_platform(report, plat)

        marker = resolve_tag_marker(package_target, tag_marker)
        do_zip, do_desc, do_name = resolve_convert_tag_flags(
            tag_output, converting=bool(converts),
            tag_modinfo_description=tag_modinfo_description,
            tag_modinfo_name=tag_modinfo_name)
        extra = build_marker if tag_build_zip_name else ""
        desc_build = build_marker if tag_build_modinfo_description else ""
        modinfo_warn = update_modinfo(
            staging, package_target, tag_output=do_desc, tag_marker=marker,
            strip_tag_markers=strip_tag_markers, tag_name=do_name)
        if modinfo_warn:
            report.warnings.append(modinfo_warn)
        if desc_build:
            try:
                append_description_marker(staging, desc_build)
            except OSError as exc:
                report.warnings.append(
                    f"Failed to update modinfo.ini: {exc}")

        from .platform.path_remap import lowercase_stm_tree

        lowered = lowercase_stm_tree(staging)
        if lowered:
            report.rename_ops.append(
                f"lowercased {lowered} ray-tracing paths under natives/stm"
            )

        if write_log:
            log_marker = marker or ""
            if build_marker and (tag_build_zip_name or tag_build_modinfo_description):
                log_marker = f"{log_marker} {build_marker}".strip()
            log_ctx = context_from_analysis(
                analysis, list(ops),
                source_name=source_name,
                as_folder=as_folder,
                tag_output=do_zip or bool(extra),
                tag_marker=log_marker,
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
                tag_output=do_zip, tag_marker=marker,
                strip_tag_markers=strip_tag_markers,
                source_name=source_name, extra_marker=extra)
        else:
            notify("Creating Fluffy-ready zip...")
            report.output_zip = make_zip(
                staging, analysis, package_target, output_dir,
                tag_output=do_zip,
                tag_marker=marker, strip_tag_markers=strip_tag_markers,
                source_name=source_name, extra_marker=extra)
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
    tag_modinfo_description: bool | None = None,
    tag_modinfo_name: bool = False,
    game_build: str | None = None,
    tag_build_zip_name: bool = True,
    tag_build_modinfo_description: bool = True,
    settings: dict | None = None,
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
        raise_if_cancelled()
        report.progress_log.append(msg)
        if _progress:
            _progress(msg)

    output_dir.mkdir(parents=True, exist_ok=True)

    marker = resolve_tag_marker(package_target, tag_marker)
    safe_bundle = safe_name(bundle_name.strip() or "Converted Batch")
    converting = any(op.target is not None for op in use_ops)
    do_zip, do_desc, do_name = resolve_convert_tag_flags(
        tag_output, converting=converting,
        tag_modinfo_description=tag_modinfo_description,
        tag_modinfo_name=tag_modinfo_name)
    if do_zip and marker:
        bundle_base = safe_name(f"{safe_bundle} {marker}")
    else:
        bundle_base = safe_bundle
    item_markers = {
        build_tag_marker(
            item.analysis,
            game_build if game_build in GAME_BUILDS else item.analysis.game_build,
        )
        for item in items
    }
    item_markers.discard("")
    bundle_extra = ""
    if tag_build_zip_name and item_markers:
        if game_build == "Ray tracing" or item_markers == {"[RTX]"}:
            bundle_extra = "[RTX]"
        elif game_build == "Classic" or item_markers == {"[Non-RTX]"}:
            bundle_extra = "[Non-RTX]"
    if bundle_extra:
        bundle_base = safe_name(f"{bundle_base} {bundle_extra}")
    zip_name = f"{bundle_base}.zip"
    zip_path = unique_path(output_dir / zip_name)

    used_names: set[str] = set()
    folder_names: list[str] = []
    item_contexts: list[ConvertLogContext] = []
    staging_tmp = tempfile.TemporaryDirectory(prefix="re2oc_batch_")
    staging_root = Path(staging_tmp.name)

    link_orphan_addons([item.analysis for item in items])
    costume_hint = bundle_costume_hint([item.analysis for item in items])

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
                    tag_modinfo_description=tag_modinfo_description,
                    tag_modinfo_name=tag_modinfo_name,
                    game_build=game_build,
                    tag_build_zip_name=tag_build_zip_name,
                    tag_build_modinfo_description=tag_build_modinfo_description,
                    settings=settings,
                    costume_dest_hint=costume_hint,
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
                        tag_output=do_zip, tag_marker=marker,
                        strip_tag_markers=strip_tag_markers,
                        write_log=False,
                        source_name=folder_name,
                        ops=use_ops,
                        tag_modinfo_description=do_desc,
                        tag_modinfo_name=do_name,
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
                tag_output=do_zip,
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

        if game_build == "Ray tracing":
            report.warnings.extend(park_addon_textures(staging_root))

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


_BUILD_TAG_MARKERS = ["[RTX]", "[Non-RTX]"]


def _game_output_name(
    analysis: AnalysisResult,
    source_name: str | None,
    marker: str,
) -> str:
    base = (
        (source_name or "").strip()
        or analysis.modinfo.name
        or (analysis.root.name if analysis.root else "mod")
    )
    base = strip_converter_tags(base, _BUILD_TAG_MARKERS).strip() or "mod"
    if marker:
        return safe_name(f"{base} {marker}")
    return safe_name(base)


def _run_game_build_stages(
    staging: Path,
    analysis: AnalysisResult,
    game_build: str,
    report: ConversionReport,
    notify,
    settings: dict | None,
) -> str:
    """Platform stages only. No outfit ops, face isolation, or costume name."""
    chosen = game_build if game_build in GAME_BUILDS else GAME_BUILDS[0]
    already = (
        (chosen == "Classic" and analysis.game_label == "Classic")
        or (chosen == "Ray tracing" and analysis.game_label == "Ray tracing")
    )
    if already:
        return chosen
    if chosen == "Classic":
        notify("Preparing a classic tree...")
        try:
            plat = prepare_classic(
                staging, progress=notify, settings=settings)
        except PlatformError as exc:
            raise ConversionError(str(exc)) from exc
        _merge_platform(report, plat)
    else:
        notify("Upgrading to ray tracing...")
        try:
            plat = upgrade_to_rt(
                staging, progress=notify, settings=settings)
        except PlatformError as exc:
            raise ConversionError(str(exc)) from exc
        _merge_platform(report, plat)
    return chosen


def _convert_one_game_build(
    analysis: AnalysisResult,
    output_dir: Path,
    *,
    game_build: str,
    progress=None,
    as_folder: bool = False,
    folder_name: str | None = None,
    source_name: str | None = None,
    write_log: bool = True,
    tag_build_zip_name: bool = True,
    tag_build_modinfo_description: bool = True,
    settings: dict | None = None,
) -> ConversionReport:
    if analysis.root is None or not analysis.root.is_dir():
        raise ConversionError("Analysis has no mod root to convert.")

    report = ConversionReport()

    def notify(msg: str) -> None:
        raise_if_cancelled()
        report.progress_log.append(msg)
        if progress:
            progress(msg)

    output_dir.mkdir(parents=True, exist_ok=True)
    staging_tmp = tempfile.TemporaryDirectory(prefix="re2oc_stage_")
    staging = Path(staging_tmp.name)
    try:
        notify("Copying mod to staging folder...")
        shutil.copytree(analysis.root, staging, dirs_exist_ok=True)
        chosen = _run_game_build_stages(
            staging, analysis, game_build, report, notify, settings)
        marker = build_tag_marker(analysis, chosen)
        if tag_build_modinfo_description and marker:
            try:
                append_description_marker(staging, marker)
            except OSError as exc:
                report.warnings.append(f"Failed to update modinfo.ini: {exc}")
        name_marker = marker if tag_build_zip_name else ""
        name = folder_name or _game_output_name(
            analysis, source_name, name_marker)
        if write_log:
            log_ctx = context_from_analysis(
                analysis, [],
                source_name=source_name or name,
                as_folder=as_folder,
                tag_output=bool(name_marker),
                tag_marker=name_marker,
                package_name=(
                    f"{'folder' if as_folder else 'zip'} "
                    f"(includes convert.log)"
                ),
            )
            write_convert_log_to_staging(staging, report, log_ctx)
        if as_folder:
            notify("Writing mod folder...")
            dest = unique_path(output_dir / safe_name(name))
            shutil.move(str(staging), str(dest))
            report.output_folder = dest
        else:
            notify("Creating Fluffy-ready zip...")
            zip_path = unique_path(output_dir / f"{safe_name(name)}.zip")
            zip_directory(staging, zip_path)
            report.output_zip = zip_path
    finally:
        staging_tmp.cleanup()
    return report


def convert_game_build(
    analyses: AnalysisResult | Sequence[AnalysisResult],
    output_dir: Path,
    *,
    game_build: str,
    progress=None,
    source_name: str | None = None,
    bundle_name: str | None = None,
    write_log: bool = True,
    tag_build_zip_name: bool = True,
    tag_build_modinfo_description: bool = True,
    settings: dict | None = None,
) -> ConversionReport | BatchReport:
    """Convert one mod, or a batch, between Classic and ray tracing.

    Copies each package and runs ``prepare_classic`` or ``upgrade_to_rt``.
    Outfit slots, face isolation, and costume names are left alone.
    """
    items = (
        [analyses] if isinstance(analyses, AnalysisResult) else list(analyses)
    )
    if not items:
        raise ConversionError("Batch is empty.")
    if len(items) == 1:
        return _convert_one_game_build(
            items[0], output_dir,
            game_build=game_build,
            progress=progress,
            source_name=source_name,
            write_log=write_log,
            tag_build_zip_name=tag_build_zip_name,
            tag_build_modinfo_description=tag_build_modinfo_description,
            settings=settings,
        )

    report = BatchReport()

    def notify(msg: str) -> None:
        raise_if_cancelled()
        report.progress_log.append(msg)
        if progress:
            progress(msg)

    output_dir.mkdir(parents=True, exist_ok=True)
    chosen = game_build if game_build in GAME_BUILDS else GAME_BUILDS[0]
    safe_bundle = safe_name(
        (bundle_name or "").strip() or source_name or "Converted Batch")
    item_markers = {
        build_tag_marker(item, chosen) for item in items
    }
    item_markers.discard("")
    bundle_extra = ""
    if tag_build_zip_name and item_markers:
        if chosen == "Ray tracing" or item_markers == {"[RTX]"}:
            bundle_extra = "[RTX]"
        elif chosen == "Classic" or item_markers == {"[Non-RTX]"}:
            bundle_extra = "[Non-RTX]"
    bundle_base = safe_bundle
    if bundle_extra:
        bundle_base = safe_name(f"{bundle_base} {bundle_extra}")
    zip_path = unique_path(output_dir / f"{bundle_base}.zip")

    used_names: set[str] = set()
    folder_names: list[str] = []
    item_contexts: list[ConvertLogContext] = []
    staging_tmp = tempfile.TemporaryDirectory(prefix="re2oc_batch_")
    staging_root = Path(staging_tmp.name)
    try:
        for i, item in enumerate(items, start=1):
            root = item.root
            preferred = (
                (root.name if root is not None else "")
                or item.modinfo.name
                or f"mod {i}"
            )
            base_name = unique_folder_name(
                item, used_names, preferred=preferred,
                strip_tag_markers=_BUILD_TAG_MARKERS,
            )
            used_names.add(base_name.lower())
            marker = build_tag_marker(item, chosen) if tag_build_zip_name else ""
            folder_name = (
                safe_name(f"{base_name} {marker}") if marker else base_name)
            notify(f"[{i}/{len(items)}] Converting {folder_name}...")
            try:
                item_report = _convert_one_game_build(
                    item, staging_root,
                    game_build=chosen,
                    progress=None,
                    as_folder=True,
                    folder_name=folder_name,
                    source_name=folder_name,
                    write_log=False,
                    tag_build_zip_name=tag_build_zip_name,
                    tag_build_modinfo_description=tag_build_modinfo_description,
                    settings=settings,
                )
            except (ConversionError, OSError) as exc:
                report.warnings.append(f"{folder_name}: {exc}")
                continue
            used_names.add(folder_name.lower())
            report.items.append(item_report)
            folder_names.append(folder_name)
            item_contexts.append(context_from_analysis(
                item, [],
                source_name=folder_name,
                as_folder=True,
                tag_output=bool(marker),
                tag_marker=marker,
                label=folder_name,
                package_name=f"folder {folder_name}/ (see bundle convert.log)",
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
