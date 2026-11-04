# -*- coding: utf-8 -*-
"""
關係模組：對 top30.json（或隨選問答時單一目標）選出的每個對話串，逐一用
fb_common.iter_messages() 掃描該對話串底下的 message_N.html，輸出一份
per-person 的訊息串流 messages_full.jsonl，供 build_features_template.py／
build_reading_excerpts_template.py 沿用。

只掃選中的對話串（而非全部候選），成本可控，可安全重跑。

**2026-10-01 同步修正**（見 `social-export-analysis` 的 `references/pitfalls.md` A1、A6）：
- 訊息檔清單改用 `fb_common.find_message_files()`：路徑太長時 Meta 會把檔名截成
  `message.html`、`mes.html`、甚至 `.html`，舊寫法只認 `message_` 開頭，會整串漏讀且不報錯。
- 新版 `fb_common.iter_messages()` 會把沒有發言者的內嵌 section 切成 `sender=None`、
  `type="system"` 的紀錄。這份語料只收有發言者的訊息（`build_features_template.py`
  用 sender 判斷 self/other，None 會被算成對方），system 筆數另外印出來。

複製到專案後另存為 build_person_corpus.py（需要已同步上述修正的 fb_common.py）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import fb_common as fc
from paths import PROJECT_ROOT, OUTPUT_ROOT

TOP30_PATH = OUTPUT_ROOT / "relationships" / "data" / "top30.json"
QUANT_DIR = OUTPUT_ROOT / "relationships" / "quant"


def build_corpus_for_person(entry):
    thread_dir = PROJECT_ROOT / entry["folder"]
    out_path = QUANT_DIR / entry["person_slug"] / "messages_full.jsonl"

    msgs = []
    for mf in fc.find_message_files(thread_dir):   # 含被截斷的檔名，依頁碼排序
        try:
            msgs.extend(fc.iter_messages(mf))
        except OSError:
            continue
    msgs.sort(key=lambda m: m["dt"])
    system_count = sum(1 for m in msgs if m["sender"] is None)
    msgs = [m for m in msgs if m["sender"] is not None]
    if system_count:
        print(f"    （略過 {system_count} 筆無發言者的 system 紀錄）", file=sys.stderr)

    records = [
        {
            "datetime": m["dt"].isoformat(),
            "date": m["dt"].strftime("%Y-%m-%d"),
            "time": m["dt"].strftime("%H:%M:%S"),
            "sender": m["sender"],
            "type": m["type"],
            "text": m["text"],
            "media_path": m["media_path"],
        }
        for m in msgs
    ]
    fc.write_jsonl(out_path, records)
    return len(records)


def main():
    """批次全量跑法：處理 top30.json 裡所有人。隨選問答單一對象時，改呼叫
    build_corpus_for_person() 傳入該對象的 entry dict 即可，不必跑整份 top30。"""
    top30 = json.loads(TOP30_PATH.read_text(encoding="utf-8"))
    for entry in top30:
        n = build_corpus_for_person(entry)
        print(f"[{entry['rank']:>2}] {entry['name']} ({entry['tier']}): {n} messages -> {entry['person_slug']}")


if __name__ == "__main__":
    main()
