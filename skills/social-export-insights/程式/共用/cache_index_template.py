# -*- coding: utf-8 -*-
"""
共用工具（跨模組）：隨選執行的快取/新鮮度機制（見 分析\\問答.md）。這是整個架構
裡唯一不是照抄現有邏輯的新工程，複製到專案後請認真測試，不要當成其他 template
一樣複製貼上就結束。

索引檔固定放在 output/social_export_insights/cache_index.json，用
"<module>/<target_slug>" 當 key（例如 "relationships/John Doe__inbox__..."），
每個模組共用同一份索引檔，不必各自維護一份。

新鮮度判斷完全基於已經算好的欄位（thread_index.json 的 message_count/last_dt、
範本檔案的 mtime），不重掃原始檔——這正是 L2 候選排名同樣的紀律，快取檢查本身
也要便宜。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import OUTPUT_ROOT  # noqa: E402

CACHE_PATH = OUTPUT_ROOT / "social_export_insights" / "cache_index.json"


def _load():
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def _save(data):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _key(module, target_slug):
    return f"{module}/{target_slug}"


def get_entry(module, target_slug):
    """回傳該對象目前的快取紀錄，沒有就回傳 None。"""
    return _load().get(_key(module, target_slug))


def is_fresh(module, target_slug, current_message_count, current_last_dt, template_paths=()):
    """檢查快取是否還能用。

    template_paths: 這次判讀依賴的範本檔案路徑列表（例如 深季判讀.md）。
    回傳 (fresh: bool, reason: str) —— reason 是 "no_cache" / "data_changed" /
    "template_changed" / "fresh"，呼叫端據此決定要不要重建、要不要提示使用者。
    """
    entry = get_entry(module, target_slug)
    if entry is None:
        return False, "no_cache"

    if entry.get("message_count_at_build") != current_message_count:
        return False, "data_changed"
    if entry.get("last_dt_at_build") != current_last_dt:
        return False, "data_changed"

    cached_versions = entry.get("template_versions", {})
    for p in template_paths:
        p = Path(p)
        if not p.exists():
            continue
        current_mtime = p.stat().st_mtime
        cached_mtime = cached_versions.get(p.name)
        if cached_mtime is None or abs(current_mtime - cached_mtime) > 1e-6:
            return False, "template_changed"

    return True, "fresh"


def update_entry(module, target_slug, *, message_count, last_dt, stage, template_paths=()):
    """某個階段（corpus/features/excerpts/note）建完後更新快取紀錄。

    stage: "corpus_built_at" / "features_built_at" / "excerpts_built_at" /
           "note_written_at" 之一，只更新對應的時間戳欄位，其餘欄位保留。
    """
    data = _load()
    key = _key(module, target_slug)
    entry = data.get(key, {
        "module": module, "target_slug": target_slug,
        "template_versions": {},
    })
    entry["message_count_at_build"] = message_count
    entry["last_dt_at_build"] = last_dt
    entry[stage] = time.strftime("%Y-%m-%dT%H:%M:%S")
    for p in template_paths:
        p = Path(p)
        if p.exists():
            entry.setdefault("template_versions", {})[p.name] = p.stat().st_mtime
    data[key] = entry
    _save(data)
    return entry


if __name__ == "__main__":
    # 手動檢查：python cache_index_template.py <module> <target_slug>
    if len(sys.argv) < 3:
        print("usage: cache_index_template.py <module> <target_slug>", file=sys.stderr)
        sys.exit(1)
    entry = get_entry(sys.argv[1], sys.argv[2])
    print(json.dumps(entry, ensure_ascii=False, indent=2) if entry else "no cache entry")
