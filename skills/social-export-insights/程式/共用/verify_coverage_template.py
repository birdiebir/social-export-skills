"""
驗證群組/聯絡人全量通讀的涵蓋率是否為 100%。

用法:
    python verify_coverage.py <messages_full.jsonl 路徑> <coverage.json 路徑>
    python verify_coverage.py --self-test        # 用虛構資料跑自我測試

檢查邏輯（依 coverage.json 提供的資訊，由強到弱）:
    A. 有「實際讀取清單」→ 核對清單本身（2026-10-01 新增，優先使用）
       - 頂層 `read_seqs`（seq 整數或 [起, 迄] 區間的清單），或
       - `batches[].seq_range: [起, 迄]`（每批實際讀的 seq 區間，含頭尾）
       讀取清單的聯集必須「剛好等於」來源 jsonl 的全部 seq：漏讀、重複讀（批次重疊）、
       清單裡有來源沒有的 seq，都判 FAIL。來源沒有 seq 欄位時，用 1 起算的行號。
    B. 只有 `batches[].period`（YYYY-MM）→ 用來源 jsonl 的日期重算每個月的實際則數，
       逐批比對；來源裡有、批次沒列到的月份，或同一個月列兩次，都判 FAIL。
    C. 只有數字 → 舊的數字比對（總數＝來源行數、batches 加總＝messages_read、
       messages_read＝來源行數），並印出 WARN：這是推斷式檢查，抓不到「重讀 A 段、
       漏讀 B 段但總數剛好相等」這種情況。

    為什麼要核對清單而不是只比數字：專案曾經用推斷規則判定「讀過」，結果被截斷檔名的
    整串對話根本沒解析，覆蓋檢查和回歸測試卻都 PASS（見 social-export-analysis 的
    references\\pitfalls.md B1）。數字相等不代表讀的是對的那幾則。

coverage.json 範例:

格式一（群組模組，有 batches[] 明細；建議每批附 seq_range）:
{
  "target": "群組或聯絡人名稱",
  "total_messages": 1733,
  "messages_read": 1733,
  "coverage_pct": 100.0,
  "batches": [
    {"period": "2018-01", "message_count": 823, "seq_range": [1, 823]},
    {"period": "2018-02", "message_count": 910, "seq_range": [824, 1733]}
  ],
  "generated_at": "2026-09-15T00:00:00"
}

格式二（relationships 模組，扁平格式，無 batches；可附 read_seqs）:
{
  "target": "聯絡人名稱",
  "messages_total": 266,
  "messages_read": 266,
  "read_seqs": [[1, 266]],
  "method": "全量通讀，單一 agent 一次讀完",
  "generated": "2026-09-18"
}

讀來源 jsonl 一律逐行迭代檔案，不用 str.splitlines()：訊息內文可能含 U+2028，
splitlines 會把一筆紀錄切成兩行，行數就錯了。
"""
import io
import json
import sys
from collections import Counter

# See verify_quotes.py for why this is needed on Windows consoles.
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def load_source(path):
    """回傳 [(seq, 月份 'YYYY-MM' 或 None)]。逐行讀（U+2028 安全）。"""
    out = []
    with open(path, encoding="utf-8") as f:
        n = 0
        for line in f:
            if not line.strip():
                continue
            n += 1
            rec = json.loads(line)
            dt = rec.get("datetime") or rec.get("dt") or rec.get("date") or ""
            out.append((rec.get("seq", n), dt[:7] if len(dt) >= 7 else None))
    return out


def _expand(items):
    """[3, [5, 7]] → [3, 5, 6, 7]（保留重複，才抓得到重疊）。"""
    seqs = []
    for it in items:
        if isinstance(it, (list, tuple)):
            a, b = it
            seqs.extend(range(int(a), int(b) + 1))
        else:
            seqs.append(int(it))
    return seqs


def read_list_of(coverage):
    """coverage.json 裡的實際讀取清單（展開成 seq 清單）；沒有就回傳 None。"""
    if "read_seqs" in coverage:
        return _expand(coverage["read_seqs"])
    batches = coverage.get("batches") or []
    if batches and all("seq_range" in b for b in batches):
        return _expand([b["seq_range"] for b in batches])
    return None


