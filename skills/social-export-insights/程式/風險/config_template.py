# -*- coding: utf-8 -*-
# 注意：這是偵測用詞表，內含冒犯字眼是為了偵測，不代表立場。
"""
風險模組共用設定：關鍵字分類、PII 正則、嚴重度標籤。所有可調參數集中在這裡
——原專案的 flag_candidates.py 把這些寫死在腳本裡，這裡依「config 集中」的
L7 紀律搬出來，方便之後調整關鍵字/嚴重度定義不用碰 pipeline 程式碼。

複製到專案的 analysis/scripts/pr_risk/ 後另存為 config.py。
"""
import re

# 要跑關鍵字預篩的文字類別（對應 output/pr_risk/data/<category>.jsonl）。
TEXT_CATEGORIES = ["posts", "comments", "group_activity"]

KEYWORD_GROUPS = {
    "political_social": [
        "政治", "政黨", "國民黨", "民進黨", "台獨", "統一", "中國", "共產黨", "罷免", "選舉", "投票給",
        "示威", "抗議", "遊行", "戰爭", "以色列", "巴勒斯坦", "俄羅斯", "烏克蘭", "宗教", "同婚", "墮胎",
        "移民", "難民", "警察", "政府", "貪污", "抗中", "反共",
    ],
    "discriminatory_offensive": [
        "白癡", "智障", "廢物", "垃圾", "去死", "幹你", "婊子", "賤", "支那", "死gay", "娘炮", "殘障",
        "外勞", "越南新娘", "歧視", "種族", "黑鬼", "阿6", "低能",
    ],
    "workplace": [
        "老闆", "公司", "同事", "客戶", "資遣", "離職", "面試", "薪水", "加班", "打卡", "主管", "職場",
        "勞資", "資方", "客訴", "離職原因",
    ],
    "illegal_grayarea": [
        "賭博", "簽賭", "毒品", "大麻", "盜版", "外掛", "私煙", "私菸", "詐騙", "洗錢", "槍", "違法",
        "偷", "闖紅燈", "酒駕", "無照",
    ],
    "conflict_report": [
        "檢舉", "黑名單", "報警", "提告", "告你", "吵架", "撕破臉", "絕交", "封鎖", "仇恨", "威脅",
        "恐嚇", "公審", "出征",
    ],
    "pii_leak": [
        "身分證字號", "身分證", "護照號碼", "信用卡號", "銀行帳號", "地址是", "電話是", "手機號碼",
    ],
}

PII_PATTERN_RE = re.compile(
    r'\b[A-Z][12]\d{8}\b'                      # TW ID number
    r'|\b09\d{2}[- ]?\d{3}[- ]?\d{3}\b'         # TW mobile number
    r'|\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b' # credit-card-like
)

# 分層抽樣：對「沒被關鍵字命中」的內容，每年抽這麼多則，交給質性審閱抓關鍵字
# 漏掉的部分（反諷、暗語、委婉說法）。
STRATIFIED_SAMPLE_PER_YEAR = 15

# 由高到低嚴重度排序（僅供關鍵字命中類別的降級呈現用；有 reviewed.jsonl 時，
# finalize_pr_risk_report_template.py 改用 LLM 判讀的 assessed_severity 分組，
# 不是這份查表——見 說明.md「為什麼需要 L5」）。
SEVERITY_ORDER = [
    "pii_leak", "pii_pattern", "illegal_grayarea", "discriminatory_offensive",
    "conflict_report", "workplace", "political_social",
]
SEVERITY_LABEL = {
    "pii_leak": "個資外洩",
    "pii_pattern": "疑似個資型態",
    "illegal_grayarea": "疑似違法/灰色地帶",
    "discriminatory_offensive": "歧視/冒犯性言論",
    "conflict_report": "衝突/糾紛紀錄",
    "workplace": "職場相關",
    "political_social": "政治/社會議題",
}
CATEGORY_LABEL = {"posts": "貼文", "comments": "留言", "group_activity": "社團貼文/留言"}
