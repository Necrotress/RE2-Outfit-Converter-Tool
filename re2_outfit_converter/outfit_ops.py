"""Per-outfit convert / delete operations for multi-slot packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from .outfits import Outfit, is_convertible_outfit
from .reports import ConversionError

if TYPE_CHECKING:
    from .analyzer import AnalysisResult


@dataclass(frozen=True)
class OutfitOp:
    """One outfit action: convert ``source`` → ``target``, or delete when target is None."""

    source: Outfit
    target: Outfit | None  # None = strip/delete from output


def normalize_ops(ops: Sequence[OutfitOp]) -> list[OutfitOp]:
    """Dedupe by source key (first wins); validate convertible outfits."""
    if not ops:
        raise ConversionError("No outfit operations selected.")
    seen: set[str] = set()
    out: list[OutfitOp] = []
    for op in ops:
        if op.source.key in seen:
            continue
        seen.add(op.source.key)
        if not is_convertible_outfit(op.source):
            raise ConversionError(
                f"Converting from {op.source.name} is not supported."
            )
        if op.target is not None and not is_convertible_outfit(op.target):
            raise ConversionError(
                f"Converting to {op.target.name} is not supported "
                "(its file layout differs from other Claire outfits)."
            )
        out.append(op)
    if not out:
        raise ConversionError("No outfit operations selected.")
    return out


def ops_from_source_target(
    source: Outfit | Sequence[Outfit],
    target: Outfit,
) -> list[OutfitOp]:
    """Build convert ops from the legacy single-target API."""
    if isinstance(source, Outfit):
        sources = [source]
    else:
        sources = list(source)
    return [OutfitOp(source=s, target=target) for s in sources]


def convert_ops(ops: Sequence[OutfitOp]) -> list[OutfitOp]:
    return [op for op in ops if op.target is not None]


def delete_ops(ops: Sequence[OutfitOp]) -> list[OutfitOp]:
    return [op for op in ops if op.target is None]


def primary_convert_target(ops: Sequence[OutfitOp]) -> Outfit | None:
    for op in ops:
        if op.target is not None:
            return op.target
    return None


def primary_convert_source(ops: Sequence[OutfitOp]) -> Outfit | None:
    for op in ops:
        if op.target is not None:
            return op.source
    return None


def package_has_outfit_assets(analysis: "AnalysisResult", outfit: Outfit) -> bool:
    """True if the package ships body mesh/tex folder or PFBs for ``outfit``."""
    from .meshes import has_mesh_entry

    if has_mesh_entry(analysis, outfit.body_id):
        return True
    return any(p.slot in outfit.all_slots for p in analysis.claire_pfbs)


def adapt_ops_for_package(
    analysis: "AnalysisResult",
    ops: Sequence[OutfitOp],
) -> list[OutfitOp]:
    """Filter/rewrite ops so AddonFor packages are not emptied by Delete.

    - Keep convert ops whose source assets exist in this package.
    - Keep delete ops when another convert still applies here.
    - If Delete would remove this package's only body assets and a batch
      convert target exists, rewrite as convert deleted → that target
      (texture AddonFors under the deleted slot).
    """
    ops = normalize_ops(ops)
    primary_target = primary_convert_target(ops)

    adapted_converts: list[OutfitOp] = []
    for op in convert_ops(ops):
        if package_has_outfit_assets(analysis, op.source):
            adapted_converts.append(op)

    adapted: list[OutfitOp] = list(adapted_converts)
    for op in delete_ops(ops):
        if not package_has_outfit_assets(analysis, op.source):
            continue
        if adapted_converts:
            adapted.append(op)
            continue
        if primary_target is not None:
            # Texture-only AddonFor on the deleted slot → remap to target.
            adapted.append(OutfitOp(source=op.source, target=primary_target))
        else:
            adapted.append(op)

    if not adapted:
        # Fall back to original ops so NothingToConvertError / passthrough
        # still runs for face-only addons with no body remaps.
        return list(ops)
    return adapted
