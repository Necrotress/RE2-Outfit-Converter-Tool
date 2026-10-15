"""Scans an extracted mod folder and figures out what it contains."""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path

from .character import CLAIRE_PROFILE, LEON_PROFILE, CharacterProfile
from .outfits import (
    CLAIRE_OUTFIT_BY_BODY_ID,
    CLAIRE_OUTFIT_BY_MSG_STEM,
    CLAIRE_OUTFIT_BY_SLOT,
    CLAIRE_OUTFIT_BY_UI_ID,
    CLAIRE_SHARED_IDS,
    LEON_OUTFIT_BY_BODY_ID,
    LEON_OUTFIT_BY_FILE_STEM,
    LEON_OUTFIT_BY_SLOT,
    LEON_OUTFIT_BY_UI_ID,
    LEON_SHARED_IDS,
    Outfit,
    character_for_id,
    character_key_for_display,
)

CLAIRE_PFB_RE = re.compile(
    r"pl1000_(?P<part>body|face|hair)_(?P<slot>default|costume_[0-9a-d])\.pfb",
    re.IGNORECASE,
)
LEON_PFB_RE = re.compile(
    r"pl0000_(?P<part>body|face|hair)_(?P<slot>default|costume_[0-9a-d])\.pfb",
    re.IGNORECASE,
)

PL_ID_RE = re.compile(r"pl\d{4}", re.IGNORECASE)
CLAIRE_MESH_FOLDER_RE = re.compile(
    r"sectionroot/character/player/pl1000/(pl1\d{3})/", re.IGNORECASE)
CLAIRE_MESH_FILE_RE = re.compile(
    r"sectionroot/character/player/pl1000/"
    r"(pl1\d{3})(?:\.(?:mesh|chain|mdf2|skeleton)|_)",
    re.IGNORECASE,
)
LEON_MESH_FOLDER_RE = re.compile(
    r"sectionroot/character/player/pl0000/(pl0\d{3})/", re.IGNORECASE)
LEON_MESH_FILE_RE = re.compile(
    r"sectionroot/character/player/pl0000/"
    r"(pl0\d{3})(?:\.(?:mesh|chain|mdf2|skeleton)|_)",
    re.IGNORECASE,
)

COSTUME_MSG_RE = re.compile(
    r"mes_sys_(?P<kind>clairecos|leoncos)_(?P<stem>[a-z0-9_]+)\.msg",
    re.IGNORECASE,
)
CLAIRE_COSTUME_UI_RE = re.compile(
    r"ui0601_01_(?P<id>\d{2})(?:_iam)?\.(?:tex|uvs|pfb)", re.IGNORECASE)
LEON_COSTUME_UI_RE = re.compile(
    r"ui0601_00_(?P<id>\d{2})(?:_iam)?\.(?:tex|uvs|pfb)", re.IGNORECASE)

