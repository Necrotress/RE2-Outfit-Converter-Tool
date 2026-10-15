"""Run Blender headless jobs to convert RT mesh/mdf2 to classic RE2."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..cancel import ConversionCancelled, cancel_requested
from .blender_detect import blender_script_dir
from .formats import parse_versioned_name
from .reports import ConversionReport

ProgressCb = Callable[[str], None] | None

MESH_RT = "mesh.2109108288"
MESH_CLASSIC = "mesh.1808312334"
MDF_RT = "mdf2.21"
MDF_CLASSIC = "mdf2.10"

# Kept in step with mdf_presets.RETARGET_PREFIX, which the Blender scripts use.
RETARGET_PREFIX = "retarget: "


@dataclass
class BlenderJob:
    kind: str  # mesh | mdf2
    src: Path
    dst: Path


@dataclass
class BlenderBatchResult:
    jobs: list[BlenderJob] = field(default_factory=list)
    ok_srcs: set[str] = field(default_factory=set)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (src, error)
    skipped_no_blender: bool = False
    message: str = ""
    material_notes: list[str] = field(default_factory=list)


def collect_mesh_mdf_jobs(staging: Path, *, to_rt: bool = False) -> list[BlenderJob]:
    """Find mesh/mdf2 under staging natives and build the other platform's paths."""
    natives = staging / "natives"
    if not natives.is_dir():
        return []
    jobs: list[BlenderJob] = []
    for path in natives.rglob("*"):
        if not path.is_file():
            continue
        parsed = parse_versioned_name(path.name)
        if parsed is None:
            continue
        if to_rt:
            if parsed.kind == "mesh" and parsed.suffix == MESH_CLASSIC:
                dst = path.with_name(f"{parsed.stem}.{MESH_RT}")
                jobs.append(BlenderJob("mesh_rt", path, dst))
            elif parsed.kind == "mdf2" and parsed.suffix == MDF_CLASSIC:
                dst = path.with_name(f"{parsed.stem}.{MDF_RT}")
                jobs.append(BlenderJob("mdf2_rt", path, dst))
        elif parsed.kind == "mesh" and parsed.suffix == MESH_RT:
            dst = path.with_name(f"{parsed.stem}.{MESH_CLASSIC}")
            jobs.append(BlenderJob("mesh", path, dst))
        elif parsed.kind == "mdf2" and parsed.suffix == MDF_RT:
            dst = path.with_name(f"{parsed.stem}.{MDF_CLASSIC}")
            jobs.append(BlenderJob("mdf2", path, dst))
    # Mesh export can drop empty slots. Align the MDF to that mesh, so the
    # mesh job runs first.
    jobs.sort(key=lambda job: 0 if job.kind.startswith("mesh") else 1)
    return jobs


def collect_shipped_mmtr(staging: Path) -> list[str]:
    """Master materials the mod brings with it.

    These are the shaders the target game will not have, because a .mmtr is
    compiled per engine build. Materials pointing at one need re-aiming at a
    stock shader or they draw nothing.
    """
    natives = staging / "natives"
    if not natives.is_dir():
        return []
    out = []
    for path in natives.rglob("*"):
        if path.is_file() and ".mmtr." in path.name.lower():
            out.append(path.name)
    return sorted(out)


def stock_shader_overrides(staging: Path) -> list[Path]:
    """Shipped master materials that shadow one the game already owns."""
    sys.path.insert(0, str(blender_script_dir()))
    try:
        import mdf_presets
    finally:
        sys.path.pop(0)

    natives = staging / "natives"
    if not natives.is_dir():
        return []
    hits = []
    for path in sorted(natives.rglob("*")):
        if not path.is_file() or ".mmtr." not in path.name.lower():
            continue
        base = path.name.lower().split(".mmtr.")[0] + ".mmtr"
        if base in mdf_presets.STOCK_RE2_MMTR:
            hits.append(path)
    return hits


