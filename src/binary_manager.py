"""Centralized management of external binaries and AI models.

DraggyEncoder downloads third-party tools (FFmpeg, Real-ESRGAN, RIFE) and
DeOldify ONNX models on first run. This module tracks which versions are
installed in a local manifest so subsequent starts are fast: if the installed
version matches the version pinned in code, the download is skipped.
"""

import os
import json
import platform
from datetime import datetime, timezone

import src.globals as g
from src.download import (
    download_ffmpeg_func,
    install_ffmpeg_func,
    download_realesrgan_func,
    install_realesrgan_func,
    download_rife_func,
    install_rife_func,
    download_deoldify_model,
)
from src.ai_tools import COLORIZE_MODELS

MANIFEST_NAME = ".manifest.json"

# ──────────────────────────────────────────────
# Pinned versions
# ──────────────────────────────────────────────
# When a URL changes or a new release is required, bump the version here.
# The manager will notice the mismatch and re-download that component.
_FFMPEG_VERSION = "2024-08-31-12-50"
_REALESRGAN_VERSION = "v0.2.5.0"
_RIFE_VERSION = "20221029"


def _deoldify_version():
    """Composite version string for all DeOldify models."""
    parts = []
    for key in sorted(COLORIZE_MODELS.keys()):
        version = COLORIZE_MODELS[key].get("version", "1")
        parts.append(f"{key}:{version}")
    return "-".join(parts)


# ──────────────────────────────────────────────
# Installation checks
# ──────────────────────────────────────────────

def _ffmpeg_installed() -> bool:
    return os.path.exists(g.ffmpeg_path) and os.path.exists(g.ffprobe_path)


def _realesrgan_installed() -> bool:
    return os.path.exists(g.realesrgan_path) and os.path.isdir(os.path.join(g.bin_dir, "models"))


def _rife_installed() -> bool:
    return os.path.exists(g.rife_path) and os.path.isdir(os.path.join(g.bin_dir, "models"))


def _deoldify_installed() -> bool:
    models_dir = os.path.join(g.bin_dir, "models")
    for info in COLORIZE_MODELS.values():
        if not os.path.exists(os.path.join(models_dir, info["model_filename"])):
            return False
    return True


# ──────────────────────────────────────────────
# Component definitions
# ──────────────────────────────────────────────

def _noop_install(_log_callback=None):
    return True


COMPONENTS = [
    {
        "key": "ffmpeg",
        "name": "FFmpeg",
        "version": _FFMPEG_VERSION,
        "required": True,
        "is_installed": _ffmpeg_installed,
        "download": download_ffmpeg_func,
        "install": install_ffmpeg_func,
    },
    {
        "key": "realesrgan",
        "name": "Real-ESRGAN",
        "version": _REALESRGAN_VERSION,
        "required": False,
        "is_installed": _realesrgan_installed,
        "download": download_realesrgan_func,
        "install": install_realesrgan_func,
    },
    {
        "key": "rife",
        "name": "RIFE",
        "version": _RIFE_VERSION,
        "required": False,
        "is_installed": _rife_installed,
        "download": download_rife_func,
        "install": install_rife_func,
    },
    {
        "key": "deoldify",
        "name": "DeOldify models",
        "version": _deoldify_version(),
        "required": False,
        "is_installed": _deoldify_installed,
        "download": download_deoldify_model,
        "install": _noop_install,
    },
]


# ──────────────────────────────────────────────
# Manifest helpers
# ──────────────────────────────────────────────

def _manifest_path():
    return os.path.join(g.bin_dir, MANIFEST_NAME)


def load_manifest():
    """Load the installed-versions manifest, returning an empty dict on error."""
    path = _manifest_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_manifest(manifest):
    """Write the manifest atomically."""
    path = _manifest_path()
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        if os.path.exists(path):
            os.remove(path)
        os.rename(tmp_path, path)
    except Exception as e:
        print(f"Warning: could not save binary manifest: {e}")


def _is_up_to_date(component, manifest):
    """Return True if the component is present and its version matches code."""
    entry = manifest.get(component["key"])
    if not entry:
        return False
    if entry.get("version") != component["version"]:
        return False
    return component["is_installed"]()


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def check_and_update_binaries(progress_callback=None, log_callback=None):
    """Ensure all external binaries are present and up-to-date.

    Args:
        progress_callback: function(int_pct) called by download routines.
        log_callback: function(str) called with status messages.

    Returns:
        dict with:
        - "results": {component_key: "uptodate" | "installed" | "failed"}
        - "required_failed": list of required component keys that failed.
    """
    if progress_callback is None:
        progress_callback = lambda _p: None
    if log_callback is None:
        log_callback = lambda _m: None

    manifest = load_manifest()
    results = {}
    required_failed = []

    os.makedirs(g.bin_dir, exist_ok=True)

    for component in COMPONENTS:
        key = component["key"]
        name = component["name"]

        if _is_up_to_date(component, manifest):
            log_callback(f"{name} is up-to-date.")
            results[key] = "uptodate"
            continue

        log_callback(f"Downloading {name}...")

        try:
            ok_download = component["download"](progress_callback, log_callback)
            if not ok_download:
                raise RuntimeError("download returned False")
            ok_install = component["install"](log_callback)
            if not ok_install:
                raise RuntimeError("install returned False")

            manifest[key] = {
                "version": component["version"],
                "installed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_manifest(manifest)
            log_callback(f"{name} installed successfully.")
            results[key] = "installed"
        except Exception as e:
            error_msg = f"{name} failed: {e}"
            log_callback(error_msg)
            print(error_msg)
            results[key] = "failed"
            if component["required"]:
                required_failed.append(key)

    return {"results": results, "required_failed": required_failed}


def is_component_ready(key):
    """Check whether a component is installed and matches the pinned version."""
    manifest = load_manifest()
    for component in COMPONENTS:
        if component["key"] == key:
            return _is_up_to_date(component, manifest)
    return False
