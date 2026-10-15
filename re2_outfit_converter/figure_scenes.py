"""Claire / Leon figure-gallery retarget on convert.

DLC outfits have an extra figure entry::

    natives/x64/objectroot/scene/ui/figure/extra/figurescene_{prefix}_{NN}.scn…
    natives/x64/objectroot/prefab/ui/figure/extra/figure_{prefix}_{NN}.pfb…

Author scenes often embed body/face/hair mesh paths. Convert **retargets**
those files onto the target DLC frame (or promotes them onto base
figure/pl paths) so Bonuses/Records can load private face/hair after
isolation. Mesh path rewrites come from the shared ``rename_map`` applied
later by ``path_patch``.

Non-target extras are stripped so leftover source-frame files do not keep
showing the mod in the wrong DLC gallery slot.
"""

from __future__ import annotations

import re
from pathlib import Path

from .character import CLAIRE_PROFILE, CharacterProfile
from .hair_prefabs import detect_hair_asset_stems, resolve_hair_chain_id
from .outfits import Outfit
from .paths import ensure_dir_ci, mesh_roots, resolve_ci
from .reports import ConversionReport


def _figure_scene_re(prefix: str) -> re.Pattern[str]:
    return re.compile(
        rf"^(figurescene_{re.escape(prefix)}_)(\d{{2}})(\.scn(?:\.\d+)?)$",
        re.IGNORECASE,
    )


def _figure_pfb_re(prefix: str) -> re.Pattern[str]:
    return re.compile(
        rf"^(figure_{re.escape(prefix)}_)(\d{{2}})(\.pfb(?:\.\d+)?)$",
        re.IGNORECASE,
    )


_FIGURE_EXTRA_SCENE_ROOT = "natives/x64/objectroot/scene/ui/figure/extra"
_FIGURE_EXTRA_PFB_ROOT = "natives/x64/objectroot/prefab/ui/figure/extra"
_FIGURE_ROOTS = (
    _FIGURE_EXTRA_SCENE_ROOT,
    _FIGURE_EXTRA_PFB_ROOT,
)

# Base Claire figure paths (vanilla Bonuses mannequins under …/figure/pl/).
_BASE_SCENE_ROOT = "natives/x64/objectroot/scene/ui/figure/pl"
_BASE_PFB_ROOT = "natives/x64/objectroot/prefab/ui/figure/pl"

# Outfit key → (figurescene stem, figure prefab stem). Scene stem is not
# always the body id: Classic Jacket is figurescene_pl1008 but the scene
# references Figure_pl1005.pfb (from RE2 dump).
_BASE_FIGURE_STEMS: dict[str, tuple[str, str]] = {
    "jacket": ("pl1000", "pl1000"),
    "tanktop": ("pl1001", "pl1001"),
    "classic_jacket": ("pl1008", "pl1005"),
    "classic_tanktop": ("pl1011", "pl1011"),
    # Leon base Bonuses mannequins (from unpack).
    "leon_casual": ("pl0002", "pl0002"),
    "leon_police": ("pl0000", "pl0000"),
    "leon_police_injured": ("pl0001", "pl0001"),
    "leon_classic_police": ("pl0003", "pl0003"),
    "leon_classic_police_injured": ("pl0006", "pl0006"),
}

# Noir=10, Military=11, Elza=12, '98=13 (Claire); Leon extras 10/11/13.
CLAIRE_EXTRA_FIGURE_IDS = frozenset({"10", "11", "12", "13"})
LEON_EXTRA_FIGURE_IDS = frozenset({"10", "11", "13"})

_BLEED_NOTE = (
    "Removed non-target figure gallery file(s) so Records viewers "
    "do not keep a leftover source-frame override."
)


