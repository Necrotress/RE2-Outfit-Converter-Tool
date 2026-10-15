"""RT vs classic platform / extension tables for RE2 Remake."""

from __future__ import annotations

import re
from dataclasses import dataclass

# natives/<platform>/...
PLATFORM_RT = "stm"
PLATFORM_CLASSIC = "x64"

# Top-level folders the RE2 pak actually mounts. A mod can still *work*
# on classic Fluffy with extras (Escape/ from RE3, a loose details/), but
# RT will not resolve those roots. Flattening their contents into
# SectionRoot (not nesting as SectionRoot/Escape) is what makes the
# mesh stop drawing the missing-texture checker. Keep in step with
# mdf_presets.RE2_PAK_ROOTS.
RE2_PAK_ROOTS = frozenset({
    "alphatest",
    "autoplay",
    "cafelatte",
    "gen",
    "hikako",
    "mastermaterial",
    "movie",
    "objectroot",
    "re_engine_library",
    "sectionroot",
    "streaming",
    "systems",
    "test",
    "tool",
    "vfx",
})

# Vanilla RT player folders are pl + four digits (pl1000, pl2000, pl5300).
# A direct child of character/player that is not that shape (RE3's wap100)
# is not in the RT dump, and textures there checkerboard the same way an
# extra SectionRoot child does. pl2000 matches and must stay: both dumps
# already ship that tree. Keep in step with mdf_presets.RE2_PLAYER_ID.
RE2_PLAYER_ID = re.compile(r"^pl\d{4}$", re.IGNORECASE)

# First-level folders vanilla RE2 actually keeps under SectionRoot/. An extra
# folder there (Escape/ from an RE3 port) is as unloadable as a fake pak root.
# setmodel lives under ObjectRoot/ in both dumps, not here. vfx is a pak root
# and must not live here. Keep in step with mdf_presets.
RE2_SECTIONROOT_CHILDREN = frozenset({
    "animation",
    "behaviortree",
    "character",
    "collision",
    "cutscene",
    "dynamics",
    "environment",
    "event",
    "leveldesign",
    "light",
    "message",
    "props",
    "sound",
    "ui",
    "userdata",
})

# Filename version suffixes used by RE2 Remake (FluffyQuack RT patch notes).
EXT_MAP_RT_TO_CLASSIC: dict[str, str] = {
    "tex.34": "tex.10",
    "mdf2.21": "mdf2.10",
    "mesh.2109108288": "mesh.1808312334",
    "pfb.17": "pfb.16",
    "chain.46": "chain.21",
    "mmtr.2109101635": "mmtr.1808160001",
}

EXT_MAP_CLASSIC_TO_RT: dict[str, str] = {
    v: k for k, v in EXT_MAP_RT_TO_CLASSIC.items()
}

# Binary types we may rewrite / path-patch (not textures — those use tex_convert).
PATCHABLE_SUFFIXES = frozenset({
    "pfb", "mdf2", "mesh", "chain", "scn", "user", "gpdef", "rcol",
    "mlist", "mmtr", "fsmv2", "uvar", "msg",
})

# Authoring leftovers to strip from output.
JUNK_SUFFIXES = frozenset({
    ".tga", ".png", ".jpg", ".jpeg", ".bmp", ".dds", ".psd",
    ".texout", ".txt", ".md", ".blend", ".fbx", ".obj",
})

# Kinds whose filename is stem.kind.version. Patchable kinds are included so
# scene/user files are path-patched; tex/mdf2/mesh/msg suffixes are remapped.
_VERSIONED_KINDS = (
    "tex|mdf2|mesh|pfb|chain|mmtr|scn|user|gpdef|rcol|mlist|fsmv2|uvar|msg"
)
_VERSIONED_RE = re.compile(
    rf"^(?P<stem>.+)\.(?P<kind>{_VERSIONED_KINDS})\.(?P<ver>[0-9]+)$",
    re.IGNORECASE,
)
# Extensions the path remap rewrites. Chain bytes are upgraded separately
# on the way to ray tracing; pfb and mmtr stay unconverted.
# Message files are renamed separately: the current game loads .msg.50397457.
REMAP_KINDS = frozenset({"tex", "mdf2", "mesh"})

MSG_VERSION_CLASSIC = 14
# 2022 ray-tracing patch. The current game does not load this.
MSG_VERSION_RT_OLD = 17
# 0x03010111. Filename suffix on the installed ray-tracing build.
MSG_VERSION_RT = 50397457


@dataclass(frozen=True)
class VersionedName:
    stem: str
    kind: str
    version: str

    @property
    def suffix(self) -> str:
        return f"{self.kind}.{self.version}".lower()

    @property
    def filename(self) -> str:
        return f"{self.stem}.{self.kind}.{self.version}"


