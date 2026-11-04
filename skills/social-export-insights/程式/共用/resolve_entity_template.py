# -*- coding: utf-8 -*-
"""
共用工具（跨模組）：把自然語言問題裡提到的名稱，解析成 thread_index.json 裡的一個
具體對象（thread_id + name），供隨選執行（見 分析\\問答.md）在跑任何 pipeline
之前先確定「使用者問的到底是誰」。

設計原則沿用 L3 join 的姓名比對哲學（analysis/lib/name_match.py）：只有唯一、有
把握的匹配才靜默採用；有歧義一律列出候選讓使用者選，不要猜。這裡的比對比
name_match.match_two_lists() 寬鬆（模糊/包含比對，不要求兩份清單都唯一），因為
這裡只有一份輸入（使用者打的名稱字串），不是結構化的雙清單 join。

複製到專案的 analysis/lib/ 後，把 sys.path.insert 那行的相對深度依實際擺放位置
調整（跟其他 analysis/lib/*.py 保持一致）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import OUTPUT_ROOT  # noqa: E402

THREAD_INDEX_PATH = OUTPUT_ROOT / "messages" / "data" / "thread_index.json"


def _normalize(s):
    return (s or "").strip().lower().replace(" ", "")


def resolve(query, want_group=None, limit=8):
    """依名稱字串在 thread_index.json 找候選對象。

    query: 使用者輸入的名稱片段（不需要完全比對，子字串即可）。
    want_group: True 只找群組、False 只找 1:1 對話、None 兩者都找
                （依呼叫模組決定，例如「關係」模組傳 False、「群組」模組傳 True）。
    回傳: 依 message_count 由高到低排序的候選 list，每筆含
          thread_id/name/message_count/first_dt/last_dt/is_group。
          呼叫端規則：
            - 0 筆 -> 找不到，如實告知使用者，不要憑空回答。
            - 1 筆 -> 視為唯一匹配，直接採用。
            - 2 筆以上 -> 列出候選（名稱/訊息量/時間範圍）請使用者選，
                          絕不靜默選 message_count 最高的那個。
    """
    thread_index = json.loads(THREAD_INDEX_PATH.read_text(encoding="utf-8"))
    q = _normalize(query)
    if not q:
        return []

    candidates = []
    for thread_id, meta in thread_index.items():
        if want_group is not None and bool(meta.get("is_group")) != want_group:
            continue
        name = meta.get("name") or ""
        if q in _normalize(name):
            candidates.append({
                "thread_id": thread_id,
                "name": name,
                "message_count": meta.get("message_count", 0),
                "first_dt": meta.get("first_dt"),
                "last_dt": meta.get("last_dt"),
                "is_group": bool(meta.get("is_group")),
            })

    candidates.sort(key=lambda c: -c["message_count"])
    return candidates[:limit]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: resolve_entity_template.py <name-substring> [--group|--person]", file=sys.stderr)
        sys.exit(1)
    query = sys.argv[1]
    want_group = None
    if "--group" in sys.argv:
        want_group = True
    elif "--person" in sys.argv:
        want_group = False
    for c in resolve(query, want_group=want_group):
        print(f"{c['message_count']:>6}  {c['name']}  ({c['thread_id']})")
