#!/usr/bin/env python3
"""Compatibility entry point for the offline NASA data build."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    runpy.run_path(str(scripts / "build_data.py"), run_name="__main__")
