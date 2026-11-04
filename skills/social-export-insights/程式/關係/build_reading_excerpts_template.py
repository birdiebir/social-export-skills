# -*- coding: utf-8 -*-
"""
關係模組：產生質性閱讀用的摘錄檔（純取樣，不做任何分析——這一步只準備素材，
真正的關係筆記由 Claude 讀這些摘錄檔＋範本\\ 底下的範本撰寫，見 說明.md
「質性分析」一節，對應 分析\架構.md 的 L5）。

深層（tier=deep）：逐季摘錄，異常月份（flagged_months.json）幾乎全文收錄，正常
  月份取代表性天數。
輕層（tier=light）：不分季，在整個關係跨度內均勻取樣少數天數，寫成單一
  whole_history.md（訊息量遠低於深層，成本可控，上限見 config_template.py）。

輸出：notes/<slug>/excerpts/*.md + excerpt_index.json
複製到專案後另存為 build_reading_excerpts.py。
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from paths import OUTPUT_ROOT

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg

TOP30_PATH = OUTPUT_ROOT / "relationships" / "data" / "top30.json"
QUANT_DIR = OUTPUT_ROOT / "relationships" / "quant"
NOTES_DIR = OUTPUT_ROOT / "relationships" / "notes"


def load_messages(person_dir):
    msgs = []
    with (person_dir / "messages_full.jsonl").open(encoding="utf-8") as f:
        for line in f:
            msgs.append(json.loads(line))
    return msgs


def cap_day(msgs, max_per_day):
    if len(msgs) <= max_per_day:
        return msgs
    step = len(msgs) / max_per_day
    idxs = sorted({int(i * step) for i in range(max_per_day)})
    return [msgs[i] for i in idxs]


def render_day(day, msgs, max_per_day):
    orig_n = len(msgs)
    msgs = cap_day(msgs, max_per_day)
    suffix = f"（原始 {orig_n} 則，等距抽樣至 {len(msgs)} 則）" if len(msgs) < orig_n else ""
    lines = [f"### {day}{suffix}"]
    for m in msgs:
        t = m["datetime"][11:16]
        if m["type"] == "unsent":
            body = "*(已收回)*"
        elif m["text"]:
            body = m["text"].replace("\n", " ")
        else:
            body = f"[{m['type']}]"
        lines.append(f"- {t} {m['sender']}: {body}")
    return "\n".join(lines)


def build_deep_excerpts(person_dir, notes_dir):
    excerpts_dir = notes_dir / "excerpts"
    excerpts_dir.mkdir(parents=True, exist_ok=True)
    flagged_path = person_dir / "flagged_months.json"
    flagged = set()
    if flagged_path.exists():
        flagged = set(json.loads(flagged_path.read_text(encoding="utf-8"))["flagged_months"])

    msgs = load_messages(person_dir)
    by_month = defaultdict(list)
    by_day = defaultdict(list)
    for m in msgs:
        by_month[m["date"][:7]].append(m)
        by_day[m["date"]].append(m)

    months = sorted(by_month.keys())
    quarters = defaultdict(list)
    for mo in months:
        y, mm = mo.split("-")
        q = (int(mm) - 1) // 3 + 1
        quarters[f"{y}Q{q}"].append(mo)

    stats = []
    for q in sorted(quarters.keys()):
        q_months = quarters[q]
        out_lines = [f"# {q} 對話節錄\n"]
        total_included = 0
        total_in_q = sum(len(by_month[mo]) for mo in q_months)
        for mo in q_months:
            days_in_month = sorted({m["date"] for m in by_month[mo]})
            if mo in flagged:
                if len(days_in_month) > 20:
                    step = max(1, len(days_in_month) // 20)
                    chosen_days = days_in_month[::step]
                else:
                    chosen_days = days_in_month
                out_lines.append(
                    f"\n## {mo}（統計異常月，重點收錄 {len(chosen_days)}/{len(days_in_month)} 天，"
                    f"每天訊息量大時等距抽樣）\n"
                )
            else:
                step = max(1, len(days_in_month) // 6)
                chosen_days = days_in_month[::step][:6]
                out_lines.append(
                    f"\n## {mo}（代表性抽樣 {len(chosen_days)}/{len(days_in_month)} 天）\n"
                )
            for d in chosen_days:
                out_lines.append(render_day(d, by_day[d], cfg.MAX_MSGS_PER_DAY))
                total_included += len(by_day[d])

        content = "\n\n".join(out_lines)
        (excerpts_dir / f"{q}.md").write_text(content, encoding="utf-8")
        stats.append({
            "quarter": q, "months": q_months,
            "flagged_months_in_quarter": [mo for mo in q_months if mo in flagged],
            "total_msgs_in_quarter": total_in_q,
            "included_msgs_in_excerpt": total_included,
        })

    (excerpts_dir / "excerpt_index.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def build_light_excerpt(person_dir, notes_dir):
    excerpts_dir = notes_dir / "excerpts"
    excerpts_dir.mkdir(parents=True, exist_ok=True)
    msgs = load_messages(person_dir)
    by_day = defaultdict(list)
    for m in msgs:
        by_day[m["date"]].append(m)
    days = sorted(by_day.keys())

    if not days:
        (excerpts_dir / "whole_history.md").write_text("（無訊息）", encoding="utf-8")
        stat = {"days_included": 0, "total_days": 0, "total_msgs": 0, "included_msgs": 0}
        (excerpts_dir / "excerpt_index.json").write_text(
            json.dumps(stat, ensure_ascii=False, indent=2), encoding="utf-8")
        return stat

    n_days_target = min(cfg.REPRESENTATIVE_DAYS_LIGHT, len(days))
    step = max(1, len(days) // n_days_target)
    chosen_days = days[::step][:n_days_target]
    max_per_day = max(1, cfg.MAX_TOTAL_MSGS_LIGHT // max(len(chosen_days), 1))

    total_msgs = sum(len(by_day[d]) for d in days)
    out_lines = [f"# 全歷程代表性摘錄（{chosen_days[0]} ~ {chosen_days[-1]}，"
                 f"{len(chosen_days)}/{len(days)} 天）\n"]
    included = 0
    for d in chosen_days:
        out_lines.append(render_day(d, by_day[d], max_per_day))
        included += min(len(by_day[d]), max_per_day)

    content = "\n\n".join(out_lines)
    (excerpts_dir / "whole_history.md").write_text(content, encoding="utf-8")
    stat = {"days_included": len(chosen_days), "total_days": len(days),
            "total_msgs": total_msgs, "included_msgs": included}
    (excerpts_dir / "excerpt_index.json").write_text(
        json.dumps(stat, ensure_ascii=False, indent=2), encoding="utf-8")
    return stat


def main():
    """批次全量跑法。隨選問答單一對象時，改直接呼叫 build_deep_excerpts()／
    build_light_excerpt() 傳入該對象的 person_dir/notes_dir 即可。"""
    top30 = json.loads(TOP30_PATH.read_text(encoding="utf-8"))
    for entry in top30:
        person_dir = QUANT_DIR / entry["person_slug"]
        notes_dir = NOTES_DIR / entry["person_slug"]
        if not (person_dir / "messages_full.jsonl").exists():
            print(f"SKIP {entry['name']}: messages_full.jsonl not found", file=sys.stderr)
            continue
        if entry["tier"] == "deep":
            stats = build_deep_excerpts(person_dir, notes_dir)
            print(f"[{entry['rank']:>2}] {entry['name']} (deep): {len(stats)} quarters", file=sys.stderr)
        else:
            stat = build_light_excerpt(person_dir, notes_dir)
            print(f"[{entry['rank']:>2}] {entry['name']} (light): "
                  f"{stat['days_included']}/{stat.get('total_days', '?')} days sampled", file=sys.stderr)


if __name__ == "__main__":
    main()
