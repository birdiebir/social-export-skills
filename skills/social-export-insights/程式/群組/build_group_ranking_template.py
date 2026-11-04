# -*- coding: utf-8 -*-
"""
群組模組 L2（候選排名/篩選）：從 messages/data/thread_index.json 篩出適合 POC 的
群組對話串。

排除規則（見 config_template.py）：
  - 參與人數超過 MAX_PARTICIPANTS_FOR_POC：課程/廣播型大群組，多數成員從未
    發言，不適合做「每個用戶的分析」。
  - likely_spam（thread_index.json 已算好，沿用既有的 is_likely_spam_thread()
    判斷）：廣告/約會機器人群組。
  - EXCLUDE_GROUP_NAMES：手動排除清單，補上述規則的已知漏網之魚。

過濾後依 message_count 由高到低取前 TOP_N_GROUPS 名。

輸出：
  data/group_ranking.jsonl  -- 全部群組的篩選明細（含排除原因，透明可稽核）
  data/top10.json           -- 選出的 N 組，含 group_slug（與 derived 的媒體
                                資料夾名一致，用 hardlink.thread_folder_name() 算）

複製到專案後另存為 build_group_ranking.py。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import fb_common as fc
from paths import OUTPUT_ROOT
from hardlink import thread_folder_name

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg

THREAD_INDEX_PATH = OUTPUT_ROOT / "messages" / "data" / "thread_index.json"
DATA_DIR = OUTPUT_ROOT / "group_analysis" / "data"


def exclusion_reason(thread_id, meta):
    if not meta.get("is_group"):
        return "not_a_group"
    if meta.get("likely_spam"):
        return "likely_spam"
    if meta.get("name") in cfg.EXCLUDE_GROUP_NAMES:
        return "manually_excluded"
    if meta.get("participant_count", 0) > cfg.MAX_PARTICIPANTS_FOR_POC:
        return "too_many_participants"
    return None


def main():
    thread_index = json.loads(THREAD_INDEX_PATH.read_text(encoding="utf-8"))

    candidates = []
    for thread_id, meta in thread_index.items():
        reason = exclusion_reason(thread_id, meta)
        candidates.append({
            "thread_id": thread_id,
            "name": meta.get("name"),
            "folder": meta.get("folder"),
            "message_count": meta.get("message_count", 0),
            "participant_count": meta.get("participant_count"),
            "first_dt": meta.get("first_dt"),
            "last_dt": meta.get("last_dt"),
            "excluded_reason": reason,
        })

    # 只對「是群組」的候選排序（不含 not_a_group），依訊息量由高到低。
    groups = [c for c in candidates if c["excluded_reason"] != "not_a_group"]
    groups.sort(key=lambda c: -c["message_count"])
    fc.write_jsonl(DATA_DIR / "group_ranking.jsonl", groups)

    selected = [c for c in groups if c["excluded_reason"] is None][: cfg.TOP_N_GROUPS]
    top_n = []
    for rank, c in enumerate(selected, start=1):
        sub, _, conv_dir_name = c["thread_id"].partition("/")
        group_slug = thread_folder_name(c["name"], sub, conv_dir_name)
        top_n.append({**c, "rank": rank, "group_slug": group_slug})
        del top_n[-1]["excluded_reason"]

    (DATA_DIR / "top10.json").write_text(
        json.dumps(top_n, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"DONE. total_groups={len(groups)} selected={len(top_n)} "
          f"(pool after exclusions={sum(1 for c in groups if c['excluded_reason'] is None)})",
          file=sys.stderr)


if __name__ == "__main__":
    main()