def check(source, coverage):
    """回傳 (errors, warnings, mode)。source 是 load_source() 的結果。"""
    errors, warnings = [], []
    total = len(source)
    reported_total = coverage.get("total_messages", coverage.get("messages_total"))
    reported_read = coverage.get("messages_read")

    if reported_total is not None and reported_total != total:
        errors.append(f"coverage.json 的 total_messages/messages_total ({reported_total}) 與來源檔案實際行數 ({total}) 不一致")

    read = read_list_of(coverage)
    if read is not None:
        mode = "read_list"
        src = {s for s, _ in source}
        cnt = Counter(read)
        dup = sorted(s for s, c in cnt.items() if c > 1)
        missing = sorted(src - set(cnt))
        extra = sorted(set(cnt) - src)
        if missing:
            errors.append(f"讀取清單漏了 {len(missing)} 則（例：seq {missing[:5]}）")
        if dup:
            errors.append(f"讀取清單重複 {len(dup)} 則，批次可能重疊（例：seq {dup[:5]}）")
        if extra:
            errors.append(f"讀取清單有 {len(extra)} 個來源沒有的 seq（例：{extra[:5]}），清單可能對錯檔")
        if reported_read is not None and reported_read != len(set(cnt) & src):
            errors.append(f"messages_read ({reported_read}) 與讀取清單實際涵蓋的則數 ({len(set(cnt) & src)}) 不一致")
        return errors, warnings, mode

    batches = coverage.get("batches")
    if batches and all("period" in b for b in batches):
        mode = "period"
        actual = Counter(m for _, m in source)
        periods = Counter(b["period"] for b in batches)
        for p, c in periods.items():
            if c > 1:
                errors.append(f"月份 {p} 在 batches 裡出現 {c} 次")
        covered_all = set()
        for b in batches:
            p = b["period"]
            # 「2019-03..2019-05」這種跨月批次：加總區間內每個月
            if ".." in p:
                a, z = p.split("..")
                covered = {k for k in actual if k and a <= k <= z}
            else:
                covered = {p}
            want = sum(actual.get(k, 0) for k in covered)
            if b["message_count"] != want:
                errors.append(f"批次 {p} 宣稱 {b['message_count']} 則，來源實際 {want} 則")
            covered_all |= covered
        uncovered = sorted(k for k in actual if k and k not in covered_all)
        if uncovered:
            errors.append(f"來源有、batches 沒列到的月份：{uncovered[:6]}")
        if reported_read is not None and reported_read != total:
            errors.append(f"涵蓋率未達 100%：實際讀取 {reported_read} / 總數 {total}")
        return errors, warnings, mode

    mode = "count_only"
    warnings.append("coverage.json 沒有讀取清單（read_seqs／batches[].seq_range）也沒有逐月批次，"
                    "只能比對數字：抓不到「重讀 A 段、漏讀 B 段但總數相等」。之後請在 coverage.json 記下每批實際讀的 seq 區間。")
    if batches:
        batch_sum = sum(b["message_count"] for b in batches)
        if batch_sum != reported_read:
            errors.append(f"batches 加總 ({batch_sum}) 與 messages_read ({reported_read}) 不一致，可能有批次重複或漏批")
    if reported_read != total:
        pct = round((reported_read or 0) / total * 100, 2) if total else 0.0
        errors.append(f"涵蓋率未達 100%：實際讀取 {reported_read} / 總數 {total}（{pct}%）")
    return errors, warnings, mode


def main():
    if len(sys.argv) != 3:
        print("用法: python verify_coverage.py <messages_full.jsonl> <coverage.json>")
        sys.exit(2)
    jsonl_path, coverage_path = sys.argv[1], sys.argv[2]
    source = load_source(jsonl_path)
    with open(coverage_path, encoding="utf-8") as f:
        coverage = json.load(f)
    errors, warnings, mode = check(source, coverage)
    target = coverage.get("target", coverage_path)
    for w in warnings:
        print(f"[WARN] {target}：{w}")
    if errors:
        print(f"[FAIL] {target}（檢查方式：{mode}）")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print(f"[PASS] {target}：涵蓋率 100%（{len(source)} 則，檢查方式：{mode}）")
    sys.exit(0)


def _self_test():
    """虛構資料：3 個月、6 則。"""
    import os
    import tempfile
    rows = [("2019-01-05T10:00:00", "line still one record"), ("2019-01-06T10:00:00", "b"),
            ("2019-02-01T10:00:00", "c"), ("2019-02-02T10:00:00", "d"),
            ("2019-03-01T10:00:00", "e"), ("2019-03-09T10:00:00", "f")]
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for i, (dt, text) in enumerate(rows, 1):
            f.write(json.dumps({"seq": i, "datetime": dt, "sender": "Person A", "text": text}, ensure_ascii=False) + "\n")
    try:
        src = load_source(path)
        assert len(src) == 6, src                                         # U+2028 沒有把一筆切成兩筆

        ok = {"target": "t", "total_messages": 6, "messages_read": 6,
              "batches": [{"period": "2019-01", "message_count": 2, "seq_range": [1, 2]},
                          {"period": "2019-02", "message_count": 2, "seq_range": [3, 4]},
                          {"period": "2019-03", "message_count": 2, "seq_range": [5, 6]}]}
        assert check(src, ok)[0] == [] and check(src, ok)[2] == "read_list"

        # 數字全對，但第二批其實重讀了第一批、漏了 3-4：舊的數字比對會 PASS，讀取清單要 FAIL
        sneaky = json.loads(json.dumps(ok))
        sneaky["batches"][1]["seq_range"] = [1, 2]
        errs = check(src, sneaky)[0]
        assert any("漏了 2 則" in e for e in errs) and any("重複" in e for e in errs), errs
        no_list = json.loads(json.dumps(sneaky))
        for b in no_list["batches"]:
            b.pop("seq_range")
            b.pop("period")
        e2, w2, m2 = check(src, no_list)
        assert e2 == [] and m2 == "count_only" and w2, (e2, w2)          # 推斷式檢查抓不到，只能警告

        # 逐月批次：宣稱數字跟來源對不上、漏月份
        per = {"target": "t", "total_messages": 6, "messages_read": 6,
               "batches": [{"period": "2019-01", "message_count": 2}, {"period": "2019-02", "message_count": 4}]}
        errs = check(src, per)[0]
        assert any("2019-02" in e and "實際 2" in e for e in errs) and any("2019-03" in e for e in errs), errs
        span = {"target": "t", "total_messages": 6, "messages_read": 6,
                "batches": [{"period": "2019-01..2019-03", "message_count": 6}]}
        assert check(src, span)[0] == []

        # 扁平格式＋read_seqs
        flat = {"target": "t", "messages_total": 6, "messages_read": 6, "read_seqs": [[1, 5], 6]}
        assert check(src, flat)[0] == []
        flat_bad = {"target": "t", "messages_total": 6, "messages_read": 6, "read_seqs": [[1, 5], 9]}
        errs = check(src, flat_bad)[0]
        assert any("漏了 1 則" in e for e in errs) and any("來源沒有" in e for e in errs), errs
    finally:
        os.remove(path)
    print("verify_coverage self-test: PASS")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        _self_test()
    else:
        main()