# Filename tails. Core is mesh, material, or texture — the files a
# classic outfit actually draws with. Prefab and chain versions count
# as ray tracing, but one of them beside a classic outfit does not.
_RT_TAILS = (
    ".tex.34", ".mdf2.21", ".mesh.2109108288",
    ".pfb.17", ".chain.46", ".mmtr.2109101635",
)
_CLASSIC_CORE_TAILS = (".tex.10", ".mdf2.10", ".mesh.1808312334")


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
    # Character-neutral fields (preferred).
    pfbs: list[PfbSlot] = field(default_factory=list)
    outfits: list[Outfit] = field(default_factory=list)
    body_ids: list[str] = field(default_factory=list)
    custom_ids: list[str] = field(default_factory=list)
    # Legacy Claire aliases (same lists when Claire-only).
    claire_pfbs: list[PfbSlot] = field(default_factory=list)
    claire_outfits: list[Outfit] = field(default_factory=list)
    claire_body_ids: list[str] = field(default_factory=list)
    claire_custom_ids: list[str] = field(default_factory=list)
    costume_msg_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    rt_file_count: int = 0
    stm_file_count: int = 0
    x64_file_count: int = 0
    classic_core_count: int = 0
    # Cached by meshes.has_mesh_entry (pl IDs under MESH_ROOTS).
    _mesh_id_set: set[str] | None = field(default=None, repr=False, compare=False)

    @property
    def character_key(self) -> str | None:
        """Primary convertible character for this package, if any."""
        if any(o.character == "leon" for o in self.outfits):
            return "leon"
        if any(o.character == "claire" for o in self.outfits):
            return "claire"
        if "Leon" in self.characters and "Claire" not in self.characters:
            return "leon"
        if "Claire" in self.characters:
            return "claire"
        if "Leon" in self.characters:
            return "leon"
        return None

    @property
    def profile(self) -> CharacterProfile | None:
        key = self.character_key
        if key == "leon":
            return LEON_PROFILE
        if key == "claire":
            return CLAIRE_PROFILE
        return None

    @property
    def has_claire_files(self) -> bool:
        return "Claire" in self.characters

    @property
    def has_leon_files(self) -> bool:
        return "Leon" in self.characters

    @property
    def is_passthrough_candidate(self) -> bool:
        """Addon-style package: no outfit remap, but keepable in a batch."""
        if self.outfits:
            return False
        return (
            bool(self.modinfo.addonfor)
            or self.has_claire_files
            or self.has_leon_files
        )

    def _has_classic_outfit(self) -> bool:
        return self.x64_file_count > 0 and self.classic_core_count > 0

    @property
    def has_rt(self) -> bool:
        """Ray-tracing assets, not a stray RT file beside a classic outfit.

        A preview under natives/stm is not ray tracing. An RT suffix is.
        A classic outfit with no stm tree stays classic even if one file
        uses an RT version.
        """
        if self.rt_file_count <= 0:
            return self.stm_file_count > 0 and not self._has_classic_outfit()
        if self._has_classic_outfit() and self.stm_file_count <= 0:
            return False
        return True

    @property
    def is_dual_pack(self) -> bool:
        return (
            self.rt_file_count > 0
            and self.stm_file_count > 0
            and self._has_classic_outfit()
        )

    @property
    def game_label(self) -> str:
        """Analysis text: Classic, Ray tracing, or both."""
        if self.is_dual_pack:
            return "Classic and ray tracing"
        if self.has_rt:
            return "Ray tracing"
        if self.x64_file_count > 0 or self.classic_core_count > 0:
            return "Classic"
        return "-"

    @property
    def game_build(self) -> str:
        """Menu value this pack starts on. Dual packs start on Classic."""
        if self.game_label == "Ray tracing":
            return "Ray tracing"
        return "Classic"

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

    def english_names_by_outfit_key(self) -> dict[str, str]:
        """English costume-file text keyed by outfit key.

        Claire ``mes_sys_clairecos_elza`` and Leon ``mes_sys_leoncos_noir``
        stay on their own rows. One file does not fill every outfit.
        """
        if self.root is None:
            return {}
        from .msg_name import read_english_name

        out: dict[str, str] = {}
        for rel in self.costume_msg_files:
            match = COSTUME_MSG_RE.search(rel.replace("\\", "/"))
            if match is None:
                continue
            text = read_english_name(self.root / rel)
            if not text:
                continue
            kind = match.group("kind").lower()
            stem = match.group("stem").lower()
            outfit = (
                CLAIRE_OUTFIT_BY_MSG_STEM.get(stem)
                if kind == "clairecos"
                else LEON_OUTFIT_BY_FILE_STEM.get(stem)
            )
            if outfit is not None:
                out[outfit.key] = text
        return out


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

    return [
        root for root in sorted(uniq, key=lambda p: str(p).lower())
        if not any(_is_inside(root, other) for other in uniq)
    ]


def _note_game_build(result: AnalysisResult, low: str) -> None:
    parts = low.split("/")
    if len(parts) > 1:
        if parts[1] == "stm":
            result.stm_file_count += 1
        elif parts[1] == "x64":
            result.x64_file_count += 1
    name = parts[-1] if parts else low
    if name.endswith(_RT_TAILS):
        result.rt_file_count += 1
    if name.endswith(_CLASSIC_CORE_TAILS):
        result.classic_core_count += 1


GAME_BUILDS = ("Classic", "Ray tracing")


def game_label_for(analyses) -> str:
    labels: list[str] = []
    for analysis in analyses:
        label = analysis.game_label
        if label != "-" and label not in labels:
            labels.append(label)
    if not labels:
        return "-"
    if len(labels) == 1:
        return labels[0]
    return "Mixed"


def game_build_for(analyses) -> str:
    """Menu default. Ray tracing only when every pack is ray tracing."""
    builds = {analysis.game_build for analysis in analyses}
    if builds == {"Ray tracing"}:
        return "Ray tracing"
    return "Classic"


