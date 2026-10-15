"""Static data about RE2 Remake characters, outfits, and file-naming conventions.

PFB slots under objectroot/prefab/.../{player_root}/ decide which in-game outfit
loads the mod. Mesh IDs under sectionroot/.../{player_root}/plXXXX/ are the
body assets. Binary files embed those IDs as path strings, so conversion uses
same-length byte patches.
"""

from __future__ import annotations

from dataclasses import dataclass

from .character import (
    CLAIRE_PROFILE,
    LEON_PROFILE,
    CharacterProfile,
    profile_for_key,
)


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
    ui_id: str                     # costume-select preview id (row-specific)
    msg_stem: str | None = None    # DLC name file stem when applicable
    # Classic slots don't reliably accept costume-select UI overrides.
    supports_costume_ui: bool = True
    # Extra figure gallery: figurescene_{prefix}_{id} / figure_{prefix}_{id}
    figure_extra_id: str | None = None
    character: str = "claire"      # "claire" | "leon"

    @property
    def all_slots(self) -> tuple[str, ...]:
        return (self.primary_slot, *self.variant_slots)

    @property
    def profile(self) -> CharacterProfile:
        return profile_for_key(self.character)


# ui_id mapping from real mods (Claire row ui0601_01_XX):
#   Jacket=00, Tank=02, Classic Jacket=01, Classic Tank=04,
#   Military=06, Noir=07, Elza=08, '98≈09 (preview only; no custom .msg seen)
# figure_extra_id: DLC gallery scenes under objectroot/scene/ui/figure/extra/
#   Noir=10, Military=11, Elza=12, '98=13
# msg_stem:
#   DLC (military/noir/elza/original='98) → mes_other_dlc/mes_sys_clairecos_{stem}.msg
#   Tank Top / Classic Tank Top → shared mes_sys_costume/reward MSG entries
# '98 is detected for analysis only — conversion is unsupported.
CLAIRE_OUTFITS: list[Outfit] = [
    Outfit("jacket", "Jacket (Default)", "Jacket", "default",
           ("costume_1", "costume_2"), "pl1000", "pl1070", "pl1050", "00",
           character="claire"),
    Outfit("tanktop", "Tank Top", "TankTop", "costume_3",
           ("costume_4",), "pl1001", "pl1070", "pl1050", "02",
           "tanktop", character="claire"),
    Outfit("classic_jacket", "Classic (Jacket)", "Classic", "costume_5",
           ("costume_6", "costume_7"), "pl1002", "pl1070", "pl1050", "01",
           supports_costume_ui=False, character="claire"),
    Outfit("classic_tanktop", "Classic (Tank Top)", "ClassicTank", "costume_8",
           ("costume_9",), "pl1003", "pl1070", "pl1050", "04",
           "classic_tanktop", supports_costume_ui=False, character="claire"),
    Outfit("98", "'98 Classic", "'98", "costume_d",
           (), "pl1007", "pl1070", "pl1057", "09", "original",
           supports_costume_ui=False, figure_extra_id="13", character="claire"),
    Outfit("noir", "Noir", "Noir", "costume_a",
           (), "pl1005", "pl1075", "pl1050", "07", "noir",
           figure_extra_id="10", character="claire"),
    Outfit("military", "Military", "Military", "costume_b",
           (), "pl1006", "pl1071", "pl1050", "06", "military",
           figure_extra_id="11", character="claire"),
    Outfit("elza", "Elza Walker", "Elza", "costume_c",
           (), "pl1004", "pl1070", "pl1050", "08", "elza",
           figure_extra_id="12", character="claire"),
]

