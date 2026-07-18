#!/usr/bin/env bash
# DraggyEncoder launcher for Linux / macOS (no WSL required).
# Make executable: chmod +x run_draggy.sh

export PYTHONIOENCODING="utf-8"
export PYTHONUTF8="1"

# Move to the script's directory so relative paths work (follow symlinks).
SCRIPT_PATH="$0"
if command -v realpath >/dev/null 2>&1; then
    SCRIPT_PATH=$(realpath "$SCRIPT_PATH" 2>/dev/null || echo "$SCRIPT_PATH")
elif command -v readlink >/dev/null 2>&1; then
    # GNU readlink supports -f; macOS readlink does not, so ignore errors.
    SCRIPT_PATH=$(readlink -f "$SCRIPT_PATH" 2>/dev/null || echo "$SCRIPT_PATH")
fi
cd "$(dirname "$SCRIPT_PATH")" || exit 1

# ── Locate a suitable Python interpreter ────────────────────────────────
PYTHON_EXE=""

# 1. Project virtual environments
if [ -x "venv/bin/python3" ]; then
    PYTHON_EXE="venv/bin/python3"
elif [ -x ".venv/bin/python3" ]; then
    PYTHON_EXE=".venv/bin/python3"
# 2. Commands on PATH
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_EXE="python"
fi

if [ -z "$PYTHON_EXE" ]; then
    echo "[ERROR] Python 3 is not installed or not in PATH."
    echo "Please install Python 3.10+ and run: pip install -r requirements.txt"
    read -r -p "Press Enter to exit..."
    exit 1
fi

$PYTHON_EXE launch.py
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[ERROR] DraggyEncoder exited with code $EXIT_CODE."
    echo "Make sure Python and the dependencies in requirements.txt are installed."
    read -r -p "Press Enter to exit..."
fi

exit $EXIT_CODE
