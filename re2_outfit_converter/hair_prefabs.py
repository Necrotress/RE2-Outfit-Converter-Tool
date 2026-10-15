"""Hair redirect PFB injection for exclusive hats and isolated hair."""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .analyzer import AnalysisResult, PfbSlot
from .character import CLAIRE_PROFILE, CharacterProfile
from .isolation import alias_standard_mesh_paths, staging_mesh_ids
from .material_hash import material_name_hash
from .outfits import EXCLUSIVE_PART_IDS, Outfit
from .path_patch import patch_ascii_ci, patch_utf16_ci, utf16_ascii_lower
from .paths import (
    PFB_EXT_RE,
    assets_dir,
    ensure_dir_ci,
    folder_has_mdf,
    mesh_roots,
    parts_dir,
    resolve_ci,
)
from .reports import ConversionReport

# A private face folder (pl1813/pl1060.mesh) is not a hair kit. Counting it
# keeps a mesh-only AddonFor hair prefab that overwrites the main redirect.
_FACE_MESH_STEMS = frozenset({
    "pl1050", "pl1057", "pl1060",
    "pl0050", "pl0057", "pl0060",
})

# Digits (pl1678) and author alphanumeric kits (pl107t / plnico).
_HAIR_MESH_STEM_RE = re.compile(
    r"^(pl[0-9a-zA-Z]{4})\.(?:mesh)(?:\.\d+)?$", re.IGNORECASE)
_HAIR_MDF_STEM_RE = re.compile(
    r"^(pl[0-9a-zA-Z]{4})\.(?:mdf2)(?:\.\d+)?$", re.IGNORECASE)
_HAIR_CHAIN_STEM_RE = re.compile(
    r"^(pl[0-9a-zA-Z]{4})\.(?:chain)(?:\.\d+)?$", re.IGNORECASE)


def detect_hair_asset_stems(
    staging: Path,
    hair_folder_id: str,
    *,
    profile: CharacterProfile | None = None,
) -> tuple[str, str]:
    """Return (mesh_stem, mdf_stem) for files inside ``hair_folder_id``.

    Custom kits often live as ``pl1605/pl1678.mesh`` or ``pl1070/pl107t.mesh``
    — folder id ≠ file stem. Defaults both stems to ``hair_folder_id`` when
    no matching file is found.
    """
    mesh_stem = hair_folder_id
    mdf_stem = hair_folder_id
    found_mesh = False
    found_mdf = False
    for root in mesh_roots(profile):
        folder = resolve_ci(staging, f"{root}/{hair_folder_id}")
        if folder is None or not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            if not found_mesh:
                m = _HAIR_MESH_STEM_RE.match(path.name)
                if m:
                    mesh_stem = m.group(1)
                    found_mesh = True
            if not found_mdf:
                m = _HAIR_MDF_STEM_RE.match(path.name)
                if m:
                    mdf_stem = m.group(1)
                    found_mdf = True
        if found_mesh and found_mdf:
            break
    if found_mesh and not found_mdf:
        mdf_stem = mesh_stem
    return mesh_stem, mdf_stem


def _hair_folder_has_mesh(
    staging: Path,
    hair_id: str,
    profile: CharacterProfile | None,
) -> bool:
    """True when the hair folder contains a .mesh file."""
    for root in mesh_roots(profile):
        folder = resolve_ci(staging, f"{root}/{hair_id}")
        if folder is None or not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.is_file() and _HAIR_MESH_STEM_RE.match(path.name):
                return True
    return False


_HAIR_MAT_SUFFIXES = ("_Hair_Mat", "_Hair2_Mat", "_Hair3_Mat")


