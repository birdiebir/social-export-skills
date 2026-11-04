# Folder layout

Validated on a Facebook export reorganization (`<export_root>\extracted\`, 2026-08).

## Top level: three categories, never mixed

```
<project>/
  raw/          the export exactly as extracted, untouched
  derived/       Claude-organized content a human browses directly
  analysis/      scripts + their output
```

Why three, not two: `raw/` and `analysis/` alone tempts you to put "reorganized but still primary content" (a photo library, a cleaned-up contact list) into `analysis/output/` where it gets buried next to JSONL intermediates the user will never open directly. `derived/` is for things designed to be *browsed*, not just piped into the next script. Even if a project only ever produces one derived thing, use a subfolder (`derived/photos_library/`) rather than letting it BE `derived/` — future derived products (a video library, a cleaned contact export) need somewhere to land without another reorg.

Rename `raw/`'s original top-level folders in place if they weren't under a `raw/` prefix already — on the same filesystem/volume this is a metadata-only rename, not a copy, regardless of how much data is inside. Hardlinks inside `derived/` are unaffected by moving `raw/`'s contents (a hardlink is just another directory entry pointing at the same inode).

## `analysis/`: role-based, not category-based, at the top

```
analysis/
  scripts/
    <category>/   one or more .py files
  output/
    <category>/   their output — same category names as scripts/, so the two trees mirror each other
  lib/
    paths.py       central path config, imported by every script (see paths_template.py)
    <connector>.py  platform-specific parser (e.g. fb_common.py)
    phase0_*.py     sanity/regression checks
```

Do NOT nest scripts and their own output data as siblings inside one category folder (`activity/extract.py` + `activity/data/` in the same dir) — it's the single biggest source of "which of these 40 files is actually code vs. output" confusion once a project has 10+ categories. The `scripts/` vs `output/` split at the top of `analysis/` fixes this once, for every category, instead of per-category.

Cross-topic scripts (joins across categories, final reports, a specific narrow analysis like a single relationship deep-dive) get their own category folder too (`scripts/joins/`, `scripts/reports/`, `scripts/<topic>/`) — don't special-case them into `analysis/` root just because they don't map to one raw-data category.

## Path depth conventions

With every script living at `analysis/scripts/<category>/<file>.py`, the depth from any script to `analysis/lib/` is always exactly 3 parents:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import RAW_ROOT, OUTPUT_ROOT  # etc.
```

This fixed depth is why the scripts/output split is worth doing even for a small project — inconsistent depths (some scripts at `analysis/foo.py`, others at `analysis/bar/baz.py`) force every script to compute its own `sys.path` insert differently, which is a common source of import breakage when files get moved later.
