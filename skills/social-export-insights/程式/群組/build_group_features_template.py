# -*- coding: utf-8 -*-
"""
群組模組 L4（量化特徵）：對選定群組跑全量（不取樣）量化分析。泛化自關係模組
build_features_template.py 的訊息層級特徵計算（本來就是 N-agnostic 的部分直接
沿用），把「self/other 二分」換成「群組內每個 sender 各一份摘要」。

刻意不做 LLM 逐行質性閱讀（那是關係模組深層的做法，成本高、不適合多組 POC
快速擴充）——這裡全部用規則式／統計式方法，對 100% 訊息做完整統計，再用簡單
規則把數字轉成描述性標籤（見 config.MEMBER_TAG_RULES，對應 分析\架構.md 的
L4「規則式自動標籤 pattern」）。

輸入：quant/<slug>/messages_full.jsonl（語料抽取步驟產出，含 is_event/event_type
      標記）
輸出（quant/<slug>/）：
  member_summary.json  -- 每個成員的量化摘要＋自動標籤（不含系統事件訊息）
  events_timeline.json -- 系統事件時間軸（加入/退出/改名/換照片/設管理員）
  activity.json         -- 逐月趨勢、weekday×hour 熱力圖、異常活躍日
  interactions.json     -- 連續發言者配對次數（簡易互動排行）
  emoji_freq.json        -- 該組 emoji/貼圖使用排行

複製到專案後另存為 build_group_features.py。
"""
import json
import re
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from snownlp import SnowNLP

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import OUTPUT_ROOT

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg

TOP10_PATH = OUTPUT_ROOT / "group_analysis" / "data" / "top10.json"
QUANT_DIR = OUTPUT_ROOT / "group_analysis" / "quant"

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "\U00002300-\U000023FF"
    "\U00002700-\U000027BF"
    "]+"
)