def align_hair_mdf_materials(
    staging: Path,
    hair_folder_id: str,
    mdf_stem: str,
    pak_hair_id: str,
    *,
    profile: CharacterProfile | None = None,
    report: ConversionReport | None = None,
) -> None:
    """Rename hair material tokens so they match the vanilla hair mesh.

    Texture paths stay on the private folder. Only ``*_Hair_Mat``,
    ``*_Hair2_Mat``, and ``*_Hair3_Mat`` are rewritten, so a blonde
    ``pl1800_Hair_ALBA`` file is left where the material file points.
    """
    if (
        not mdf_stem
        or not pak_hair_id
        or mdf_stem.lower() == pak_hair_id.lower()
        or len(mdf_stem) != len(pak_hair_id)
    ):
        return
    roots: list[str] = []
    for root in mesh_roots(profile):
        roots.append(root)
        stm = root.replace("natives/x64/", "natives/stm/")
        if stm not in roots:
            roots.append(stm)
    changed = False
    for root in roots:
        folder = resolve_ci(staging, f"{root}/{hair_folder_id}")
        if folder is None or not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file() or ".mdf2" not in path.name.lower():
                continue
            data = path.read_bytes()
            patched = data
            for suffix in _HAIR_MAT_SUFFIXES:
                old = f"{mdf_stem}{suffix}"
                new = f"{pak_hair_id}{suffix}"
                patched = _patch_equal_token(patched, old, new)
                patched = _retarget_material_hash(patched, old, new)
            if patched != data:
                path.write_bytes(patched)
                changed = True
    if changed and report is not None:
        report.pfb_ops.append(
            f"hair mdf materials {mdf_stem} -> {pak_hair_id} "
            "(vanilla mesh can draw them; texture paths stay private)"
        )


def _retarget_material_hash(data: bytes, old: str, new: str) -> bytes:
    """Keep the Murmur3 hash in step with a renamed material string.

    The mesh binds on the hash. A renamed string with the old hash draws
    nothing (invisible hair or an invisible body part).
    """
    if old == new or len(old) != len(new):
        return data
    old_u = old.encode("utf-16-le")
    new_u = new.encode("utf-16-le")
    if old_u not in data and new_u not in data:
        return data
    old_h = struct.pack("<I", material_name_hash(old))
    new_h = struct.pack("<I", material_name_hash(new))
    if old_h == new_h or old_h not in data:
        return data
    return data.replace(old_h, new_h)


def resolve_hair_chain_id(
    staging: Path,
    hair_folder_id: str,
    mesh_stem: str | None = None,
    *,
    profile: CharacterProfile | None = None,
) -> str | None:
    """Return the hair ``.chain`` stem present on disk, or ``None``.

    Prefers an author sidecar matching the mesh stem (``pl107t.chain`` beside
    ``pl1816/pl107t.mesh``), then a chain named like the folder id, then any
    ``.chain`` inside the hair folder.
    """
    stem = mesh_stem or hair_folder_id
    if _hair_chain_present(staging, stem, profile=profile):
        return stem
    if stem != hair_folder_id and _hair_chain_present(
        staging, hair_folder_id, profile=profile,
    ):
        return hair_folder_id
    for root in mesh_roots(profile):
        folder = resolve_ci(staging, f"{root}/{hair_folder_id}")
        if folder is None or not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            m = _HAIR_CHAIN_STEM_RE.match(path.name)
            if m:
                return m.group(1)
    return None


def hair_pfb_ext(analysis: AnalysisResult) -> str:
    for p in (analysis.pfbs or analysis.claire_pfbs):
        m = PFB_EXT_RE.search(p.relpath)
        if m:
            return m.group(1)
    return ".pfb.16"


def _retarget_hair_id_bytes(data: bytes, old_id: str, new_id: str) -> bytes:
    """Same-length plXXXX rewrite in ASCII + UTF-16LE (mesh/mdf/mat tokens)."""
    if len(old_id) != len(new_id) or old_id == new_id:
        return data
    return _patch_equal_token(data, old_id, new_id)


def _patch_equal_token(data: bytes, old: str, new: str) -> bytes:
    if len(old) != len(new) or old == new:
        return data
    needle = old.lower().encode("ascii")
    data_l = data.lower()
    if needle in data_l:
        data, _ = patch_ascii_ci(data, data_l, old, new, needle)
    u16_needle = b"".join(bytes([ord(c), 0]) for c in old.lower())
    u16_view = utf16_ascii_lower(data)
    if u16_needle in u16_view:
        data, _ = patch_utf16_ci(data, u16_view, old, new, u16_needle)
    return data


