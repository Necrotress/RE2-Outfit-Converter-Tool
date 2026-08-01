"""Promote deleted-slot body assets onto convert survivors before strip.

Duplicate-slot packs (e.g. Jacket + Tank Top sharing one dress) often keep
meshes on both body IDs but textures under only one. Deleting that slot
without promoting blanks the surviving convert.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .isolation import add_rename, register_material_name_aliases
from .outfit_ops import OutfitOp
from .paths import MESH_ROOTS, resolve_ci
from .reports import ConversionReport

_TEX_HINT = (".tex", ".mdf2")


def _body_folder_has_textures(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    return any(
        p.is_file() and any(h in p.name.lower() for h in _TEX_HINT)
        for p in folder.rglob("*")
    )


def _remap_name(name: str, old_id: str, new_id: str) -> str:
    name_low = name.lower()
    old_l = old_id.lower()
    if name_low.startswith(f"--{old_l}"):
        return new_id + name[len(old_id) + 2:]
    if name_low.startswith(old_l):
        return new_id + name[len(old_id):]
    if old_l in name_low:
        idx = name_low.index(old_l)
        return name[:idx] + new_id + name[idx + len(old_id):]
    return name


def _remap_rel(rel: Path, old_id: str, new_id: str) -> Path:
    return Path(*[_remap_name(p, old_id, new_id) for p in rel.parts])


def _merge_into_existing(
    src: Path,
    dest: Path,
    staging: Path,
    old_id: str,
    new_id: str,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> int:
    """Merge files from ``src`` into existing ``dest``. Returns files moved."""
    moved = 0
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        dest_rel = _remap_rel(rel, old_id, new_id)
        dest_file = dest / dest_rel
        if dest_file.exists():
            continue
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        old_rel = path.relative_to(staging).as_posix()
        shutil.move(str(path), str(dest_file))
        add_rename(
            rename_map, old_rel, dest_file.relative_to(staging).as_posix())
        moved += 1
    register_material_name_aliases(dest, old_id, new_id, rename_map)
    return moved


def _rename_folder_to_new(
    src: Path,
    dest: Path,
    staging: Path,
    old_id: str,
    new_id: str,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    """Rename ``src`` → ``dest`` and remap file stems that embed ``old_id``."""
    files = [f.relative_to(src) for f in src.rglob("*") if f.is_file()]
    old_rels = {
        rel: (src / rel).relative_to(staging).as_posix() for rel in files
    }
    src.rename(dest)
    report.rename_ops.append(f"promoted folder {old_id}/  ->  {new_id}/")
    for rel in sorted(files):
        cur = dest / rel
        if not cur.exists():
            continue
        dest_rel = _remap_rel(rel, old_id, new_id)
        final = dest / dest_rel
        if dest_rel != rel:
            final.parent.mkdir(parents=True, exist_ok=True)
            if not final.exists():
                cur.rename(final)
            else:
                final = cur
        add_rename(
            rename_map, old_rels[rel],
            final.relative_to(staging).as_posix())
    register_material_name_aliases(dest, old_id, new_id, rename_map)


def merge_or_rename_body(
    staging: Path,
    old_id: str,
    new_id: str,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> bool:
    """Move/merge ``old_id`` body folders into ``new_id`` across MESH_ROOTS."""
    if old_id == new_id or len(old_id) != len(new_id):
        return False
    promoted = False
    for root in MESH_ROOTS:
        root_dir = resolve_ci(staging, root)
        if root_dir is None or not root_dir.is_dir():
            continue

        # Sidecar files beside the body folder (e.g. pl1001.chain.21).
        for entry in list(root_dir.iterdir()):
            if not entry.is_file():
                continue
            name_low = entry.name.lower()
            if not (
                name_low.startswith(old_id.lower() + ".")
                or name_low.startswith(old_id.lower() + "_")
            ):
                continue
            new_name = new_id + entry.name[len(old_id):]
            dest_file = entry.with_name(new_name)
            if dest_file.exists():
                continue
            old_rel = entry.relative_to(staging).as_posix()
            entry.rename(dest_file)
            add_rename(
                rename_map, old_rel, dest_file.relative_to(staging).as_posix())
            report.rename_ops.append(f"promoted {entry.name}  ->  {new_name}")
            promoted = True

        src = resolve_ci(staging, f"{root}/{old_id}")
        if src is None or not src.is_dir():
            continue

        existing = resolve_ci(staging, f"{root}/{new_id}")
        if existing is not None and existing.is_dir():
            n = _merge_into_existing(
                src, existing, staging, old_id, new_id, rename_map, report)
            if n:
                report.rename_ops.append(
                    f"promoted {n} file(s) from {old_id}/ into {new_id}/"
                )
                promoted = True
            shutil.rmtree(src, ignore_errors=True)
            report.removed_ops.append(
                f"removed leftover {old_id}/ after promote into {new_id}/"
            )
        else:
            dest = root_dir / new_id
            _rename_folder_to_new(
                src, dest, staging, old_id, new_id, rename_map, report)
            promoted = True

    return promoted


def promote_deleted_body_assets(
    staging: Path,
    deletes: list[OutfitOp],
    converts: list[OutfitOp],
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    """Before strip: move deleted-slot body assets onto a convert source body.

    Assets then ride the normal convert rename (source → target) so textures
    that only lived on the deleted sibling still appear on the target outfit.
    """
    if not deletes or not converts:
        return

    receivers = [op.source for op in converts if op.target is not None]
    if not receivers:
        return

    for del_op in deletes:
        deleted_id = del_op.source.body_id
        if any(r.body_id == deleted_id for r in receivers):
            continue

        has_assets = False
        for root in MESH_ROOTS:
            folder = resolve_ci(staging, f"{root}/{deleted_id}")
            if folder is not None and folder.is_dir() and any(folder.iterdir()):
                has_assets = True
                break
            root_dir = resolve_ci(staging, root)
            if root_dir is None:
                continue
            for entry in root_dir.iterdir():
                name_low = entry.name.lower()
                if (
                    name_low.startswith(deleted_id.lower() + ".")
                    or name_low.startswith(deleted_id.lower() + "_")
                ):
                    has_assets = True
                    break
            if has_assets:
                break
        if not has_assets:
            continue

        receiver = receivers[0]
        for cand in receivers:
            for root in MESH_ROOTS:
                if resolve_ci(staging, f"{root}/{cand.body_id}") is not None:
                    receiver = cand
                    break
            else:
                continue
            break

        del_has_tex = False
        need_promote = False
        for root in MESH_ROOTS:
            d_folder = resolve_ci(staging, f"{root}/{deleted_id}")
            r_folder = resolve_ci(staging, f"{root}/{receiver.body_id}")
            if d_folder is not None and _body_folder_has_textures(d_folder):
                del_has_tex = True
            if r_folder is None and d_folder is not None:
                need_promote = True
        if del_has_tex:
            need_promote = True
        if not need_promote:
            continue

        report.rename_ops.append(
            f"promote deleted {del_op.source.name} ({deleted_id}) body "
            f"assets into {receiver.name} ({receiver.body_id}) before strip"
        )
        merge_or_rename_body(
            staging, deleted_id, receiver.body_id, rename_map, report,
        )