def game_build_direction(detected: str, chosen: str) -> str:
    """Direction line under the Game build menu."""
    if chosen == "Ray tracing" and detected != "Ray tracing":
        return "Classic to ray tracing"
    if chosen == "Classic" and detected not in ("Classic", "-"):
        return "Ray tracing to Classic"
    return "No build change"


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

    claire_seen: dict[str, Outfit] = {}
    leon_seen: dict[str, Outfit] = {}
    claire_body_ids: set[str] = set()
    leon_body_ids: set[str] = set()
    claire_body_mesh_ids: set[str] = set()
    leon_body_mesh_ids: set[str] = set()
    claire_custom: set[str] = set()
    leon_custom: set[str] = set()
    claire_pfbs: list[PfbSlot] = []
    leon_pfbs: list[PfbSlot] = []

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
        _note_game_build(result, low)

        ids_in_path = {m.lower() for m in PL_ID_RE.findall(rel)}
        chars_hit = {character_for_id(i) for i in ids_in_path} - {"Unknown"}
        for char in chars_hit:
            result.characters[char] = result.characters.get(char, 0) + 1

        if "objectroot/prefab" in low:
            m = CLAIRE_PFB_RE.search(low)
            if m:
                part, slot = m.group("part"), m.group("slot")
                claire_pfbs.append(PfbSlot(part, slot, rel))
                outfit = CLAIRE_OUTFIT_BY_SLOT.get(slot)
                if outfit:
                    claire_seen[outfit.key] = outfit
            m = LEON_PFB_RE.search(low)
            if m:
                part, slot = m.group("part"), m.group("slot")
                leon_pfbs.append(PfbSlot(part, slot, rel))
                outfit = LEON_OUTFIT_BY_SLOT.get(slot)
                if outfit:
                    leon_seen[outfit.key] = outfit

        fm = CLAIRE_MESH_FOLDER_RE.search(low) or CLAIRE_MESH_FILE_RE.search(low)
        if fm:
            mesh_id = fm.group(1).lower()
            if mesh_id in CLAIRE_OUTFIT_BY_BODY_ID:
                claire_body_ids.add(mesh_id)
                if ".mesh" in Path(low).name:
                    claire_body_mesh_ids.add(mesh_id)
            elif mesh_id not in CLAIRE_SHARED_IDS:
                claire_custom.add(mesh_id)

        fm = LEON_MESH_FOLDER_RE.search(low) or LEON_MESH_FILE_RE.search(low)
        if fm:
            mesh_id = fm.group(1).lower()
            if mesh_id in LEON_OUTFIT_BY_BODY_ID:
                leon_body_ids.add(mesh_id)
                if ".mesh" in Path(low).name:
                    leon_body_mesh_ids.add(mesh_id)
            elif mesh_id not in LEON_SHARED_IDS:
                leon_custom.add(mesh_id)

        msg_m = COSTUME_MSG_RE.search(low)
        if msg_m and "/message/" in low:
            kind = msg_m.group("kind").lower()
            stem = msg_m.group("stem").lower()
            if kind == "clairecos":
                outfit = CLAIRE_OUTFIT_BY_MSG_STEM.get(stem)
                if outfit:
                    claire_seen.setdefault(outfit.key, outfit)
            else:
                outfit = LEON_OUTFIT_BY_FILE_STEM.get(stem)
                if outfit:
                    leon_seen.setdefault(outfit.key, outfit)
            result.costume_msg_files.append(rel)

        ui_m = CLAIRE_COSTUME_UI_RE.search(low)
        if ui_m and "ui0600" in low:
            outfit = CLAIRE_OUTFIT_BY_UI_ID.get(ui_m.group("id"))
            if outfit:
                claire_seen.setdefault(outfit.key, outfit)

        ui_m = LEON_COSTUME_UI_RE.search(low)
        if ui_m and "ui0600" in low:
            outfit = LEON_OUTFIT_BY_UI_ID.get(ui_m.group("id"))
            if outfit:
                leon_seen.setdefault(outfit.key, outfit)

    # Body-folder outfit detection (same Nurse-style guard as Claire).
    claire_pfb_keys = {
        CLAIRE_OUTFIT_BY_SLOT[p.slot].key
        for p in claire_pfbs
        if p.slot in CLAIRE_OUTFIT_BY_SLOT
    }
    for mesh_id in claire_body_ids:
        outfit = CLAIRE_OUTFIT_BY_BODY_ID[mesh_id]
        if claire_pfb_keys and outfit.key not in claire_pfb_keys:
            continue
        claire_seen.setdefault(outfit.key, outfit)

    leon_pfb_keys = {
        LEON_OUTFIT_BY_SLOT[p.slot].key
        for p in leon_pfbs
        if p.slot in LEON_OUTFIT_BY_SLOT
    }
    for mesh_id in leon_body_ids:
        outfit = LEON_OUTFIT_BY_BODY_ID[mesh_id]
        if leon_pfb_keys and outfit.key not in leon_pfb_keys:
            continue
        leon_seen.setdefault(outfit.key, outfit)

    # Prefer a single primary character when both somehow appear.
    primary = _pick_primary_character(
        result.characters, claire_seen, leon_seen, claire_pfbs, leon_pfbs,
        claire_body_mesh_ids, leon_body_mesh_ids)

    if primary == "leon":
        result.pfbs = leon_pfbs
        result.outfits = list(leon_seen.values())
        result.body_ids = sorted(leon_body_ids)
        result.custom_ids = sorted(leon_custom)
        # Keep Claire legacy fields empty for Leon packs.
        result.claire_pfbs = []
        result.claire_outfits = []
        result.claire_body_ids = []
        result.claire_custom_ids = []
    else:
        result.pfbs = claire_pfbs
        result.outfits = list(claire_seen.values())
        result.body_ids = sorted(claire_body_ids)
        result.custom_ids = sorted(claire_custom)
        result.claire_pfbs = claire_pfbs
        result.claire_outfits = list(claire_seen.values())
        result.claire_body_ids = sorted(claire_body_ids)
        result.claire_custom_ids = sorted(claire_custom)

    if not result.natives_files:
        result.warnings.append("The natives folder is empty.")
    if result.custom_ids:
        result.warnings.append(
            "Mod uses custom mesh folder(s): "
            + ", ".join(result.custom_ids)
            + " (loaded via PFB redirect - these convert cleanly)."
        )
    if primary is None and result.characters:
        result.warnings.append(
            "No Claire/Leon outfit files detected - this mod targets: "
            + ", ".join(sorted(result.characters))
        )
    elif primary == "claire" and "Claire" not in result.characters and result.characters:
        result.warnings.append(
            "No Claire files detected - this mod targets: "
            + ", ".join(sorted(result.characters))
        )
    return result