def write_hair_redirect_slots(
    staging: Path,
    analysis: AnalysisResult,
    target: Outfit,
    report: ConversionReport,
    note: str,
    slots: list[str] | None = None,
    hair_id: str | None = None,
    mesh_id: str | None = None,
    mdf_id: str | None = None,
    chain_id: str | None = None,
    mesh_stem: str | None = None,
    mdf_stem: str | None = None,
    overwrite: bool = False,
) -> bool:
    """Write redirect PFB into hair slots. Returns False if template missing.

    Template ships as Claire ``pl1070``. ``hair_id`` defaults to the target
    character's shared hair (Claire ``pl1070``, Leon ``pl0070``) so a Leon
    hide-exclusive inject cannot keep Claire's id under ``pl0000`` (missing
    ``pl1070.chain`` freezes on outfit switch / cutscene).

    ``hair_id`` retargets material tokens (must match mesh material names).
    ``mesh_id`` / ``mdf_id`` / ``chain_id`` may differ: exclusive hats keep
    mats/chain on ``pl1071`` while mesh/mdf sit on a private folder; isolated
    shared hair keeps the vanilla shared ``.chain`` so a missing
    ``pl18xx.chain`` cannot freeze on outfit switch.

    ``mesh_stem`` / ``mdf_stem`` may differ from folder ids when files are
    e.g. ``pl1605/pl1678.mesh`` or ``pl1070/pl107t.mesh`` (same-length
    ``pl`` + 4-char stems only).
    """
    profile = target.profile or CLAIRE_PROFILE
    template = assets_dir() / "pl1000_hair_redirect_pl1070.pfb.16"
    if not template.is_file():
        return False
    hair_id = hair_id or profile.default_hair_id
    mesh_id = mesh_id or hair_id
    mdf_id = mdf_id or hair_id
    chain_id = chain_id or hair_id
    mesh_stem = mesh_stem or mesh_id
    mdf_stem = mdf_stem or mdf_id
    target_dir = ensure_dir_ci(staging, parts_dir(profile))
    data = template.read_bytes()
    # Claire template embeds pl1000 / pl1070 — retarget player root then hair.
    if profile.player_root != "pl1000":
        data = _retarget_hair_id_bytes(data, "pl1000", profile.player_root)
    default_hair = profile.default_hair_id
    data = _retarget_hair_id_bytes(data, "pl1070", default_hair)
    if hair_id != default_hair:
        data = _retarget_hair_id_bytes(data, default_hair, hair_id)
    have_mesh = f"{hair_id}/{hair_id}.mesh"
    want_mesh = f"{mesh_id}/{mesh_stem}.mesh"
    if want_mesh != have_mesh:
        if len(want_mesh) == len(have_mesh):
            data = _patch_equal_token(data, have_mesh, want_mesh)
        else:
            report.warnings.append(
                f"Hair redirect mesh path length mismatch "
                f"({have_mesh} → {want_mesh}); path not patched."
            )
    have_mdf = f"{hair_id}/{hair_id}.mdf2"
    want_mdf = f"{mdf_id}/{mdf_stem}.mdf2"
    if want_mdf != have_mdf:
        if len(want_mdf) == len(have_mdf):
            data = _patch_equal_token(data, have_mdf, want_mdf)
        else:
            report.warnings.append(
                f"Hair redirect mdf path length mismatch "
                f"({have_mdf} → {want_mdf}); path not patched."
            )
    if chain_id != hair_id:
        data = _patch_equal_token(
            data,
            f"{hair_id}.chain",
            f"{chain_id}.chain",
        )
    ext = hair_pfb_ext(analysis)
    root = profile.player_root

    for slot in (slots if slots is not None else list(target.all_slots)):
        dest = target_dir / f"{root}_hair_{slot}{ext}"
        existing = list(target_dir.glob(f"{root}_hair_{slot}.pfb*"))
        if existing and not overwrite:
            continue
        if overwrite:
            for old in existing:
                if old != dest:
                    old.unlink(missing_ok=True)
        dest.write_bytes(data)
        action = "replaced" if existing and overwrite else "injected"
        report.pfb_ops.append(
            f"{action} hair redirect  ->  {dest.name} ({note})"
        )
    return True


def _hair_chain_present(
    staging: Path,
    hair_id: str,
    *,
    profile: CharacterProfile | None = None,
) -> bool:
    """True if the mod ships a .chain for this hair id (folder or sidecar)."""
    hid = hair_id.lower()
    for root in mesh_roots(profile):
        root_dir = resolve_ci(staging, root)
        if root_dir is None:
            continue
        for entry in root_dir.iterdir():
            name = entry.name.lower()
            if name == f"{hid}.chain" or name.startswith(f"{hid}.chain."):
                if entry.is_file():
                    return True
        folder = resolve_ci(staging, f"{root}/{hair_id}")
        if folder is not None and folder.is_dir():
            for path in folder.iterdir():
                if not path.is_file():
                    continue
                name = path.name.lower()
                if name == f"{hid}.chain" or name.startswith(f"{hid}.chain."):
                    return True
    return False


