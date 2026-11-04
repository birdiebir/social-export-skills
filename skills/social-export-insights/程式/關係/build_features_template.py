# -*- coding: utf-8 -*-
"""
關係模組 L4（量化特徵）：對選定的每個對話對象跑量化特徵分析。

深層（tier=deep）：月粒度特徵矩陣＋SnowNLP情緒＋迴歸趨勢＋轉折點偵測＋
  KMeans+PCA 關係階段分群＋逐季 jieba 主題詞。
輕層（tier=light）：年粒度特徵矩陣＋逐年 jieba 主題詞，跳過迴歸/轉折點/分群
  （成本考量，見 說明.md「分層規則」）。

用 role（self/other）欄位泛化，不對特定姓名硬編碼——這樣同一份程式碼可以套用
在任何目標身上，是這個模組能從「單一好友原型」擴大成「任意 N 人」的關鍵設計
（見 分析\架構.md「演進案例」一節）。

輸入：quant/<slug>/messages_full.jsonl（build_person_corpus_template.py 產出）
輸出（quant/<slug>/）：
  feature_matrix.csv, meta.json，以及
  （深層限定）regression_results.csv / flagged_months.json / phase_clusters.csv /
             topic_keywords_by_quarter.json
  （輕層限定）topic_keywords_by_year.json

複製到專案後另存為 build_features.py。
"""
import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from snownlp import SnowNLP

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import OUTPUT_ROOT

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg

TOP30_PATH = OUTPUT_ROOT / "relationships" / "data" / "top30.json"
QUANT_DIR = OUTPUT_ROOT / "relationships" / "quant"


