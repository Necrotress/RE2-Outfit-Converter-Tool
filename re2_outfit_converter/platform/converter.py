"""Ray-tracing platform stages. Mutates a staging folder; does not zip."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable

from ..cancel import raise_if_cancelled
from .nested import nested_package_dirs
from .blender_batch import (
    apply_blender_result_to_report,
    collect_mesh_mdf_jobs,
    collect_shipped_mmtr,
    run_blender_batch,
)
from .blender_detect import probe_blender, resolve_blender_for_convert
from .formats import (
    RE2_PAK_ROOTS,
    RE2_PLAYER_ID,
    classic_suffix_for,
    is_junk_file,
    parse_versioned_name,
    remap_rel_to_classic,
    rt_suffix_for,
)
from .path_patch import patch_binaries
from .path_remap import (
    move_tree_to_classic,
    move_tree_to_rt,
    stm_to_x64_rename_map,
    x64_to_stm_rename_map,
)
from .chain_convert import convert_chain_to_rt
from .pfb_convert import convert_chain, convert_pfb
from .reports import ConversionError, ConversionReport, FormatConversionError
from .body_prefab import publish_classic_body_prefabs, publish_rt_body_prefabs
from .costume_slots import mount_claire_costume_parts
from .tex_convert import convert_tex_file, convert_tex_to_rt

ProgressCb = Callable[[str], None] | None

_RE3_PLAYER_ID = re.compile(r"^pl2\d{3}$", re.IGNORECASE)
_RE2_CLAIRE_ID = re.compile(r"^pl1\d{3}$", re.IGNORECASE)
# Shared face/hair and the Noir/Military hat slots. A private face such as
# pl1810/pl1060.mesh is the same kind of file: the stem is what the game
# loads, and counting that folder as a costume leaves color add-ons on wap100.
_FACE_HAIR_FOLDERS = frozenset({
    "pl1050", "pl1057", "pl1060", "pl1070", "pl1071", "pl1075",
})


def _is_face_or_hair_file(path: Path) -> bool:
    stem = path.name.split(".", 1)[0].lower()
    if stem in _FACE_HAIR_FOLDERS:
        return True
    # pl1050/pl1050_04/pl1050_04_face_albm.tex — the face id is an ancestor,
    # not the parent of the texture.
    for parent in path.parents:
        name = parent.name.lower()
        if name in _FACE_HAIR_FOLDERS:
            return True
        if name == "player":
            break
    return False

# Stock engine nulls both dumps already ship. A converted copy overrides the
# game's file (Sportsuit NullWhite is 384 vs vanilla RT 128) and that can
# checkerboard every material that binds the slot. Inverse: drop the same
# names going classic so we do not overlay the Non-RTX dump either.
_STOCK_NULL_FOLDERS = frozenset({
    ("systems", "rendering"),
    ("mastermaterial", "textures"),
    ("vfx", "recordsystem", "recordtexture", "basetextures"),
})


def _is_stock_engine_null(rel_posix: str) -> bool:
    parts = rel_posix.replace("\\", "/").split("/")
    if len(parts) < 4 or parts[0].lower() != "natives":
        return False
    name = parts[-1].lower()
    if not name.startswith("null") or ".tex." not in name:
        return False
    folder = [p.lower() for p in parts[2:-1]]
    if folder and folder[0] == "streaming":
        folder = folder[1:]
    return tuple(folder) in _STOCK_NULL_FOLDERS



def prepare_classic(
    staging: Path,
    *,
    progress: ProgressCb = None,
    settings: dict | None = None,
    blender_path: str | Path | None = None,
    use_blender: bool | None = None,
) -> ConversionReport:
    """Turn a ray-tracing or dual tree into classic ``natives/x64``.

    A classic-only tree is left as it is. A dual pack drops ``natives/stm``
    when the classic file is already there, then converts anything that
    only existed on the ray-tracing side.
    """
    return _apply_platform(
        staging, to_rt=False, progress=progress, settings=settings,
        blender_path=blender_path, use_blender=use_blender,
    )


def upgrade_to_rt(
    staging: Path,
    *,
    progress: ProgressCb = None,
    settings: dict | None = None,
    blender_path: str | Path | None = None,
    use_blender: bool | None = None,
    costume_dest_hint: str | None = None,
    face_slot: str | None = None,
) -> ConversionReport:
    """Rebuild ``staging`` as a ray-tracing ``natives/stm`` tree.

    A tree that is already ray tracing is left as it is.
    """
    return _apply_platform(
        staging, to_rt=True, progress=progress, settings=settings,
        blender_path=blender_path, use_blender=use_blender,
        costume_dest_hint=costume_dest_hint,
        face_slot=face_slot,
    )


def bundle_costume_hint(analyses) -> str | None:
    """Costume folder shared by a batch, ignoring face-only packages."""
    return _bundle_costume_prefix([(item, "") for item in analyses])


def park_addon_textures(staging_root: Path) -> list[str]:
    """Move add-on suit textures onto the one costume folder in a batch."""
    warnings: list[str] = []
    _park_bundle_addon_textures(staging_root, warnings)
    return warnings


def _apply_platform(
    staging: Path,
    *,
    to_rt: bool,
    progress: ProgressCb = None,
    settings: dict | None = None,
    blender_path: str | Path | None = None,
    use_blender: bool | None = None,
    costume_dest_hint: str | None = None,
    face_slot: str | None = None,
) -> ConversionReport:
    """Mutate ``staging`` in place. Does not zip or edit modinfo."""
    report = ConversionReport()

    def notify(msg: str) -> None:
        raise_if_cancelled()
        if progress:
            progress(msg)

    _strip_junk(staging, report, to_rt=to_rt)

    if not to_rt and _staging_is_dual(staging):
        report.mode = "dual_pack_strip"
        notify("Dual-pack: removing stm files that already exist in x64…")
        _strip_stm_counterparts(staging, report)
    elif to_rt:
        report.mode = "full_convert_to_rt"
    else:
        report.mode = "full_convert"

    needs_work = (
        _platform_has_files(staging, "x64") or _has_classic_extensions(staging)
        if to_rt else
        _stm_has_files(staging) or _has_rt_extensions(staging)
    )
    if not needs_work:
        return report

    if to_rt:
        report.mode = "full_convert_to_rt"
    elif report.mode != "dual_pack_strip":
        report.mode = "full_convert"
    notify("Converting textures…")
    _convert_textures_and_unsupported(staging, report, notify, to_rt=to_rt)
    re3_player_dest = None
    if to_rt:
        _nest_unknown_roots_under_sectionroot(staging, report)
        _fold_streaming_texture_twins(staging, report)
        re3_player_dest = _relocate_unmounted_player_textures(staging, report)
        re3_mesh_dest = _relocate_re3_player_textures(staging, report)
        re3_player_dest = (
            re3_player_dest or re3_mesh_dest or costume_dest_hint
        )

    blender, reason = resolve_blender_for_convert(
        settings, blender_path=blender_path, use_blender=use_blender,
    )
    jobs = collect_mesh_mdf_jobs(staging, to_rt=to_rt)
    if jobs:
        if blender is None:
            raise ConversionError(reason)
        probe = probe_blender(blender)
        if not probe.ok:
            detail = probe.message or "RE Mesh Editor is not ready."
            raise ConversionError(
                f"{detail} Mesh and material conversion needs Blender 4.3 "
                "and RE Mesh Editor (see Settings)."
            )
        notify(f"Blender: {len(jobs)} mesh/mdf job(s)…")
        batch = run_blender_batch(
            blender, jobs, progress=progress,
            shipped_mmtr=collect_shipped_mmtr(staging),
            re3_player_dest=re3_player_dest,
        )
        apply_blender_result_to_report(staging, batch, report)
        _drop_stock_shader_overrides(staging, report)
        if batch.message:
            report.warnings.append(batch.message)

    if (
        not report.converted_ops
        and report.passthrough_ops
        and _only_unsupported_files(staging)
    ):
        raise ConversionError(
            "Nothing in this mod could be converted. It only contains "
            "formats with no converter (pfb, chain, mmtr, rtex), so "
            "the output would be the original files under a new folder."
        )

    if to_rt:
        notify("Remapping natives/x64 → natives/stm…")
        move_tree_to_rt(staging, report)
        notify("Patching embedded paths…")
        patch_binaries(staging, x64_to_stm_rename_map(), report)
        mount_claire_costume_parts(staging, report, face_slot=face_slot)
        publish_rt_body_prefabs(staging, report)
    else:
        notify("Remapping natives/stm → natives/x64…")
        move_tree_to_classic(staging, report)
        notify("Patching embedded paths…")
        patch_binaries(staging, stm_to_x64_rename_map(), report)
        publish_classic_body_prefabs(staging, report)

    if report.failed_ops:
        if blender is not None:
            advice = (
                "Blender ran but could not read or write them, usually "
                "because the mod's own data trips up RE Mesh Editor. "
                "The game falls back to the vanilla part for those."
            )
        else:
            advice = (
                "For mesh/mdf, install Blender + RE Mesh Editor and set "
                "the path in Settings."
            )
        report.warnings.append(
            f"{len(report.failed_ops)} file(s) could not be converted and "
            f"were removed. {advice}"
        )
    carried = _unsupported_kinds(report)
    if carried:
        report.warnings.append(_unsupported_warning(carried))
    if any(op.startswith("mmtr:") for op in report.passthrough_ops):
        report.warnings.append(_MMTR_WARNING)

    natives_left = staging / "natives"
    if not natives_left.is_dir() or not any(
        p.is_file() for p in natives_left.rglob("*")
    ):
        raise ConversionError(
            "Output has no natives/ files after convert. "
            "Unsupported files (pfb, chain, mmtr) were removed and "
            "nothing else was left to ship."
        )
    return report


def _staging_is_dual(staging: Path) -> bool:
    return (
        _platform_has_files(staging, "stm")
        and _platform_has_files(staging, "x64")
        and _has_rt_extensions(staging)
        and _has_classic_extensions(staging)
    )



def _copy_mod_tree(src: Path, dest: Path, *, dirs_exist_ok: bool = False) -> None:
    """Copy a package without the nested mods that are converted on their own."""
    skip = {item.resolve() for item in nested_package_dirs(src)}

    def ignore(directory: str, names: list[str]) -> list[str]:
        base = Path(directory)
        return [
            name for name in names
            if (base / name).resolve() in skip
        ]

    shutil.copytree(src, dest, ignore=ignore, dirs_exist_ok=dirs_exist_ok)


def _only_unsupported_files(staging: Path) -> bool:
    """True when every natives file is a format this converter does not rewrite."""
    natives = staging / "natives"
    if not natives.is_dir():
        return False
    files = [path for path in natives.rglob("*") if path.is_file()]
    if not files:
        return False
    tokens = (".pfb.", ".chain.", ".mmtr.", ".rtex.")
    return all(
        any(token in path.name.lower() for token in tokens)
        for path in files
    )


def _rel(staging: Path, path: Path) -> str:
    try:
        return path.relative_to(staging).as_posix()
    except ValueError:
        return path.name


def _strip_junk(
    staging: Path,
    report: ConversionReport,
    *,
    to_rt: bool = False,
    drop_rtex: bool = True,
) -> None:
    natives = staging / "natives"
    if not natives.is_dir():
        return
    for path in list(natives.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        lower = name.lower()
        rel = path.relative_to(staging).as_posix()
        if _is_stock_engine_null(rel):
            try:
                path.unlink()
                report.removed_ops.append(rel)
                report.warnings.append(
                    f"Dropped stock engine texture {rel} so the game's file loads"
                )
            except OSError as e:
                report.warnings.append(f"Could not remove stock texture {rel}: {e}")
            continue
        under_stm = "/stm/" in rel.lower()
        if (
            drop_rtex
            and not to_rt
            and (".rtex." in lower or lower.endswith(".rtex"))
            and (under_stm or lower.endswith(".rtex.5"))
        ):
            # RT rtex.5 is not a classic rtex.4. Classicize already retargets
            # those binds, so the file is dropped on the way to classic.
            # Classic → RT keeps the file beside the path the mod authored.
            # Aiming every Rec_RTT at Claire's record texture was wrong for
            # Ada (pl2000).
            try:
                path.unlink()
                report.removed_ops.append(rel)
                report.warnings.append(
                    f"Removed unsupported render-target {rel}"
                )
            except OSError as e:
                report.warnings.append(f"Could not remove rtex {rel}: {e}")
            continue
        if lower.endswith((".tga", ".texout", ".blend", ".fbx", ".obj", ".dds")):
            try:
                path.unlink()
                report.removed_ops.append(rel)
            except OSError as e:
                report.warnings.append(f"Could not remove junk {rel}: {e}")
        elif is_junk_file(name) and not lower.endswith((".tex.10", ".tex.34")):
            if lower.endswith((".psd", ".txt", ".md")):
                try:
                    path.unlink()
                    report.removed_ops.append(rel)
                except OSError:
                    pass


def _stm_dir(staging: Path) -> Path | None:
    natives = staging / "natives"
    if not natives.is_dir():
        return None
    for child in natives.iterdir():
        if child.is_dir() and child.name.lower() == "stm":
            return child
    return None


def _stm_has_files(staging: Path) -> bool:
    return _platform_has_files(staging, "stm")


def _platform_has_files(staging: Path, platform: str) -> bool:
    natives = staging / "natives"
    if not natives.is_dir():
        return False
    for child in natives.iterdir():
        if child.is_dir() and child.name.lower() == platform:
            return any(p.is_file() for p in child.rglob("*"))
    return False


def _has_classic_extensions(staging: Path) -> bool:
    natives = staging / "natives"
    if not natives.is_dir():
        return False
    for path in natives.rglob("*"):
        if not path.is_file():
            continue
        parsed = parse_versioned_name(path.name)
        if parsed is not None and rt_suffix_for(parsed.suffix):
            return True
    return False


def _has_rt_extensions(staging: Path) -> bool:
    natives = staging / "natives"
    if not natives.is_dir():
        return False
    for path in natives.rglob("*"):
        if not path.is_file():
            continue
        parsed = parse_versioned_name(path.name)
        if parsed is not None and classic_suffix_for(parsed.suffix):
            return True
    return False


def _strip_stm_counterparts(staging: Path, report: ConversionReport) -> None:
    """Drop stm files whose classic path already exists. Keep stm-only files."""
    stm = _stm_dir(staging)
    if stm is None:
        return
    removed = 0
    for src in list(stm.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(staging).as_posix()
        dest = staging.joinpath(*remap_rel_to_classic(rel).split("/"))
        if not dest.is_file() or dest.resolve() == src.resolve():
            continue
        try:
            src.unlink()
            report.removed_ops.append(rel)
            removed += 1
        except OSError as e:
            report.warnings.append(f"Could not strip {rel}: {e}")
    _remove_empty_stm(stm, report, removed)


def _remove_empty_stm(stm: Path, report: ConversionReport, removed: int) -> None:
    if not stm.exists():
        return
    for path in sorted(stm.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    if any(p.is_file() for p in stm.rglob("*")):
        if removed:
            report.warnings.append(
                "Dual-pack kept stm files that had no classic counterpart "
                "and will convert those."
            )
        return
    try:
        shutil.rmtree(stm)
        report.removed_ops.append("natives/stm")
        report.converted_ops.append(
            "dual-pack strip: kept natives/x64, removed natives/stm"
        )
    except OSError as e:
        report.warnings.append(f"Could not remove natives/stm: {e}")


def is_rt_mmtr(suffix: str) -> bool:
    return suffix.lower().startswith("mmtr.") and suffix.lower() != "mmtr.1808160001"


def _rename_converted(path: Path, *, to_rt: bool = False) -> Path:
    """Rename the version suffix after the bytes have been rewritten."""
    parsed = parse_versioned_name(path.name)
    if parsed is None or parsed.kind not in ("tex", "mdf2", "mesh", "chain"):
        return path
    mapped = (
        rt_suffix_for(parsed.suffix) if to_rt
        else classic_suffix_for(parsed.suffix)
    )
    if mapped is None:
        return path
    dest = path.with_name(f"{parsed.stem}.{mapped}")
    if dest.resolve() == path.resolve():
        return path
    if dest.exists():
        dest.unlink()
    path.replace(dest)
    return dest


_UNSUPPORTED_EFFECT = {
    "pfb": "costume prefabs (pfb) that wire the outfit into its slot",
    "chain": "physics chains (chain) for hair and cloth",
}

def _drop_stock_shader_overrides(staging: Path, report) -> None:
    """Remove mod-shipped shaders that shadow one the game already has.

    The material pass has just re-aimed every reference away from a shipped
    mmtr, laying the materials out for the stock shader. If the mod's copy
    stayed it would keep overriding that stock shader by name, and the
    rebuilt materials would meet the wrong parameter list. This bites on the
    way back to classic in particular, where a shipped mmtr is a live
    override rather than an inert ride-along.
    """
    from .blender_batch import stock_shader_overrides

    for path in stock_shader_overrides(staging):
        rel = _rel(staging, path)
        path.unlink()
        report.removed_ops.append(f"mod copy of a stock shader: {rel}")
        report.passthrough_ops[:] = [
            op for op in report.passthrough_ops if not op.endswith(rel)
        ]


# mmtr gets its own note: the files still ride along, but nothing points at
# them any more because the material pass re-aims every reference.
# Folders are not part of this. Escape/ and pl2000/ stay where the mod put them.
_MMTR_WARNING = (
    "This mod ships its own master materials (mmtr). A master material is "
    "compiled for one engine build, so the other game cannot load it — the "
    "materials that used one were re-aimed at the closest stock shader "
    "instead, which can change how those parts look. Where the mod's shader "
    "shared a name with one the game ships, the mod's copy was dropped so "
    "the game's own shader loads; the rest ride along unused."
)


def _unsupported_kinds(report: ConversionReport) -> list[str]:
    """pfb/chain kinds shipped unchanged because they cannot convert."""
    kinds: list[str] = []
    for entry in report.passthrough_ops:
        kind = entry.split(":", 1)[0].strip()
        if kind in _UNSUPPORTED_EFFECT and kind not in kinds:
            kinds.append(kind)
    return kinds


def _unsupported_warning(kinds: list[str]) -> str:
    what = [_UNSUPPORTED_EFFECT[k] for k in kinds]
    if len(what) == 1:
        listed = what[0]
    elif len(what) == 2:
        listed = f"{what[0]} and {what[1]}"
    else:
        listed = f"{', '.join(what[:-1])}, and {what[-1]}"
    return (
        f"This mod ships {listed}. Those formats have no converter, so they "
        "were copied over unchanged. If the target game does not read that "
        "file version, the outfit can fall back to the vanilla model or "
        "fail to load. Test this one in game before relying on it."
    )


def _carry_unsupported(
    path: Path,
    staging: Path,
    report: ConversionReport,
    kind: str,
) -> None:
    """Ship a format we cannot convert as-is.

    The community workflow converts mesh / mdf / tex and moves everything
    else untouched. A file the target game does not read is inert, while a
    missing one the mod's materials point at is fatal.
    """
    report.passthrough_ops.append(
        f"{kind}: {path.relative_to(staging).as_posix()}")


def _convert_textures_and_unsupported(
    staging: Path,
    report: ConversionReport,
    notify: Callable[[str], None],
    *,
    to_rt: bool = False,
) -> None:
    """Convert TEX and classic chain.21 in Python. pfb and mmtr stay unconverted.

    Mesh/mdf are handled separately via Blender batch.
    """
    natives = staging / "natives"
    if not natives.is_dir():
        return
    files = [p for p in natives.rglob("*") if p.is_file()]
    for i, path in enumerate(files):
        raise_if_cancelled()
        parsed = parse_versioned_name(path.name)
        if parsed is None:
            continue
        kind = parsed.kind
        ver_suffix = parsed.suffix
        if to_rt:
            if kind == "tex" and ver_suffix == "tex.10":
                _try_convert(
                    path, staging, report,
                    lambda data, n=path.name: convert_tex_to_rt(data, name=n),
                    "tex", to_rt=True)
            elif kind == "pfb" and ver_suffix == "pfb.16":
                _carry_unsupported(path, staging, report, "pfb")
            elif kind == "chain" and ver_suffix == "chain.21":
                _try_convert(
                    path, staging, report, convert_chain_to_rt, "chain",
                    to_rt=True, keep_on_failure=True)
            elif kind == "mmtr" and ver_suffix == "mmtr.1808160001":
                _carry_unsupported(path, staging, report, "mmtr")
        elif kind == "tex" and ver_suffix == "tex.34":
            _try_convert(path, staging, report, convert_tex_file, "tex")
        elif kind == "pfb" and ver_suffix == "pfb.17":
            _try_convert(
                path, staging, report, convert_pfb, "pfb", keep_on_failure=True)
        elif kind == "chain" and ver_suffix == "chain.46":
            _try_convert(
                path, staging, report, convert_chain, "chain",
                keep_on_failure=True)
        elif kind == "mmtr" and is_rt_mmtr(ver_suffix):
            _carry_unsupported(path, staging, report, "mmtr")
        if i % 25 == 0:
            notify(f"Converting textures… ({i + 1}/{len(files)})")


def _nest_unknown_roots_under_sectionroot(
    staging: Path, report: ConversionReport
) -> None:
    """Merge RE3/custom roots into sectionroot so RT can resolve them.

    ``escape/character/...`` becomes ``sectionroot/character/...``, not
    ``sectionroot/escape/character/...``. An extra Escape folder under
    SectionRoot still checkerboards. Inverse is a no-op: classic Fluffy
    already loads unknown roots, and the flattened tree stays on the way back.
    """
    natives = staging / "natives"
    if not natives.is_dir():
        return
    for plat in list(natives.iterdir()):
        if not plat.is_dir():
            continue
        _flatten_unknown_children(plat, staging, report)
        stream = plat / "streaming"
        if stream.is_dir():
            _flatten_unknown_children(stream, staging, report)


_LIFT_PAK_ROOTS = RE2_PAK_ROOTS - {"sectionroot", "streaming"}


def _flatten_unknown_children(
    parent: Path, staging: Path, report: ConversionReport
) -> None:
    section = parent / "sectionroot"
    for child in list(parent.iterdir()):
        if not child.is_dir() or child.name.lower() in RE2_PAK_ROOTS:
            continue
        name = child.name
        merged_section = False
        for item in list(child.iterdir()):
            if item.is_file():
                section.mkdir(parents=True, exist_ok=True)
                target = section / item.name
                if target.exists():
                    try:
                        if target.stat().st_size >= item.stat().st_size:
                            item.unlink()
                            merged_section = True
                            continue
                        target.unlink()
                    except OSError:
                        continue
                shutil.move(str(item), str(target))
                merged_section = True
                continue
            if not item.is_dir():
                continue
            gname = item.name.lower()
            if gname in _LIFT_PAK_ROOTS:
                dest = parent / gname
                _merge_tree_into(item, dest)
                report.warnings.append(
                    f"Moved contents of {name}/{item.name}/ into "
                    f"{dest.relative_to(staging).as_posix()}/ "
                    "so RT can resolve those textures"
                )
            elif gname == "setmodel":
                dest = parent / "objectroot" / item.name
                _merge_tree_into(item, dest)
                report.warnings.append(
                    f"Moved contents of {name}/{item.name}/ into "
                    f"{dest.relative_to(staging).as_posix()}/ "
                    "so RT can resolve those textures"
                )
            else:
                dest = section / item.name
                _merge_tree_into(item, dest)
                merged_section = True
        shutil.rmtree(child, ignore_errors=True)
        if merged_section:
            report.warnings.append(
                f"Moved contents of {name}/ into "
                f"{section.relative_to(staging).as_posix()}/ "
                "so RT can resolve those textures"
            )
    if not section.is_dir():
        return
    for child in list(section.iterdir()):
        if not child.is_dir():
            continue
        low = child.name.lower()
        if low in _LIFT_PAK_ROOTS:
            dest = parent / low
            _merge_tree_into(child, dest)
            report.warnings.append(
                f"Moved contents of sectionroot/{child.name}/ into "
                f"{dest.relative_to(staging).as_posix()}/ "
                "so RT can resolve those textures"
            )
            continue
        if low == "setmodel":
            dest = parent / "objectroot" / child.name
            _merge_tree_into(child, dest)
            report.warnings.append(
                f"Moved contents of sectionroot/{child.name}/ into "
                f"{dest.relative_to(staging).as_posix()}/ "
                "so RT can resolve those textures"
            )
            continue
        if low not in {"escape", "details"}:
            continue
        name = child.name
        _merge_tree_into(child, section)
        report.warnings.append(
            f"Moved contents of sectionroot/{name}/ into "
            f"{section.relative_to(staging).as_posix()}/ "
            "so RT can resolve those textures"
        )


def _park_bundle_addon_textures(
    staging_root: Path, warnings: list[str]
) -> None:
    """Land add-on suit textures on the costume folder the main mod uses.

    The main mod's mesh tells the convert where ``wap100`` and
    ``pl2000/mesh`` textures have to sit. A color add-on is only those
    textures, so that step does not run and the red files stay on a path
    the outfit no longer reads. One costume folder in the bundle is the
    destination. Two different costume folders are left alone.
    """
    rels: list[Path] = []
    for mod in staging_root.iterdir():
        if not mod.is_dir():
            continue
        rel = _bundle_costume_rel(mod)
        if rel is not None:
            rels.append(rel)
    unique = {rel.as_posix().lower(): rel for rel in rels}
    if len(unique) != 1:
        if len(unique) > 1:
            warnings.append(
                "Add-on textures were left in place: this bundle has "
                "more than one costume folder"
            )
        return
    costume_rel = next(iter(unique.values()))
    for mod in staging_root.iterdir():
        if not mod.is_dir() or _bundle_costume_rel(mod) is not None:
            continue
        moved = _move_unmounted_textures_to(mod, mod / costume_rel)
        if moved:
            warnings.append(
                f"Moved {moved} add-on texture(s) from {mod.name} next to "
                f"{costume_rel.as_posix()}/ so they replace the main mod"
            )


def _bundle_costume_rel(mod_root: Path) -> Path | None:
    natives = mod_root / "natives"
    if not natives.is_dir():
        return None
    for plat in natives.iterdir():
        if not plat.is_dir():
            continue
        section = plat / "sectionroot"
        dest = _find_claire_costume_dir(section)
        if dest is None:
            dest = _find_claire_costume_tex_dir(section)
        if dest is not None:
            return dest.relative_to(mod_root)
    return None


def _find_claire_costume_tex_dir(section: Path) -> Path | None:
    """Costume folder that holds suit textures after the mesh was removed."""
    player = section / "character" / "player"
    if not player.is_dir():
        return None
    hits: list[Path] = []
    for pl in player.iterdir():
        if not pl.is_dir() or not _RE2_CLAIRE_ID.match(pl.name):
            continue
        for tex in pl.rglob("*"):
            if not tex.is_file() or ".tex." not in tex.name.lower():
                continue
            if _is_face_or_hair_file(tex):
                continue
            hits.append(tex.parent)
    if not hits:
        return None
    hits.sort(key=lambda p: -len(p.relative_to(player).parts))
    return hits[0]


def _move_unmounted_textures_to(mod_root: Path, dest: Path) -> int:
    natives = mod_root / "natives"
    if not natives.is_dir():
        return 0
    moved = 0
    for plat in natives.iterdir():
        if not plat.is_dir():
            continue
        roots = [plat / "sectionroot" / "character" / "player"]
        stream_player = (
            plat / "streaming" / "sectionroot" / "character" / "player"
        )
        if stream_player.is_dir():
            roots.append(stream_player)
        sources: list[Path] = []
        for player in roots:
            if not player.is_dir():
                continue
            for child in player.iterdir():
                if child.is_dir() and not RE2_PLAYER_ID.match(child.name):
                    sources.append(child)
            sources.extend(_re3_mesh_texture_dirs(player))
        for folder in sources:
            for src in list(folder.rglob("*")):
                if not src.is_file() or ".tex." not in src.name.lower():
                    continue
                if dest in src.parents:
                    continue
                dest_name = src.name
                low_name = src.name.lower()
                under_stm = any(part.lower() == "stm" for part in dest.parts)
                payload: bytes | None = None
                if under_stm and low_name.endswith(".tex.10"):
                    try:
                        payload = convert_tex_to_rt(src.read_bytes(), name=src.name)
                        dest_name = src.name[:-2] + "34"
                    except (OSError, ValueError, FormatConversionError):
                        payload = None
                        dest_name = src.name
                target = dest / dest_name
                target.parent.mkdir(parents=True, exist_ok=True)
                if (
                    target.exists()
                    and target.stat().st_size >= src.stat().st_size
                ):
                    try:
                        src.unlink()
                    except OSError:
                        pass
                else:
                    if target.exists():
                        try:
                            target.unlink()
                        except OSError:
                            pass
                    if payload is not None:
                        target.write_bytes(payload)
                        try:
                            src.unlink()
                        except OSError:
                            pass
                    else:
                        shutil.move(str(src), str(target))
                moved += 1
            if folder.exists() and not any(
                p.is_file() for p in folder.rglob("*")
            ):
                shutil.rmtree(folder, ignore_errors=True)
    return moved


def _find_claire_costume_dir(section: Path) -> Path | None:
    """Folder that already holds a Claire body mesh (pl1000/pl1004, …).

    Face and hair folders (pl1050, pl1060, pl1070) are not a costume.
    A bunny-ears add-on is only those meshes. Counting it made the
    bundle look like two costumes, so the gold textures stayed on wap100.
    """
    player = section / "character" / "player"
    if not player.is_dir():
        return None
    hits: list[Path] = []
    for pl in player.iterdir():
        if not pl.is_dir() or not _RE2_CLAIRE_ID.match(pl.name):
            continue
        for mesh in pl.rglob("*"):
            if not mesh.is_file() or ".mesh." not in mesh.name.lower():
                continue
            if _is_face_or_hair_file(mesh):
                continue
            hits.append(mesh.parent)
    if not hits:
        return None
    hits.sort(key=lambda p: -len(p.relative_to(player).parts))
    return hits[0]


def _bundle_costume_prefix(items) -> str | None:
    """MDF prefix of the one body costume in a bundle, if there is one.

    Face-only packages are ignored. Two different body folders return
    nothing so each mod keeps its own path.
    """
    prefixes: list[str] = []
    for analysis, _name in items:
        root = analysis.root
        if root is None:
            continue
        natives = root / "natives"
        if not natives.is_dir():
            continue
        for plat in natives.iterdir():
            if not plat.is_dir():
                continue
            section = plat / "sectionroot"
            dest = _find_claire_costume_dir(section)
            if dest is None:
                continue
            prefixes.append(_mdf_prefix_for_costume(section, dest))
            break
    unique = {prefix.lower(): prefix for prefix in prefixes}
    if len(unique) != 1:
        return None
    return next(iter(unique.values()))


def _mdf_prefix_for_costume(section: Path, dest: Path) -> str:
    parts = ["SectionRoot"]
    for part in dest.relative_to(section).parts:
        low = part.lower()
        if low == "character":
            parts.append("Character")
        elif low == "player":
            parts.append("Player")
        else:
            parts.append(part)
    return "/".join(parts)


def _fold_streaming_texture_twins(staging: Path, report: ConversionReport) -> None:
    """One TEX per path on the way to RT.

    Classic keeps a small base file and a larger copy under ``streaming/``
    for the same slot. Each file is a full TEX, so upgrading both leaves two
    headers. RT reads them as one texture and checkerboards the material.
    The streaming file is the fuller image (Sportsuit cotton, cover, sling).
    It replaces the base, and the streaming copy is removed. A streaming-only
    file stays. Inverse is a no-op: classic already uses these pairs, and
    this runs only toward RT.
    """
    natives = staging / "natives"
    if not natives.is_dir():
        return
    folded = 0
    for plat in natives.iterdir():
        if not plat.is_dir():
            continue
        stream = plat / "streaming"
        if not stream.is_dir():
            continue
        for src in list(stream.rglob("*")):
            if not src.is_file() or ".tex." not in src.name.lower():
                continue
            base = plat / src.relative_to(stream)
            if not base.is_file():
                continue
            if src.stat().st_size > base.stat().st_size:
                base.write_bytes(src.read_bytes())
            try:
                src.unlink()
            except OSError as e:
                report.warnings.append(
                    f"Could not remove streaming twin {src.name}: {e}"
                )
                continue
            folded += 1
            report.removed_ops.append(
                f"streaming twin: {_rel(staging, src)}"
            )
        if stream.is_dir() and not any(p.is_file() for p in stream.rglob("*")):
            shutil.rmtree(stream, ignore_errors=True)
    if folded:
        report.warnings.append(
            f"Folded {folded} streaming texture twin(s) into the base file "
            "so RT does not checkerboard that slot"
        )


def _relocate_unmounted_player_textures(
    staging: Path, report: ConversionReport
) -> str | None:
    """Move textures under a non-player folder onto the costume mesh folder.

    Vanilla RT ``character/player`` children are ``pl`` plus four digits.
    Hardcore Punisher's suit albedo is ``player/wap100/pl2020/mesh/``,
    which the dump does not have, so the body draws the missing-texture
    checker while hair under ``pl1000/pl1070`` does not. Files land next
    to the Claire costume mesh (the folder the body prefab already
    loads). ``pl2000`` matches the vanilla shape and is left alone.
    Inverse is a no-op: classicize does not move the path back.
    """
    natives = staging / "natives"
    if not natives.is_dir():
        return None
    prefix = None
    for plat in natives.iterdir():
        if not plat.is_dir():
            continue
        section = plat / "sectionroot"
        dest = _find_claire_costume_dir(section)
        if dest is None:
            continue
        prefix = _mdf_prefix_for_costume(section, dest)
        roots = [section / "character" / "player"]
        stream_player = (
            plat / "streaming" / "sectionroot" / "character" / "player"
        )
        if stream_player.is_dir():
            roots.append(stream_player)
        for player in roots:
            if not player.is_dir():
                continue
            for child in list(player.iterdir()):
                if not child.is_dir() or RE2_PLAYER_ID.match(child.name):
                    continue
                name = child.name
                moved = 0
                for src in list(child.rglob("*")):
                    if not src.is_file() or ".tex." not in src.name.lower():
                        continue
                    target = dest / src.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if (
                        target.exists()
                        and target.stat().st_size >= src.stat().st_size
                    ):
                        try:
                            src.unlink()
                        except OSError:
                            pass
                    else:
                        if target.exists():
                            try:
                                target.unlink()
                            except OSError:
                                pass
                        shutil.move(str(src), str(target))
                    moved += 1
                if child.exists() and not any(
                    p.is_file() for p in child.rglob("*")
                ):
                    shutil.rmtree(child, ignore_errors=True)
                if moved:
                    report.warnings.append(
                        f"Moved {moved} texture(s) out of player/{name}/ "
                        f"next to {dest.relative_to(staging).as_posix()}/ "
                        "so RT can resolve them"
                    )
    return prefix


def _re3_mesh_texture_dirs(player: Path) -> list[Path]:
    """``player/pl2000/mesh`` and ``player/pl2000/pl2005/mesh``.

    Not ``player/pl2000/pl2050`` itself. Those are face meshes, not textures.
    """
    found: list[Path] = []
    if not player.is_dir():
        return found
    for folder in player.rglob("*"):
        if not folder.is_dir() or folder.name.lower() != "mesh":
            continue
        if not _RE3_PLAYER_ID.match(folder.parent.name):
            continue
        # pl2050/mesh is the face, not the suit textures.
        if folder.parent.name.lower() in {"pl1050", "pl1060", "pl1070", "pl2050"}:
            continue
        found.append(folder)
    return found


def _relocate_re3_player_textures(
    staging: Path, report: ConversionReport
) -> str | None:
    """Move pl2000/mesh textures next to the RE2 costume mesh.

    RTX has no texture folder at ``character/player/pl2000/mesh``. A suit
    whose albedo stays there checkerboards. Face files under pl2050 stay.
    Inverse is a no-op.
    """
    natives = staging / "natives"
    if not natives.is_dir():
        return None
    prefix = None
    for plat in natives.iterdir():
        if not plat.is_dir():
            continue
        section = plat / "sectionroot"
        dest = _find_claire_costume_dir(section)
        if dest is None:
            continue
        prefix = _mdf_prefix_for_costume(section, dest)
        roots = [section / "character" / "player"]
        stream_player = (
            plat / "streaming" / "sectionroot" / "character" / "player"
        )
        if stream_player.is_dir():
            roots.append(stream_player)
        moved = 0
        for player in roots:
            for mesh_dir in _re3_mesh_texture_dirs(player):
                for src in list(mesh_dir.rglob("*")):
                    if not src.is_file() or ".tex." not in src.name.lower():
                        continue
                    target = dest / src.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if (
                        target.exists()
                        and target.stat().st_size >= src.stat().st_size
                    ):
                        try:
                            src.unlink()
                        except OSError:
                            pass
                    else:
                        if target.exists():
                            try:
                                target.unlink()
                            except OSError:
                                pass
                        shutil.move(str(src), str(target))
                    moved += 1
                if mesh_dir.exists() and not any(
                    p.is_file() for p in mesh_dir.rglob("*")
                ):
                    shutil.rmtree(mesh_dir, ignore_errors=True)
        if moved:
            report.warnings.append(
                f"Moved {moved} texture(s) out of player/pl2000/mesh/ "
                f"next to {dest.relative_to(staging).as_posix()}/ "
                "so RT can resolve them"
            )
    return prefix


def _merge_tree_into(src_dir: Path, dest_root: Path) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)
    for src in src_dir.rglob("*"):
        if not src.is_file():
            continue
        target = dest_root / src.relative_to(src_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            try:
                if target.stat().st_size >= src.stat().st_size:
                    src.unlink()
                    continue
                target.unlink()
            except OSError:
                continue
        shutil.move(str(src), str(target))
    shutil.rmtree(src_dir, ignore_errors=True)


def _try_convert(
    path: Path,
    staging: Path,
    report: ConversionReport,
    fn,
    label: str,
    *,
    to_rt: bool = False,
    keep_on_failure: bool = False,
) -> None:
    """Convert one file in place, then rename it to the target suffix.

    ``keep_on_failure`` ships the original bytes untouched. Only safe for
    kinds the tree move leaves alone (pfb / chain / mmtr): a kept tex would
    later be renamed to the other suffix and ship the wrong bytes.
    """
    rel = path.relative_to(staging).as_posix()
    try:
        data = path.read_bytes()
        out = fn(data)
        path.write_bytes(out)
        renamed = _rename_converted(path, to_rt=to_rt)
        shown = renamed.relative_to(staging).as_posix()
        report.converted_ops.append(f"{label}: {shown}")
        return
    except FormatConversionError as e:
        reason = str(e)
    except OSError as e:
        reason = str(e)

    if keep_on_failure and path.is_file():
        report.passthrough_ops.append(f"{label}: {rel}")
        return
    report.failed_ops.append(f"{rel}: {reason}")
    try:
        if path.is_file():
            path.unlink()
            report.removed_ops.append(rel)
    except OSError:
        pass


__all__ = ["convert", "ConversionReport", "ConversionError", "input_base_name"]
