"""
資料涵蓋率儀表板產生器（範本，2026-09-18 新增，見 `分析\\分層.md`「涵蓋率追蹤」）。

用途：對每個「候選池式」模組（先排名、再挑一批做分析的模組，例如 relationships/
group_analysis/group_posts），計算目前做到多少、還剩多少、做到多深，輸出機器可讀
的 coverage.json（給 AI agent 判斷下一步用）＋人類可讀的 report.html。

**這是範本，不是可以直接執行的通用腳本**——每個專案的候選池欄位名稱、已完成資料夾的
判斷方式、分層規則都不一樣，複製這份範本後，把 MODULES 設定改成符合實際專案的欄位，
並依專案既有的分層定義調整 infer_tier()。

核心洞察（務必保留）：**候選數量佔比會嚴重低估真實覆蓋度，一定要同時算訊息量加權版本**
——只做了候選池 2.8% 的候選數量，可能已經涵蓋了 85% 以上的訊息量，因為分層方法論本來
就是優先做重要/活躍的候選。只呈現數量佔比會讓人誤以為進度嚴重落後。

用法（改完 MODULES 設定後）：
    python build_coverage_dashboard.py
"""
import io
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# 依實際專案調整：每個候選池式模組怎麼讀候選池、怎麼判斷「已完成」、用哪個欄位加權
# ---------------------------------------------------------------------------
MODULES = [
    {
        "name": "relationships",
        "pool_jsonl": "analysis/output/relationships/data/thread_ranking.jsonl",
        "done_dir": "analysis/output/relationships/quant",
        # 已完成資料夾內的中繼資料檔案，用來反查候選池裡的哪一筆——
        # 不要自己對候選名稱做檔案系統安全字元替換去猜資料夾名稱（群組/社團名稱常有
        # 特殊字元、emoji、甚至原始匯出檔本身編碼錯亂，猜資料夾名稱容易誤判或漏算）。
        "match_meta_file": "meta.json",
        "match_field": "thread_id",       # meta.json 裡對應候選池 pool_key_field 的欄位
        "pool_key_field": "thread_id",    # 候選池 jsonl 裡的唯一鍵欄位
        "weight_field": "message_count",  # 用哪個欄位算「訊息量加權覆蓋率」
    },
    # 群組/社團模組依樣新增一筆設定，欄位名稱依實際 jsonl/meta.json 調整
]

# 沒有候選池概念的一次性全量模組（好友清單、個人動態這類），另外用簡單布林/完整度
# 描述，不要硬套候選池百分比公式。
FULL_CORPUS_MODULES = [
    # {"name": "friends_insight", "output_check": "analysis/output/friends_insight/report.html"},
]


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def infer_tier(done_dir_path):
    """依檔案存在與否推斷輕/中/深——沒有 meta.json 裡 tier 欄位時的 fallback。
    優先順序：先看候選自己的 meta.json 有沒有明確 tier 欄位，那個比較權威；
    這個函式只在沒有該欄位的模組上使用。依實際專案的分層定義調整判斷式。"""
    has = lambda name: os.path.exists(os.path.join(done_dir_path, name))
    if has("regression_results.csv") or has("phase_clusters.csv"):
        return "深"
    if has("note.md") or has("group_note.md"):
        return "中"
    return "輕"


def compute_module_coverage(module):
    pool = load_jsonl(module["pool_jsonl"])
    pool_by_key = {r[module["pool_key_field"]]: r for r in pool}

    done_root = module["done_dir"]
    done_keys = set()
    tier_counts = {"輕": 0, "中": 0, "深": 0}

    for entry in os.listdir(done_root):
        meta_path = os.path.join(done_root, entry, module["match_meta_file"])
        if not os.path.exists(meta_path):
            continue  # 只有原始訊息匯出、沒有真正分析產出，不算已完成
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        key = meta.get(module["match_field"])
        if key is None or key not in pool_by_key:
            continue
        done_keys.add(key)
        tier = meta.get("tier") or infer_tier(os.path.join(done_root, entry))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    total_weight = sum(r.get(module["weight_field"], 0) for r in pool)
    done_weight = sum(
        pool_by_key[k].get(module["weight_field"], 0) for k in done_keys
    )

    next_candidates = sorted(
        (r for r in pool if r[module["pool_key_field"]] not in done_keys),
        key=lambda r: -r.get(module["weight_field"], 0),
    )[:10]

    return {
        "module": module["name"],
        "candidate_pool": len(pool),
        "extraction": {"done": len(pool), "pct": 100.0},  # 候選排名本身通常已是全量計算
        "analysis": {
            "count_done": len(done_keys),
            "count_pool": len(pool),
            "pct_by_count": round(100 * len(done_keys) / len(pool), 2) if pool else 0.0,
            "weighted_done": done_weight,
            "weighted_total": total_weight,
            "pct_by_weight": round(100 * done_weight / total_weight, 2) if total_weight else 0.0,
        },
        "tier_counts": tier_counts,
        "next_candidates": [
            {"name": r.get("name", r[module["pool_key_field"]]), module["weight_field"]: r.get(module["weight_field"])}
            for r in next_candidates
        ],
    }


def main():
    results = [compute_module_coverage(m) for m in MODULES]
    for m in FULL_CORPUS_MODULES:
        results.append({
            "module": m["name"],
            "candidate_pool": None,
            "pool_type": "full_corpus",
            "extraction": {"pct": 100.0 if os.path.exists(m["output_check"]) else 0.0},
            "analysis": {"pct_by_count": 100.0 if os.path.exists(m["output_check"]) else 0.0},
        })

    tz = timezone(timedelta(hours=8))
    out = {"generated_at": datetime.now(tz).isoformat(), "modules": results}

    os.makedirs("analysis/output/coverage", exist_ok=True)
    with open("analysis/output/coverage/coverage.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    for r in results:
        if "analysis" in r and "pct_by_weight" in r.get("analysis", {}):
            print(
                f"{r['module']}: 數量 {r['analysis']['count_done']}/{r['analysis']['count_pool']}"
                f"（{r['analysis']['pct_by_count']}%） | 訊息量加權 "
                f"{r['analysis']['pct_by_weight']}%"
            )
    print("[DONE] coverage.json 已產生，report.html 請依專案既有共用樣式另外組頁")


if __name__ == "__main__":
    main()