def load_messages(person_dir):
    rows = []
    with (person_dir / "messages_full.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def add_message_level_features(df, self_names):
    text = df["text"].fillna("")
    df["role"] = df["sender"].apply(lambda s: "self" if s in self_names else "other")
    df["char_len"] = text.str.len()
    df["is_question"] = text.str.contains(r"[?？]", regex=True)
    df["is_exclaim"] = text.str.contains(r"[!！]", regex=True)
    df["is_ellipsis"] = text.str.contains(r"(\.\.\.|…)", regex=True)
    df["is_media"] = df["type"].isin(cfg.MEDIA_TYPES)
    df["is_unsent"] = df["type"] == "unsent"
    df["hour"] = df["datetime"].dt.hour
    df["is_late_night"] = df["hour"].between(0, 4)
    df["month"] = df["datetime"].dt.to_period("M").astype(str)
    df["quarter"] = df["datetime"].dt.to_period("Q").astype(str)
    df["year"] = df["datetime"].dt.to_period("Y").astype(str)

    for cat, words in cfg.KEYWORDS.items():
        pattern = "|".join(re.escape(w) for w in words)
        df[f"kw_{cat}"] = text.str.count(pattern)

    sentiments = np.full(len(df), np.nan)
    mask = (df["type"] == "text") & (df["char_len"] >= 2)
    idxs = df.index[mask]
    for i, txt in zip(idxs, text[mask]):
        try:
            sentiments[i] = SnowNLP(txt).sentiments
        except Exception:
            pass
    df["sentiment"] = sentiments
    return df


def add_turn_taking_features(df):
    df = df.sort_values("datetime").reset_index(drop=True)
    prev_sender = df["sender"].shift(1)
    prev_dt = df["datetime"].shift(1)
    gap = df["datetime"] - prev_dt
    is_alt = (df["sender"] != prev_sender) & prev_sender.notna()
    is_response = is_alt & (gap <= pd.Timedelta(hours=2))
    is_initiation = (prev_sender.isna()) | (is_alt & (gap > pd.Timedelta(hours=2)))
    df["response_latency_min"] = np.where(is_response, gap.dt.total_seconds() / 60.0, np.nan)
    df["is_response"] = is_response
    df["is_initiation"] = is_initiation
    return df


def build_period_matrix(df, period_col):
    idx_col = f"{period_col}_idx"
    records = []
    periods = sorted(df[period_col].unique())
    for p in periods:
        sub = df[df[period_col] == p]
        rec = {period_col: p, "total_messages": len(sub)}
        rec["active_days"] = sub["date"].nunique()
        rec["avg_msgs_per_active_day"] = rec["total_messages"] / max(rec["active_days"], 1)

        resp = sub[sub["is_response"]]
        rec["median_response_latency_min"] = resp["response_latency_min"].median()

        for role in ("self", "other"):
            s = sub[sub["role"] == role]
            n = len(s)
            rec[f"msgs_{role}"] = n
            rec[f"avg_len_{role}"] = s["char_len"].mean() if n else np.nan
            rec[f"question_rate_{role}"] = s["is_question"].mean() if n else np.nan
            rec[f"exclaim_rate_{role}"] = s["is_exclaim"].mean() if n else np.nan
            rec[f"ellipsis_rate_{role}"] = s["is_ellipsis"].mean() if n else np.nan
            rec[f"media_rate_{role}"] = s["is_media"].mean() if n else np.nan
            rec[f"unsent_rate_{role}"] = s["is_unsent"].mean() if n else np.nan
            rec[f"latenight_rate_{role}"] = s["is_late_night"].mean() if n else np.nan
            rec[f"sentiment_mean_{role}"] = s["sentiment"].mean()
            rec[f"sentiment_std_{role}"] = s["sentiment"].std()

            resp_s = resp[resp["role"] == role]
            rec[f"response_latency_min_{role}"] = resp_s["response_latency_min"].median()

            init_s = s[s["is_initiation"]]
            rec[f"initiations_{role}"] = len(init_s)

            total_chars = s["char_len"].sum()
            for cat in cfg.KEYWORDS:
                cnt = s[f"kw_{cat}"].sum()
                rec[f"kw_{cat}_per1k_{role}"] = (cnt / total_chars * 1000) if total_chars else np.nan

        init_total = rec["initiations_self"] + rec["initiations_other"]
        rec["initiation_share_self"] = rec["initiations_self"] / init_total if init_total else np.nan

        records.append(rec)

    fm = pd.DataFrame(records)
    fm[idx_col] = np.arange(len(fm))
    return fm


def run_regressions(fm, period_col):
    idx_col = f"{period_col}_idx"
    exclude = {period_col, idx_col}
    results = []
    for col in fm.columns:
        if col in exclude:
            continue
        y = fm[col].values.astype(float)
        x = fm[idx_col].values.astype(float)
        mask = ~np.isnan(y)
        if mask.sum() < 8:
            continue
        slope, intercept, r, p, se = stats.linregress(x[mask], y[mask])
        results.append({
            "feature": col,
            "slope_per_period": slope,
            "intercept": intercept,
            "r_squared": r ** 2,
            "p_value": p,
            "significant_p05": bool(p < 0.05),
            "n_periods": int(mask.sum()),
            "mean": float(np.nanmean(y)),
        })
    cols = ["feature", "slope_per_period", "intercept", "r_squared", "p_value",
            "significant_p05", "n_periods", "mean"]
    if not results:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(results).sort_values("p_value")


def flag_turning_points(fm, reg, period_col):
    idx_col = f"{period_col}_idx"
    sig = reg[reg["significant_p05"]].set_index("feature") if len(reg) else reg
    flags = {p: [] for p in fm[period_col]}
    for feat, row in sig.iterrows():
        series = fm[feat]
        roll = series.rolling(3, min_periods=1, center=True).mean()
        predicted = row["intercept"] + row["slope_per_period"] * fm[idx_col]
        resid = roll - predicted
        sigma = np.nanstd(resid)
        if sigma == 0 or np.isnan(sigma):
            continue
        dev = resid.abs() / sigma
        for p, d in zip(fm[period_col], dev):
            if pd.notna(d) and d > 2.0:
                flags[p].append(feat)
    # 要求至少 2 個獨立顯著特徵在同一期co-deviate才算真正轉折點（避免對~15個特徵
    # 逐一檢定時的多重比較假陽性）。
    flagged_periods = sorted([p for p, feats in flags.items() if len(feats) >= 2])
    return flagged_periods, flags


def cluster_phases(fm, period_col):
    from sklearn.decomposition import PCA
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    idx_col = f"{period_col}_idx"
    feat_cols = [c for c in fm.columns if c not in (period_col, idx_col)]
    X = fm[feat_cols].copy()
    X = X.fillna(X.mean(numeric_only=True))
    Xs = StandardScaler().fit_transform(X)

    n_components = max(1, min(5, Xs.shape[1], Xs.shape[0]))
    pca = PCA(n_components=n_components)
    Xp = pca.fit_transform(Xs)

    k = max(1, min(4, len(fm)))
    if k < 2:
        labels = np.zeros(len(fm), dtype=int)
    else:
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(Xp)

    fm2 = fm[[period_col]].copy()
    fm2["phase_cluster"] = labels
    fm2["pc1"] = Xp[:, 0] if Xp.shape[1] >= 1 else 0.0
    fm2["pc2"] = Xp[:, 1] if Xp.shape[1] >= 2 else 0.0
    explained = float(pca.explained_variance_ratio_[: min(2, n_components)].sum())
    return fm2, explained


def build_name_stopwords(other_name, self_names):
    """把 other_name 與所有 self_names 拆成 token（含無空白串接版本）當停用詞，
    避免對話對象/本人姓名被誤判成主題關鍵字——依對象動態組合，不硬編碼特定姓名。"""
    names = set()
    for full in [other_name, *self_names]:
        parts = full.split()
        names.update(parts)
        names.add("".join(parts))
    return names


def topic_keywords_by_period(df, period_col, other_name, self_names):
    import jieba
    import jieba.analyse

    stopwords = cfg.JIEBA_STOPWORDS
    names = build_name_stopwords(other_name, self_names)
    url_re = re.compile(r"https?://\S+")
    chinese_word_re = re.compile(r"^[一-鿿]{2,}$")

    out = {}
    for p, sub in df[df["type"] == "text"].groupby(period_col):
        text_blob = " ".join(sub["text"].astype(str).tolist())
        text_blob = url_re.sub(" ", text_blob)
        if not text_blob.strip():
            out[p] = []
            continue
        tags = jieba.analyse.extract_tags(text_blob, topK=40)
        tags = [t for t in tags if chinese_word_re.match(t) and t not in stopwords and t not in names]
        out[p] = tags[:10]
    return out


def build_features_for_person(entry, person_dir):
    tier = entry["tier"]
    other_name = entry["name"]
    self_names = cfg.SELF_NAMES

    df = load_messages(person_dir)
    df = add_message_level_features(df, self_names)
    df = add_turn_taking_features(df)

    period_col = "month" if tier == "deep" else "year"
    fm = build_period_matrix(df, period_col)
    fm.to_csv(person_dir / "feature_matrix.csv", index=False, encoding="utf-8-sig")

    meta = {
        "tier": tier, "self_names": sorted(self_names), "other_name": other_name,
        "thread_id": entry["thread_id"], "message_count": int(len(df)),
        "date_range": [str(df["date"].min()), str(df["date"].max())] if len(df) else [None, None],
        "period_granularity": period_col,
    }

    if tier == "deep":
        reg = run_regressions(fm, period_col)
        reg.to_csv(person_dir / "regression_results.csv", index=False, encoding="utf-8-sig")

        flagged_periods, flags = flag_turning_points(fm, reg, period_col)
        (person_dir / "flagged_months.json").write_text(
            json.dumps({"flagged_months": flagged_periods,
                        "detail": {k: v for k, v in flags.items() if v}},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        phases, explained = cluster_phases(fm, period_col)
        phases.to_csv(person_dir / "phase_clusters.csv", index=False, encoding="utf-8-sig")
        meta["pca2_explained_variance"] = explained

        topics = topic_keywords_by_period(df, "quarter", other_name, self_names)
        (person_dir / "topic_keywords_by_quarter.json").write_text(
            json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")

        meta["n_significant_trends"] = int(reg["significant_p05"].sum()) if len(reg) else 0
    else:
        topics = topic_keywords_by_period(df, "year", other_name, self_names)
        (person_dir / "topic_keywords_by_year.json").write_text(
            json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")

    (person_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main():
    """批次全量跑法。隨選問答單一對象時，改呼叫 build_features_for_person()
    傳入該對象的 entry dict + person_dir 即可。"""
    top30 = json.loads(TOP30_PATH.read_text(encoding="utf-8"))
    for entry in top30:
        person_dir = QUANT_DIR / entry["person_slug"]
        if not (person_dir / "messages_full.jsonl").exists():
            print(f"SKIP {entry['name']}: messages_full.jsonl not found "
                  f"(run build_person_corpus_template.py first)", file=sys.stderr)
            continue
        print(f"[{entry['rank']:>2}] {entry['name']} ({entry['tier']})...", file=sys.stderr)
        meta = build_features_for_person(entry, person_dir)
        print(f"    -> {meta['message_count']} msgs, {meta['period_granularity']} granularity", file=sys.stderr)


if __name__ == "__main__":
    main()
