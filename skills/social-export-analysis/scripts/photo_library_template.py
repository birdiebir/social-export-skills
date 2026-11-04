# -*- coding: utf-8 -*-
"""
Template: build a consolidated, browsable media library from a raw export
using NTFS/same-volume hardlinks — zero extra disk, original files never
moved/copied/modified, safe to re-run (idempotent).

This is a GENERALIZED version of a Facebook-export-specific builder — the
parts marked "ADAPT" are where a new project's file layout / HTML parsing
differs. Everything else (hardlink logic, manifest shape, by_person/by_time
dual view, idempotency check, fallback-timestamp handling) is reusable as-is.

Copy to <project>/analysis/scripts/<name>/build_<name>_library.py, then:
  1. Point MEDIA_SOURCES at the raw folders that actually contain media.
  2. Replace index_media_for_source() with logic that maps
     {filename: (sender_or_owner, datetime_or_None)} for your export's format
     (HTML regex parsing for Facebook, JSON walk for Instagram/Takeout, etc).
  3. Adjust the by_person / by_time destination path shapes if your source
     categories differ from "messages" / "posts".

Standard library only.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import RAW_ROOT, DERIVED_ROOT  # noqa: E402

# ---- ADAPT: where the library lands, and where source media lives ----
LIB_NAME = "media_library"  # e.g. "photos_library"
LIB_ROOT = DERIVED_ROOT / LIB_NAME

# List of (category, source_subtype, source_dir) to walk. ADAPT to your export.
MEDIA_SOURCES = [
    # ("messages", "inbox", RAW_ROOT / "messages" / "inbox"),
    # ("posts", "your_posts", RAW_ROOT / "posts" / "media" / "your_posts"),
]


def index_media_for_source(source_dir):
    """ADAPT: return {filename: (sender_or_owner_name, datetime_or_None)} by
    parsing whatever accompanies source_dir's media (an HTML export page, a
    JSON sidecar, EXIF, etc). Return {} if there's nothing to cross-reference
    — files will fall back to filesystem mtime with confidence="fallback-mtime"."""
    return {}


def sanitize(s, max_len=120):
    import re
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len] if s else "unknown"


def link_file(src: Path, dst: Path):
    """Create a hardlink, or report it already exists (same inode) — makes
    re-running the whole builder safe after new source files appear."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    candidate = dst
    n = 1
    src_ino = src.stat().st_ino
    while candidate.exists():
        try:
            if candidate.stat().st_ino == src_ino:
                return candidate, "already-linked"
        except OSError:
            pass
        n += 1
        candidate = dst.with_name(f"{dst.stem}__{n}{dst.suffix}")
    os.link(src, candidate)
    return candidate, "linked"


def rel(p: Path) -> str:
    return str(p.relative_to(LIB_ROOT)).replace("\\", "/")


def process_file(src, category, source_subtype, group_folder, sender, ts, stats, log_lines):
    fname = src.name
    confidence = "html" if ts is not None else "fallback-mtime"
    if ts is None:
        ts = datetime.fromtimestamp(src.stat().st_mtime)
    year, month = ts.year, ts.month

    person_dst = LIB_ROOT / "by_person" / category / source_subtype / sanitize(group_folder) / str(year) / fname
    time_dst = LIB_ROOT / "by_time" / str(year) / f"{month:02d}" / f"{source_subtype}__{sanitize(group_folder)}__{fname}"

    person_path, person_status = link_file(src, person_dst)
    time_path, time_status = link_file(src, time_dst)
    stats[person_status] += 1
    stats[time_status] += 1

    unknown_path = None
    if confidence == "fallback-mtime":
        unk_dst = LIB_ROOT / "unknown" / f"{category}__{source_subtype}__{sanitize(group_folder)}__{fname}"
        unknown_path, unk_status = link_file(src, unk_dst)
        stats[unk_status] += 1
        log_lines.append(f"fallback-mtime: {src}")

    return {
        "new_path_by_person": rel(person_path),
        "new_path_by_time": rel(time_path),
        "new_path_unknown": rel(unknown_path) if unknown_path else None,
        "original_path": str(src.relative_to(RAW_ROOT)).replace("\\", "/"),
        "category": category,
        "source_subtype": source_subtype,
        "group_folder": group_folder,
        "sender_name": sender,
        "timestamp_iso": ts.isoformat() if confidence == "html" else None,
        "confidence": confidence,
        "file_size": src.stat().st_size,
        "file_ext": src.suffix.lower(),
    }


def main():
    import json
    stats = {"linked": 0, "already-linked": 0}
    log_lines = []
    manifest_records = []

    for category, source_subtype, source_dir in MEDIA_SOURCES:
        if not source_dir.exists():
            continue
        index = index_media_for_source(source_dir)
        for f in sorted(p for p in source_dir.iterdir() if p.is_file()):
            sender, ts = index.get(f.name, (None, None))
            rec = process_file(
                f, category, source_subtype, group_folder=source_dir.name,
                sender=sender, ts=ts, stats=stats, log_lines=log_lines,
            )
            manifest_records.append(rec)

    LIB_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = LIB_ROOT / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for rec in manifest_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    log_path = LIB_ROOT / "build_log.txt"
    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"Run summary: {len(manifest_records)} files processed\n")
        f.write(f"linked={stats['linked']} already-linked={stats['already-linked']}\n")
        f.write("\n".join(log_lines) + "\n")

    print(
        f"DONE. total={len(manifest_records)} linked={stats['linked']} "
        f"already-linked={stats['already-linked']}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