def _pick_primary_character(
    characters: dict[str, int],
    claire_seen: dict[str, Outfit],
    leon_seen: dict[str, Outfit],
    claire_pfbs: list[PfbSlot],
    leon_pfbs: list[PfbSlot],
    claire_body_mesh_ids: set[str] | None = None,
    leon_body_mesh_ids: set[str] | None = None,
) -> str | None:
    if leon_seen or leon_pfbs:
        if claire_seen or claire_pfbs:
            leon_score = len(leon_seen) * 10 + len(leon_pfbs)
            claire_score = len(claire_seen) * 10 + len(claire_pfbs)
            if leon_score > claire_score:
                return "leon"
            if claire_score > leon_score:
                return "claire"
            # Tie: a real body .mesh beats leftover textures (Marston-style).
            leon_mesh = _seen_has_body_mesh(leon_seen, leon_body_mesh_ids)
            claire_mesh = _seen_has_body_mesh(claire_seen, claire_body_mesh_ids)
            if leon_mesh != claire_mesh:
                return "leon" if leon_mesh else "claire"
            leon_n = int(characters.get("Leon") or 0)
            claire_n = int(characters.get("Claire") or 0)
            if leon_n != claire_n:
                return "leon" if leon_n > claire_n else "claire"
            return "claire"
        return "leon"
    if claire_seen or claire_pfbs:
        return "claire"
    if "Leon" in characters and "Claire" not in characters:
        return "leon"
    if "Claire" in characters:
        return "claire"
    if "Leon" in characters:
        return "leon"
    return None


def _seen_has_body_mesh(
    seen: dict[str, Outfit],
    mesh_ids: set[str] | None,
) -> bool:
    if not seen or not mesh_ids:
        return False
    seen_bodies = {o.body_id.lower() for o in seen.values()}
    return any(mid.lower() in seen_bodies for mid in mesh_ids)


def _read_modinfo(path: Path) -> tuple[ModInfo, str | None]:
    """Parse modinfo.ini. Returns (info, warning) — warning set on parse failure."""
    info = ModInfo()
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
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