def load_messages(group_dir):
    rows = []
    with (group_dir / "messages_full.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def add_message_level_features(df):
    text = df["text"].fillna("")
    df["char_len"] = text.str.len()
    df["is_question"] = text.str.contains(r"[?？]", regex=True)
    df["is_exclaim"] = text.str.contains(r"[!！]", regex=True)
    df["is_ellipsis"] = text.str.contains(r"(\.\.\.|…)", regex=True)
    df["is_media"] = df["type"].isin(cfg.MEDIA_TYPES)
    df["hour"] = df["datetime"].dt.hour
    df["weekday"] = df["datetime"].dt.dayofweek  # 0=Mon
    df["is_late_night"] = df["hour"].between(0, 4)
    df["month"] = df["datetime"].dt.to_period("M").astype(str)

    sentiments = np.full(len(df), np.nan)
    mask = (df["type"] == "text") & (df["char_len"] >= 2) & (~df["is_event"])
    idxs = df.index[mask]
    for i, txt in zip(idxs, text[mask]):
        try:
            sentiments[i] = SnowNLP(txt).sentiments
        except Exception:
            pass
    df["sentiment"] = sentiments
    return df


def add_turn_taking_features(df):
    prev_sender = df["sender"].shift(1)
    prev_dt = df["datetime"].shift(1)
    gap = df["datetime"] - prev_dt
    is_alt = (df["sender"] != prev_sender) & prev_sender.notna()
    is_initiation = (prev_sender.isna()) | (is_alt & (gap > pd.Timedelta(hours=2)))
    df["is_initiation"] = is_initiation
    return df


def build_name_stopwords(member_names):
    names = set()
    for full in member_names:
        parts = full.split()
        names.update(parts)
        names.add("".join(parts))
    return names


def register_member_names(member_names):
    """把成員全名餵給 jieba 當自訂詞，避免姓名被斷成破碎片段（例如虛構姓名「王曉閎」被
    切成「王曉」＋「閎」）混進主題詞——斷詞完整後，build_name_stopwords() 才能
    正確用完整姓名字串過濾掉。"""
    import jieba
    for name in member_names:
        for token in [name, *name.split()]:
            if token:
                jieba.add_word(token)


def top_keywords_for_text(text_blob, stopwords, limit=10):
    import jieba
    import jieba.analyse

    url_re = re.compile(r"https?://\S+")
    chinese_word_re = re.compile(r"^[一-鿿]{2,}$")
    text_blob = url_re.sub(" ", text_blob)
    if not text_blob.strip():
        return []
    tags = jieba.analyse.extract_tags(text_blob, topK=40)
    tags = [t for t in tags if chinese_word_re.match(t) and t not in stopwords]
    return tags[:limit]


def build_member_summary(df, group_slug):
    human = df[~df["is_event"]].copy()
    member_names = sorted(human["sender"].unique())
    register_member_names(member_names)
    name_stopwords = cfg.JIEBA_STOPWORDS | build_name_stopwords(member_names)
    total_human = len(human)

    members = []
    for name in member_names:
        s = human[human["sender"] == name]
        n = len(s)
        text_blob = " ".join(s.loc[s["type"] == "text", "text"].astype(str).tolist())
        members.append({
            "name": name,
            "message_count": int(n),
            "message_share": round(n / total_human, 4) if total_human else 0.0,
            "avg_len": round(float(s["char_len"].mean()), 2) if n else None,
            "question_rate": round(float(s["is_question"].mean()), 4) if n else None,
            "exclaim_rate": round(float(s["is_exclaim"].mean()), 4) if n else None,
            "ellipsis_rate": round(float(s["is_ellipsis"].mean()), 4) if n else None,
            "media_rate": round(float(s["is_media"].mean()), 4) if n else None,
            "latenight_rate": round(float(s["is_late_night"].mean()), 4) if n else None,
            "sentiment_mean": round(float(s["sentiment"].mean()), 4) if s["sentiment"].notna().any() else None,
            "initiation_count": int(s["is_initiation"].sum()),
            "top_keywords": top_keywords_for_text(text_blob, name_stopwords),
            "tags": [],
        })

    # 自動標籤：每項指標在「訊息數達門檻」的成員裡取前 TAG_TOP_FRACTION。
    qualified = [m for m in members if m["message_count"] >= cfg.MIN_MESSAGES_FOR_TAG]
    n_tagged = max(1, round(len(qualified) * cfg.TAG_TOP_FRACTION)) if qualified else 0
    for metric, tag in cfg.MEMBER_TAG_RULES:
        ranked = sorted(qualified, key=lambda m: (m.get(metric) or 0), reverse=True)
        for m in ranked[:n_tagged]:
            if (m.get(metric) or 0) > 0:
                m["tags"].append(tag)

    members.sort(key=lambda m: -m["message_count"])
    return {
        "group_slug": group_slug,
        "message_count_total": int(len(df)),
        "message_count_human": total_human,
        "member_count": len(members),
        "members": members,
    }


def _clean(value):
    """pandas 把混雜 None/字串的欄位讀回時，None 可能被轉成 float NaN——
    json.dumps 對 NaN 會輸出不合法的 JSON，這裡統一轉回 None。"""
    return None if (value is None or (isinstance(value, float) and np.isnan(value))) else value


def build_events_timeline(df):
    events = df[df["is_event"]].copy()
    out = []
    for _, row in events.iterrows():
        out.append({
            "datetime": row["datetime"].isoformat(),
            "event_type": _clean(row["event_type"]),
            "actor": _clean(row["event_actor"]),
            "target": _clean(row["event_target"]),
        })
    return out


def build_activity(df):
    monthly = df.groupby("month").size()
    monthly_trend = [{"month": m, "count": int(c)} for m, c in monthly.items()]

    heatmap = df.groupby(["weekday", "hour"]).size()
    weekday_hour = [
        {"weekday": int(wd), "hour": int(hr), "count": int(c)}
        for (wd, hr), c in heatmap.items()
    ]

    daily = df.groupby(df["datetime"].dt.date).size()
    mean, std = daily.mean(), daily.std()
    spikes = []
    if std and not np.isnan(std) and std > 0:
        z = (daily - mean) / std
        for d, zc in z.items():
            if zc > cfg.DAILY_SPIKE_ZSCORE:
                spikes.append({"date": str(d), "count": int(daily[d]), "zscore": round(float(zc), 2)})
    spikes.sort(key=lambda s: -s["zscore"])

    return {
        "monthly_trend": monthly_trend,
        "weekday_hour_heatmap": weekday_hour,
        "daily_spikes": spikes,
    }


def build_interactions(df):
    prev_sender = df["sender"].shift(1)
    pairs = Counter()
    for a, b in zip(prev_sender, df["sender"]):
        if pd.isna(a) or a == b:
            continue
        key = tuple(sorted([a, b]))
        pairs[key] += 1
    ranked = [{"pair": list(k), "count": v} for k, v in pairs.most_common(30)]
    return {"top_pairs": ranked}


def build_emoji_freq(df):
    counter = Counter()
    for text in df["text"].fillna(""):
        for em in EMOJI_RE.findall(text):
            for ch in em:
                counter[ch] += 1
    return {"emoji_freq": counter.most_common(30)}


def build_features_for_group(entry):
    group_dir = QUANT_DIR / entry["group_slug"]
    df = load_messages(group_dir)
    df = add_message_level_features(df)
    df = add_turn_taking_features(df)

    (group_dir / "member_summary.json").write_text(
        json.dumps(build_member_summary(df, entry["group_slug"]), ensure_ascii=False, indent=2),
        encoding="utf-8")
    (group_dir / "events_timeline.json").write_text(
        json.dumps(build_events_timeline(df), ensure_ascii=False, indent=2), encoding="utf-8")
    (group_dir / "activity.json").write_text(
        json.dumps(build_activity(df), ensure_ascii=False, indent=2), encoding="utf-8")
    (group_dir / "interactions.json").write_text(
        json.dumps(build_interactions(df), ensure_ascii=False, indent=2), encoding="utf-8")
    (group_dir / "emoji_freq.json").write_text(
        json.dumps(build_emoji_freq(df), ensure_ascii=False, indent=2), encoding="utf-8")

    meta = {
        "group_slug": entry["group_slug"], "name": entry["name"],
        "thread_id": entry["thread_id"], "message_count": int(len(df)),
        "participant_count": int(df[~df["is_event"]]["sender"].nunique()),
        "date_range": [str(df["date"].min()), str(df["date"].max())] if len(df) else [None, None],
    }
    (group_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main():
    top10 = json.loads(TOP10_PATH.read_text(encoding="utf-8"))
    for entry in top10:
        group_dir = QUANT_DIR / entry["group_slug"]
        if not (group_dir / "messages_full.jsonl").exists():
            print(f"SKIP {entry['name']}: messages_full.jsonl not found "
                  f"(run the corpus-extraction step first)", file=sys.stderr)
            continue
        print(f"[{entry['rank']:>2}] {entry['name']}...", file=sys.stderr)
        meta = build_features_for_group(entry)
        print(f"    -> {meta['message_count']} msgs, {meta['participant_count']} members", file=sys.stderr)


if __name__ == "__main__":
    main()