def write_manifest(
    jobs: list[BlenderJob],
    path: Path,
    shipped_mmtr: list[str] | None = None,
    re3_player_dest: str | None = None,
) -> None:
    payload = {
        "jobs": [
            {
                "kind": j.kind,
                "src": str(j.src.resolve()),
                "dst": str(j.dst.resolve()),
            }
            for j in jobs
        ],
        "shipped_mmtr": list(shipped_mmtr or []),
        "re3_player_dest": re3_player_dest or "",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_result(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("results") or [])


def _kill_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _wait_blender(proc: subprocess.Popen, timeout: float) -> tuple[str, str]:
    """Wait for Blender, stopping it when the convert is cancelled.

    Output is drained on a side thread so a chatty Blender cannot fill the
    pipe and stall while we poll for cancel.
    """
    holder: dict = {}

    def _read() -> None:
        try:
            holder["out"] = proc.communicate()
        except Exception as exc:
            holder["err"] = exc

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    while reader.is_alive():
        if cancel_requested():
            _kill_process(proc)
            reader.join(timeout=5)
            raise ConversionCancelled("Convert cancelled.")
        if time.monotonic() > deadline:
            _kill_process(proc)
            reader.join(timeout=5)
            raise subprocess.TimeoutExpired(proc.args, timeout)
        reader.join(0.2)
    if "err" in holder:
        raise holder["err"]
    stdout, stderr = holder.get("out", ("", ""))
    return stdout or "", stderr or ""


def run_blender_batch(
    blender: Path,
    jobs: list[BlenderJob],
    *,
    progress: ProgressCb = None,
    timeout: float = 3600.0,
    shipped_mmtr: list[str] | None = None,
    re3_player_dest: str | None = None,
) -> BlenderBatchResult:
    """Execute jobs in one Blender process; apply successful outputs in place."""
    out = BlenderBatchResult(jobs=list(jobs))
    if not jobs:
        out.message = "No mesh/mdf jobs."
        return out

    script = blender_script_dir() / "batch_rt_to_re2.py"
    if not script.is_file():
        out.message = f"Missing Blender batch script: {script}"
        out.failed = [(str(j.src), out.message) for j in jobs]
        return out

    def notify(msg: str) -> None:
        if progress:
            progress(msg)

    with tempfile.TemporaryDirectory(prefix="re2rtx_blend_") as tmp:
        tmp_path = Path(tmp)
        manifest = tmp_path / "manifest.json"
        result_json = tmp_path / "result.json"
        write_manifest(
            jobs, manifest, shipped_mmtr, re3_player_dest=re3_player_dest
        )

        notify(f"Blender: converting {len(jobs)} mesh/mdf file(s)…")
        cmd = [
            str(blender),
            "--background",
            "--python",
            str(script),
            "--",
            "--manifest",
            str(manifest),
            "--result",
            str(result_json),
        ]
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                ),
            )
        except OSError as e:
            out.message = f"Failed to launch Blender: {e}"
            out.failed = [(str(j.src), out.message) for j in jobs]
            return out
        try:
            stdout, stderr = _wait_blender(proc, timeout)
        except subprocess.TimeoutExpired:
            out.message = "Blender batch timed out."
            out.failed = [(str(j.src), out.message) for j in jobs]
            return out

        out.material_notes = [
            line.split(":", 1)[1].strip()
            for line in (stdout or "").splitlines()
            if line.startswith("RE2RTX_MDF:") or line.startswith("RE2RTX_MESH:")
        ]

        if not result_json.is_file():
            err = (stderr or stdout or "").strip()
            out.message = (
                f"Blender produced no result file (exit {proc.returncode}). "
                f"{err[:500]}"
            )
            out.failed = [(str(j.src), out.message) for j in jobs]
            return out

        try:
            results = parse_result(result_json)
        except (OSError, json.JSONDecodeError) as e:
            out.message = f"Bad Blender result JSON: {e}"
            out.failed = [(str(j.src), out.message) for j in jobs]
            return out

        by_src = {str(Path(r.get("src", "")).resolve()).lower(): r for r in results}
        for job in jobs:
            key = str(job.src.resolve()).lower()
            r = by_src.get(key)
            if r and r.get("ok") and job.dst.is_file():
                # The converted file sits beside the source. A leftover
                # source is later remapped onto that same name and replaces
                # the converted bytes. Do not call the job ok until the
                # source is gone.
                removed = True
                if job.src.exists() and job.src.resolve() != job.dst.resolve():
                    try:
                        job.src.unlink()
                    except OSError:
                        removed = False
                        parked = job.src.with_name(job.src.name + ".re2oc-src")
                        try:
                            if parked.exists():
                                parked.unlink()
                            job.src.rename(parked)
                            removed = not job.src.exists()
                        except OSError:
                            removed = False
                if removed:
                    out.ok_srcs.add(str(job.src))
                    notify(f"Blender: ok {job.src.name}")
                else:
                    out.failed.append((
                        str(job.src),
                        "Converted file written but the source mesh could not "
                        "be removed",
                    ))
                    notify(f"Blender: failed {job.src.name}")
            else:
                err = (r or {}).get("error") or "Blender conversion failed"
                # Clean partial dst
                try:
                    if job.dst.is_file() and not (r and r.get("ok")):
                        job.dst.unlink()
                except OSError:
                    pass
                out.failed.append((str(job.src), str(err).splitlines()[0][:300]))
                notify(f"Blender: failed {job.src.name}")

        out.message = (
            f"Blender: {len(out.ok_srcs)} ok, {len(out.failed)} failed"
        )
        return out


def apply_blender_result_to_report(
    staging: Path,
    batch: BlenderBatchResult,
    report: ConversionReport,
) -> None:
    """Record blender successes/failures on the conversion report."""
    retargets = [
        n[len(RETARGET_PREFIX):]
        for n in batch.material_notes
        if n.startswith(RETARGET_PREFIX)
    ]
    if retargets:
        report.warnings.append(
            f"{len(retargets)} material(s) re-aimed at a stock shader because "
            "the mod ships its own master material, which the other game "
            "cannot load:"
        )
        report.warnings.extend(f"  {n}" for n in retargets)

    rebuilds = [
        n for n in batch.material_notes
        if "broken property table" in n
    ]
    if rebuilds:
        report.warnings.append(
            f"{len(rebuilds)} material(s) had a truncated property table "
            "and were rebuilt onto the stock layout:"
        )
        report.warnings.extend(f"  {n}" for n in rebuilds)

    def rel_of(path: Path) -> str:
        try:
            return path.relative_to(staging).as_posix()
        except ValueError:
            return path.name

    ok_resolved = {Path(s).resolve() for s in batch.ok_srcs}
    for job in batch.jobs:
        rel = rel_of(job.src)
        if job.src.resolve() in ok_resolved or str(job.src) in batch.ok_srcs:
            if job.dst.is_file():
                report.converted_ops.append(
                    f"blender-{job.kind}: {rel_of(job.dst)}"
                )
            else:
                report.converted_ops.append(f"blender-{job.kind}: {rel}")
        else:
            err = next(
                (e for s, e in batch.failed
                 if Path(s).resolve() == job.src.resolve()
                 or Path(s).name == job.src.name),
                "Blender conversion failed",
            )
            report.failed_ops.append(f"{rel}: {err}")
            try:
                if job.src.is_file():
                    job.src.unlink()
                    report.removed_ops.append(rel)
            except OSError:
                pass