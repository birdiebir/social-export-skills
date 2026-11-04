# -*- coding: utf-8 -*-
"""
風險模組：把候選清單收斂成一份人類可讀、按嚴重度分組排序的最終 markdown 報告，
方便使用者逐項決定要不要刪除/設為私人。

**優先使用 L5 判讀結果**（data/reviewed.jsonl，見 範本\審閱判讀.md／範本\筆記格式.md）
依 assessed_severity 分組——這是真正讀過內容判斷的結果，不是關鍵字命中類別。

data/reviewed.jsonl 不存在時，優雅降級成依 flagged_candidates.jsonl 的
matched_categories 關鍵字命中類別分組（config.SEVERITY_ORDER 查表排序），並在
報告開頭註明目前是降級模式、尚未經過質性審閱——不要讓使用者誤以為這已經是
最終判讀結果。

輸入：pr_risk/data/reviewed.jsonl（優先）或 flagged_candidates.jsonl（降級）
輸出：pr_risk/data/final_report.md
複製到專案後另存為 finalize_pr_risk_report.py。
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import OUTPUT_ROOT

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg

DATA_DIR = OUTPUT_ROOT / "pr_risk" / "data"
REVIEWED_PATH = DATA_DIR / "reviewed.jsonl"
FLAGGED_PATH = DATA_DIR / "flagged_candidates.jsonl"
OUT_PATH = DATA_DIR / "final_report.md"


def load_jsonl(path):
    if not path.exists():
        return []
    # 逐行讀檔，不用 str.splitlines()：訊息內文可能含 U+2028／U+2029，splitlines 會把它當換行，
    # 一筆 JSONL 被切成兩段壞掉的行（見 social-export-analysis 的 references\pitfalls.md A9）。
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    reviewed = load_jsonl(REVIEWED_PATH)

    if reviewed:
        mode = "reviewed"
        by_severity = defaultdict(list)
        for r in reviewed:
            by_severity[r.get("assessed_severity", "未分類")].append(r)
        # 嚴重度分組順序沿用 config.SEVERITY_ORDER 的標籤（若 assessed_severity
        # 用同一套詞彙），未知類別排在最後。
        ordered_keys = [k for k in cfg.SEVERITY_ORDER if k in by_severity] + \
                       sorted([k for k in by_severity if k not in cfg.SEVERITY_ORDER])
        total = len(reviewed)
    else:
        mode = "degraded"
        flagged = load_jsonl(FLAGGED_PATH)
        if not flagged:
            print(f"找不到 {REVIEWED_PATH} 也找不到 {FLAGGED_PATH}，"
                  f"請先跑 flag_candidates_template.py", file=sys.stderr)
            return
        by_severity = defaultdict(list)
        for r in flagged:
            matched = r.get("matched_categories") or ["未分類"]
            primary = next((s for s in cfg.SEVERITY_ORDER if s in matched), matched[0])
            by_severity[primary].append(r)
        ordered_keys = [k for k in cfg.SEVERITY_ORDER if k in by_severity] + \
                       [k for k in by_severity if k not in cfg.SEVERITY_ORDER]
        total = len(flagged)

    lines = ["# PR 風險候選清單 — 最終報告\n"]
    if mode == "degraded":
        lines.append(
            "> **降級模式**：`reviewed.jsonl` 不存在，以下僅依關鍵字命中類別粗略分組，"
            "**尚未經過質性審閱**，不代表真正的風險程度。請先走 說明.md 的第 2 步"
            "（範本\\審閱判讀.md）產生 reviewed.jsonl，再重跑本腳本取得真正判讀過的報告。\n"
        )
    lines.append(f"來源：{'reviewed.jsonl（已質性審閱）' if mode == 'reviewed' else 'flagged_candidates.jsonl（僅關鍵字命中，未審閱）'}"
                 f"（共 {total} 筆）\n")
    lines.append(
        "> 這份清單僅供你快速掃過、自行判斷要不要刪除或設為私人——"
        "**任何刪除/設為私人的動作都需要你自己手動執行**，本流程不具備瀏覽器自動化或 FB API 存取權限。\n"
    )

    lines.append("## 目錄\n")
    for k in ordered_keys:
        label = cfg.SEVERITY_LABEL.get(k, k)
        lines.append(f"- [{label}（{k}）](#{k}) — {len(by_severity[k])} 筆")
    lines.append("")

    for k in ordered_keys:
        label = cfg.SEVERITY_LABEL.get(k, k)
        items = sorted(by_severity[k], key=lambda r: r.get("timestamp", ""))
        lines.append(f"\n## {label}（{k}） {{#{k}}}\n")
        for r in items:
            cat = cfg.CATEGORY_LABEL.get(r.get("category"), r.get("category", "?"))
            ts = r.get("timestamp", "?")
            header = r.get("header", "")
            text = (r.get("text") or "").replace("\n", " ")
            if len(text) > 200:
                text = text[:200] + "…"
            url = r.get("url", "")
            lines.append(f"- **[{cat}] {ts}** — {header}")
            if mode == "reviewed" and r.get("rationale"):
                lines.append(f"  - 判讀：{r['rationale']}")
                if r.get("recommended_action"):
                    lines.append(f"  - 建議：{r['recommended_action']}")
            if text:
                lines.append(f"  > {text}")
            if url:
                lines.append(f"  ({url[:80]}...)" if len(url) > 80 else f"  ({url})")

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"DONE ({mode}). {total} 筆分成 {len(by_severity)} 類，寫入 {OUT_PATH}")
    for k in ordered_keys:
        print(f"  {cfg.SEVERITY_LABEL.get(k, k)}: {len(by_severity[k])}")


if __name__ == "__main__":
    main()
