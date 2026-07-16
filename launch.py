#!/usr/bin/env python3
"""Cross-platform launcher for DraggyEncoder.

Double-click this file (or run `python launch.py`) on Windows / Linux / macOS.
Forces UTF-8 stdout/stderr so the 'charmap' codec error during ffmpeg
NUL/console output can never appear inside the Python process itself.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _force_utf8_stdout() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _set_env_utf8() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")


def main() -> int:
    _force_utf8_stdout()
    _set_env_utf8()

    here = Path(__file__).resolve().parent
    entry = here / "main.py"
    if not entry.exists():
        print(f"[launch] ERROR: {entry} not found.", file=sys.stderr)
        return 1

    import runpy
    try:
        runpy.run_path(str(entry), run_name="__main__")
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:
        print(f"[launch] DraggyEncoder failed: {e}", file=sys.stderr)
        try:
            input("Press Enter to close…")
        except EOFError:
            pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
