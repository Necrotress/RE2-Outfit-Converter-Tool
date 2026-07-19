"""Hair redirect PFB injection for exclusive hats and isolated hair."""

from __future__ import annotations

from pathlib import Path

from .analyzer import AnalysisResult, PfbSlot
from .isolation import alias_standard_mesh_paths, staging_mesh_ids
from .outfits import CLAIRE_HAIR_MESH_IDS, EXCLUSIVE_PART_IDS, Outfit
from .paths import PARTS_DIR, PFB_EXT_RE, assets_dir, ensure_dir_ci
from .reports import ConversionReport


def hair_pfb_ext(analysis: AnalysisResult) -> str:
    for p in analysis.claire_pfbs:
        m = PFB_EXT_RE.search(p.relpath)
        if m:
            return m.group(1)
    return ".pfb.16"
def write_hair_redirect_slots(
    staging: Path,
    analysis: AnalysisResult,
    target: Outfit,
    report: ConversionReport,
    note: str,
    slots: list[str] | None = None,
) -> bool:
    """Write redirect PFB into missing hair slots. Returns False if template missing."""
    template = assets_dir() / "pl1000_hair_redirect_pl1070.pfb.16"
    if not template.is_file():
        return False
    target_dir = ensure_dir_ci(staging, PARTS_DIR)
    data = template.read_bytes()
    ext = hair_pfb_ext(analysis)
    for slot in (slots if slots is not None else list(target.all_slots)):
        dest = target_dir / f"pl1000_hair_{slot}{ext}"
        if dest.exists() or list(target_dir.glob(f"pl1000_hair_{slot}.pfb*")):
            continue
        dest.write_bytes(data)
        report.pfb_ops.append(f"injected hair redirect  ->  {dest.name} ({note})")
    return True
def ensure_exclusive_hair_override(
    staging: Path,
    analysis: AnalysisResult,
    source: Outfit,
    target: Outfit,
    src_pfbs: list[PfbSlot],
    report: ConversionReport,
) -> None:
    """When converting into Noir/Military, hide vanilla exclusive hair/hat.

    Those outfits load pl1075 (Noir hat) or pl1071 (Military) via the hair
    PFB. Elza/Jacket mods often omit a hair PFB, so after a slot swap the
    vanilla hat/headband still appears. Inject a redirect PFB that loads
    shared Claire hair (pl1070) instead.
    """
    if target.hair_id not in EXCLUSIVE_PART_IDS:
        return
    if source.hair_id == target.hair_id:
        return

    # Already converting a source hair PFB into the target slot covers this.
    if any(p.part == "hair" for p in src_pfbs):
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
    """After hair isolation, ensure the costume slot loads the private hair ID.

    Many Claire mods (especially CR-AW) override shared ``pl1070`` textures /
    materials without shipping a hair PFB. Isolation moves those files to a
    private ``pl18xx`` folder; without a hair prefab the game keeps loading
    vanilla ``pl1070`` and the custom hair color never appears.

    Inject the bundled pl1070 hair redirect into every target slot when needed.
    Existing ``rename_map`` aliases then rewrite its paths to ``hair_priv``
    during binary patching. Mesh paths that were never in the mod stay on
    ``pl1070`` so vanilla hair mesh can still load.
    """
    if not hair_priv or len(hair_priv) != 6:
        return
    present = staging_mesh_ids(staging)
    if hair_priv not in present:
        return

    # Hair was not actually isolated away from a shared/exclusive ID.
    if hair_priv in CLAIRE_HAIR_MESH_IDS:
        return

    target_dir = ensure_dir_ci(staging, PARTS_DIR)
    missing = [
        slot for slot in target.all_slots
        if not list(target_dir.glob(f"pl1000_hair_{slot}.pfb*"))
    ]
    if not missing:
        return

    # Ensure standard pl1070 → private aliases exist for patching the inject.
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
