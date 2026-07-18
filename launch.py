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


def _native_error(title: str, message: str) -> None:
    """Show a native error dialog when running without a visible console."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # type: ignore[attr-defined]
        except Exception:
            pass
    else:
        # Best-effort Linux desktop notification; fall back to stderr.
        try:
            import shutil
            import subprocess

            if shutil.which("zenity"):
                subprocess.run(["zenity", "--error", "--title", title, "--text", message], check=False)
            elif shutil.which("kdialog"):
                subprocess.run(["kdialog", "--error", message, "--title", title], check=False)
        except Exception:
            pass


def _check_dependencies() -> list[str]:
    """Return a list of missing required packages (fast, no module execution)."""
    import importlib.util

    missing: list[str] = []
    # Map import name -> pip package name for clearer error messages.
    required = {
        "PySide6": "PySide6",
        "requests": "requests",
        "psutil": "psutil",
        "cv2": "opencv-python",
        "notifypy": "notify-py",
    }
    for import_name, pip_name in required.items():
        if importlib.util.find_spec(import_name) is None:
            missing.append(pip_name)
    return missing


def main() -> int:
    _force_utf8_stdout()
    _set_env_utf8()

    here = Path(__file__).resolve().parent
    entry = here / "main.py"
    if not entry.exists():
        print(f"[launch] ERROR: {entry} not found.", file=sys.stderr)
        return 1

    missing = _check_dependencies()
    if missing:
        msg = (
            f"Missing required packages: {', '.join(missing)}\n\n"
            "Install them with:\n"
            "  pip install -r requirements.txt"
        )
        print(f"[launch] ERROR:\n{msg}", file=sys.stderr)
        _native_error("DraggyEncoder - Missing dependencies", msg)
        return 3

    import runpy
    try:
        sys.argv[0] = str(entry)
        runpy.run_path(str(entry), run_name="__main__")
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:
        print(f"[launch] DraggyEncoder failed: {e}", file=sys.stderr)
        _native_error("DraggyEncoder - Startup error", str(e))
        try:
            input("Press Enter to close…")
        except EOFError:
            pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
