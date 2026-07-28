"""Command-line interface for analyze / convert."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .archive import ExtractError
from .converter import BatchItem, convert_batch, convert_with_ops
from .outfit_health import incomplete_outfits, incomplete_outfits_for_load
from .outfit_ops import OutfitOp
from .outfits import (
    CLAIRE_OUTFIT_BY_KEY,
    CONVERTIBLE_OUTFITS,
    is_convertible_outfit,
)
from .reports import (
    BatchReport,
    ConversionError,
    ConversionReport,
    NothingToConvertError,
)
from .packaging import input_base_name
from .session import close_loaded, load_inputs, package_label


def _outfit_keys() -> list[str]:
    return [o.key for o in CONVERTIBLE_OUTFITS]


def _parse_outfit(key: str):
    outfit = CLAIRE_OUTFIT_BY_KEY.get(key.lower())
    if outfit is None or not is_convertible_outfit(outfit):
        valid = ", ".join(_outfit_keys())
        raise argparse.ArgumentTypeError(
            f"unknown or non-convertible outfit {key!r} "
            f"(choose one of: {valid})"
        )
    return outfit


def _parse_map(value: str) -> OutfitOp:
    if ":" not in value:
        raise argparse.ArgumentTypeError(
            f"invalid --map {value!r}; expected SRC:DST (e.g. jacket:tanktop)"
        )
    src_key, dst_key = value.split(":", 1)
    src = _parse_outfit(src_key.strip())
    dst = _parse_outfit(dst_key.strip())
    return OutfitOp(source=src, target=dst)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="re2_outfit_converter",
        description=(
            "Convert RE2 Remake Claire Fluffy costume mods between outfit slots. "
            "Works without a GUI (CLI for Linux and scripting)."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser(
        "list-outfits", help="List convertible outfit keys and names")
    p_list.set_defaults(func=_cmd_list_outfits)

    p_an = sub.add_parser("analyze", help="Analyze mod folder(s) or archive(s)")
    p_an.add_argument(
        "inputs", nargs="+", type=Path, help="Mod folders or .zip/.rar/.7z")
    p_an.set_defaults(func=_cmd_analyze)

    p_cv = sub.add_parser("convert", help="Convert outfit slot(s) and package")
    p_cv.add_argument(
        "inputs", nargs="+", type=Path, help="Mod folders or .zip/.rar/.7z")
    p_cv.add_argument(
        "--from", dest="source", required=False, type=_parse_outfit,
        metavar="OUTFIT", help="Source outfit key (e.g. elza)")
    p_cv.add_argument(
        "--to", dest="target", required=False, type=_parse_outfit,
        metavar="OUTFIT", help="Target outfit key (e.g. noir)")
    p_cv.add_argument(
        "--map", dest="maps", action="append", type=_parse_map,
        metavar="SRC:DST", default=[],
        help="Map source→target (repeatable; e.g. --map jacket:noir)")
    p_cv.add_argument(
        "--delete", dest="deletes", action="append", type=_parse_outfit,
        metavar="OUTFIT", default=[],
        help="Strip outfit slot from output (repeatable)")
    p_cv.add_argument(
        "-o", "--output", type=Path, required=True,
        help="Output directory for zip/folder")
    p_cv.add_argument(
        "--name", dest="display_name", default=None,
        help="In-game outfit display name (DLC / Tank slots)")
    p_cv.add_argument(
        "--folder", action="store_true",
        help="Write a folder instead of a zip (single-mod only)")
    p_cv.add_argument(
        "--no-tag", action="store_true",
        help="Do not append outfit tags to names/descriptions")
    p_cv.add_argument(
        "--batch-name", default=None,
        help="Multi-mod zip base name (default: first main mod name)")
    p_cv.add_argument(
        "--military-face",
        choices=("dirty", "clean"),
        default="clean",
        help=(
            "Face textures for the convert: clean = Claire's default face "
            "(seeded into the mod), dirty = leave the target outfit's normal "
            "face. Ignored if the mod already has face data."
        ),
    )
    p_cv.add_argument(
        "--no-log", action="store_true",
        help="Do not embed convert.log inside the output package",
    )
    p_cv.set_defaults(func=_cmd_convert)

    return parser


def _resolve_ops(args: argparse.Namespace) -> list[OutfitOp]:
    ops: list[OutfitOp] = list(args.maps or [])
    for outfit in args.deletes or []:
        ops.append(OutfitOp(source=outfit, target=None))
    if ops:
        if args.source is not None or args.target is not None:
            raise ConversionError(
                "Use either --from/--to or --map/--delete, not both."
            )
        return ops
    if args.source is None or args.target is None:
        raise ConversionError(
            "Specify --from and --to, or at least one --map / --delete."
        )
    return [OutfitOp(source=args.source, target=args.target)]


def _cmd_list_outfits(_args: argparse.Namespace) -> int:
    for o in CONVERTIBLE_OUTFITS:
        print(f"{o.key:18} {o.name}  ({o.tag})")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    result = load_inputs(list(args.inputs))
    try:
        for err in result.errors:
            print(f"error: {err}", file=sys.stderr)
        for info in result.infos:
            print(f"note: {info}", file=sys.stderr)
        if not result.packages:
            print("No mod packages loaded.", file=sys.stderr)
            return 1
        load_incomplete = incomplete_outfits_for_load(
            [pkg.analysis for pkg in result.packages])
        for pkg in result.packages:
            a = pkg.analysis
            label = pkg.label or package_label(a, pkg.source)
            outfits = ", ".join(o.name for o in a.claire_outfits) or "(none)"
            chars = ", ".join(sorted(a.characters)) or "(none)"
            print(f"=== {label} ===")
            print(f"  root:       {a.root}")
            print(f"  outfits:    {outfits}")
            print(f"  characters: {chars}")
            if a.modinfo.addonfor:
                print(f"  AddonFor:   {a.modinfo.addonfor}")
            for w in a.warnings:
                print(f"  warning:    {w}")
            pkg_incomplete = incomplete_outfits(a)
            for key, reason in pkg_incomplete.items():
                if key not in load_incomplete:
                    continue
                outfit = CLAIRE_OUTFIT_BY_KEY.get(key)
                name = outfit.name if outfit else key
                print(f"  warning:    {name} incomplete: {reason}")
            print()
        return 0 if not result.errors else 1
    finally:
        close_loaded(result.packages)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _print_report(
    report: ConversionReport | BatchReport,
    *,
    write_log: bool = True,
) -> None:
    warnings: list[str] = []
    out: Path | None = None
    if isinstance(report, BatchReport):
        out = report.output_zip
        warnings = list(report.warnings)
        for item in report.items:
            warnings.extend(item.warnings)
    else:
        out = report.output_zip or report.output_folder
        warnings = list(report.warnings)

    if out is not None:
        print(f"Saved: {out}")
        if write_log:
            print("Log: convert.log embedded in package.")
    else:
        print("Conversion completed (no output path).")
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
    patch_skips = [w for w in warnings if "path patch" in w.lower()
                   or "skipped" in w.lower() and "patch" in w.lower()]
    if patch_skips:
        print(f"Binary patch skips/notes: {len(patch_skips)}")


def _cmd_convert(args: argparse.Namespace) -> int:
    result = load_inputs(list(args.inputs))
    try:
        for err in result.errors:
            print(f"error: {err}", file=sys.stderr)
        for info in result.infos:
            print(f"note: {info}", file=sys.stderr)
        if not result.packages:
            print("No mod packages loaded.", file=sys.stderr)
            return 1

        convertible = [
            p for p in result.packages if p.analysis.claire_outfits
        ]
        if not convertible and not any(
                p.analysis.is_passthrough_candidate for p in result.packages):
            print("No convertible Claire outfits found.", file=sys.stderr)
            return 1

        try:
            ops = _resolve_ops(args)
        except ConversionError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

        out_dir: Path = args.output
        out_dir.mkdir(parents=True, exist_ok=True)
        tag_output = not args.no_tag
        write_log = not args.no_log
        display = (args.display_name or "").strip() or None
        package_target = next(
            (op.target for op in ops if op.target is not None),
            ops[0].source,
        )

        try:
            if len(result.packages) == 1:
                pkg = result.packages[0]
                report = convert_with_ops(
                    pkg.analysis,
                    ops,
                    out_dir,
                    progress=_progress,
                    as_folder=args.folder,
                    outfit_display_name=display,
                    tag_output=tag_output,
                    source_name=input_base_name(pkg.source.original),
                    military_face=args.military_face,
                    write_log=write_log,
                )
            else:
                if args.folder:
                    print(
                        "error: --folder is only supported for a single mod; "
                        "batch mode always writes a multi-mod zip.",
                        file=sys.stderr,
                    )
                    return 2
                items = [
                    BatchItem(
                        analysis=p.analysis,
                        label=p.label or package_label(p.analysis, p.source),
                    )
                    for p in result.packages
                ]
                mains = [p for p in result.packages if p.analysis.claire_outfits]
                bundle = args.batch_name or (
                    package_label(mains[0].analysis, mains[0].source)
                    if mains else "Converted Batch"
                )
                report = convert_batch(
                    items,
                    package_target,
                    package_target,
                    out_dir,
                    bundle,
                    progress=_progress,
                    outfit_display_name=display,
                    tag_output=tag_output,
                    military_face=args.military_face,
                    ops=ops,
                    write_log=write_log,
                )
        except NothingToConvertError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except (ConversionError, ExtractError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

        _print_report(report, write_log=write_log)
        return 0
    finally:
        close_loaded(result.packages)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