def _path_has_mesh_id(path: str, mesh_id: str) -> bool:
    """True when ``path`` is a file or folder for this mesh ID."""
    low = path.lower().replace("\\", "/")
    mid = mesh_id.lower()
    padded = f"/{low.strip('/')}/"
    return (
        f"/{mid}/" in padded
        or low.endswith((f"/{mid}.mesh", f"/{mid}.mdf2", f"/{mid}.chain"))
    )


def _exclusive_source_id(
    rename_map: dict[str, str], hair_priv: str,
) -> str | None:
    """Exclusive ID whose files were renamed into this private hair folder.

    Other exclusive renames in the same convert (hat isolated beside shared
    hair) must not change this folder's material or chain tokens.
    """
    for old, new in rename_map.items():
        if not _path_has_mesh_id(new, hair_priv):
            continue
        for excl in EXCLUSIVE_PART_IDS:
            if _path_has_mesh_id(old, excl):
                return excl
    return None


def ensure_exclusive_hair_override(
    staging: Path,
    analysis: AnalysisResult,
    source: Outfit,
    target: Outfit,
    src_pfbs: list[PfbSlot],
    report: ConversionReport,
) -> None:
    """When converting into an exclusive-hair slot, hide vanilla hat/hair.

    Claire: Noir ``pl1075`` / Military ``pl1071``. Leon: Noir ``pl0074`` /
    Arklay Sheriff ``pl0075``. Redirect uses that character's shared hair
    so the vanilla exclusive kit is not instantiated.

    Skipped when the mod already ships the source outfit's exclusive hat/hair
    mesh — that kit is loaded (or isolated) later instead of hidden.
    """
    if target.hair_id not in EXCLUSIVE_PART_IDS:
        return
    if source.hair_id == target.hair_id:
        return

    # A color add-on has no hair. Injecting a redirect here replaces the
    # main mod's hair prefab under Fluffy and freezes the outfit change.
    if analysis.modinfo.addonfor:
        profile = target.profile or source.profile or CLAIRE_PROFILE
        present = staging_mesh_ids(staging, profile)
        has_hair = bool(present & profile.hair_mesh_ids) or any(
            p.part == "hair" for p in src_pfbs
        )
        if not has_hair:
            report.pfb_ops.append(
                "skipped hair redirect for AddonFor "
                "(addon has no hair of its own)"
            )
            return

    if any(p.part == "hair" for p in src_pfbs):
        return

    if source.hair_id in EXCLUSIVE_PART_IDS:
        present = staging_mesh_ids(staging, source.profile or target.profile)
        if source.hair_id in present:
            report.pfb_ops.append(
                f"skipped hide-{target.hair_id} redirect "
                f"(keeping source exclusive {source.hair_id})"
            )
            return

    profile = target.profile or CLAIRE_PROFILE
    target_dir = ensure_dir_ci(staging, parts_dir(profile))
    root = profile.player_root
    missing = [
        slot for slot in target.all_slots
        if not list(target_dir.glob(f"{root}_hair_{slot}.pfb*"))
    ]
    if not missing:
        return

    if not write_hair_redirect_slots(
            staging, analysis, target, report,
            f"hides {target.hair_id}", slots=missing,
            hair_id=profile.default_hair_id):
        report.warnings.append(
            f"{target.name} uses exclusive hair/hat ({target.hair_id}) and this "
            "mod has no hair PFB — vanilla hat/hair may still show "
            "(missing redirect template: pl1000_hair_redirect_pl1070.pfb.16)."
        )


def _hair_ids_present(
    staging: Path,
    *,
    profile: CharacterProfile | None = None,
) -> list[str]:
    """Shared + private hair/hat folder ids currently on staging."""
    profile = profile or CLAIRE_PROFILE
    present = staging_mesh_ids(staging, profile)
    hair_ids = profile.hair_mesh_ids
    face_stems = _FACE_MESH_STEMS | {mid.lower() for mid in profile.face_ids}
    out: list[str] = []
    for pid in sorted(present):
        if pid in hair_ids:
            out.append(pid)
            continue
        if not (pid.lower().startswith("pl18") and len(pid) == 6):
            continue
        mesh_stem, _mdf = detect_hair_asset_stems(
            staging, pid, profile=profile)
        if mesh_stem.lower() in face_stems:
            continue
        out.append(pid)
    return out


def _any_hair_mdf(
    staging: Path,
    hair_ids: list[str],
    *,
    profile: CharacterProfile | None = None,
) -> bool:
    for hid in hair_ids:
        for root in mesh_roots(profile):
            folder = resolve_ci(staging, f"{root}/{hid}")
            if folder is not None and folder_has_mdf(folder):
                return True
    return False


