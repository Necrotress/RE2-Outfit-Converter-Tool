"""Hair redirect PFB injection for exclusive hats and isolated hair."""

from __future__ import annotations

from pathlib import Path

from .analyzer import AnalysisResult, PfbSlot
from .isolation import alias_standard_mesh_paths, staging_mesh_ids
from .outfits import CLAIRE_HAIR_MESH_IDS, EXCLUSIVE_PART_IDS, Outfit
from .path_patch import patch_ascii_ci, patch_utf16_ci, utf16_ascii_lower
from .paths import (
    MESH_ROOTS,
    PARTS_DIR,
    PFB_EXT_RE,
    assets_dir,
    ensure_dir_ci,
    folder_has_mdf,
    resolve_ci,
)
from .reports import ConversionReport


def hair_pfb_ext(analysis: AnalysisResult) -> str:
    for p in analysis.claire_pfbs:
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
    hair_id: str = "pl1070",
    mesh_id: str | None = None,
    mdf_id: str | None = None,
    chain_id: str | None = None,
    overwrite: bool = False,
) -> bool:
    """Write redirect PFB into hair slots. Returns False if template missing.

    Template ships as pl1070. ``hair_id`` retargets material tokens (must match
    mesh material names). ``mesh_id`` / ``mdf_id`` / ``chain_id`` may differ:
    exclusive hats keep mats/chain on ``pl1071`` while mesh/mdf sit on a
    private folder; isolated shared hair keeps ``pl1070.chain`` (vanilla) so a
    missing ``pl18xx.chain`` cannot freeze on outfit switch.
    """
    template = assets_dir() / "pl1000_hair_redirect_pl1070.pfb.16"
    if not template.is_file():
        return False
    mesh_id = mesh_id or hair_id
    mdf_id = mdf_id or hair_id
    chain_id = chain_id or hair_id
    target_dir = ensure_dir_ci(staging, PARTS_DIR)
    data = _retarget_hair_id_bytes(template.read_bytes(), "pl1070", hair_id)
    if mesh_id != hair_id:
        data = _patch_equal_token(
            data,
            f"{hair_id}/{hair_id}.mesh",
            f"{mesh_id}/{mesh_id}.mesh",
        )
    if mdf_id != hair_id:
        data = _patch_equal_token(
            data,
            f"{hair_id}/{hair_id}.mdf2",
            f"{mdf_id}/{mdf_id}.mdf2",
        )
    if chain_id != hair_id:
        data = _patch_equal_token(
            data,
            f"{hair_id}.chain",
            f"{chain_id}.chain",
        )
    ext = hair_pfb_ext(analysis)

    for slot in (slots if slots is not None else list(target.all_slots)):
        dest = target_dir / f"pl1000_hair_{slot}{ext}"
        existing = list(target_dir.glob(f"pl1000_hair_{slot}.pfb*"))
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


def _hair_chain_present(staging: Path, hair_id: str) -> bool:
    """True if the mod ships a .chain for this hair id (folder or sidecar)."""
    hid = hair_id.lower()
    for root in MESH_ROOTS:
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
                if path.is_file() and ".chain" in path.name.lower():
                    return True
    return False