def strip_claire_extra_figures(
    staging: Path,
    report: ConversionReport,
    *,
    reason: str | None = None,
    keep_ids: frozenset[str] | set[str] | None = None,
    figure_prefix: str = "pl1000",
    extra_ids: frozenset[str] | set[str] | None = None,
) -> int:
    """Delete DLC extra figure scene/prefab files.

    When ``keep_ids`` is set, files for those gallery ids are left in place.
    Returns how many files were removed.
    """
    allowed = frozenset(extra_ids) if extra_ids is not None else (
        CLAIRE_EXTRA_FIGURE_IDS if figure_prefix == "pl1000"
        else LEON_EXTRA_FIGURE_IDS
    )
    keep = {i for i in (keep_ids or ()) if i in allowed}
    scene_re = _figure_scene_re(figure_prefix)
    pfb_re = _figure_pfb_re(figure_prefix)
    removed = 0
    note = reason or _BLEED_NOTE
    for root in _FIGURE_ROOTS:
        root_dir = resolve_ci(staging, root)
        if root_dir is None or not root_dir.is_dir():
            continue
        for path in list(root_dir.iterdir()):
            if not path.is_file():
                continue
            m = scene_re.match(path.name) or pfb_re.match(path.name)
            if m is None or m.group(2) not in allowed:
                continue
            if m.group(2) in keep:
                continue
            rel = path.relative_to(staging).as_posix()
            path.unlink(missing_ok=True)
            report.removed_ops.append(rel)
            removed += 1
    if removed:
        report.warnings.append(note)
    return removed


_BASE_SCENE_FILE_RE = re.compile(
    r"^(figurescene_)(pl[0-9a-zA-Z]{4})(\.scn(?:\.\d+)?)$",
    re.IGNORECASE,
)
_BASE_PFB_FILE_RE = re.compile(
    r"^(figure_)(pl[0-9a-zA-Z]{4})(\.pfb(?:\.\d+)?)$",
    re.IGNORECASE,
)

# Face/hair mesh stems embedded in figure binaries (UTF-16LE path strings).
_FIGURE_MESH_STEM_RE = re.compile(
    r"(pl[0-9a-zA-Z]{4})/(pl[0-9a-zA-Z]{4})\.(mesh|mdf2)",
    re.IGNORECASE,
)
_FIGURE_CHAIN_STEM_RE = re.compile(
    r"(pl[0-9a-zA-Z]{4})\.chain",
    re.IGNORECASE,
)


