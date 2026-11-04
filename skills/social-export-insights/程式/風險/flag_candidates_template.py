# -*- coding: utf-8 -*-
"""
風險模組 L2（候選篩選）：對 posts.jsonl / comments.jsonl / group_activity.jsonl
做關鍵字/正則預篩，篩出候選給後續質性審閱，另外對「沒命中」的內容做分層隨機
抽樣（抓關鍵字漏掉的部分，見 分析\踩坑.md 第 14 條）。

這一步只做預篩，不做真正的風險判斷——「命中關鍵字」不等於「真的有問題」，
真正的判讀在下一步（範本\審閱判讀.md，見 說明.md）。

標準函式庫優先。複製到專案後另存為 flag_candidates.py，config_template.py
另存為 config.py。
"""
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import OUTPUT_ROOT

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg

DATA_DIR = OUTPUT_ROOT / "pr_risk" / "data"


def compile_group_re(words):
    return re.compile("|".join(re.escape(w) for w in words))


COMPILED = {g: compile_group_re(ws) for g, ws in cfg.KEYWORD_GROUPS.items()}


def year_of(ts):
    m = re.search(r'(\d{4})', ts or "")
    return m.group(1) if m else "unknown"


def main():
    flagged = []
    all_by_year = defaultdict(list)

    for cat in cfg.TEXT_CATEGORIES:
        path = DATA_DIR / f"{cat}.jsonl"
        if not path.exists():
            continue
        # 逐行讀檔，不用 str.splitlines()：訊息內文可能含 U+2028，splitlines 會把一筆切成兩段
        # （見 social-export-analysis 的 references\pitfalls.md A9）。
        with path.open(encoding="utf-8") as fh:
            lines = [ln for ln in fh if ln.strip()]
        for line in lines:
            rec = json.loads(line)
            text = (rec.get("text") or "") + " " + (rec.get("header") or "")
            if not text.strip():
                continue
            hits = [g for g, rx in COMPILED.items() if rx.search(text)]
            if cfg.PII_PATTERN_RE.search(text):
                hits.append("pii_pattern")
            yr = year_of(rec.get("timestamp"))
            all_by_year[yr].append(rec)
            if hits:
                flagged.append({**rec, "matched_categories": hits})

    out_path = DATA_DIR / "flagged_candidates.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for rec in flagged:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # stratified sample of unflagged content by year, for the review step to
    # spot-check what the keyword list missed (sarcasm, coded language, etc.)
    random.seed(42)
    flagged_keys = {(r["category"], r["source_file"], r["seq"]) for r in flagged}
    sample = []
    for yr, recs in sorted(all_by_year.items()):
        unflagged = [r for r in recs if (r["category"], r["source_file"], r["seq"]) not in flagged_keys and r.get("text")]
        k = min(cfg.STRATIFIED_SAMPLE_PER_YEAR, len(unflagged))
        sample.extend(random.sample(unflagged, k))

    sample_path = DATA_DIR / "unflagged_sample.jsonl"
    with sample_path.open("w", encoding="utf-8") as f:
        for rec in sample:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"flagged: {len(flagged)} / scanned: {sum(len(v) for v in all_by_year.values())}")
    print(f"unflagged_sample: {len(sample)}")
    by_group = defaultdict(int)
    for r in flagged:
        for g in r["matched_categories"]:
            by_group[g] += 1
    for g, c in sorted(by_group.items(), key=lambda x: -x[1]):
        print(f"  {g}: {c}")


if __name__ == "__main__":
    main()
