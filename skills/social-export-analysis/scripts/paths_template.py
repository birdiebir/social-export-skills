# -*- coding: utf-8 -*-
"""Central path config template — copy to <project>/analysis/lib/paths.py.

Every extract/join/report/check script should import from this module instead
of hardcoding an absolute path. That's what makes the whole pipeline portable
across projects and machines.

If your layout differs from the recommended
    <project>/analysis/scripts/<category>/<file>.py
    <project>/analysis/lib/paths.py
adjust PROJECT_ROOT's parents[N] accordingly (N = number of directories
between this file and <project>/).
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # analysis/lib/paths.py -> <project>/
RAW_ROOT = PROJECT_ROOT / "raw"
DERIVED_ROOT = PROJECT_ROOT / "derived"
ANALYSIS_ROOT = PROJECT_ROOT / "analysis"
OUTPUT_ROOT = ANALYSIS_ROOT / "output"