def _any_hair_chain(
    staging: Path,
    hair_ids: list[str],
    *,
    profile: CharacterProfile | None = None,
) -> bool:
    for hid in hair_ids:
        mesh_stem, _ = detect_hair_asset_stems(staging, hid, profile=profile)
        if resolve_hair_chain_id(staging, hid, mesh_stem, profile=profile):
            return True
    return False


def drop_mesh_only_hair_pfbs(
    staging: Path,
    report: ConversionReport,
    *,
    is_addon: bool = False,
    profile: CharacterProfile | None = None,
) -> int:
    """Remove hair PFBs that would overwrite a main mod's good redirect.

    Cases:
    - Mesh-only packs (e.g. No Hat): hair mesh, no ``.mdf2``.
    - AddonFor with mesh/mdf but no local ``.chain`` (e.g. Apocalypse NSFW):
      injecting a vanilla-chain redirect stomps the main package's custom
      ``pl18xx.chain`` physics under Fluffy load order.

    Standalone mods without a chain still keep their redirect (Beach Girl
    vanilla-chain fallback) — pass ``is_addon=False``.
    """
    profile = profile or CLAIRE_PROFILE
    hair_ids = _hair_ids_present(staging, profile=profile)
    if not hair_ids:
        return 0
    has_mdf = _any_hair_mdf(staging, hair_ids, profile=profile)
    has_chain = _any_hair_chain(staging, hair_ids, profile=profile)
    if has_mdf and not (is_addon and not has_chain):
        return 0
    target_dir = resolve_ci(staging, parts_dir(profile))
    if target_dir is None or not target_dir.is_dir():
        return 0
    removed = 0
    root = profile.player_root
    for path in sorted(target_dir.glob(f"{root}_hair_*.pfb*")):
        if not path.is_file():
            continue
        rel = path.relative_to(staging).as_posix()
        path.unlink(missing_ok=True)
        report.removed_ops.append(rel)
        removed += 1
    if removed:
        if not has_mdf:
            reason = (
                "mesh-only hair package (no local .mdf2 — main mod's "
                "textured/physics redirect is kept)"
            )
        else:
            reason = (
                "AddonFor hair package with no local .chain — main mod's "
                "physics redirect is kept"
            )
        report.warnings.append(
            f"Dropped hair redirect PFB(s) from {reason}."
        )
    return removed