def _exclusive_source_id(rename_map: dict[str, str]) -> str | None:
    """Exclusive ID that was renamed onto a private folder, if any."""
    for old in rename_map:
        low = old.lower().replace("\\", "/")
        for excl in EXCLUSIVE_PART_IDS:
            if f"/{excl}/" in low or low.endswith(f"/{excl}.mesh"):
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
    """When converting into Noir/Military, hide vanilla exclusive hair/hat.

    Skipped when the mod already ships the source outfit's exclusive hat/hair
    mesh — that kit is loaded (or isolated) later instead of hidden.
    """
    if target.hair_id not in EXCLUSIVE_PART_IDS:
        return
    if source.hair_id == target.hair_id:
        return

    if any(p.part == "hair" for p in src_pfbs):
        return

    if source.hair_id in EXCLUSIVE_PART_IDS:
        present = staging_mesh_ids(staging)
        if source.hair_id in present:
            report.pfb_ops.append(
                f"skipped hide-{target.hair_id} redirect "
                f"(keeping source exclusive {source.hair_id})"
            )
            return

    target_dir = ensure_dir_ci(staging, PARTS_DIR)
    missing = [
        slot for slot in target.all_slots
        if not list(target_dir.glob(f"pl1000_hair_{slot}.pfb*"))
    ]
    if not missing:
        return

    if not write_hair_redirect_slots(
            staging, analysis, target, report,
            f"hides {target.hair_id}", slots=missing):
        report.warnings.append(
            f"{target.name} uses exclusive hair/hat ({target.hair_id}) and this "
            "mod has no hair PFB — vanilla hat/hair may still show "
            "(missing redirect template: pl1000_hair_redirect_pl1070.pfb.16)."
        )


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
    present = staging_mesh_ids(staging)
    if hair_priv not in present:
        return

    target_slots = list(target.all_slots)

    if hair_priv in EXCLUSIVE_PART_IDS:
        if not write_hair_redirect_slots(
                staging, analysis, target, report,
                f"loads exclusive {hair_priv}", slots=target_slots,
                hair_id=hair_priv, overwrite=True):
            report.warnings.append(
                f"Mod ships exclusive hair/hat {hair_priv} but the redirect "
                "template is missing "
                "(pl1000_hair_redirect_pl1070.pfb.16) — hat may not load."
            )
        return

    # Private exclusive kit: mesh materials stay on exclusive ID; bundled
    # private mdf binds renamed scarf textures; chain stays vanilla exclusive.
    excl = _exclusive_source_id(rename_map)
    priv_has_mdf = False
    for root in MESH_ROOTS:
        folder = resolve_ci(staging, f"{root}/{hair_priv}")
        if folder is not None and folder_has_mdf(folder):
            priv_has_mdf = True
            break
    if excl and priv_has_mdf:
        if not write_hair_redirect_slots(
                staging, analysis, target, report,
                f"loads isolated {hair_priv} mesh+mdf "
                f"(mats/chain {excl})",
                slots=target_slots, hair_id=excl,
                mesh_id=hair_priv, mdf_id=hair_priv, overwrite=True):
            report.warnings.append(
                f"Isolated exclusive hair to {hair_priv} but the redirect "
                "template is missing — hat may not load."
            )
        return

    if excl and not priv_has_mdf:
        if not write_hair_redirect_slots(
                staging, analysis, target, report,
                f"loads isolated {hair_priv} mesh + vanilla {excl}.mdf2",
                slots=target_slots, hair_id=excl, mesh_id=hair_priv,
                overwrite=True):
            report.warnings.append(
                f"Isolated exclusive hair to {hair_priv} but the redirect "
                "template is missing — hat may not load."
            )
        return

    if priv_has_mdf:
        # Shared pl1070 hair rarely ships a .chain. After isolation, pointing
        # the PFB at pl18xx.chain freezes on outfit switch — keep vanilla chain.
        chain_id = (
            hair_priv if _hair_chain_present(staging, hair_priv) else "pl1070"
        )
        if not write_hair_redirect_slots(
                staging, analysis, target, report,
                f"loads isolated {hair_priv} mesh+mdf (chain {chain_id})",
                slots=target_slots, hair_id=hair_priv,
                mesh_id=hair_priv, mdf_id=hair_priv, chain_id=chain_id,
                overwrite=True):
            report.warnings.append(
                f"Isolated hair to {hair_priv} but the redirect template is "
                "missing — hat may not load."
            )
        return

    target_dir = ensure_dir_ci(staging, PARTS_DIR)
    missing = [
        slot for slot in target_slots
        if not list(target_dir.glob(f"pl1000_hair_{slot}.pfb*"))
    ]
    if not missing:
        return

    if hair_priv in CLAIRE_HAIR_MESH_IDS:
        return

    alias_standard_mesh_paths(
        staging, "pl1070", hair_priv, rename_map, report)

    if not write_hair_redirect_slots(
            staging, analysis, target, report,
            f"loads isolated {hair_priv}", slots=missing):
        report.warnings.append(
            f"Isolated hair to {hair_priv} but no hair PFB exists and the "
            "redirect template is missing "
            "(pl1000_hair_redirect_pl1070.pfb.16) — custom hair may not load."
        )