def convert_figure_scenes(
    staging: Path,
    source: Outfit,
    target: Outfit,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    """Retarget author figure gallery files for ``source`` → ``target``.

    DLC targets keep/rename extras onto ``target.figure_extra_id``. Base Claire
    targets (no extra id) promote author extras onto vanilla
    ``…/figure/pl/figurescene_*`` paths (Jacket ``pl1000``, Tank ``pl1001``,
    Classic Jacket ``pl1008``, Classic Tank ``pl1011``) so Bonuses can resolve
    isolated face/hair without overwriting the wrong gallery slot.

    Base→base converts also rename existing ``figure/pl/`` files (e.g. Classic
    ``figurescene_pl1008`` → Tank ``figurescene_pl1001``) so the source gallery
    slot does not keep showing the mod.
    """
    profile = target.profile or source.profile or CLAIRE_PROFILE
    prefix = profile.figure_prefix
    extra_ids = profile.extra_figure_ids
    new_id = target.figure_extra_id
    present = _list_extra_figure_files(
        staging, figure_prefix=prefix, extra_ids=extra_ids)

    if new_id:
        if present:
            _retarget_extras_to_id(
                staging, present, new_id, rename_map, report,
                preferred_id=source.figure_extra_id,
                figure_prefix=prefix,
            )
        return

    if present:
        _promote_extras_to_base_figure(
            staging, present, rename_map, report,
            preferred_id=source.figure_extra_id,
            target=target,
            figure_prefix=prefix,
        )

    if source.figure_extra_id is None and target.figure_extra_id is None:
        _retarget_base_figure_pl_files(
            staging, source, target, rename_map, report)
        _sync_base_figure_asset_stems(
            staging, rename_map, report, profile=profile)


def convert_figure_scenes_for_ops(
    staging: Path,
    converts: list[tuple[Outfit, Outfit]],
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    """Retarget figure gallery for convert ops ``(source, target)`` pairs."""
    if not converts:
        strip_claire_extra_figures(staging, report)
        return

    profile = converts[0][1].profile or converts[0][0].profile or CLAIRE_PROFILE
    prefix = profile.figure_prefix
    extra_ids = profile.extra_figure_ids

    seen_targets: set[str] = set()
    ordered_targets: list[Outfit] = []
    for source, target in converts:
        convert_figure_scenes(staging, source, target, rename_map, report)
        if target.key not in seen_targets:
            seen_targets.add(target.key)
            ordered_targets.append(target)

    keep = frozenset(
        t.figure_extra_id for t in ordered_targets
        if t.figure_extra_id in extra_ids
    )
    if keep:
        strip_claire_extra_figures(
            staging, report, keep_ids=keep,
            figure_prefix=prefix, extra_ids=extra_ids,
        )
    else:
        # Base promotion moves files out of extra/; clear any leftovers.
        strip_claire_extra_figures(
            staging, report, figure_prefix=prefix, extra_ids=extra_ids,
        )


def _list_extra_figure_files(
    staging: Path,
    *,
    figure_prefix: str = "pl1000",
    extra_ids: frozenset[str] | set[str] | None = None,
) -> list[tuple[Path, str, str]]:
    """Return ``(path, figure_id, kind)`` for character extra figure files."""
    allowed = frozenset(extra_ids) if extra_ids is not None else (
        CLAIRE_EXTRA_FIGURE_IDS if figure_prefix == "pl1000"
        else LEON_EXTRA_FIGURE_IDS
    )
    scene_re = _figure_scene_re(figure_prefix)
    pfb_re = _figure_pfb_re(figure_prefix)
    found: list[tuple[Path, str, str]] = []
    for root in _FIGURE_ROOTS:
        root_dir = resolve_ci(staging, root)
        if root_dir is None or not root_dir.is_dir():
            continue
        for path in sorted(root_dir.iterdir(), key=lambda p: p.name.lower()):
            if not path.is_file():
                continue
            m = scene_re.match(path.name)
            kind = "scene"
            if m is None:
                m = pfb_re.match(path.name)
                kind = "pfb"
            if m is None or m.group(2) not in allowed:
                continue
            found.append((path, m.group(2), kind))
    return found


def _retarget_extras_to_id(
    staging: Path,
    present: list[tuple[Path, str, str]],
    new_id: str,
    rename_map: dict[str, str],
    report: ConversionReport,
    *,
    preferred_id: str | None,
    figure_prefix: str = "pl1000",
) -> None:
    """Rename extra figure files onto ``new_id``; preferred source id wins."""
    scene_re = _figure_scene_re(figure_prefix)
    # Process preferred id first so it overwrites a stale target-frame file.
    ordered = sorted(
        present,
        key=lambda item: (0 if item[1] == preferred_id else 1, item[0].name),
    )
    for path, old_id, _kind in ordered:
        if old_id == new_id:
            continue
        new_name = _retarget_figure_name(
            path.name, old_id, new_id, figure_prefix=figure_prefix)
        if new_name is None:
            continue
        root = (
            _FIGURE_EXTRA_SCENE_ROOT
            if scene_re.match(path.name)
            else _FIGURE_EXTRA_PFB_ROOT
        )
        dest_dir = ensure_dir_ci(staging, root)
        dest = dest_dir / new_name
        if dest.exists() and dest.resolve() != path.resolve():
            dest_rel = dest.relative_to(staging).as_posix()
            dest.unlink()
            report.removed_ops.append(dest_rel)
        old_name = path.name
        old_rel = path.relative_to(staging).as_posix()
        path.rename(dest)
        new_rel = dest.relative_to(staging).as_posix()
        report.rename_ops.append(
            f"{old_rel}  ->  {new_rel} (figure gallery)"
        )
        _register_figure_token(rename_map, old_name, new_name)


def _base_figure_stems(target: Outfit) -> tuple[str, str] | None:
    """Return ``(figurescene_stem, figure_prefab_stem)`` for base Claire targets."""
    return _BASE_FIGURE_STEMS.get(target.key)


def _promote_extras_to_base_figure(
    staging: Path,
    present: list[tuple[Path, str, str]],
    rename_map: dict[str, str],
    report: ConversionReport,
    *,
    preferred_id: str | None,
    target: Outfit,
    figure_prefix: str = "pl1000",
) -> None:
    """Move DLC extra figure files onto vanilla ``…/figure/pl/`` paths."""
    stems = _base_figure_stems(target)
    profile = target.profile or CLAIRE_PROFILE
    if stems is None:
        # Unknown base target — drop extras rather than overwrite default.
        strip_claire_extra_figures(
            staging, report,
            reason=(
                f"Removed author figure gallery file(s); {target.name} has "
                f"no known Bonuses figure path mapping."
            ),
            figure_prefix=figure_prefix,
            extra_ids=profile.extra_figure_ids,
        )
        return

    scene_re = _figure_scene_re(figure_prefix)
    pfb_re = _figure_pfb_re(figure_prefix)
    scene_stem, pfb_stem = stems
    ordered = sorted(
        present,
        key=lambda item: (0 if item[1] == preferred_id else 1, item[0].name),
    )
    promoted = 0
    for path, _old_id, kind in ordered:
        if kind == "scene":
            m = scene_re.match(path.name)
            if m is None:
                continue
            new_name = f"figurescene_{scene_stem}{m.group(3)}"
            dest_dir = ensure_dir_ci(staging, _BASE_SCENE_ROOT)
        else:
            m = pfb_re.match(path.name)
            if m is None:
                continue
            new_name = f"figure_{pfb_stem}{m.group(3)}"
            dest_dir = ensure_dir_ci(staging, _BASE_PFB_ROOT)

        dest = dest_dir / new_name
        if dest.exists() and dest.resolve() != path.resolve():
            dest_rel = dest.relative_to(staging).as_posix()
            dest.unlink()
            report.removed_ops.append(dest_rel)
        old_name = path.name
        old_rel = path.relative_to(staging).as_posix()
        path.rename(dest)
        new_rel = dest.relative_to(staging).as_posix()
        report.rename_ops.append(
            f"{old_rel}  ->  {new_rel} (base figure gallery)"
        )
        # Filename length usually changes (_NN dropped); skip unequal tokens.
        _register_figure_token(rename_map, old_name, new_name)
        promoted += 1

    if promoted:
        # Author clone scenes usually embed Figure_{player_root}; retarget when
        # lengths match.
        default_fig = f"Figure_{figure_prefix}"
        if pfb_stem != figure_prefix:
            new_fig = f"Figure_{pfb_stem}"
            if len(default_fig) == len(new_fig):
                rename_map[default_fig] = new_fig
        report.warnings.append(
            f"Promoted author figure gallery onto "
            f"figure/pl/{scene_stem} for {target.name} "
            f"(Bonuses/Records custom face/hair)."
        )


def _retarget_figure_name(
    filename: str,
    old_id: str,
    new_id: str,
    *,
    figure_prefix: str = "pl1000",
) -> str | None:
    for cre in (
        _figure_scene_re(figure_prefix),
        _figure_pfb_re(figure_prefix),
    ):
        m = cre.match(filename)
        if not m:
            continue
        if m.group(2) != old_id:
            return None
        return f"{m.group(1)}{new_id}{m.group(3)}"
    return None


def _engine_figure_token(
    filename: str,
    *,
    figure_prefix: str | None = None,
) -> str | None:
    """Basename without trailing version, for same-length binary patches."""
    prefixes = (
        (figure_prefix,) if figure_prefix
        else ("pl1000", "pl0000")
    )
    for prefix in prefixes:
        for cre in (_figure_scene_re(prefix), _figure_pfb_re(prefix)):
            m = cre.match(filename)
            if m:
                stem = m.group(1) + m.group(2)
                ext = m.group(3).split(".")[1]  # scn or pfb
                return f"{stem}.{ext}"
    low = filename.lower()
    if ".scn" in low:
        base = filename.split(".scn")[0]
        return f"{base}.scn"
    if ".pfb" in low:
        base = filename.split(".pfb")[0]
        return f"{base}.pfb"
    return None


def _register_figure_token(
    rename_map: dict[str, str],
    old_name: str,
    new_name: str,
) -> None:
    """Register bare figure basename tokens (costume-UI style, not add_rename)."""
    old_eng = _engine_figure_token(old_name)
    new_eng = _engine_figure_token(new_name)
    if not old_eng or not new_eng or old_eng == new_eng:
        return
    if len(old_eng) != len(new_eng):
        return
    rename_map[old_eng] = new_eng


def _retarget_base_figure_pl_files(
    staging: Path,
    source: Outfit,
    target: Outfit,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    """Rename ``figure/pl/`` gallery files from source base stems to target.

    Classic Jacket→Tank Top leaves ``figurescene_pl1008`` behind unless this
    runs — Records then still shows the Classic slot. Only touches known base
    Claire stems from ``_BASE_FIGURE_STEMS``.
    """
    src_stems = _base_figure_stems(source)
    dst_stems = _base_figure_stems(target)
    if src_stems is None or dst_stems is None:
        return
    src_scene, src_pfb = src_stems
    dst_scene, dst_pfb = dst_stems
    if src_scene == dst_scene and src_pfb == dst_pfb:
        return

    # Only the source gallery. Other base stems belong to outfits that
    # are not part of this convert.
    known_scenes = {src_scene}
    known_pfbs = {src_pfb}

    moved = 0
    scene_dir = resolve_ci(staging, _BASE_SCENE_ROOT)
    if scene_dir is not None and scene_dir.is_dir():
        moved += _move_base_figure_files(
            staging, scene_dir, _BASE_SCENE_FILE_RE, known_scenes,
            prefer_stem=src_scene, dest_stem=dst_scene, rename_map=rename_map,
            report=report, kind="scene",
        )

    pfb_dir = resolve_ci(staging, _BASE_PFB_ROOT)
    if pfb_dir is not None and pfb_dir.is_dir():
        moved += _move_base_figure_files(
            staging, pfb_dir, _BASE_PFB_FILE_RE, known_pfbs,
            prefer_stem=src_pfb, dest_stem=dst_pfb, rename_map=rename_map,
            report=report, kind="pfb",
        )

    if moved:
        if src_pfb != dst_pfb and len(src_pfb) == len(dst_pfb):
            rename_map.setdefault(f"Figure_{src_pfb}", f"Figure_{dst_pfb}")
            rename_map.setdefault(f"figure_{src_pfb}", f"figure_{dst_pfb}")
        # Default-slot clone templates often embed Figure_{player_root}.
        profile = target.profile or source.profile or CLAIRE_PROFILE
        default_fig = f"Figure_{profile.figure_prefix}"
        if dst_pfb != profile.figure_prefix:
            new_fig = f"Figure_{dst_pfb}"
            if len(default_fig) == len(new_fig):
                rename_map.setdefault(default_fig, new_fig)
        report.warnings.append(
            f"Retargeted base figure gallery "
            f"{src_scene}/{src_pfb} → {dst_scene}/{dst_pfb} for {target.name}."
        )


def _move_base_figure_files(
    staging: Path,
    directory: Path,
    name_re: re.Pattern[str],
    known_stems: set[str],
    *,
    prefer_stem: str,
    dest_stem: str,
    rename_map: dict[str, str],
    report: ConversionReport,
    kind: str,
) -> int:
    """Move preferred (then other known) base figure files onto ``dest_stem``."""
    candidates: list[tuple[int, Path, str, str]] = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file():
            continue
        m = name_re.match(path.name)
        if m is None:
            continue
        stem = m.group(2)
        if stem.lower() == dest_stem.lower():
            continue
        if stem.lower() not in {s.lower() for s in known_stems}:
            continue
        # Prefer the convert source stem, then any other known leftover.
        rank = 0 if stem.lower() == prefer_stem.lower() else 1
        candidates.append((rank, path, stem, m.group(3)))

    if not candidates:
        return 0

    candidates.sort(key=lambda item: (item[0], item[1].name.lower()))
    moved = 0
    primary = True
    for _rank, path, stem, ext in candidates:
        new_name = (
            f"figurescene_{dest_stem}{ext}"
            if kind == "scene"
            else f"figure_{dest_stem}{ext}"
        )
        dest = directory / new_name
        if primary:
            if dest.exists() and dest.resolve() != path.resolve():
                report.removed_ops.append(
                    dest.relative_to(staging).as_posix())
                dest.unlink()
            old_rel = path.relative_to(staging).as_posix()
            path.rename(dest)
            new_rel = dest.relative_to(staging).as_posix()
            report.rename_ops.append(
                f"{old_rel}  ->  {new_rel} (base figure gallery)"
            )
            _register_figure_token(rename_map, path.name, new_name)
            moved += 1
            primary = False
        else:
            # Extra source-frame leftovers (e.g. Classic scene after Tank copy).
            rel = path.relative_to(staging).as_posix()
            path.unlink(missing_ok=True)
            report.removed_ops.append(rel)
            moved += 1
    return moved


def _detect_folder_mesh_stem(
    staging: Path,
    folder_id: str,
    *,
    profile: CharacterProfile | None = None,
) -> str | None:
    """First ``plXXXX.mesh`` stem inside a mesh folder, if any."""
    profile = profile or CLAIRE_PROFILE
    stem_re = re.compile(
        r"^(pl[0-9a-zA-Z]{4})\.(?:mesh)(?:\.\d+)?$", re.IGNORECASE)
    for root in mesh_roots(profile):
        folder = resolve_ci(staging, f"{root}/{folder_id}")
        if folder is None or not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            m = stem_re.match(path.name)
            if m:
                return m.group(1)
    return None


def _sync_base_figure_asset_stems(
    staging: Path,
    rename_map: dict[str, str],
    report: ConversionReport,
    *,
    profile: CharacterProfile | None = None,
) -> None:
    """Map leftover template stems in figure binaries onto real mesh stems.

    Tank Top ``figure_pl1001`` templates often keep ``plmira`` / ``pl107l`` /
    ``pl100l`` while gameplay uses ``plnico`` / ``pl107t`` / ``pl100t``. Register
    same-length aliases so ``path_patch`` rewrites the gallery prefab.
    """
    profile = profile or CLAIRE_PROFILE
    roots = mesh_roots(profile)
    present_ids: set[str] = set()
    for root in roots:
        root_dir = resolve_ci(staging, root)
        if root_dir is None or not root_dir.is_dir():
            continue
        for entry in root_dir.iterdir():
            name = entry.name
            if entry.is_dir() and re.match(r"^pl[0-9a-zA-Z]{4}$", name):
                present_ids.add(name)
            elif entry.is_file():
                m = re.match(
                    r"^(pl[0-9a-zA-Z]{4})\.chain(?:\.\d+)?$", name, re.I)
                if m:
                    present_ids.add(m.group(1))

    # Face / hair folders (vanilla shared ids, or private pl18xx by mesh stem).
    face_set_ids = {x.lower() for x in profile.face_ids}
    hair_set_ids = {x.lower() for x in profile.hair_mesh_ids}
    face_folders: list[str] = []
    hair_folders: list[str] = []
    for pid in sorted(present_ids):
        low = pid.lower()
        if low in face_set_ids:
            face_folders.append(pid)
            continue
        if low in hair_set_ids:
            hair_folders.append(pid)
            continue
        if not (low.startswith("pl18") and len(pid) == 6):
            continue
        stem = _detect_folder_mesh_stem(staging, pid, profile=profile)
        hair_prefix = profile.default_hair_id[:5].lower()  # pl107 / pl007
        if stem and stem.lower().startswith(hair_prefix):
            hair_folders.append(pid)
        elif stem:
            face_folders.append(pid)

    want_face: str | None = None
    for fid in face_folders:
        stem = _detect_folder_mesh_stem(staging, fid, profile=profile)
        if stem:
            want_face = stem
            if stem.lower() != fid.lower():
                break

    want_hair: str | None = None
    want_hair_chain: str | None = None
    for hid in hair_folders:
        mesh_stem, _ = detect_hair_asset_stems(
            staging, hid, profile=profile)
        if mesh_stem:
            want_hair = mesh_stem
        chain = resolve_hair_chain_id(
            staging, hid, mesh_stem, profile=profile)
        if chain:
            want_hair_chain = chain
        if want_hair and want_hair_chain:
            break

    # Body physics sidecars under mesh roots.
    want_body_chain: str | None = None
    for root in roots:
        root_dir = resolve_ci(staging, root)
        if root_dir is None:
            continue
        for entry in root_dir.iterdir():
            if not entry.is_file():
                continue
            m = re.match(
                r"^(pl[0-9a-z]{4})\.(?:chain)(?:\.\d+)?$",
                entry.name, re.I,
            )
            if not m:
                continue
            stem = m.group(1).lower()
            if stem == profile.player_root.lower():
                continue
            # Body physics sidecars share the player digit family (pl1 / pl0).
            if stem.startswith(profile.player_root[:3].lower()):
                want_body_chain = m.group(1)
                break
        if want_body_chain:
            break

    figure_files: list[Path] = []
    for root in (_BASE_SCENE_ROOT, _BASE_PFB_ROOT):
        root_dir = resolve_ci(staging, root)
        if root_dir is None or not root_dir.is_dir():
            continue
        figure_files.extend(
            p for p in root_dir.iterdir()
            if p.is_file() and (
                ".scn" in p.name.lower() or ".pfb" in p.name.lower()
            )
        )
    if not figure_files:
        return

    added = 0
    face_set = {f.lower() for f in face_folders}
    hair_set = {h.lower() for h in hair_folders}
    for path in figure_files:
        try:
            text = path.read_bytes().decode("utf-16-le", errors="ignore")
        except OSError:
            continue
        for match in _FIGURE_MESH_STEM_RE.finditer(text):
            folder = match.group(1)
            stem = match.group(2)
            want = None
            if want_face and folder.lower() in face_set:
                want = want_face
            elif want_hair and folder.lower() in hair_set:
                want = want_hair
            if not want or stem.lower() == want.lower():
                continue
            if len(stem) != len(want):
                continue
            if rename_map.get(stem) == want:
                continue
            # Bare stem alias (plmira→plnico) — safe; these are not body IDs.
            rename_map[stem] = want
            added += 1
        for match in _FIGURE_CHAIN_STEM_RE.finditer(text):
            stem = match.group(1)
            want = None
            hair_prefix = profile.default_hair_id[:5].lower()
            body_prefix = profile.player_root[:5].lower()
            if want_hair_chain and stem.lower().startswith(hair_prefix):
                want = want_hair_chain
            elif want_body_chain and stem.lower().startswith(body_prefix):
                want = want_body_chain
            if not want or stem.lower() == want.lower():
                continue
            if len(stem) != len(want):
                continue
            if rename_map.get(stem) == want:
                continue
            rename_map[stem] = want
            added += 1

    if added:
        report.rename_ops.append(
            f"aliased {added} figure gallery stem(s) onto local mesh/chain ids"
        )
