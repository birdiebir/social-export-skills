# -*- coding: utf-8 -*-
"""共用 strict 引文驗證器（範本；2026-10 從一個實際專案移植並去識別化）。

用途：任何寫「逐字語錄」的模組（關係、群組、社團貼文、PR 審閱、時間軸出處）共用同一支驗證器，
不要每個模組各寫一套比對規則。比對對象是 L1 的「一則一則紀錄」：訊息串 jsonl（時間欄 ``dt``），
或模組自己組好的紀錄清單（例：社團貼文／留言，時間欄 ``datetime``）。時間要跟 L1 同一個時區。

為什麼需要 strict：舊版驗證只比到「同一分鐘」並先去掉空白，所以全部 PASS；
改成 strict 後在一個專案裡一次抓出數百筆（大多是同一分鐘但秒數抄錯、抄進心情回應尾巴、只差空白）。

strict 規則：
- 引文必須對到**同一則**紀錄：發言者相同、時間吻合；
- 引文用刪節號（``...``／``…``／``⋯``）切成的每個片段，依序都是該則 text 的子字串（空白正規化：所有空白壓成一個空格）；
- 不原諒：改寫、截斷後拼接、跨訊息合併、只差標點或空白、把 L1 尾端的心情回應（「表情＋人名」）抄進引文。
- 時間精度跟著 notes 寫的精度走：notes 寫到秒就比到秒，只寫到分鐘就比到分鐘（``match_entry``）。

``Thread.match`` 回傳的層級（level）：
    strict／placeholder        通過（placeholder＝「*(已收回)*」對 type=unsent）
    reaction                   抄進了心情回應尾巴
    punct                      只差標點或空白
    multi                      一段裡塞了同一發言者的好幾則（跨訊息拼接）
    speaker                    文字對得上，但是別人說的
    time                       同發言者有這句，但時間不符
    fail                       找不到
``refine=True`` 時，``fail`` 再細分（只用於診斷，仍算不通過）：
    elided                     同一則訊息裡挑幾段拼起來、中間沒標刪節號（截斷後拼接）
    paraphrase                 附近有意思很像的訊息，但字不一樣（改寫被當成引文）
    empty                      引文是空的
結果只記層級與 seq，不寫原文（驗證結果檔可能被打包或分享，不要讓它變成私訊副本）。

搭配：
- 回寫工具（建議另寫 ``strict_fix_quotes``）：只處理「可機械修」的三類——補秒數（同一分鐘只有一則候選才改）、
  截掉心情尾巴（``trim_reaction``）、照 L1 抄回空白（``restore_ws``，只有唯一一段對得上才改）；預設 dry-run。
- 正文引號：``quote_occurrences`` 抓 notes 正文「」『』，不是逐字的要嘛改成原文、改成轉述，
  要嘛登記成術語（``inline_terms``）或他串出處（``inline_source``），見 social-export-insights ``分析\查證與協作.md`` §8。
- 沒有外部依賴（只用標準庫），可以直接複製進專案的共用 lib。
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta

WINDOW_MIN = 60
STRICT_OK = {"strict", "placeholder"}
ELLIPSIS_RE = re.compile(r"\.{3,}|[…⋯]+")     # 半形「...」、U+2026「…」、U+22EF「⋯」（中文排版常用）
PART_RE = re.compile(r"[/／]")
QUOTE_RE = re.compile(r"「([^「」]+)」|『([^『』]+)』")

# 不通過層級 → 盤點用的原因分類（盤點報告與 meta.yaml 修正紀錄共用這組名稱）
CAUSE = {
    "punct": "標點空白",
    "multi": "跨訊息拼接",
    "reaction": "心情尾巴",
    "elided": "改寫被當成引文",
    "paraphrase": "改寫被當成引文",
    "speaker": "發言者錯",
    "self_alias": "發言者錯",
    "time": "時間錯",
    "time_sec": "時間錯",
    "seq_mismatch": "時間錯",
    "quarter": "時間錯",
    "fail": "找不到",
    "empty": "找不到",
    "no_source": "找不到",
}
CAUSE_ORDER = ["標點空白", "跨訊息拼接", "心情尾巴", "改寫被當成引文", "發言者錯", "時間錯", "找不到"]


# ── 文字工具 ─────────────────────────────────────────
def norm_ws(s) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def loose(s) -> str:
    """去掉空白、標點、符號（含 emoji）後的字串：只用來診斷「只差標點或空白」，不算通過。"""
    s = unicodedata.normalize("NFKC", s or "")
    return "".join(ch for ch in s if not (ch.isspace() or unicodedata.category(ch)[0] in "PSZC"))


def fragments(text: str) -> list[str]:
    """以刪節號切段；整段只有刪節號（例如對方真的只傳了「...」）時當字面比對。"""
    t = norm_ws(text)
    fr = [norm_ws(f) for f in ELLIPSIS_RE.split(t) if norm_ws(f)]
    return fr or ([t] if t else [])


def contains_in_order(hay: str, frs: list[str]) -> bool:
    pos = 0
    for f in frs:
        i = hay.find(f, pos)
        if i < 0:
            return False
        pos = i + len(f)
    return True


def is_placeholder(text: str) -> bool:
    return re.sub(r"[*()（）\s]", "", text or "") == "已收回"


def ws_only(a: str, b_hay: str) -> bool:
    """a 跟 b_hay 某段只差空白（去掉所有空白後是子字串）：盤點時區分「只差空白」與「差標點」。"""
    return bool(a) and re.sub(r"\s+", "", a) in re.sub(r"\s+", "", b_hay or "")


def elided_pieces(q: str, hay: str, min_piece: int = 2, max_pieces: int = 4) -> int:
    """q（已 loose）能不能切成 ≤ max_pieces 段、每段 ≥ min_piece 字、依序都是 hay（已 loose）的子字串。
    回傳段數（≥2 才算「截斷後拼接」；1 表示整段就是子字串；0 表示做不到）。貪婪取最長前綴。"""
    if not q or not hay:
        return 0
    pos, n, i = 0, 0, 0
    while i < len(q):
        best = 0
        for j in range(len(q), i + min_piece - 1, -1):
            k = hay.find(q[i:j], pos)
            if k >= 0:
                best = j - i
                pos = k + best
                break
        if best < min_piece:
            return 0
        i += best
        n += 1
        if n > max_pieces:
            return 0
    return n


def bigram_cover(q: str, hay: str) -> float:
    """q 的字元雙字組有幾成出現在 hay 裡（兩者都已 loose）：判斷「意思很像但字不一樣」。"""
    if len(q) < 2 or not hay:
        return 0.0
    grams = [q[i:i + 2] for i in range(len(q) - 1)]
    hs = {hay[i:i + 2] for i in range(len(hay) - 1)}
    return sum(g in hs for g in grams) / len(grams)


PARAPHRASE_MIN_LEN = 4
PARAPHRASE_COVER = 0.5


def parse_ts(ts) -> tuple[datetime | None, int]:
    """notes 寫的時間 → (datetime, 精度秒數)。寫到秒 → 0（同一秒）；寫到分鐘 → 59（同一分鐘）。
    接受 ``YYYY-MM-DDTHH:MM[:SS]`` 與空格分隔。解析不到回 (None, 0)。"""
    s = str(ts or "").strip().replace(" ", "T")
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if not m:
        return None, 0
    t = datetime.fromisoformat(f"{m.group(1)}T{int(m.group(2)):02d}:{m.group(3)}:{m.group(4) or '00'}")
    return t, (0 if m.group(4) else 59)


# ── 比對索引 ─────────────────────────────────────────
class Thread:
    """一串紀錄的比對索引（訊息串要含 unsent，不需要 system）。

    ts_key：時間欄（訊息串 ``dt``；模組自組紀錄常用 ``datetime``）；seq_key：紀錄編號欄（要能排序）。"""

    def __init__(self, msgs: list[dict], ts_key: str = "dt", seq_key: str = "seq"):
        self.seq_key = seq_key
        self.msgs = sorted(msgs, key=lambda m: m.get(seq_key) or 0)
        self.t = [self._dt(m.get(ts_key)) for m in self.msgs]
        self.norm = [norm_ws(m.get("text")) for m in self.msgs]
        self.loose = [loose(m.get("text")) for m in self.msgs]
        self.sender = [norm_ws(m.get("sender")) for m in self.msgs]
        self.by_seq = {m.get(seq_key): i for i, m in enumerate(self.msgs)}
        self.speakers = sorted({s for s in self.sender if s}, key=len, reverse=True)

    @staticmethod
    def _dt(v):
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v)[:19])
        except ValueError:
            return None

    def seq(self, i: int):
        return self.msgs[i].get(self.seq_key)

    def reaction_tail(self, i: int, frs: list[str]) -> bool:
        """L1 的 text 尾端混有心情回應（「表情＋人名」，部分匯出版本再加「 (時間)」），不是訊息內文。
        引文抄到人名，或引文最後一個字元正好是回應表情（L1 原文緊接著人名）→ True。"""
        names = "|".join(re.escape(n) for n in self.speakers)
        if not names:
            return False
        last = frs[-1]
        if re.search(rf"\S(?:{names})(?: \([^)]*\))?$", last):
            return True
        t, pos = self.norm[i], 0
        for f in frs:
            pos = t.find(f, pos) + len(f)
        # 回應格式是表情後面直接接人名（中間沒有空白）；一般句子裡提到人名前面通常有空白或標點
        return bool(pos > 0 and not t[pos - 1].isspace() and unicodedata.category(t[pos - 1])[0] in "SMC"
                    and re.match(rf"(?:{names})(?:\s|\(|$)", t[pos:]))

    def window(self, t0: datetime, explicit: bool, span_s: int | None = None, before_s: int = 0) -> list[int]:
        if span_s is None:
            span_s = 59 if explicit else WINDOW_MIN * 60
        t_lo, t1 = t0 - timedelta(seconds=before_s), t0 + timedelta(seconds=span_s)
        return [i for i, t in enumerate(self.t) if t and t_lo <= t <= t1]

    def match(self, speaker: str, text: str, t0: datetime, explicit: bool, after_seq=None, *,
              span_s: int | None = None, refine: bool = False) -> dict:
        """回傳 {level, seq}（層級見模組說明）。span_s：時間容許（秒，從 t0 起算）；不給就是
        explicit → 同一分鐘（t0 要是整分）、非 explicit → 60 分鐘內。refine=True 時把 fail 細分。"""
        speaker = norm_ws(speaker)
        win = [i for i in self.window(t0, explicit, span_s) if after_seq is None or self.seq(i) > after_seq]
        same = [i for i in win if self.sender[i] == speaker]
        if is_placeholder(text):
            hit = next((i for i in same if self.msgs[i].get("type") == "unsent"), None)
            return {"level": "placeholder" if hit is not None else "fail", "seq": self.seq(hit) if hit is not None else None}
        frs = fragments(text)
        if not frs:
            return {"level": "empty" if refine else "fail", "seq": None}
        hit = next((i for i in same if contains_in_order(self.norm[i], frs)), None)
        if hit is not None:
            lvl = "reaction" if self.reaction_tail(hit, frs) else "strict"
            return {"level": lvl, "seq": self.seq(hit)}
        lfr = [loose(f) for f in frs if loose(f)]
        if lfr:
            hit = next((i for i in same if contains_in_order(self.loose[i], lfr)), None)
            if hit is not None:
                return {"level": "punct", "seq": self.seq(hit)}
            # 跨訊息：同發言者連續幾則串起來才對得上（一段裡塞了好幾則）
            wide = [i for i in self.window(t0, False, before_s=WINDOW_MIN * 60 if refine else 0)
                    if self.sender[i] == speaker]
            lq = "".join(lfr)
            # 只有「沒有任何單一則含整段」時才算跨訊息；單一則就含整段的是時間（或標點）問題，留給下面判斷
            if not any(contains_in_order(self.loose[i], lfr) for i in wide):
                for k, i in enumerate(wide):
                    acc = ""
                    for j in wide[k:k + 12]:
                        acc += self.loose[j]
                        if lq in acc:
                            if j != i:
                                return {"level": "multi", "seq": self.seq(i)}
                            break
            hit = next((i for i in win if self.sender[i] != speaker and contains_in_order(self.loose[i], lfr)), None)
            if hit is not None:
                return {"level": "speaker", "seq": self.seq(hit)}
            hit = next((i for i, s in enumerate(self.sender) if s == speaker and contains_in_order(self.norm[i], frs)), None)
            if hit is None and refine:      # 時間錯而且另差標點空白：仍歸「時間錯」（先修時間，再看文字）
                hit = next((i for i, s in enumerate(self.sender) if s == speaker and contains_in_order(self.loose[i], lfr)), None)
            if hit is not None:
                return {"level": "time", "seq": self.seq(hit)}
            if refine:
                return self._refine(speaker, lq, t0)
        return {"level": "fail", "seq": None}

    def _refine(self, speaker: str, lq: str, t0: datetime) -> dict:
        """找不到時再細分：同發言者 ±1 天內「同一則挑段拼接」→ elided；任何人 ±1 天內字面很像 → paraphrase。"""
        near = self.window(t0, False, span_s=86400, before_s=86400)
        for i in near:
            if self.sender[i] == speaker and elided_pieces(lq, self.loose[i]) >= 2:
                return {"level": "elided", "seq": self.seq(i)}
        if len(lq) >= PARAPHRASE_MIN_LEN:
            best = max(((bigram_cover(lq, self.loose[i]), i) for i in near), default=(0.0, None))
            if best[0] >= PARAPHRASE_COVER:
                return {"level": "paraphrase", "seq": self.seq(best[1])}
        return {"level": "fail", "seq": None}

    def find_anywhere(self, text: str) -> int | None:
        """引文（strict 片段規則）出現在這串的哪一則（不管發言者、時間）；盤點正文引號用。"""
        frs = fragments(text)
        if not frs:
            return None
        return next((i for i in range(len(self.msgs)) if contains_in_order(self.norm[i], frs)), None)


# ── quotes.json 型的登記（{speaker, timestamp, quote}） ──
def match_entry(th: Thread, speaker, ts, quote, *, refine: bool = True, is_self=None) -> dict:
    """一筆 quotes.json／events_narrative 證據語錄 → {level, seq, cause}。時間精度跟 notes 寫的精度走。
    refine 時另外細分：time_sec（同一分鐘、秒數不對）、self_alias（發言者是本人另一個別名）。
    is_self：判斷名字是不是本人的函式（給 self_alias 用；不給就不細分）。"""
    t0, span = parse_ts(ts)
    if not norm_ws(quote):
        r = {"level": "empty" if refine else "fail", "seq": None}
    elif t0 is None:
        r = {"level": "fail", "seq": None}
        if refine:
            r["why"] = "timestamp 格式"
    else:
        r = th.match(speaker, quote, t0, True, span_s=span, refine=refine)
        if refine and r["level"] == "time" and span == 0:
            r2 = th.match(speaker, quote, t0.replace(second=0), True, span_s=59)
            if r2["level"] in STRICT_OK:
                r = {"level": "time_sec", "seq": r2["seq"]}
            elif r2["level"] in ("reaction", "punct"):     # 文字本身就有問題：先歸文字的原因，秒數不符另記
                r = {"level": r2["level"], "seq": r2["seq"], "also": "秒數不符"}
        if refine and r["level"] == "speaker" and is_self and r["seq"] in th.by_seq:
            other = th.sender[th.by_seq[r["seq"]]]
            if is_self(norm_ws(speaker)) and is_self(other):
                r = {"level": "self_alias", "seq": r["seq"]}
        if refine and r["level"] == "punct" and r["seq"] in th.by_seq:
            # 盤點細分：只差空白（可機械修：照 L1 抄回空白）vs 差標點
            r["sub"] = "只差空白" if ws_only(norm_ws(quote), th.norm[th.by_seq[r["seq"]]]) else "差標點"
    r["cause"] = None if r["level"] in STRICT_OK else CAUSE.get(r["level"], "找不到")
    return r


def verify_entries(th: Thread, entries: list[dict], *, quote_key="quote", speaker_key="speaker",
                   ts_key="timestamp", refine: bool = True, is_self=None, mode: str | None = None) -> dict:
    """一份語錄清單（quotes.json 或 events_narrative 證據）逐筆 strict 驗證。回傳：
    {mode, total, pass, status, levels, causes, failures, items}；items 只有 i／speaker／timestamp／level／seq／cause。
    events_narrative 沒有證據語錄的事件（quote 欄空白或沒有）不列入。"""
    items = []
    for i, e in enumerate(entries or []):
        if quote_key not in e or e.get(quote_key) in (None, ""):
            if quote_key != "quote":
                continue
        r = match_entry(th, e.get(speaker_key), e.get(ts_key), e.get(quote_key), refine=refine, is_self=is_self)
        items.append({"i": i, "speaker": e.get(speaker_key), "timestamp": e.get(ts_key),
                      "level": r["level"], "seq": r["seq"], "cause": r["cause"],
                      **({"sub": r["sub"]} if r.get("sub") else {}), **({"also": r["also"]} if r.get("also") else {})})
    return summary(items, mode or "strict(同一則＋發言者＋時間精度同 notes＋刪節號片段依序為子字串)")


def summary(items: list[dict], mode: str) -> dict:
    lv = Counter(it["level"] for it in items)
    causes = Counter(it.get("cause") or CAUSE.get(it["level"], "找不到") for it in items if it["level"] not in STRICT_OK)
    n_ok = sum(it["level"] in STRICT_OK for it in items)
    return {"mode": mode, "total": len(items), "pass": n_ok,
            "status": "PASS" if items and n_ok == len(items) else ("EMPTY" if not items else "FAIL"),
            "levels": dict(lv), "causes": dict(causes),
            "failures": [it for it in items if it["level"] not in STRICT_OK], "items": items}


# ── 修正輔助（給回寫腳本用；只算新值，不寫檔） ──
def _grapheme_start(t: str, end: int) -> int:
    """t[:end] 最後一個「表情字元」（含膚色、變體選擇符、ZWJ 連起來的組合）的起點。"""
    j = end
    while True:
        while j > 0 and (unicodedata.category(t[j - 1]) in ("Mn", "Me", "Cf") or 0x1F3FB <= ord(t[j - 1]) <= 0x1F3FF):
            j -= 1
        if j > 0 and unicodedata.category(t[j - 1])[0] in "SC":
            j -= 1
        if j > 0 and t[j - 1] == "‍":
            j -= 1
            continue
        return j


def reaction_body_end(th: Thread, i: int) -> int | None:
    """第 i 則（索引）的 L1 文字（norm_ws）裡，尾端心情回應（一個或多個「表情＋人名［ (時間)］」）開始的位置；
    沒有回應尾巴回 None。"""
    names = "|".join(re.escape(n) for n in th.speakers)
    if not names:
        return None
    t, end, found = th.norm[i], len(th.norm[i]), False
    while True:
        m = re.search(rf"(?:{names})(?: \([^)]*\))?$", t[:end])
        if not m:
            break
        j = _grapheme_start(t, m.start())
        if j == m.start():                     # 人名前面不是表情 → 不是心情回應
            break
        end, found = j, True
    return end if found else None


def trim_reaction(th: Thread, i: int, quote: str) -> str | None:
    """引文抄進了第 i 則的心情回應尾巴 → 回傳截掉尾巴後的引文（norm_ws）；截不出非空的內文回 None。"""
    body_end = reaction_body_end(th, i)
    frs = fragments(quote)
    if body_end is None or not frs or not contains_in_order(th.norm[i], frs):
        return None
    t, pos, starts = th.norm[i], 0, []
    for f in frs:
        k = t.find(f, pos)
        starts.append(k)
        pos = k + len(f)
    last, s_last = frs[-1], starts[-1]
    keep = body_end - s_last
    if keep <= 0:
        return None
    new_last = last[:keep].rstrip()
    if not loose(new_last):
        return None
    q = norm_ws(quote)
    k = q.rfind(last)
    out = (q[:k] + new_last + q[k + len(last):]).strip()
    return out if out != q else None


def restore_ws(hay: str, quote: str) -> str | None:
    """引文跟 hay 某段只差空白 → 回傳 hay 裡那一段（照 L1 的空白）；對到 0 段或超過 1 段回 None。
    刪節號照字面比（L1 本來就有「....」才對得上；表示省略的刪節號自然對不到，回 None）。"""
    chars = [c for c in (quote or "") if not c.isspace()]
    if not chars:
        return None
    pat = re.compile(r"\s*".join(re.escape(c) for c in chars))
    hits = {(m.start(), m.end()) for m in pat.finditer(hay or "")}
    if len(hits) != 1:
        return None
    a, b = hits.pop()
    return hay[a:b]


def same_minute_candidates(th: Thread, speaker: str, quote: str, t0: datetime) -> list[int]:
    """同一分鐘內、同發言者、strict 片段規則對得上的紀錄索引（補秒數用：只有一則才能改）。"""
    frs = fragments(quote)
    sp = norm_ws(speaker)
    return [i for i in th.window(t0.replace(second=0), True, span_s=59)
            if th.sender[i] == sp and frs and contains_in_order(th.norm[i], frs)]


def quote_occurrences(text: str, skip_blockquote: bool = True) -> list[dict]:
    """正文裡的引號內文字：[{line, quote}]。skip_blockquote：略過「> 」開頭的引用行（那些另有格式驗證）。"""
    out = []
    for no, ln in enumerate((text or "").splitlines(), 1):
        if skip_blockquote and ln.startswith("> "):
            continue
        for m in QUOTE_RE.finditer(ln):
            out.append({"line": no, "quote": m.group(1) or m.group(2)})
    return out
