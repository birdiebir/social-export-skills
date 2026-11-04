# -*- coding: utf-8 -*-
r"""notes 個資掃描（範本；2026-10 從一個實際專案移植並去識別化）：電話、Email、身分證字號、門牌地址、銀行帳號格式。

為什麼需要：AI 寫的質化筆記會把私訊裡的第三方電話、Email、地址原樣抄進正文或語錄。
機械語錄驗證不會擋這件事，所以要另外掃描，並把結果接進專案的 verify（先 WARN，規則穩定後再升級成 FAIL）。

用途：
- verify：掃全部 notes（不含 ``_superseded``），只印 WARN 筆數與「檔名、行號、類別」，不印命中的原文。
- 遮罩腳本（建議另寫，預設 dry-run）：照這裡的規則遮。引號外換成（電話略）這類字樣；引文裡的個資換成「…」
  （其餘仍逐字，strict 驗證照過）；整個引號只有個資就整段換字樣；結構化語錄整句只有個資就刪整筆。
  遮罩前先把舊版存 ``_superseded``（舊版本身也要遮）；讀寫用位元組原樣處理，避免 Windows 把 LF 改成 CRLF。

規則：
- 電話、Email、身分證字號、銀行帳號：一律算個資（本人的也算；要保留本人的，另外在 private 豁免）。
- 地址：預設算個資；``private/<SELF_ADDR_FILE>``（不進 git）登記過、使用者確認是本人的地址不算。
- 銀行帳號只認「帳號／帳戶／匯款／轉帳／銀行／BSB…」後面 12 字內的 10～16 位數字（含 - 和空白），避免把 thread id、seq 誤判成帳號。
- 電話樣式由檔頭 ``COUNTRIES`` 決定（預設只開 TW；AU 規則保留、預設關閉，依需要加入國家）；並跟頁面遮罩（PR 頁）用同一組樣式。
- 常見誤判：把 thread id、檔名裡的長數字當成電話。``_NB``／``_NA`` 前後界已擋大部分；遮罩後要抽查 id 有沒有被誤遮。
測試只能用虛構資料（連街名都不要用真的）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_D = "[0-9０-９]"
_DC = "0-9０-９"
_S = "[-－ ]?"
_NB = r"(?<![0-9０-９A-Za-z_/=.%\-#])"      # 前面不是英數字／網址字元（避免吃到網址或 id 裡的數字）
_NA = r"(?![0-9０-９A-Za-z_]|\.html?)"       # 後面不是英數字（避免吃到 sha256、id 裡的一段數字）

# 電話樣式的國家清單：依需要加入國家（各國規則在 _PHONE_RULES，要新增就照格式補一條）。預設只開台灣。
COUNTRIES = ["TW"]

_PHONE_RULES: dict[str, list[str]] = {
    "TW": [
        rf"(?:\+?886{_S}|[0０])[9９]{_D}{{2}}{_S}{_D}{{3}}{_S}{_D}{{3}}",                      # 台灣手機
        rf"\(?[0０][2-8２-８]{_D}?\)?{_S}{_D}{{3,4}}{_S}{_D}{{4}}",                            # 台灣市話
    ],
    "AU": [  # 預設關閉；要用就把 "AU" 加進 COUNTRIES
        rf"(?:\+?61{_S}|[0０])[4４]{_D}{{2}}{_S}{_D}{{3}}{_S}{_D}{{3}}",                       # 澳洲手機
        rf"\(?[0０][2378２３７８]\)?{_S}{_D}{{4}}{_S}{_D}{{4}}",                               # 澳洲市話（02／03／07／08）
        rf"\+61{_S}[2378]{_S}{_D}{{4}}{_S}{_D}{{4}}",                                          # 澳洲市話國際碼
    ],
}


def _phone_pattern() -> re.Pattern:
    alts = [r for c in COUNTRIES for r in _PHONE_RULES[c]]
    return re.compile(_NB + "(?:" + "|".join(alts) + ")" + _NA)


PATTERNS: dict[str, re.Pattern] = {
    "電話": _phone_pattern(),
    "Email": re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    "身分證字號": re.compile(r"(?<![A-Za-z0-9])[A-Z][1289]\d{8}(?![0-9])"),
    "地址": re.compile(
        rf"(?:{_D}{{3,6}})?(?:[一-鿿]{{1,3}}[市縣])?(?:[一-鿿]{{1,3}}[區鄉鎮市])?"
        rf"[一-鿿{_DC}]{{1,8}}?(?:路|街|大道)(?:[一二三四五六七八九十{_DC}]+段)?"
        rf"(?:{_D}+巷)?(?:{_D}+弄)?{_D}+(?:之{_D}+)?號(?:{_D}+(?:樓|[Ff])(?:之{_D}+)?)?"
        r"|\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:St|Street|Rd|Road|Ave|Avenue|Dr|Drive|Pl|Place|Ln|Lane|Blvd|Cres|Ct|Tce|Hwy|Pde)\b\.?"),
    "銀行帳號": re.compile(r"(?:帳號|帳戶|账号|戶頭|匯款|轉帳|轉賬|銀行|郵局|BSB|[Aa]ccount(?: [Nn]o\.?| number)?)"
                       r"[^\n0-9]{0,12}?"
                       r"((?<![0-9A-Za-z_])[0-9](?:[0-9]|[- ](?=[0-9])){9,20}(?![0-9A-Za-z_]))"),
}
_DATE_LIKE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2})?$")


def _bank_ok(frag: str) -> bool:
    """銀行帳號候選的後檢查：10～16 位數字、不是日期（2020-01-31 這類）。"""
    digits = re.sub(r"\D", "", frag)
    return 10 <= len(digits) <= 16 and not _DATE_LIKE.match(frag)
MASK = {"電話": "（電話略）", "Email": "（Email略）", "身分證字號": "（身分證字號略）", "地址": "（地址略）", "銀行帳號": "（帳號略）"}
KINDS = tuple(PATTERNS)

SELF_ADDR_FILE = "self_addresses.yaml"     # 本人地址豁免清單（放 private/，不進 git；跟頁面遮罩共用同一份）
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".jsonl", ".txt", ".csv"}
SKIP_DIRS = {"_superseded"}
# 刻意保留、不遮的位置（相對 notes 的路徑片段；verify 另列「保留」筆數，不算 WARN）。新增前要寫理由並記決策紀錄。
# 下面是虛構的例子：審閱資料要用原文當清理錨點（頁面顯示時才遮）；排除清單的社團名稱本身含廣告電話、是比對鍵。
KEEP_RULES = [
    ("/pr_risk/", "PR 審閱資料要用原文對回 L1、當清理清單錨點；個資只在頁面顯示時遮"),
    ("/group_posts/_exclusions/", "社團名稱是排除比對鍵（名稱本身含廣告電話），遮了排除會失效"),
]


def keep_reason(rel: str) -> str | None:
    """notes 相對路徑落在 KEEP_RULES → 理由；否則 None。"""
    r = "/" + str(rel).replace("\\", "/")
    for frag, why in KEEP_RULES:
        if frag in r:
            return why
    return None


@dataclass(frozen=True)
class Hit:
    kind: str
    start: int
    end: int
    text: str


def norm_addr(s: str) -> str:
    """地址比對用的正規化：去空白、全形英數轉半形、臺→台、大小寫不分（頁面遮罩要用同一個正規化）。"""
    s = "".join(chr(ord(c) - 0xFEE0) if "０" <= c <= "９" or "Ａ" <= c <= "ｚ" else c for c in s or "")
    return "".join(s.split()).replace("臺", "台").lower()


def self_addresses(private_dir: Path | None = None) -> tuple[str, ...]:
    """private/<SELF_ADDR_FILE> 的 self_addresses（只取地址字串）。檔案不存在＝沒有豁免（全部遮，安全預設）。
    private_dir 由呼叫端從專案設定傳入（不要寫死個人路徑）。"""
    if private_dir is None:
        return ()
    p = Path(private_dir) / SELF_ADDR_FILE
    if not p.is_file():
        return ()
    return _read_self(str(p), p.stat().st_mtime_ns)


@lru_cache(maxsize=4)
def _read_self(path: str, _mtime: int) -> tuple[str, ...]:
    import yaml

    out = []
    for it in (yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}).get("self_addresses") or []:
        a = it.get("地址") if isinstance(it, dict) else it
        if a:
            out.append(str(a))
    return tuple(out)


def find(text: str, keep_addresses=()) -> list[Hit]:
    """文字裡的個資位置（不重疊；同一段被多種樣式命中時取先出現、較長的）。登記的本人地址不算。"""
    keep = [k for k in (norm_addr(a) for a in keep_addresses or ()) if k]
    hits: list[Hit] = []
    for kind, pat in PATTERNS.items():
        for m in pat.finditer(text or ""):
            a, b = (m.start(1), m.end(1)) if kind == "銀行帳號" else (m.start(), m.end())
            frag = text[a:b]
            if kind == "銀行帳號" and not _bank_ok(frag):
                continue
            if kind == "地址" and keep:
                n = norm_addr(frag)
                if any(k in n or n in k for k in keep):
                    continue
            hits.append(Hit(kind, a, b, frag))
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    out: list[Hit] = []
    for h in hits:
        if out and h.start < out[-1].end:
            continue
        out.append(h)
    return out


def mask(text: str, keep_addresses=(), repl=None) -> tuple[str, list[Hit]]:
    """把個資換成（電話略）這類字樣；repl(hit) 可自訂替換字串。回傳（新文字, 命中清單）。"""
    hs = find(text, keep_addresses)
    if not hs:
        return text, []
    parts, last = [], 0
    for h in hs:
        parts.append(text[last:h.start])
        parts.append(repl(h) if repl else MASK[h.kind])
        last = h.end
    parts.append(text[last:])
    return "".join(parts), hs


def iter_files(root: Path, include_superseded: bool = False):
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if not include_superseded and SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        yield p


def scan_tree(root: Path, keep_addresses=None, include_superseded: bool = False, private_dir: Path | None = None) -> list[dict]:
    """掃一個資料夾 → [{file（相對 root）, line, kind, kept（KEEP_RULES 理由或 None）}]。
    不回傳命中的原文，方便直接印或存檔。"""
    keep = self_addresses(private_dir) if keep_addresses is None else keep_addresses
    out = []
    for p in iter_files(root, include_superseded):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = str(p.relative_to(root))
        kept = keep_reason(rel)
        for h in find(text, keep):
            out.append({"file": rel, "line": text.count("\n", 0, h.start) + 1, "kind": h.kind, "kept": kept})
    return out


def summarize(rows: list[dict]) -> dict:
    from collections import Counter

    warn = [r for r in rows if not r.get("kept")]
    kept = [r for r in rows if r.get("kept")]
    return {"total": len(warn), "files": len({r["file"] for r in warn}), "by_kind": dict(Counter(r["kind"] for r in warn)),
            "kept": len(kept), "kept_files": len({r["file"] for r in kept})}


def print_warn(rows: list[dict], label: str = "notes") -> None:
    s = summarize(rows)
    kept = f"；刻意保留 {s['kept']} 處（{s['kept_files']} 個檔，KEEP_RULES）" if s["kept"] else ""
    if not s["total"]:
        print(f"[verify --pii] {label}：個資樣式 0 處{kept}")
        return
    kinds = "、".join(f"{k} {v}" for k, v in s["by_kind"].items())
    print(f"[verify --pii] WARN {label}：個資樣式 {s['total']} 處（{s['files']} 個檔；{kinds}）{kept}；目前只警告、不判 FAIL，"
          "明細用 --json（只有檔名、行號、類別）")