# Leon (ui0601_00_XX). Body/slot map from vanilla pl0000_* PFBs + DLC holders.
# DLC: costume_a/pl0004/ui07/figure_10 = Noir (mes_sys_leoncos_noir);
#      costume_b/pl0005/ui06/figure_11 = Arklay Sheriff (mes_sys_leoncos_sheriff).
# '98 detect-only (unsupported), same stance as Claire.
LEON_OUTFITS: list[Outfit] = [
    Outfit("leon_casual", "Casual", "Casual", "default",
           (), "pl0002", "pl0070", "pl0050", "00",
           character="leon"),
    Outfit("leon_police", "Police", "Police", "costume_1",
           ("costume_2",), "pl0000", "pl0070", "pl0050", "01",
           character="leon"),
    Outfit("leon_police_injured", "Police (Injured)", "PoliceInjured",
           "costume_3", ("costume_4",), "pl0001", "pl0070", "pl0050", "02",
           character="leon"),
    Outfit("leon_classic_police", "Classic Police", "ClassicPolice",
           "costume_5", ("costume_6", "costume_7"), "pl0003", "pl0070",
           "pl0050", "03", character="leon"),
    Outfit("leon_classic_police_injured", "Classic Police (Injured)",
           "ClassicPoliceInjured", "costume_8", ("costume_9",), "pl0006",
           "pl0070", "pl0050", "04", character="leon"),
    Outfit("leon_noir", "Noir", "Noir", "costume_a",
           (), "pl0004", "pl0074", "pl0050", "07", "leon_noir",
           figure_extra_id="10", character="leon"),
    Outfit("leon_sheriff", "Arklay Sheriff", "Sheriff", "costume_b",
           (), "pl0005", "pl0075", "pl0050", "06", "sheriff",
           figure_extra_id="11", character="leon"),
    Outfit("leon_98", "'98 Classic", "'98", "costume_d",
           (), "pl0007", "pl0070", "pl0057", "09",
           supports_costume_ui=False, figure_extra_id="13", character="leon"),
]

ALL_OUTFITS: list[Outfit] = [*CLAIRE_OUTFITS, *LEON_OUTFITS]

# Outfits offered in From/To menus and outfit-tag settings.
UNSUPPORTED_CONVERT_KEYS = frozenset({"98", "leon_98"})
CONVERTIBLE_CLAIRE_OUTFITS: list[Outfit] = [
    o for o in CLAIRE_OUTFITS if o.key not in UNSUPPORTED_CONVERT_KEYS
]
CONVERTIBLE_LEON_OUTFITS: list[Outfit] = [
    o for o in LEON_OUTFITS if o.key not in UNSUPPORTED_CONVERT_KEYS
]
# Legacy alias: Claire convertibles (most existing callers/tests).
CONVERTIBLE_OUTFITS: list[Outfit] = CONVERTIBLE_CLAIRE_OUTFITS
ALL_CONVERTIBLE_OUTFITS: list[Outfit] = [
    *CONVERTIBLE_CLAIRE_OUTFITS, *CONVERTIBLE_LEON_OUTFITS
]

OUTFIT_TAGS = tuple(o.tag for o in ALL_CONVERTIBLE_OUTFITS)
# Older defaults kept so re-converts can strip them from names/descriptions.
LEGACY_OUTFIT_TAGS = ("Tank", "'98", "98")

CLAIRE_OUTFIT_BY_KEY = {o.key: o for o in CLAIRE_OUTFITS}
LEON_OUTFIT_BY_KEY = {o.key: o for o in LEON_OUTFITS}
OUTFIT_BY_KEY = {o.key: o for o in ALL_OUTFITS}


def default_tag_marker(outfit: Outfit) -> str:
    """Default suffix appended to zip names / modinfo, e.g. ``[Elza]``."""
    return f"[{outfit.tag}]"


def default_outfit_tag_markers() -> dict[str, str]:
    return {o.key: default_tag_marker(o) for o in ALL_CONVERTIBLE_OUTFITS}


def is_convertible_outfit(outfit: Outfit) -> bool:
    return outfit.key not in UNSUPPORTED_CONVERT_KEYS


def convertible_outfits_for(character: str) -> list[Outfit]:
    if character == "leon":
        return list(CONVERTIBLE_LEON_OUTFITS)
    return list(CONVERTIBLE_CLAIRE_OUTFITS)


