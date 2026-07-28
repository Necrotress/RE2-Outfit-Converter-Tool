"""Per-outfit convert / delete operations for multi-slot packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .outfits import Outfit, is_convertible_outfit
from .reports import ConversionError


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
