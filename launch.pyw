#!/usr/bin/env python3
"""Windows windowed launcher for DraggyEncoder.

Double-click this file in Explorer to start DraggyEncoder without a console
window. It simply delegates to launch.py, which is the cross-platform entry
point.
"""
from __future__ import annotations

import sys

# Import the cross-platform launcher and run its main entry point.
import launch  # noqa: F401  # imported for side-effects / main()


if __name__ == "__main__":
    sys.exit(launch.main())
