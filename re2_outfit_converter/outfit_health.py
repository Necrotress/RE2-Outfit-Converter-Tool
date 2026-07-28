"""Detect incomplete / broken Claire outfit slots in an analyzed mod."""

from __future__ import annotations

from collections.abc import Sequence

from .analyzer import AnalysisResult
from .meshes import has_mesh_entry
from .outfits import Outfit, is_convertible_outfit
from .paths import MESH_ROOTS


def incomplete_outfits(analysis: AnalysisResult) -> dict[str, str]:
    """Return ``{outfit_key: concise reason}`` for incomplete detected outfits.

    Primary rule (Casual Claire Jacket): body folder has textures/mdf but no
    ``.mesh`` under mesh roots for that body id.
    """
    reasons: dict[str, str] = {}
    for outfit in analysis.claire_outfits:
        if not is_convertible_outfit(outfit):
            continue
        reason = _incomplete_reason(analysis, outfit)
        if reason:
            reasons[outfit.key] = reason
    return reasons


def outfit_has_body_mesh(analysis: AnalysisResult, outfit: Outfit) -> bool:
    """True if this package has a real ``.mesh`` for the outfit body id."""
    body_id = outfit.body_id.lower()
    return has_mesh_entry(analysis, body_id) and _has_mesh_file(
        analysis, body_id)


def incomplete_outfits_for_load(
    analyses: Sequence[AnalysisResult],
) -> dict[str, str]:
    """Merge incomplete reasons across a load set (GUI / multi-path analyze).

    Suppresses addon-only texture-without-mesh flags when any **main** package
    (no AddonFor) already supplies a complete body mesh for that outfit.
    Main-package incompletes always win. Single-package loads match
    ``incomplete_outfits``.
    """
    if not analyses:
        return {}
    if len(analyses) == 1:
        return incomplete_outfits(analyses[0])

    mains = [a for a in analyses if not a.modinfo.addonfor]
    addons = [a for a in analyses if a.modinfo.addonfor]

    main_incomplete: dict[str, str] = {}
    for a in mains:
        for key, reason in incomplete_outfits(a).items():
            main_incomplete.setdefault(key, reason)

    addon_incomplete: dict[str, str] = {}
    for a in addons:
        for key, reason in incomplete_outfits(a).items():
            addon_incomplete.setdefault(key, reason)

    # Outfit keys with a complete body mesh on any main package.
    main_mesh_keys: set[str] = set()
    for a in mains:
        for outfit in a.claire_outfits:
            if is_convertible_outfit(outfit) and outfit_has_body_mesh(
                    a, outfit):
                main_mesh_keys.add(outfit.key)

    result = dict(main_incomplete)
    for key, reason in addon_incomplete.items():
        if key in result:
            continue
        if key in main_mesh_keys:
            continue
        result[key] = reason
    return result


def _incomplete_reason(analysis: AnalysisResult, outfit: Outfit) -> str | None:
    body_id = outfit.body_id.lower()
    has_mesh = outfit_has_body_mesh(analysis, outfit)
    has_body_assets = _has_body_non_mesh_assets(analysis, body_id)
    has_body_pfb = any(
        p.part == "body" and p.slot in outfit.all_slots
        for p in analysis.claire_pfbs
    )

    if has_body_assets and not has_mesh:
        return (
            "Missing body mesh (textures only). "
            "Convert may fail or look wrong — Delete is safest."
        )

    # Detected via UI/MSG alone with no body PFB and no body assets at all.
    if not has_mesh and not has_body_assets and not has_body_pfb:
        # Weak signal only — skip noisy warnings for name/UI-only ghosts.
        return None

    return None


def _has_mesh_file(analysis: AnalysisResult, body_id: str) -> bool:
    """True if a real ``.mesh`` file exists under mesh roots for body_id."""
    bid = body_id.lower()
    for rel in analysis.natives_files:
        low = rel.lower().replace("\\", "/")
        for root in MESH_ROOTS:
            root_l = root.lower()
            if not low.startswith(root_l + "/"):
                continue
            rest = low[len(root_l) + 1:]
            # pl1000/pl1000.mesh... or pl1000.mesh...
            if rest.startswith(bid + "/") and ".mesh" in rest:
                return True
            if rest.startswith(bid + ".") and ".mesh" in rest:
                return True
    return False


def _has_body_non_mesh_assets(analysis: AnalysisResult, body_id: str) -> bool:
    """Textures / mdf2 / other files under the body id folder (no mesh required)."""
    bid = body_id.lower()
    for rel in analysis.natives_files:
        low = rel.lower().replace("\\", "/")
        for root in MESH_ROOTS:
            root_l = root.lower()
            if not low.startswith(root_l + "/"):
                continue
            rest = low[len(root_l) + 1:]
            if not (rest.startswith(bid + "/") or rest.startswith(bid + ".")):
                continue
            if ".mesh" in rest:
                continue
            # Any other file under the body folder counts (tex, mdf2, …).
            if "/" in rest or rest.startswith(bid + "."):
                return True
    return False
