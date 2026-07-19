"""Scans an extracted mod folder and figures out what it contains."""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path

from .outfits import (
    CLAIRE_OUTFIT_BY_BODY_ID,
    CLAIRE_OUTFIT_BY_MSG_STEM,
    CLAIRE_OUTFIT_BY_SLOT,
    CLAIRE_OUTFIT_BY_UI_ID,
    CLAIRE_SHARED_IDS,
    Outfit,
    character_for_id,
)

PFB_RE = re.compile(
    r"pl1000_(?P<part>body|face|hair)_(?P<slot>default|costume_[0-9a-d])\.pfb",
    re.IGNORECASE,
)
PL_ID_RE = re.compile(r"pl\d{4}", re.IGNORECASE)
MESH_FOLDER_RE = re.compile(
    r"sectionroot/character/player/pl1000/(pl1\d{3})/", re.IGNORECASE)
# Body/part IDs also appear as loose files (e.g. pl1004.chain.21) without a folder.
MESH_FILE_RE = re.compile(
    r"sectionroot/character/player/pl1000/"
    r"(pl1\d{3})(?:\.(?:mesh|chain|mdf2|skeleton)|_)",
    re.IGNORECASE,
)
COSTUME_MSG_RE = re.compile(
    r"mes_sys_clairecos_(?P<stem>[a-z0-9_]+)\.msg", re.IGNORECASE)
COSTUME_UI_RE = re.compile(
    r"ui0601_01_(?P<id>\d{2})(?:_iam)?\.(?:tex|uvs|pfb)", re.IGNORECASE)


@dataclass
class PfbSlot:
    part: str
    slot: str
    relpath: str


@dataclass
class ModInfo:
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    screenshot: str = ""
    addonfor: str = ""
    nameasbundle: str = ""


@dataclass
class AnalysisResult:
    root: Path | None = None
    modinfo: ModInfo = field(default_factory=ModInfo)
    natives_files: list[str] = field(default_factory=list)
    characters: dict[str, int] = field(default_factory=dict)
    claire_pfbs: list[PfbSlot] = field(default_factory=list)
    claire_outfits: list[Outfit] = field(default_factory=list)
    claire_body_ids: list[str] = field(default_factory=list)
    claire_custom_ids: list[str] = field(default_factory=list)
    costume_msg_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    # Cached by meshes.has_mesh_entry (pl IDs under MESH_ROOTS).
    _mesh_id_set: set[str] | None = field(default=None, repr=False, compare=False)

    @property
    def has_claire_files(self) -> bool:
        return "Claire" in self.characters

    @property
    def is_passthrough_candidate(self) -> bool:
        """Addon-style package: no outfit remap, but keepable in a batch.

        True for explicit AddonFor mods, and for Claire face/hair/texture
        packs that omit AddonFor (common for all-suit gag/makeup addons).
        """
        if self.claire_outfits:
            return False
        return bool(self.modinfo.addonfor) or self.has_claire_files

    def suggested_outfit_display_name(self, fallback: str = "") -> str:
        """Prefer existing costume MSG English text, else modinfo Name, else fallback."""
        if self.root is not None:
            from .msg_name import read_english_name
            for rel in self.costume_msg_files:
                text = read_english_name(self.root / rel)
                if text:
                    return text
        if self.modinfo.name.strip():
            return self.modinfo.name.strip()
        return (fallback or "").strip()



def find_mod_root(folder: Path) -> Path | None:
    """Locate the shallowest folder that directly contains 'natives'."""
    roots = find_mod_roots(folder)
    return roots[0] if roots else None


def find_mod_roots(folder: Path) -> list[Path]:
    """Locate every Fluffy mod package under folder (multi-mod zips included).

    Prefers folders that contain both modinfo.ini and natives/. Falls back to
    every folder that directly contains natives/.
    """
    with_ini: list[Path] = []
    for ini in folder.rglob("modinfo.ini"):
        root = ini.parent
        if (root / "natives").is_dir():
            with_ini.append(root)
    if with_ini:
        return _dedupe_mod_roots(with_ini)

    natives_roots: list[Path] = []
    if (folder / "natives").is_dir():
        natives_roots.append(folder)
    for natives in folder.rglob("natives"):
        if natives.is_dir():
            natives_roots.append(natives.parent)
    return _dedupe_mod_roots(natives_roots)


def _dedupe_mod_roots(roots: list[Path]) -> list[Path]:
    uniq: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()).lower()
        if key not in seen:
            seen.add(key)
            uniq.append(root)

    def _is_inside(inner: Path, outer: Path) -> bool:
        try:
            inner.resolve().relative_to(outer.resolve())
            return inner.resolve() != outer.resolve()
        except ValueError:
            return False

    # Drop nested packages (keep the outer Fluffy package folders).
    return [
        root for root in sorted(uniq, key=lambda p: str(p).lower())
        if not any(_is_inside(root, other) for other in uniq)
    ]


