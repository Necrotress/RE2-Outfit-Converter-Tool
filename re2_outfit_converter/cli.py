"""Command-line interface for analyze / convert (Windows, Linux, Steam Deck)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .archive import ExtractError
from .converter import BatchItem, convert, convert_batch
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="re2_outfit_converter",
        description=(
            "Convert RE2 Remake Claire Fluffy costume mods between outfit slots. "
            "Works without a GUI (useful on Steam Deck / Linux)."
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
        "--from", dest="source", required=True, type=_parse_outfit,
        metavar="OUTFIT", help="Source outfit key (e.g. elza)")
    p_cv.add_argument(
        "--to", dest="target", required=True, type=_parse_outfit,
        metavar="OUTFIT", help="Target outfit key (e.g. noir)")
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
    p_cv.set_defaults(func=_cmd_convert)

    return parser


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
            print()
        return 0 if not result.errors else 1
    finally:
        close_loaded(result.packages)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _print_report(report: ConversionReport | BatchReport) -> None:
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

        out_dir: Path = args.output
        out_dir.mkdir(parents=True, exist_ok=True)
        tag_output = not args.no_tag
        display = (args.display_name or "").strip() or None

        try:
            if len(result.packages) == 1:
                pkg = result.packages[0]
                report = convert(
                    pkg.analysis,
                    args.source,
                    args.target,
                    out_dir,
                    progress=_progress,
                    as_folder=args.folder,
                    outfit_display_name=display,
                    tag_output=tag_output,
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
                    args.source,
                    args.target,
                    out_dir,
                    bundle,
                    progress=_progress,
                    outfit_display_name=display,
                    tag_output=tag_output,
                )
        except NothingToConvertError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except (ConversionError, ExtractError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

        _print_report(report)
        return 0
    finally:
        close_loaded(result.packages)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