def parse_versioned_name(name: str) -> VersionedName | None:
    m = _VERSIONED_RE.match(name)
    if not m:
        return None
    return VersionedName(
        stem=m.group("stem"),
        kind=m.group("kind").lower(),
        version=m.group("ver"),
    )


def classic_suffix_for(rt_suffix: str) -> str | None:
    return EXT_MAP_RT_TO_CLASSIC.get(rt_suffix.lower())


def rt_suffix_for(classic_suffix: str) -> str | None:
    return EXT_MAP_CLASSIC_TO_RT.get(classic_suffix.lower())


def is_rt_suffix(suffix: str) -> bool:
    return suffix.lower() in EXT_MAP_RT_TO_CLASSIC


def is_classic_suffix(suffix: str) -> bool:
    return suffix.lower() in EXT_MAP_CLASSIC_TO_RT


def platform_from_rel(rel: str) -> str | None:
    """Return 'stm' / 'x64' if rel starts with natives/<platform>/."""
    parts = rel.replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[0].lower() == "natives":
        plat = parts[1].lower()
        if plat in (PLATFORM_RT, PLATFORM_CLASSIC):
            return plat
    return None


def remap_msg_suffix(suffix: str, *, to_rt: bool) -> str | None:
    """Return the message suffix for the other game build, if this one changes."""
    suffix = suffix.lower()
    if to_rt and suffix in (
        f"msg.{MSG_VERSION_CLASSIC}",
        f"msg.{MSG_VERSION_RT_OLD}",
    ):
        return f"msg.{MSG_VERSION_RT}"
    if not to_rt and suffix in (
        f"msg.{MSG_VERSION_RT}",
        f"msg.{MSG_VERSION_RT_OLD}",
    ):
        return f"msg.{MSG_VERSION_CLASSIC}"
    return None


def _apply_parsed_suffix(parts: list[str], parsed: VersionedName, suffix: str) -> None:
    kind, ver = suffix.split(".", 1)
    parts[-1] = f"{parsed.stem}.{kind}.{ver}"


def remap_rel_to_classic(rel: str) -> str:
    """Rewrite natives/stm/... + RT extensions to classic paths."""
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    if len(parts) >= 2 and parts[0].lower() == "natives" and parts[1].lower() == PLATFORM_RT:
        parts[1] = PLATFORM_CLASSIC
    name = parts[-1]
    parsed = parse_versioned_name(name)
    if parsed is not None:
        msg_suffix = remap_msg_suffix(parsed.suffix, to_rt=False)
        if msg_suffix is not None:
            _apply_parsed_suffix(parts, parsed, msg_suffix)
        elif parsed.kind in REMAP_KINDS:
            classic = classic_suffix_for(parsed.suffix)
            if classic is not None:
                _apply_parsed_suffix(parts, parsed, classic)
    return "/".join(parts)


def remap_rel_to_rt(rel: str) -> str:
    """Rewrite natives/x64/... + classic extensions to RT paths."""
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    if (
        len(parts) >= 2
        and parts[0].lower() == "natives"
        and parts[1].lower() == PLATFORM_CLASSIC
    ):
        parts[1] = PLATFORM_RT
    name = parts[-1]
    parsed = parse_versioned_name(name)
    if parsed is not None:
        msg_suffix = remap_msg_suffix(parsed.suffix, to_rt=True)
        if msg_suffix is not None:
            _apply_parsed_suffix(parts, parsed, msg_suffix)
        elif parsed.kind in REMAP_KINDS:
            upgraded = rt_suffix_for(parsed.suffix)
            if upgraded is not None:
                _apply_parsed_suffix(parts, parsed, upgraded)
    return "/".join(parts)


def msg_bytes_as_classic(data: bytes) -> bytes:
    """Return GMSG bytes the classic reader can parse.

    A 2022 ``.msg.17`` file is a classic body with the version dword set
    to 17. Restoring 14 lets the classic entry layout load.
    """
    if (
        len(data) >= 4
        and int.from_bytes(data[:4], "little") == MSG_VERSION_RT_OLD
    ):
        return MSG_VERSION_CLASSIC.to_bytes(4, "little") + data[4:]
    return data


def patchable(filename: str) -> bool:
    lower = filename.lower()
    # versioned: file.mdf2.21
    parsed = parse_versioned_name(filename)
    if parsed is not None:
        return parsed.kind in PATCHABLE_SUFFIXES
    # unversioned rare
    for suf in PATCHABLE_SUFFIXES:
        if lower.endswith("." + suf):
            return True
    return False


def is_junk_file(name: str) -> bool:
    lower = name.lower()
    if lower in ("modinfo.ini",):
        return False
    if lower.endswith(".texout.tga") or lower.endswith(".texout"):
        return True
    for suf in JUNK_SUFFIXES:
        if lower.endswith(suf) and not lower.endswith(".tex.34") and not lower.endswith(".tex.10"):
            # Keep Fluffy screenshots (.png/.jpg at mod root) — caller filters by path.
            return True
    return False