def ensure_isolated_hair_redirect(
    staging: Path,
    analysis: AnalysisResult,
    target: Outfit,
    hair_priv: str,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    """Ensure the costume hair slot loads the mod's hair/hat mesh ID."""
    if not hair_priv or len(hair_priv) != 6:
        return
    profile = target.profile or analysis.profile or CLAIRE_PROFILE
    present = staging_mesh_ids(staging, profile)
    if hair_priv not in present:
        return

    is_addon = bool(analysis.modinfo.addonfor)
    target_slots = list(target.all_slots)
    mesh_stem, mdf_stem = detect_hair_asset_stems(
        staging, hair_priv, profile=profile)
    stem_note = ""
    if mesh_stem != hair_priv or mdf_stem != hair_priv:
        stem_note = f" (files {mesh_stem}.mesh/{mdf_stem}.mdf2)"

    if hair_priv in EXCLUSIVE_PART_IDS:
        if not write_hair_redirect_slots(
                staging, analysis, target, report,
                f"loads exclusive {hair_priv}{stem_note}", slots=target_slots,
                hair_id=hair_priv,
                mesh_stem=mesh_stem, mdf_stem=mdf_stem, overwrite=True):
            report.warnings.append(
                f"Mod ships exclusive hair/hat {hair_priv} but the redirect "
                "template is missing "
                "(pl1000_hair_redirect_pl1070.pfb.16) — hat may not load."
            )
        return

    # Private exclusive kit: mesh materials stay on exclusive ID; bundled
    # private mdf binds renamed scarf textures; chain stays vanilla exclusive.
    excl = _exclusive_source_id(rename_map, hair_priv)
    priv_has_mdf = False
    for root in mesh_roots(profile):
        folder = resolve_ci(staging, f"{root}/{hair_priv}")
        if folder is not None and folder_has_mdf(folder):
            priv_has_mdf = True
            break
    if excl and priv_has_mdf:
        if not write_hair_redirect_slots(
                staging, analysis, target, report,
                f"loads isolated {hair_priv} mesh+mdf "
                f"(mats/chain {excl}){stem_note}",
                slots=target_slots, hair_id=excl,
                mesh_id=hair_priv, mdf_id=hair_priv,
                mesh_stem=mesh_stem, mdf_stem=mdf_stem, overwrite=True):
            report.warnings.append(
                f"Isolated exclusive hair to {hair_priv} but the redirect "
                "template is missing — hat may not load."
            )
        return

    if excl and not priv_has_mdf:
        if not write_hair_redirect_slots(
                staging, analysis, target, report,
                f"loads isolated {hair_priv} mesh + vanilla {excl}.mdf2"
                f"{stem_note}",
                slots=target_slots, hair_id=excl, mesh_id=hair_priv,
                mesh_stem=mesh_stem, overwrite=True):
            report.warnings.append(
                f"Isolated exclusive hair to {hair_priv} but the redirect "
                "template is missing — hat may not load."
            )
        return

    if priv_has_mdf:
        # Texture-only hair (Girl in Red): the folder has an mdf and albedo
        # but no mesh. Pointing the prefab at that missing mesh hides the
        # hair or freezes the outfit change. Keep the pak mesh and chain,
        # and let the private mdf supply the albedo.
        if not _hair_folder_has_mesh(staging, hair_priv, profile):
            pak_hair = target.hair_id
            align_hair_mdf_materials(
                staging, hair_priv, mdf_stem, pak_hair,
                profile=profile, report=report,
            )
            local_chain = resolve_hair_chain_id(
                staging, hair_priv, mesh_stem, profile=profile)
            if is_addon and not local_chain:
                report.pfb_ops.append(
                    f"skipped hair redirect for AddonFor {hair_priv} "
                    "(no local .chain — main mod's physics redirect is kept)"
                )
                return
            chain_id = local_chain or pak_hair
            if not write_hair_redirect_slots(
                    staging, analysis, target, report,
                    f"loads vanilla {pak_hair} mesh+chain and "
                    f"{hair_priv} mdf{stem_note}",
                    slots=target_slots, hair_id=pak_hair,
                    mesh_id=pak_hair, mdf_id=hair_priv, chain_id=chain_id,
                    mesh_stem=pak_hair, mdf_stem=mdf_stem, overwrite=True):
                report.warnings.append(
                    f"Isolated hair to {hair_priv} but the redirect template "
                    "is missing — hat may not load."
                )
            return

        local_chain = resolve_hair_chain_id(
            staging, hair_priv, mesh_stem, profile=profile)
        # AddonFor overlays (Apocalypse NSFW): do not inject a vanilla-chain
        # redirect — Fluffy would overwrite the main mod's custom pl18xx.chain.
        if is_addon and not local_chain:
            report.pfb_ops.append(
                f"skipped hair redirect for AddonFor {hair_priv} "
                "(no local .chain — main mod's physics redirect is kept)"
            )
            return
        # Prefer author sidecar. Shared kits with no .chain keep vanilla
        # default hair chain — pointing at a missing pl18xx.chain freezes.
        chain_id = local_chain or profile.default_hair_id
        if not write_hair_redirect_slots(
                staging, analysis, target, report,
                f"loads isolated {hair_priv} mesh+mdf (chain {chain_id})"
                f"{stem_note}",
                slots=target_slots, hair_id=hair_priv,
                mesh_id=hair_priv, mdf_id=hair_priv, chain_id=chain_id,
                mesh_stem=mesh_stem, mdf_stem=mdf_stem, overwrite=True):
            report.warnings.append(
                f"Isolated hair to {hair_priv} but the redirect template is "
                "missing — hat may not load."
            )
        return

    root = profile.player_root
    target_dir = ensure_dir_ci(staging, parts_dir(profile))
    missing = [
        slot for slot in target_slots
        if not list(target_dir.glob(f"{root}_hair_{slot}.pfb*"))
    ]
    if not missing:
        return

    if hair_priv in profile.hair_mesh_ids:
        return

    alias_standard_mesh_paths(
        staging, profile.default_hair_id, hair_priv, rename_map, report,
        profile=profile,
    )

    # Redirect stays on default hair id; aliases remap to the private folder.
    if not write_hair_redirect_slots(
            staging, analysis, target, report,
            f"loads isolated {hair_priv}", slots=missing):
        report.warnings.append(
            f"Isolated hair to {hair_priv} but no hair PFB exists and the "
            "redirect template is missing "
            "(pl1000_hair_redirect_pl1070.pfb.16) — custom hair may not load."
        )
