# -*- coding: utf-8 -*-
"""
群組模組共用設定：POC 篩選規則、標籤規則閾值。所有可調參數集中在這裡——之後要
調整 POC 篩選或標籤規則，只需要改這裡的常數再重跑 build_group_ranking_template.py
（純 JSON，很便宜）。

方法論細節見同目錄的 說明.md。
複製到專案的 analysis/scripts/group_analysis/ 後另存為 config.py。
"""

# 帳號本人在所有對話中出現過的姓名，跟關係模組的 config 各自維護一份
# （避免跨模組 import 造成耦合）。
SELF_NAMES = {"Account A", "Account B"}  # 換成本人各帳號在匯出裡顯示的名稱

# 參與人數超過這個門檻的視為「課程/廣播型大群組」，排除在 POC 之外——這類群組
# 多數成員從未發言，「每個用戶的分析」對他們沒有意義（見 說明.md「已知限制」）。
MAX_PARTICIPANTS_FOR_POC = 30

# thread_index.json 的 is_likely_spam_thread() 是廣義的關鍵字/規則判斷，會漏掉
# 部分假陰性（例如特定語言的敏感內容關鍵字未涵蓋）。這份清單只在本模組篩選
# POC 時額外排除，不影響 thread_index.json 本身，比照關係模組 config.py 的
# EXCLUDE_NAMES 做法——之後看到新的漏網群組，直接把名稱加進來即可。
EXCLUDE_GROUP_NAMES = set()

TOP_N_GROUPS = 10  # POC 規模

# ---- 每成員量化摘要（build_group_features_template.py，全量掃描，不取樣）----
MEDIA_TYPES = {"photo", "gif", "media", "audio"}

JIEBA_STOPWORDS = set("""的 了 是 我 你 妳 他 她 也 就 在 都 和 有 這 那 個 們 嗎 啊 喔 呢 吧
    很 不 沒 就是 一個 什麼 這個 那個 還是 可以 一下 因為 所以 但是 如果 而且 對 要 會
    去 來 好 沒有 現在 已經 還有 這樣 那樣 大家 自己 一直 覺得 真的 應該 可能 時候
    今天 明天 昨天 訊息 傳送 收回 附件 語音 通話 貼圖 分享
    我們 你們 他們 妳們 她們 上午 下午 時間 怎麼 那邊 這邊 不是 還是 然後
    已經 什麼時候 為什麼 這樣子 那樣子""".split())

# 成員自動標籤規則：每項指標取該群組內排名前 TOP_FRACTION 的成員給予對應標籤
# （至少要有 MIN_MESSAGES_FOR_TAG 則訊息才納入標籤判斷，避免只發過 1-2 則的
# 人被極端比率誤判）。規則刻意簡單、不用 LLM，符合「簡易 persona」的要求。
TAG_TOP_FRACTION = 0.2
MIN_MESSAGES_FOR_TAG = 10
MEMBER_TAG_RULES = [
    ("latenight_rate", "深夜活躍"),
    ("question_rate", "常主動提問"),
    ("exclaim_rate", "情緒外顯"),
    ("media_rate", "貼圖/媒體愛用者"),
    ("message_share", "話最多的人"),
    ("initiation_count", "常主動開啟話題"),
]

# 異常活躍日偵測：該群組單日訊息數的 z-score 超過這個門檻才算「異常活躍日」。
DAILY_SPIKE_ZSCORE = 2.0
