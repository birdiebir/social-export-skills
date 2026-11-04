# -*- coding: utf-8 -*-
"""
Template: Phase 0 sanity check + Phase-N regression check skeleton.

Copy to <project>/analysis/lib/_phase0_sanity_check.py and
<project>/analysis/lib/_phase0_regression_check.py (split or keep combined,
your call), then fill in SANITY_SOURCES / REGRESSION_SOURCES for your export.

Run sanity BEFORE scaling a new/changed parser to all files of its template.
Run regression AFTER changing any parser that already has committed output,
to catch silent drift (count changes with no corresponding data change).
"""
import sys
import json
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
# import your_connector as fc          # e.g. fb_common, ig_json_common, ...
from paths import RAW_ROOT, OUTPUT_ROOT  # noqa: E402


# ---- ADAPT: one representative (parser_fn, args, expected_category) per template ----
SANITY_SOURCES = [
    # (fc.parse_timeline, (RAW_ROOT / "some_category" / "some_file.html", "some_category"), None),
]


def run_sanity():
    for parser_fn, args, _ in SANITY_SOURCES:
        result = parser_fn(*args)
        records = result[0] if isinstance(result, tuple) else result
        print(f"\n--- {parser_fn.__name__}{args}: {len(records)} 筆 ---")
        for r in records[:2]:
            print(r)


# ---- ADAPT: (category, output_jsonl_name, parser_fn, args) for regression ----
REGRESSION_SOURCES = [
    # ("some_category", "some_category", fc.parse_timeline,
    #  (RAW_ROOT / "some_category" / "some_file.html", "some_category")),
]


def existing_count(output_subdir, name):
    p = OUTPUT_ROOT / output_subdir / "data" / f"{name}.jsonl"
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as f:
        return sum(1 for _ in f)


def run_regression():
    by_category = Counter()
    for category, output_subdir, parser_fn, args in REGRESSION_SOURCES:
        result = parser_fn(*args)
        records = result[0] if isinstance(result, tuple) else result
        by_category[(category, output_subdir)] += len(records)

    ok = True
    for (category, output_subdir), new_count in by_category.items():
        old_count = existing_count(output_subdir, category)
        status = "OK" if old_count == new_count else "MISMATCH"
        if old_count != new_count:
            ok = False
        print(f"{category}: new={new_count} old={old_count} -> {status}")
    print("\nRESULT:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    run_sanity()
    print("\n" + "=" * 60)
    run_regression()
