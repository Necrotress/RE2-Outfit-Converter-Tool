"""Body mesh rename and sectionroot/streaming sync."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .analyzer import AnalysisResult
from .character import CLAIRE_PROFILE, CharacterProfile
from .isolation import add_rename, rename_entries
from .outfits import (
    CLAIRE_FACE_IDS,
    CLAIRE_HAIR_MESH_IDS,
    CLAIRE_OUTFIT_BY_BODY_ID,
    CLAIRE_SHARED_IDS,
    LEON_FACE_IDS,
    LEON_HAIR_MESH_IDS,
    LEON_OUTFIT_BY_BODY_ID,
    LEON_SHARED_IDS,
    Outfit,
)
from .paths import MESH_ROOTS, mesh_roots, parts_dir, resolve_ci
from .reports import ConversionReport

_PL_ID_RE = re.compile(r"pl[0-9]\d{3}", re.IGNORECASE)


def _mesh_ids_from_natives(
    natives_files: list[str],
    roots: tuple[str, ...] | None = None,
) -> set[str]:
    """Collect plXXXX IDs that appear under mesh roots in a natives file list."""
    use_roots = roots or MESH_ROOTS
    found: set[str] = set()
    for rel in natives_files:
        low = rel.lower().replace("\\", "/")
        for root in use_roots:
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


def body_id_on_disk(staging: Path, outfit: Outfit) -> bool:
    """True when this body id is a folder or file under the mesh roots now.

    Promote can create the source folder after analysis was taken. The
    pre-promote file list must not decide that the folder is absent.
    """
    profile = outfit.profile or CLAIRE_PROFILE
    bid = outfit.body_id.lower()
    for root in mesh_roots(profile):
        root_dir = resolve_ci(staging, root)
        if root_dir is None:
            continue
        for entry in root_dir.iterdir():
            name = entry.name.lower()
            if (
                name == bid
                or name.startswith(bid + ".")
                or name.startswith(bid + "_")
            ):
                return True
    return False


def has_mesh_entry(analysis: AnalysisResult, pl_id: str) -> bool:
    if analysis._mesh_id_set is None:
        roots = (
            analysis.profile.mesh_roots if analysis.profile is not None
            else MESH_ROOTS
        )
        analysis._mesh_id_set = _mesh_ids_from_natives(
            analysis.natives_files, roots)
    return pl_id.lower() in analysis._mesh_id_set


def convert_mesh_ids(staging: Path, _analysis: AnalysisResult,
                      source: Outfit, target: Outfit,
                      rename_map: dict[str, str],
                      report: ConversionReport) -> None:
    """Rename body mesh folders only; face/hair are handled by isolation."""
    old_id, new_id = source.body_id, target.body_id
    if old_id == new_id:
        return
    profile = target.profile or source.profile or CLAIRE_PROFILE
    for root in mesh_roots(profile):
        root_dir = resolve_ci(staging, root)
        if root_dir is not None:
            rename_entries(root_dir, staging, old_id, new_id, rename_map, report,
                           register_dir_prefix=True)


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
    profile = target.profile or CLAIRE_PROFILE
    for source in sources:
        old_id = source.body_id
        if old_id == target.body_id:
            continue
        for root in mesh_roots(profile):
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
    """Custom plXXXX ids referenced by target body PFBs (e.g. pl1008 redirects)."""
    profile = target.profile or CLAIRE_PROFILE
    parts = resolve_ci(staging, parts_dir(profile))
    if parts is None:
        return set()
    shared = (
        CLAIRE_SHARED_IDS | CLAIRE_FACE_IDS | CLAIRE_HAIR_MESH_IDS
        if profile.key == "claire" else
        LEON_SHARED_IDS | LEON_FACE_IDS | LEON_HAIR_MESH_IDS
    )
    skip = (
        {target.body_id.lower(), profile.player_root}
        | {x.lower() for x in shared}
    )
    found: set[str] = set()
    root_name = profile.player_root
    for slot in target.all_slots:
        for pfb in parts.glob(f"{root_name}_body_{slot}.pfb*"):
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
    # Only retarget IDs that still exist on disk (incl. nested host redirects).
    body_map = (
        CLAIRE_OUTFIT_BY_BODY_ID if profile.key == "claire"
        else LEON_OUTFIT_BY_BODY_ID
    )
    outfit_bodies = {b.lower() for b in body_map}
    kept: set[str] = set()
    for pid in found:
        if pid in outfit_bodies:
            continue
        for root in mesh_roots(profile):
            root_dir = resolve_ci(staging, root)
            if root_dir is not None and _custom_body_present(
                root_dir, pid, host_name=profile.player_root,
            ):
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
    profile = target.profile or CLAIRE_PROFILE
    for custom_id in sorted(custom_ids):
        if len(custom_id) != len(new_id):
            report.warnings.append(
                f"Could not retarget custom body {custom_id} → {new_id}: "
                "id length mismatch."
            )
            continue
        _retarget_one_custom_body(
            staging, custom_id, new_id, rename_map, report, profile=profile)


def _custom_body_present(
    root_dir: Path,
    custom_id: str,
    *,
    host_name: str = "pl1000",
) -> bool:
    cid = custom_id.lower()
    host = host_name.lower()
    for entry in root_dir.iterdir():
        name = entry.name.lower()
        if name == cid or name.startswith(cid + ".") or name.startswith(cid + "_"):
            return True
        if entry.is_dir() and name == host:
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
    *,
    profile: CharacterProfile | None = None,
) -> None:
    profile = profile or CLAIRE_PROFILE
    host_name = profile.player_root
    for root in mesh_roots(profile):
        root_dir = resolve_ci(staging, root)
        if root_dir is None:
            continue
        if not _custom_body_present(
            root_dir, custom_id, host_name=host_name,
        ):
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

        # Top-level custom id / chain under the mesh root.
        rename_entries(
            root_dir, staging, custom_id, new_id, rename_map, report,
            register_dir_prefix=True)

        # Nested host folder: pl1000/pl1008.mesh (Jacket-id folder redirect).
        host = next(
            (c for c in root_dir.iterdir()
             if c.is_dir() and c.name.lower() == host_name.lower()),
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


def sync_streaming_meshes(staging: Path, target: Outfit,
                           report: ConversionReport) -> None:
    """Ensure mesh folders exist under both sectionroot and streaming roots.

    RE2 loads low-res from sectionroot and high-res from streaming/sectionroot.
    Mods often ship only one; converting into another outfit (e.g. Elza→Noir)
    then blends mod textures with vanilla target textures and looks broken.
    """
    profile = target.profile or CLAIRE_PROFILE
    roots = mesh_roots(profile)
    section = resolve_ci(staging, roots[0])
    stream = resolve_ci(staging, roots[1])

    if section is not None and stream is None:
        stream = staging / roots[1]
        stream.mkdir(parents=True, exist_ok=True)
    elif stream is not None and section is None:
        section = staging / roots[0]
        section.mkdir(parents=True, exist_ok=True)

    if section is None and stream is None:
        return

    sec_by = ({c.name.lower(): c for c in section.iterdir()}
              if section is not None else {})
    str_by = ({c.name.lower(): c for c in stream.iterdir()}
              if stream is not None else {})
    names = sorted(set(sec_by) | set(str_by))
    prefix = profile.player_root[:3]  # pl1 / pl0

    for name_low in names:
        if not name_low.startswith(prefix):
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
