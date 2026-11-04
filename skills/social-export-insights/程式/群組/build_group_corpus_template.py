# -*- coding: utf-8 -*-
"""
群組模組：對選定的每個群組，逐一用 fb_common.iter_messages() 掃描該對話串底下
全部 message_N.html，輸出一份 per-group 的訊息串流 messages_full.jsonl（全量、
不取樣——群組模組跟關係模組不同，不做輕/深分層取樣，見 說明.md）。

跟 關係模組 build_person_corpus_template.py 幾乎一致，差別是這裡每則訊息額外
跑 fb_common.classify_group_event() 標記系統事件（加入/退出/改名/換照片/設
管理員），供 build_group_features_template.py 的事件時間軸使用。

**已知坑**（見 分析\踩坑.md）：message_N.html 依頁碼由新到舊排列（Facebook
匯出的分頁慣例），逐檔 append 之後務必依時間重新排序——不要以為檔案本身的
頁碼順序就是時間順序，直接用就會把整個對話串的時序讀反。

**2026-10-01 同步修正**（見 `social-export-analysis` 的 `references/pitfalls.md` A1、A6）：
- 訊息檔清單改用 `fb_common.find_message_files()`：路徑太長時 Meta 會把檔名截成
  `message.html`、`mes.html`、甚至 `.html`，舊寫法只認 `message_` 開頭，會整串漏讀且不報錯。
- 新版 `fb_common.iter_messages()` 會把沒有發言者的內嵌 section 切成 `sender=None`、
  `type="system"` 的紀錄（以前被併進前一則的文字和時間）。這份語料只收有發言者的訊息，
  跟 `message_count` 同口徑；system 筆數另外印出來，需要時再另存。

複製到專案後另存為 build_group_corpus.py（需要已同步上述修正的 fb_common.py）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import fb_common as fc
from paths import PROJECT_ROOT, OUTPUT_ROOT

TOP10_PATH = OUTPUT_ROOT / "group_analysis" / "data" / "top10.json"
QUANT_DIR = OUTPUT_ROOT / "group_analysis" / "quant"


def build_corpus_for_group(entry):
    thread_dir = PROJECT_ROOT / entry["folder"]
    out_path = QUANT_DIR / entry["group_slug"] / "messages_full.jsonl"

    msgs = []
    for mf in fc.find_message_files(thread_dir):   # 含被截斷的檔名，依頁碼排序
        try:
            msgs.extend(fc.iter_messages(mf))
        except OSError:
            continue
    msgs.sort(key=lambda m: m["dt"])  # 見上方 docstring：頁碼順序不等於時間順序
    system_count = sum(1 for m in msgs if m["sender"] is None)
    msgs = [m for m in msgs if m["sender"] is not None]
    if system_count:
        print(f"    （略過 {system_count} 筆無發言者的 system 紀錄）", file=sys.stderr)

    records = []
    for m in msgs:
        event = fc.classify_group_event(m["text"]) if m["type"] == "text" else None
        records.append({
            "datetime": m["dt"].isoformat(),
            "date": m["dt"].strftime("%Y-%m-%d"),
            "time": m["dt"].strftime("%H:%M:%S"),
            "sender": m["sender"],
            "type": m["type"],
            "text": m["text"],
            "media_path": m["media_path"],
            "is_event": event is not None,
            "event_type": event["event_type"] if event else None,
            "event_actor": event["actor"] if event else None,
            "event_target": event["target"] if event else None,
        })
    fc.write_jsonl(out_path, records)
    return len(records)


def main():
    top10 = json.loads(TOP10_PATH.read_text(encoding="utf-8"))
    for entry in top10:
        n = build_corpus_for_group(entry)
        print(f"[{entry['rank']:>2}] {entry['name']}: {n} messages -> {entry['group_slug']}")


if __name__ == "__main__":
    main()