def analyze(folder: Path) -> AnalysisResult:
    """Analyze a single mod root (folder that contains natives/)."""
    result = AnalysisResult()
    root = folder if (folder / "natives").is_dir() else find_mod_root(folder)
    if root is None:
        result.error = ("No 'natives' folder found - this doesn't look like a "
                        "Fluffy Mod Manager mod.")
        return result
    result.root = root

    ini_path = root / "modinfo.ini"
    if ini_path.is_file():
        result.modinfo, modinfo_warn = _read_modinfo(ini_path)
        if modinfo_warn:
            result.warnings.append(modinfo_warn)
    else:
        result.warnings.append(
            "No modinfo.ini found (Fluffy will show it without a name/screenshot).")

    seen_outfits: dict[str, Outfit] = {}
    body_ids: set[str] = set()
    custom_ids: set[str] = set()

    natives = next(
        (c for c in root.iterdir() if c.is_dir() and c.name.lower() == "natives"),
        None,
    )
    scan_root = natives if natives is not None else root
    for path in scan_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        low = rel.lower()
        if not low.startswith("natives/"):
            continue
        result.natives_files.append(rel)

        ids_in_path = {m.lower() for m in PL_ID_RE.findall(rel)}
        chars_hit = {character_for_id(i) for i in ids_in_path} - {"Unknown"}
        for char in chars_hit:
            result.characters[char] = result.characters.get(char, 0) + 1

        m = PFB_RE.search(low)
        if m and "objectroot/prefab" in low:
            part, slot = m.group("part"), m.group("slot")
            result.claire_pfbs.append(PfbSlot(part, slot, rel))
            outfit = CLAIRE_OUTFIT_BY_SLOT.get(slot)
            if outfit:
                seen_outfits[outfit.key] = outfit

        fm = MESH_FOLDER_RE.search(low) or MESH_FILE_RE.search(low)
        if fm:
            mesh_id = fm.group(1).lower()
            if mesh_id in CLAIRE_OUTFIT_BY_BODY_ID:
                body_ids.add(mesh_id)
            elif mesh_id not in CLAIRE_SHARED_IDS:
                custom_ids.add(mesh_id)

        msg_m = COSTUME_MSG_RE.search(low)
        if msg_m and "/message/" in low:
            stem = msg_m.group("stem").lower()
            outfit = CLAIRE_OUTFIT_BY_MSG_STEM.get(stem)
            if outfit:
                seen_outfits.setdefault(outfit.key, outfit)
            result.costume_msg_files.append(rel)

        ui_m = COSTUME_UI_RE.search(low)
        if ui_m and "ui0600" in low:
            ui_id = ui_m.group("id")
            outfit = CLAIRE_OUTFIT_BY_UI_ID.get(ui_id)
            if outfit:
                seen_outfits.setdefault(outfit.key, outfit)

    result.claire_body_ids = sorted(body_ids)
    result.claire_custom_ids = sorted(custom_ids)
    # Body-folder outfit detection: only promote a body ID to a source outfit
    # when there is no PFB evidence yet, or when matching PFBs already exist.
    # Nurse-style packs host a custom mesh under pl1000/ while only shipping
    # Elza PFBs — treating pl1000 as Jacket then leaves broken Elza leftovers
    # after a multi-source convert.
    pfb_outfit_keys = {
        CLAIRE_OUTFIT_BY_SLOT[p.slot].key
        for p in result.claire_pfbs
        if p.slot in CLAIRE_OUTFIT_BY_SLOT
    }
    for mesh_id in body_ids:
        outfit = CLAIRE_OUTFIT_BY_BODY_ID[mesh_id]
        if pfb_outfit_keys and outfit.key not in pfb_outfit_keys:
            continue
        seen_outfits.setdefault(outfit.key, outfit)

    result.claire_outfits = list(seen_outfits.values())

    if not result.natives_files:
        result.warnings.append("The natives folder is empty.")
    if result.claire_custom_ids:
        result.warnings.append(
            "Mod uses custom mesh folder(s): "
            + ", ".join(result.claire_custom_ids)
            + " (loaded via PFB redirect - these convert cleanly)."
        )
    if "Claire" not in result.characters and result.characters:
        result.warnings.append(
            "No Claire files detected - this mod targets: "
            + ", ".join(sorted(result.characters))
        )
    return result


def _read_modinfo(path: Path) -> tuple[ModInfo, str | None]:
    """Parse modinfo.ini. Returns (info, warning) — warning set on parse failure."""
    info = ModInfo()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string("[mod]\n" + text)
        section = parser["mod"]
        info.name = section.get("name", "")
        info.version = section.get("version", "")
        info.description = section.get("description", "")
        info.author = section.get("author", "")
        info.screenshot = section.get("screenshot", "")
        info.addonfor = section.get("addonfor", "")
        info.nameasbundle = section.get("nameasbundle", "")
    except Exception as e:
        return info, f"Could not parse modinfo.ini: {e}"
    return info, None
