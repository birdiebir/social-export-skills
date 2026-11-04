# -*- coding: utf-8 -*-
"""
關係模組 L2（候選排名）：從 messages/data/thread_index.json 篩出所有合格的 1:1
對話（排除群組、排除疑似垃圾對話、訊息數低於門檻的對話），用多因子公式算重要性
分數，選出前 TOP_N_TOTAL 名，分成 deep/light 兩層，並比對 social/data/friends.jsonl
取得 friend_since。評分公式與權重見 config_template.py／說明.md。

輸出（output/relationships/data/）：
  thread_ranking.jsonl -- 所有合格對話，含完整評分明細（透明可稽核）
  top30.json            -- 選出的前 N 名，含 rank/tier/person_slug/friend_since

可重跑（純 JSON-only，很便宜）：改 config 的權重/門檻後直接重跑即可。
複製到專案的 analysis/scripts/relationships/ 後另存為 build_thread_ranking.py，
config_template.py 另存為 config.py。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from scipy.stats import rankdata

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import fb_common as fc
from paths import OUTPUT_ROOT
from hardlink import thread_folder_name
from name_match import match_two_lists

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg

THREAD_INDEX_PATH = OUTPUT_ROOT / "messages" / "data" / "thread_index.json"
FRIENDS_PATH = OUTPUT_ROOT / "social" / "data" / "friends.jsonl"
OUT_DIR = OUTPUT_ROOT / "relationships" / "data"


def load_jsonl(path):
    out = []
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            out.append(json.loads(line))
    return out


def percentile_rank(values):
    """回傳 0..1 的百分位排名（並列用平均排名），空輸入回傳空list。"""
    if not values:
        return []
    n = len(values)
    if n == 1:
        return [1.0]
    ranks = rankdata(values, method="average")
    return [(r - 1) / (n - 1) for r in ranks]


def main():
    thread_index = json.loads(THREAD_INDEX_PATH.read_text(encoding="utf-8"))
    friends = load_jsonl(FRIENDS_PATH)

    eligible = []
    for thread_id, meta in thread_index.items():
        if meta.get("is_group") or meta.get("likely_spam"):
            continue
        if meta.get("name") in cfg.EXCLUDE_NAMES:
            continue
        if meta.get("message_count", 0) < cfg.MIN_MESSAGE_COUNT_FLOOR:
            continue
        if not meta.get("first_dt") or not meta.get("last_dt"):
            continue
        eligible.append((thread_id, meta))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not eligible:
        print("No eligible 1:1 threads found.", file=sys.stderr)
        fc.write_jsonl(OUT_DIR / "thread_ranking.jsonl", [])
        (OUT_DIR / "top30.json").write_text("[]", encoding="utf-8")
        return

    corpus_max_last_dt = max(datetime.fromisoformat(meta["last_dt"]) for _, meta in eligible)

    rows = []
    for thread_id, meta in eligible:
        first_dt = datetime.fromisoformat(meta["first_dt"])
        last_dt = datetime.fromisoformat(meta["last_dt"])
        span_days = max((last_dt - first_dt).days, cfg.MIN_SPAN_DAYS_FOR_DENSITY)
        recency_days = (corpus_max_last_dt - last_dt).days
        message_count = meta["message_count"]
        density = message_count / span_days
        media_total = sum(meta.get("media_counts", {}).values())
        media_richness = media_total / message_count if message_count else 0.0
        rows.append({
            "thread_id": thread_id, "name": meta["name"], "folder": meta["folder"],
            "message_count": message_count, "span_days": span_days,
            "recency_days": recency_days, "density": density,
            "media_total": media_total, "media_richness": media_richness,
        })

    pct_msg = percentile_rank([r["message_count"] for r in rows])
    pct_span = percentile_rank([r["span_days"] for r in rows])
    pct_rec = percentile_rank([-r["recency_days"] for r in rows])
    pct_dens = percentile_rank([r["density"] for r in rows])
    pct_media = percentile_rank([r["media_richness"] for r in rows])

    for i, r in enumerate(rows):
        r["pct_message_count"] = pct_msg[i]
        r["pct_span_days"] = pct_span[i]
        r["pct_recency"] = pct_rec[i]
        r["pct_density"] = pct_dens[i]
        r["pct_media_richness"] = pct_media[i]
        r["importance_score"] = 100 * (
            cfg.WEIGHTS["message_count"] * pct_msg[i]
            + cfg.WEIGHTS["span_days"] * pct_span[i]
            + cfg.WEIGHTS["recency"] * pct_rec[i]
            + cfg.WEIGHTS["density"] * pct_dens[i]
            + cfg.WEIGHTS["media_richness"] * pct_media[i]
        )

    rows.sort(key=lambda r: -r["importance_score"])

    # 身份／好友核對：沿用 messages 領域既有的姓名比對模式（L3 紀律）。
    contacts = []
    for r in rows:
        sub, _, conv_dir_name = r["thread_id"].partition("/")
        contacts.append({"header": r["name"], "thread_id": r["thread_id"],
                          "sub": sub, "conv_dir_name": conv_dir_name})
    confident, ambiguous, _only_c, _only_f = match_two_lists(contacts, friends)
    friend_since_by_thread = {c["a"]["thread_id"]: c["b"].get("timestamp") for c in confident}
    ambiguous_names = {a["name"] for a in ambiguous}

    fc.write_jsonl(OUT_DIR / "thread_ranking.jsonl", rows)

    top = rows[: cfg.TOP_N_TOTAL]
    top30 = []
    for rank, r in enumerate(top, start=1):
        sub, _, conv_dir_name = r["thread_id"].partition("/")
        person_slug = thread_folder_name(r["name"], sub, conv_dir_name)
        friend_since_raw = friend_since_by_thread.get(r["thread_id"])
        friend_since = None
        if friend_since_raw:
            parsed = fc.parse_ts(friend_since_raw)
            friend_since = parsed.strftime("%Y-%m-%d") if parsed else friend_since_raw
        if friend_since:
            match_status = "confident"
        elif r["name"] in ambiguous_names:
            match_status = "ambiguous"
        else:
            match_status = "not_found"
        top30.append({
            **r,
            "rank": rank,
            "tier": "deep" if rank <= cfg.TOP_N_DEEP else "light",
            "person_slug": person_slug,
            "friend_since": friend_since,
            "friend_match_status": match_status,
        })

    (OUT_DIR / "top30.json").write_text(
        json.dumps(top30, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    n_deep = sum(1 for t in top30 if t["tier"] == "deep")
    n_light = sum(1 for t in top30 if t["tier"] == "light")
    print(f"DONE. eligible={len(rows)} selected={len(top30)} deep={n_deep} light={n_light}")
    print(f"wrote {OUT_DIR / 'thread_ranking.jsonl'}")
    print(f"wrote {OUT_DIR / 'top30.json'}")


if __name__ == "__main__":
    main()
