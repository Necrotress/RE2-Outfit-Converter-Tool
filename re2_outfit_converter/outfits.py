"""Static data about RE2 Remake characters, outfits, and file-naming conventions.

PFB slots under objectroot/prefab/.../pl1000/ decide which in-game outfit loads
the mod. Mesh IDs under sectionroot/.../pl1000/pl10XX/ are the body assets.
Binary files embed those IDs as path strings, so conversion uses same-length
byte patches.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Outfit:
    key: str
    name: str
    tag: str                       # short modinfo.ini label, e.g. "Elza"
    primary_slot: str
    variant_slots: tuple[str, ...]
    body_id: str
    hair_id: str
    head_id: str
    ui_id: str                     # costume-select preview: ui0601_01_{ui_id}_iam.tex
    msg_stem: str | None = None    # DLC name file: mes_sys_clairecos_{stem}.msg
    # Classic slots don't reliably accept costume-select UI overrides.
    supports_costume_ui: bool = True

    @property
    def all_slots(self) -> tuple[str, ...]:
        return (self.primary_slot, *self.variant_slots)


# ui_id mapping from real mods:
#   Jacket=00, Tank=02, Classic Jacket=01, Classic Tank=04,
#   Military=06, Noir=07, Elza=08, '98≈09 (preview only; no custom .msg seen)
# msg_stem:
#   DLC (military/noir/elza/original='98) → mes_other_dlc/mes_sys_clairecos_{stem}.msg
#   Tank Top / Classic Tank Top → shared mes_sys_costume/reward MSG entries
#   Jacket / Classic Jacket → no custom-name path (same shared MSG file;
#   shipping it for those slots would fight Tank/Classic-Tank renames)
# Order matches the in-game Claire costume list (Jacket → … → Elza).
# '98 is detected for analysis only — conversion is unsupported (mesh-swap
# layout differs from every other Claire outfit).
CLAIRE_OUTFITS: list[Outfit] = [
    Outfit("jacket", "Jacket (Default)", "Jacket", "default",
           ("costume_1", "costume_2"), "pl1000", "pl1070", "pl1050", "00"),
    Outfit("tanktop", "Tank Top", "TankTop", "costume_3",
           ("costume_4",), "pl1001", "pl1070", "pl1050", "02",
           "tanktop"),
    Outfit("classic_jacket", "Classic (Jacket)", "Classic", "costume_5",
           ("costume_6", "costume_7"), "pl1002", "pl1070", "pl1050", "01",
           supports_costume_ui=False),
    Outfit("classic_tanktop", "Classic (Tank Top)", "ClassicTank", "costume_8",
           ("costume_9",), "pl1003", "pl1070", "pl1050", "04",
           "classic_tanktop", supports_costume_ui=False),
    Outfit("98", "'98 Classic", "'98", "costume_d",
           (), "pl1007", "pl1070", "pl1057", "09", "original",
           supports_costume_ui=False),
    Outfit("noir", "Noir", "Noir", "costume_a",
           (), "pl1005", "pl1075", "pl1050", "07", "noir"),
    Outfit("military", "Military", "Military", "costume_b",
           (), "pl1006", "pl1071", "pl1050", "06", "military"),
    Outfit("elza", "Elza Walker", "Elza", "costume_c",
           (), "pl1004", "pl1070", "pl1050", "08", "elza"),
]

# Outfits offered in From/To menus and outfit-tag settings.
UNSUPPORTED_CONVERT_KEYS = frozenset({"98"})
CONVERTIBLE_OUTFITS: list[Outfit] = [
    o for o in CLAIRE_OUTFITS if o.key not in UNSUPPORTED_CONVERT_KEYS
]

OUTFIT_TAGS = tuple(o.tag for o in CONVERTIBLE_OUTFITS)
# Older defaults kept so re-converts can strip them from names/descriptions.
LEGACY_OUTFIT_TAGS = ("Tank", "'98", "98")

CLAIRE_OUTFIT_BY_KEY = {o.key: o for o in CLAIRE_OUTFITS}


def default_tag_marker(outfit: Outfit) -> str:
    """Default suffix appended to zip names / modinfo, e.g. ``[Elza]``."""
    return f"[{outfit.tag}]"


def default_outfit_tag_markers() -> dict[str, str]:
    return {o.key: default_tag_marker(o) for o in CONVERTIBLE_OUTFITS}


def is_convertible_outfit(outfit: Outfit) -> bool:
    return outfit.key not in UNSUPPORTED_CONVERT_KEYS


CLAIRE_OUTFIT_BY_BODY_ID = {o.body_id: o for o in CLAIRE_OUTFITS}
CLAIRE_OUTFIT_BY_SLOT: dict[str, Outfit] = {
    slot: o for o in CLAIRE_OUTFITS for slot in o.all_slots
}
CLAIRE_OUTFIT_BY_UI_ID = {o.ui_id: o for o in CLAIRE_OUTFITS}
CLAIRE_OUTFIT_BY_MSG_STEM = {o.msg_stem: o for o in CLAIRE_OUTFITS if o.msg_stem}

# Non-body Claire mesh IDs (never treated as outfit bodies)
CLAIRE_SHARED_IDS = frozenset({
    "pl1050", "pl1057", "pl1070", "pl1071", "pl1075",
})

# Exclusive hair/hat IDs that load via the hair PFB (Noir hat, Military band).
# '98's pl1057 is face/head only — not a hair-slot exclusive.
EXCLUSIVE_PART_IDS = frozenset({"pl1071", "pl1075"})

# Face / hair mesh IDs that conversion may isolate away from shared slots
CLAIRE_FACE_IDS = frozenset({"pl1050", "pl1057"})
CLAIRE_HAIR_MESH_IDS = frozenset({"pl1070", "pl1071", "pl1075"})

# Common custom body IDs seen in community mods (keep private face/hair free of these)
COMMON_CUSTOM_IDS = frozenset({"pl1099", "pl1080", "pl1081", "pl1088", "pl1089"})

# IDs never used as private face/hair targets
RESERVED_MESH_IDS = frozenset(
    {o.body_id for o in CLAIRE_OUTFITS}
    | CLAIRE_SHARED_IDS
    | EXCLUSIVE_PART_IDS
    | COMMON_CUSTOM_IDS
)
_CHARACTER_PREFIXES = (
    ("pl64", "Katherine Warren"),
    ("pl60", "William Birkin"),
    ("pl57", "Marvin Branagh"),
    ("pl53", "Annette Birkin"),
    ("pl52", "Ben Bertolucci"),
    ("pl51", "Chief Irons"),
    ("pl50", "Robert Kendo"),
    ("pl41", "Tofu"),
    ("pl40", "Hunk"),
    ("pl30", "Sherry"),
    ("pl20", "Ada"),
    ("pl10", "Claire"),
    ("pl00", "Leon"),
)


def character_for_id(pl_id: str) -> str:
    pl_id = pl_id.lower()
    for prefix, name in _CHARACTER_PREFIXES:
        if pl_id.startswith(prefix):
            return name
    return "Unknown"


# Engine-ish extensions that may embed filesystem path strings.
# Prefer an allowlist over "everything except textures" so huge/unrelated
# binaries are not scanned (see docs/BINARY_PATCHING.md).
PATCHABLE_TYPES = frozenset({
    "pfb", "mdf2", "chain", "mesh", "skeleton", "scn",
    "motlist", "motbank", "user", "fsm", "gpuc", "rcol",
    "bhvt", "clip", "def", "asl",
})

# Legacy denylist kept for reference / tests that imported the name.
NO_PATCH_TYPES = frozenset({
    "tex", "rtex", "dds", "png", "jpg", "jpeg", "bmp", "gif",
    "ini", "txt", "fbx", "msg",
})


def patchable(filename: str) -> bool:
    """True if any dotted segment is a known patchable engine type."""
    parts = filename.lower().split(".")[1:]
    return any(part in PATCHABLE_TYPES for part in parts)
