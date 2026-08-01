"""Pure helpers for multi-slot From focus / in-game name UI."""

from __future__ import annotations

from .msg_name import CLAIRECOS_MSG_STEMS, CLAIRE_SHARED_NAME_PACK_KEYS
from .outfits import Outfit

# Convert-to Claire targets that share mes_sys_costume / mes_sys_reward.
SHARED_NAME_PACK_KEYS = CLAIRE_SHARED_NAME_PACK_KEYS

SHARED_NAME_PACK_HINT = (
    "Jacket / Tank / Classic* share one name file — use Costume names instead."
)


def is_convert_namable(target: Outfit | None) -> bool:
    """True when Convert can set an in-game name (DLC clairecos only)."""
    if target is None or not target.msg_stem:
        return False
    return target.msg_stem.lower() in CLAIRECOS_MSG_STEMS


def uses_shared_name_pack(target: Outfit | None) -> bool:
    """Jacket / Tank Top / Classic Jacket / Classic Tank Top."""
    return target is not None and target.key in SHARED_NAME_PACK_KEYS


def from_checkbox_label(
    outfit: Outfit,
    *,
    incomplete: bool,
    focused: bool,
    base_label: str,
) -> str:
    """Checkbox text: optional focus marker + incomplete warning + name."""
    parts: list[str] = []
    if focused:
        parts.append("▸")
    if incomplete:
        parts.append("⚠")
    parts.append(base_label)
    return " ".join(parts)


def active_convert_name_target(
    active: Outfit | None,
    choice: str,
    *,
    resolve_target,
) -> Outfit | None:
    """Return the Convert-to outfit for the focused From row if it can be named.

    ``resolve_target(choice)`` should return an Outfit or None (Delete / unknown).
    Shared Jacket/Tank/Classic slots are not convert-namable.
    """
    if active is None:
        return None
    if (choice or "").startswith("Delete"):
        return None
    target = resolve_target(choice)
    if not is_convert_namable(target):
        return None
    return target


def other_namable_hint(
    checked: list[Outfit],
    *,
    choice_for,
    resolve_target,
    skip_key: str | None = None,
) -> str | None:
    """Short hint naming another ticked row that can set an in-game name."""
    for outfit in checked:
        if skip_key and outfit.key == skip_key:
            continue
        choice = choice_for(outfit)
        if (choice or "").startswith("Delete"):
            continue
        target = resolve_target(choice)
        if is_convert_namable(target):
            return (
                f"Focus {outfit.name} → {target.name} to set that outfit's name."
            )
    return None


def collect_display_names_by_target(
    ops: list,
    names_by_source: dict[str, str],
) -> dict[str, str]:
    """Map target outfit key → display name for convert-namable ops."""
    out: dict[str, str] = {}
    for op in ops:
        target = getattr(op, "target", None)
        source = getattr(op, "source", None)
        if target is None or source is None or not is_convert_namable(target):
            continue
        text = (names_by_source.get(source.key) or "").strip()
        if text:
            out[target.key] = text
    return out
