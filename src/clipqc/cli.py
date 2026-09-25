"""Command line: `clipqc check DIR` and `clipqc doctor`."""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from clipqc import __version__
from clipqc.config import ConfigError, load_config
from clipqc.report import exit_code, render_table, to_json
from clipqc.runner import DETECTORS, check_clips, discover

USAGE_ERROR = 2


def _ffmpeg_version() -> str:
    proc = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL)
    first = proc.stdout.splitlines()[0] if proc.stdout else ""
    return first.split(" Copyright")[0].removeprefix("ffmpeg version ").strip()


def _missing_tools() -> list[str]:
    return [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]


def _parse_only(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return DETECTORS
    names = tuple(dict.fromkeys(n.strip() for n in raw.split(",") if n.strip()))
    unknown = [n for n in names if n not in DETECTORS]
    if unknown or not names:
        raise ValueError(f"unknown detector(s): {', '.join(unknown) or '(none)'}; "
                         f"available: {', '.join(DETECTORS)}")
    return names


def _check(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    if not root.is_dir():
        print(f"clipqc: not a directory: {args.dir}", file=sys.stderr)
        return USAGE_ERROR
    missing = _missing_tools()
    if missing:
        print(f"clipqc: not found on PATH: {', '.join(missing)}", file=sys.stderr)
        return USAGE_ERROR
    try:
        cfg = load_config(Path(args.config) if args.config else None)
        detectors = _parse_only(args.only)
    except (ConfigError, ValueError) as exc:
        print(f"clipqc: {exc}", file=sys.stderr)
        return USAGE_ERROR
    clips = discover(root)
    if not clips:
        print(f"clipqc: no video files under {args.dir}", file=sys.stderr)
        return USAGE_ERROR

    def progress(rel: str) -> None:
        print(f"checking {rel}", file=sys.stderr)

    results = check_clips(root, clips, cfg, detectors, on_clip=progress)
    if args.json:
        print(to_json(results, cfg, _ffmpeg_version()))
    else:
        print(render_table(results))
    return exit_code(results, strict=args.strict)


def _doctor(_: argparse.Namespace) -> int:
    print(f"clipqc {__version__} on Python {platform.python_version()}")
    missing = _missing_tools()
    for tool in ("ffmpeg", "ffprobe"):
        print(f"{tool}: {shutil.which(tool) or 'NOT FOUND'}")
    if "ffmpeg" not in missing:
        print(f"ffmpeg version: {_ffmpeg_version()}")
    return USAGE_ERROR if missing else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clipqc", description=(
        "QC gate for batches of exported videos. Never edits video."))
    parser.add_argument("--version", action="version", version=f"clipqc {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="check every video under DIR")
    check.add_argument("dir")
    check.add_argument("--only", help=f"comma-separated detectors ({', '.join(DETECTORS)})")
    check.add_argument("--json", action="store_true", help="print one JSON report on stdout")
    check.add_argument("--config", help="path to clipqc.toml")
    check.add_argument("--strict", action="store_true",
                       help="exit 1 (not 3) when a clip could not be fully checked")
    check.set_defaults(func=_check)
    doctor = sub.add_parser("doctor", help="show ffmpeg/ffprobe and environment")
    doctor.set_defaults(func=_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