def outfits_for_character(character: str) -> list[Outfit]:
    if character == "leon":
        return list(LEON_OUTFITS)
    return list(CLAIRE_OUTFITS)


CLAIRE_OUTFIT_BY_BODY_ID = {o.body_id: o for o in CLAIRE_OUTFITS}
LEON_OUTFIT_BY_BODY_ID = {o.body_id: o for o in LEON_OUTFITS}
OUTFIT_BY_BODY_ID = {o.body_id: o for o in ALL_OUTFITS}

CLAIRE_OUTFIT_BY_SLOT: dict[str, Outfit] = {
    slot: o for o in CLAIRE_OUTFITS for slot in o.all_slots
}
LEON_OUTFIT_BY_SLOT: dict[str, Outfit] = {
    slot: o for o in LEON_OUTFITS for slot in o.all_slots
}

CLAIRE_OUTFIT_BY_UI_ID = {o.ui_id: o for o in CLAIRE_OUTFITS}
LEON_OUTFIT_BY_UI_ID = {o.ui_id: o for o in LEON_OUTFITS}

CLAIRE_OUTFIT_BY_MSG_STEM = {
    o.msg_stem: o for o in CLAIRE_OUTFITS if o.msg_stem
}
_LEON_BY_KEY = {o.key: o for o in LEON_OUTFITS}
# mes_sys_leoncos_{noir,sheriff}.msg — file stem, not the outfit msg_stem.
LEON_OUTFIT_BY_FILE_STEM = {
    "noir": _LEON_BY_KEY["leon_noir"],
    "sheriff": _LEON_BY_KEY["leon_sheriff"],
}

# Non-body Claire mesh IDs (never treated as outfit bodies)
CLAIRE_SHARED_IDS = CLAIRE_PROFILE.shared_ids
LEON_SHARED_IDS = LEON_PROFILE.shared_ids

# Exclusive hair/hat IDs that load via the hair PFB.
EXCLUSIVE_PART_IDS = (
    CLAIRE_PROFILE.exclusive_part_ids | LEON_PROFILE.exclusive_part_ids
)

CLAIRE_FACE_IDS = CLAIRE_PROFILE.face_ids
CLAIRE_HAIR_MESH_IDS = CLAIRE_PROFILE.hair_mesh_ids
LEON_FACE_IDS = LEON_PROFILE.face_ids
LEON_HAIR_MESH_IDS = LEON_PROFILE.hair_mesh_ids

# Common custom body IDs seen in community mods (keep private face/hair free)
COMMON_CUSTOM_IDS = frozenset({
    "pl1099", "pl1080", "pl1081", "pl1088", "pl1089",
    "pl0099", "pl0080", "pl0081", "pl0088", "pl0089",
})

# IDs never used as private face/hair targets
RESERVED_MESH_IDS = frozenset(
    {o.body_id for o in ALL_OUTFITS}
    | CLAIRE_SHARED_IDS
    | LEON_SHARED_IDS
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


def character_key_for_display(name: str) -> str | None:
    """Map analyzer display name ('Claire'/'Leon') to profile key."""
    low = name.strip().lower()
    if low == "claire":
        return "claire"
    if low == "leon":
        return "leon"
    return None


# Engine-ish extensions that may embed filesystem path strings.
PATCHABLE_TYPES = frozenset({
    "pfb", "mdf2", "chain", "mesh", "skeleton", "scn",
    "motlist", "motbank", "user", "fsm", "gpuc", "rcol",
    "bhvt", "clip", "def", "asl",
})

NO_PATCH_TYPES = frozenset({
    "tex", "rtex", "dds", "png", "jpg", "jpeg", "bmp", "gif",
    "ini", "txt", "fbx", "msg",
})


def patchable(filename: str) -> bool:
    """True if any dotted segment is a known patchable engine type."""
    parts = filename.lower().split(".")[1:]
    return any(part in PATCHABLE_TYPES for part in parts)
