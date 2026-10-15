"""Locate Blender and verify RE Mesh Editor is available."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

BLENDER_DOWNLOAD = "https://download.blender.org/release/"
RE_MESH_EDITOR_URL = "https://github.com/NSACloud/RE-Mesh-Editor"
RE_MESH_EDITOR_NAME = "RE Mesh Editor"

# Common Windows install roots.
_WIN_SEARCH_ROOTS = (
    Path(r"C:\Program Files\Blender Foundation"),
    Path(r"C:\Program Files (x86)\Blender Foundation"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Blender Foundation",
)


@dataclass
class BlenderProbeResult:
    ok: bool
    blender_path: str = ""
    blender_version: str = ""
    addon_ok: bool = False
    addon_module: str = ""
    message: str = ""


def find_blender(preferred: str | Path | None = None) -> Path | None:
    """Return blender.exe path from preferred setting, PATH, or common installs."""
    if preferred:
        cand = Path(preferred)
        if cand.is_file():
            return cand
        if cand.is_dir():
            exe = cand / "blender.exe"
            if exe.is_file():
                return exe

    which = shutil.which("blender") or shutil.which("blender.exe")
    if which:
        which_path = Path(which)
        text = str(which_path).lower()
        if "blender 5." not in text and "blender5." not in text:
            return which_path

    if sys.platform == "win32":
        found: list[Path] = []
        for root in _WIN_SEARCH_ROOTS:
            if not root.is_dir():
                continue
            for exe in root.rglob("blender.exe"):
                found.append(exe)
        if found:
            def _score(p: Path) -> tuple[int, str]:
                # RE Mesh Editor is supported on Blender 4.3. Do not pick 5.x.
                text = str(p).lower().replace("/", "\\")
                if "blender 5." in text or "blender5." in text:
                    return (-1, text)
                if "blender 4.3" in text:
                    return (3, text)
                if "blender 4." in text:
                    return (2, text)
                if "blender 3." in text:
                    return (1, text)
                return (0, text)

            found = [p for p in found if _score(p)[0] >= 0]
            if not found:
                return None
            found.sort(key=_score, reverse=True)
            return found[0]
    return None


def blender_script_dir() -> Path:
    """Directory containing batch_rt_to_re2.py (dev tree or frozen bundle)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "re2_outfit_converter" / "platform" / "blender_scripts"
    return Path(__file__).resolve().parent / "blender_scripts"


def probe_blender(blender: Path, *, timeout: float = 120.0) -> BlenderProbeResult:
    """Run a tiny headless script to confirm Blender + RE Mesh Editor operators."""
    blender = Path(blender)
    if not blender.is_file():
        return BlenderProbeResult(
            ok=False, message=f"Blender not found: {blender}"
        )

    probe_py = textwrap.dedent(
        r"""
        import json
        import sys
        import bpy
        import addon_utils

        result = {
            "blender_version": "%s.%s.%s" % bpy.app.version,
            "addon_ok": False,
            "addon_module": "",
            "ops": [],
            "error": "",
        }
        try:
            for mod in addon_utils.modules():
                info = getattr(mod, "bl_info", {}) or {}
                name = str(info.get("name", ""))
                if "RE Mesh Editor" in name or name == "RE Mesh Editor":
                    result["addon_module"] = mod.__name__
                    # Ensure enabled
                    try:
                        addon_utils.enable(mod.__name__, default_set=True)
                    except Exception as e:
                        result["error"] = "enable failed: %s" % e
                    break
            has_mesh = hasattr(bpy.ops, "re_mesh") and hasattr(bpy.ops.re_mesh, "importfile")
            has_mdf = hasattr(bpy.ops, "re_mdf") and hasattr(bpy.ops.re_mdf, "importfile")
            result["ops"] = [
                "re_mesh.importfile" if has_mesh else "",
                "re_mdf.importfile" if has_mdf else "",
            ]
            result["addon_ok"] = bool(has_mesh and has_mdf)
            if not result["addon_ok"] and not result["error"]:
                result["error"] = (
                    "RE Mesh Editor operators missing. Install/enable the addon: "
                    "https://github.com/NSACloud/RE-Mesh-Editor"
                )
        except Exception as e:
            result["error"] = str(e)
        out = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else ""
        if out:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(result, f)
        print("RE2RTX_PROBE:" + json.dumps(result))
        """
    ).strip()

    with tempfile.TemporaryDirectory(prefix="re2rtx_probe_") as tmp:
        script = Path(tmp) / "probe.py"
        out_json = Path(tmp) / "probe.json"
        script.write_text(probe_py, encoding="utf-8")
        cmd = [
            str(blender),
            "--background",
            "--python",
            str(script),
            "--",
            str(out_json),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.TimeoutExpired:
            return BlenderProbeResult(
                ok=False,
                blender_path=str(blender),
                message="Blender probe timed out.",
            )
        except OSError as e:
            return BlenderProbeResult(
                ok=False,
                blender_path=str(blender),
                message=f"Failed to launch Blender: {e}",
            )

        data: dict = {}
        if out_json.is_file():
            try:
                data = json.loads(out_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        if not data:
            # Fallback: parse stdout marker
            for line in (proc.stdout or "").splitlines():
                if line.startswith("RE2RTX_PROBE:"):
                    try:
                        data = json.loads(line[len("RE2RTX_PROBE:"):])
                    except json.JSONDecodeError:
                        pass
                    break

        if not data:
            err = (proc.stderr or proc.stdout or "").strip()
            return BlenderProbeResult(
                ok=False,
                blender_path=str(blender),
                message=f"Blender probe failed (exit {proc.returncode}). {err[:400]}",
            )

        addon_ok = bool(data.get("addon_ok"))
        msg = data.get("error") or (
            "OK — Blender and RE Mesh Editor are ready."
            if addon_ok
            else "RE Mesh Editor not detected."
        )
        return BlenderProbeResult(
            ok=addon_ok,
            blender_path=str(blender),
            blender_version=str(data.get("blender_version") or ""),
            addon_ok=addon_ok,
            addon_module=str(data.get("addon_module") or ""),
            message=msg,
        )


def resolve_blender_for_convert(
    settings: dict | None = None,
    *,
    blender_path: str | Path | None = None,
    use_blender: bool | None = None,
) -> tuple[Path | None, str]:
    """Pick blender path for conversion. Returns (path_or_None, reason)."""
    settings = settings or {}
    if use_blender is None:
        use_blender = bool(settings.get("use_blender", True))
    if not use_blender:
        return None, "Blender mesh/mdf conversion disabled in settings."

    preferred = blender_path or settings.get("blender_path") or ""
    found = find_blender(preferred if preferred else None)
    if found is None:
        return None, (
            "Blender 4.3.2 not found. Install Blender 4.3 and RE Mesh Editor, "
            f"then set the path in Settings. ({BLENDER_DOWNLOAD})"
        )
    return found, "ok"
