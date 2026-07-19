"""Body mesh rename and sectionroot/streaming sync."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .analyzer import AnalysisResult
from .isolation import add_rename, rename_entries
from .outfits import (
    CLAIRE_FACE_IDS,
    CLAIRE_HAIR_MESH_IDS,
    CLAIRE_OUTFIT_BY_BODY_ID,
    CLAIRE_SHARED_IDS,
    Outfit,
)
from .paths import MESH_ROOTS, PARTS_DIR, resolve_ci
from .reports import ConversionReport

_PL_ID_RE = re.compile(r"pl1\d{3}", re.IGNORECASE)


def _mesh_ids_from_natives(natives_files: list[str]) -> set[str]:
    """Collect pl1xxx IDs that appear under MESH_ROOTS in a natives file list."""
    found: set[str] = set()
    for rel in natives_files:
        low = rel.lower().replace("\\", "/")
        for root in MESH_ROOTS:
            root_l = root.lower()
            if not low.startswith(root_l):
                continue
            rest = low[len(root_l):]
            if not rest.startswith("/"):
                continue
            m = _PL_ID_RE.match(rest, 1)
            if m:
                found.add(m.group(0).lower())
    return found


def has_mesh_entry(analysis: AnalysisResult, pl_id: str) -> bool:
    if analysis._mesh_id_set is None:
        analysis._mesh_id_set = _mesh_ids_from_natives(analysis.natives_files)
    return pl_id.lower() in analysis._mesh_id_set


def convert_mesh_ids(staging: Path, _analysis: AnalysisResult,
                      source: Outfit, target: Outfit,
                      rename_map: dict[str, str],
                      report: ConversionReport) -> None:
    """Rename body mesh folders only; face/hair are handled by isolation."""
    old_id, new_id = source.body_id, target.body_id
    if old_id == new_id:
        return
    for root in MESH_ROOTS:
        root_dir = resolve_ci(staging, root)
        if root_dir is not None:
            rename_entries(root_dir, staging, old_id, new_id, rename_map, report)


def purge_source_body_meshes(
    staging: Path,
    sources: list[Outfit],
    target: Outfit,
    report: ConversionReport,
) -> None:
    """Delete source body mesh leftovers that still override the old outfit.

    Happens when renaming ``pl1004`` → ``pl1006`` is skipped because the
    target folder already exists (common when Elza + Jacket are both selected
    on Nurse-style packs that host a custom body under ``pl1000``).
    """
    for source in sources:
        old_id = source.body_id
        if old_id == target.body_id:
            continue
        for root in MESH_ROOTS:
            root_dir = resolve_ci(staging, root)
            if root_dir is None:
                continue
            for entry in sorted(root_dir.iterdir(), key=lambda p: p.name.lower()):
                name_low = entry.name.lower()
                if not (name_low == old_id
                        or name_low.startswith(old_id + ".")
                        or name_low.startswith(old_id + "_")):
                    continue
                rel = entry.relative_to(staging).as_posix()
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink(missing_ok=True)
                report.removed_ops.append(rel)
                report.warnings.append(
                    f"Removed leftover {entry.name} from {source.name} so it "
                    f"no longer overrides that outfit in-game."
                )


def _body_pfb_custom_ids(staging: Path, target: Outfit) -> set[str]:
    """Custom pl1xxx ids referenced by target body PFBs (e.g. pl1008 redirects)."""
    parts = resolve_ci(staging, PARTS_DIR)
    if parts is None:
        return set()
    skip = (
        {target.body_id.lower(), "pl1000"}
        | {x.lower() for x in CLAIRE_SHARED_IDS}
        | {x.lower() for x in CLAIRE_FACE_IDS}
        | {x.lower() for x in CLAIRE_HAIR_MESH_IDS}
    )
    found: set[str] = set()
    for slot in target.all_slots:
        for pfb in parts.glob(f"pl1000_body_{slot}.pfb*"):
            if not pfb.is_file():
                continue
            data = pfb.read_bytes()
            # Prefer UTF-16 ASCII runs so odd-length headers don't garble IDs.
            chars: list[str] = []
            chunks: list[str] = []
            i = 0
            while i + 1 < len(data):
                if data[i + 1] == 0 and 32 <= data[i] < 127:
                    chars.append(chr(data[i]))
                    i += 2
                else:
                    if chars:
                        chunks.append("".join(chars))
                        chars = []
                    i += 1
            if chars:
                chunks.append("".join(chars))
            text = "\n".join(chunks) + "\n" + data.decode("ascii", errors="ignore")
            for m in _PL_ID_RE.finditer(text):
                pid = m.group(0).lower()
                if pid not in skip:
                    found.add(pid)
    # Only retarget IDs that still exist on disk (incl. nested pl1000/pl1008).
    # After convert_mesh_ids the source body id may linger in the unpatched PFB
    # while the folder is already target.body_id — do not treat that as custom.
    outfit_bodies = {b.lower() for b in CLAIRE_OUTFIT_BY_BODY_ID}
    kept: set[str] = set()
    for pid in found:
        if pid in outfit_bodies:
            continue
        for root in MESH_ROOTS:
            root_dir = resolve_ci(staging, root)
            if root_dir is not None and _custom_body_present(root_dir, pid):
                kept.add(pid)
                break
    return kept


def retarget_redirect_bodies(
    staging: Path,
    target: Outfit,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    """Move PFB-redirect custom bodies onto ``target.body_id``.

    Nurse / Ghost Witch style packs keep the real mesh as ``pl1008`` under
    ``pl1000/`` while the outfit body id is ``pl1004``/``pl1005``. After a
    slot convert the PFB still points at ``pl1008``, which '98 ignores in
    favor of vanilla ``pl1007``. Same-length retarget (pl1008→pl1007) fixes it.
    """
    custom_ids = _body_pfb_custom_ids(staging, target)
    if not custom_ids:
        return
    new_id = target.body_id.lower()
    for custom_id in sorted(custom_ids):
        if len(custom_id) != len(new_id):
            report.warnings.append(
                f"Could not retarget custom body {custom_id} → {new_id}: "
                "id length mismatch."
            )
            continue
        _retarget_one_custom_body(
            staging, custom_id, new_id, rename_map, report)


def _custom_body_present(root_dir: Path, custom_id: str) -> bool:
    cid = custom_id.lower()
    for entry in root_dir.iterdir():
        name = entry.name.lower()
        if name == cid or name.startswith(cid + ".") or name.startswith(cid + "_"):
            return True
        if entry.is_dir() and name == "pl1000":
            for child in entry.iterdir():
                cname = child.name.lower()
                if (cname == cid or cname.startswith(cid + ".")
                        or cname.startswith(cid + "_") or cid in cname):
                    return True
    return False


def _retarget_one_custom_body(
    staging: Path,
    custom_id: str,
    new_id: str,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    for root in MESH_ROOTS:
        root_dir = resolve_ci(staging, root)
        if root_dir is None:
            continue
        if not _custom_body_present(root_dir, custom_id):
            continue

        # Drop stub target body left from source-outfit rename so custom can
        # take the slot (e.g. tiny pl1007 from pl1004 sitting beside pl1008).
        for entry in list(root_dir.iterdir()):
            name_low = entry.name.lower()
            if not (name_low == new_id
                    or name_low.startswith(new_id + ".")
                    or name_low.startswith(new_id + "_")):
                continue
            # Keep if this entry is somehow the custom id (shouldn't happen).
            if name_low == custom_id or name_low.startswith(custom_id + "."):
                continue
            rel = entry.relative_to(staging).as_posix()
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
            report.removed_ops.append(rel)
            report.warnings.append(
                f"Removed stub {entry.name} so custom body {custom_id} "
                f"can occupy {new_id}."
            )

        # Top-level pl1008 / pl1008.chain under the mesh root.
        rename_entries(
            root_dir, staging, custom_id, new_id, rename_map, report)

        # Nested host folder: pl1000/pl1008.mesh (Jacket-id folder redirect).
        host = next(
            (c for c in root_dir.iterdir()
             if c.is_dir() and c.name.lower() == "pl1000"),
            None,
        )
        if host is None:
            continue
        dest_dir = root_dir / new_id
        moved_any = False
        for entry in list(host.iterdir()):
            name_low = entry.name.lower()
            if not (name_low == custom_id
                    or name_low.startswith(custom_id + ".")
                    or name_low.startswith(custom_id + "_")
                    or custom_id in name_low):
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            new_name = entry.name
            if name_low.startswith(custom_id):
                new_name = new_id + entry.name[len(custom_id):]
            elif custom_id in name_low:
                idx = name_low.index(custom_id)
                new_name = (
                    entry.name[:idx] + new_id + entry.name[idx + len(custom_id):]
                )
            dest = dest_dir / new_name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            old_rel = entry.relative_to(staging).as_posix()
            entry.rename(dest)
            new_rel = dest.relative_to(staging).as_posix()
            add_rename(rename_map, old_rel, new_rel)
            report.rename_ops.append(
                f"{old_rel}  ->  {new_rel} (retarget body)")
            moved_any = True
        if moved_any:
            # Always patch bare id for PFB path strings.
            rename_map[custom_id] = new_id
            try:
                if not any(host.iterdir()):
                    host.rmdir()
            except OSError:
                pass
def sync_streaming_meshes(staging: Path, _target: Outfit,
                           report: ConversionReport) -> None:
    """Ensure mesh folders exist under both sectionroot and streaming roots.

    RE2 loads low-res from sectionroot and high-res from streaming/sectionroot.
    Mods often ship only one; converting into another outfit (e.g. Elza→Noir)
    then blends mod textures with vanilla target textures and looks broken.
    """
    section = resolve_ci(staging, MESH_ROOTS[0])
    stream = resolve_ci(staging, MESH_ROOTS[1])

    if section is not None and stream is None:
        stream = staging / MESH_ROOTS[1]
        stream.mkdir(parents=True, exist_ok=True)

    if section is None and stream is None:
        return

    sec_by = ({c.name.lower(): c for c in section.iterdir()}
              if section is not None else {})
    str_by = ({c.name.lower(): c for c in stream.iterdir()}
              if stream is not None else {})
    names = sorted(set(sec_by) | set(str_by))

    for name_low in names:
        if not name_low.startswith("pl1"):
            continue
        sec_item = sec_by.get(name_low)
        str_item = str_by.get(name_low)
        if sec_item is not None and str_item is None and stream is not None:
            dest = stream / sec_item.name
            if sec_item.is_dir():
                shutil.copytree(sec_item, dest)
            else:
                shutil.copy2(sec_item, dest)
            report.rename_ops.append(f"mirrored to streaming: {sec_item.name}")
        elif str_item is not None and sec_item is None and section is not None:
            dest = section / str_item.name
            if str_item.is_dir():
                shutil.copytree(str_item, dest)
            else:
                shutil.copy2(str_item, dest)
            report.rename_ops.append(
                f"mirrored to sectionroot: {str_item.name}")
