"""
驗證 quotes.json / events_narrative.json 裡的逐字語錄與事件證據，
必須真的出現在原始資料裡（防止 LLM 幻覺捏造語錄）。

用法（群組，來源是 messages_full.jsonl）:
    python verify_quotes.py --quotes quotes.json --jsonl messages_full.jsonl

用法（聯絡人，來源是 excerpts/*.md 資料夾）:
    python verify_quotes.py --quotes quotes.json --excerpts-dir notes/<contact>/excerpts

檢查邏輯:
    對 quotes.json 裡每一筆 {speaker, quote, timestamp}：
    - JSONL 來源：找出 sender == speaker 且 datetime 前綴等於 timestamp 的訊息，
      確認該訊息的 text 欄位包含 quote 的內容（去除頭尾空白後做子字串比對）。
    - Markdown 來源：確認 quote 的內容（去除頭尾空白）在任一份 excerpt .md
      檔案的原文中以子字串形式出現。
    找不到就記一筆失敗，最後回報失敗數量；只要有 1 筆失敗，腳本以 exit code 1 結束。
"""
import argparse
import io
import json
import re
import sys
from pathlib import Path

# Windows consoles often default to a legacy codepage (e.g. cp950) that can't
# encode every character in Traditional Chinese contact/group folder names or
# quotes (e.g. "ī"), crashing print() with UnicodeEncodeError even though the
# verification itself succeeded. Force UTF-8 stdout so PASS/FAIL output is
# never the thing that fails.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _normalize_ws(s):
    # Messenger sometimes merges consecutive short lines into one record with
    # literal embedded "\n" characters (e.g. "不好意思\n \n 請問..."). quotes.json
    # commonly flattens these to plain spaces for readability, which used to make
    # a legitimate verbatim quote fail a raw substring match against the source
    # text (false FAIL, not a fabricated-quote signal). Collapse all whitespace
    # runs (including newlines) to a single space on BOTH sides before comparing,
    # so formatting differences don't mask/produce false verification results in
    # either direction. This does NOT forgive paraphrasing, truncation, or
    # cross-message splicing — those still fail because the wording itself differs.
    return re.sub(r"\s+", " ", s).strip()


def load_jsonl_index(jsonl_path):
    index = {}
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            key = (rec["sender"], rec["datetime"])
            index.setdefault(key, []).append(rec["text"])
    return index


def verify_against_jsonl(quotes, jsonl_path):
    index = load_jsonl_index(jsonl_path)
    failures = []
    for i, q in enumerate(quotes):
        speaker, ts, quote = q["speaker"], q["timestamp"], _normalize_ws(q["quote"])
        matched = False
        for (sender, datetime_), texts in index.items():
            if sender == speaker and datetime_.startswith(ts[:16]):
                if any(quote in _normalize_ws(t) for t in texts):
                    matched = True
                    break
        if not matched:
            failures.append(f"第 {i} 筆語錄找不到對應原文：{speaker} @ {ts} 「{quote[:30]}...」")
    return failures


def verify_against_excerpts(quotes, excerpts_dir):
    corpus = _normalize_ws("".join(
        md_file.read_text(encoding="utf-8") for md_file in Path(excerpts_dir).glob("*.md")
    ))
    failures = []
    for i, q in enumerate(quotes):
        quote = _normalize_ws(q["quote"])
        if quote not in corpus:
            failures.append(f"第 {i} 筆語錄找不到對應原文：{q.get('speaker','?')} 「{quote[:30]}...」")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quotes", required=True)
    parser.add_argument("--jsonl")
    parser.add_argument("--excerpts-dir")
    args = parser.parse_args()

    with open(args.quotes, encoding="utf-8") as f:
        quotes = json.load(f)

    if args.jsonl:
        failures = verify_against_jsonl(quotes, args.jsonl)
    elif args.excerpts_dir:
        failures = verify_against_excerpts(quotes, args.excerpts_dir)
    else:
        print("必須指定 --jsonl 或 --excerpts-dir 其中一個來源")
        sys.exit(2)

    if failures:
        print(f"[FAIL] {args.quotes}：{len(failures)} 筆語錄無法對應原文")
        for f_ in failures:
            print(f"  - {f_}")
        sys.exit(1)

    print(f"[PASS] {args.quotes}：全部 {len(quotes)} 筆語錄都能對應到原文出處")
    sys.exit(0)


if __name__ == "__main__":
    main()
