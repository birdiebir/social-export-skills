---
name: social-export-insights
description: Use when the user asks a natural-language question about a specific person/relationship, group, or PR-risk concern derived from an already-organized personal social-data export (Facebook Messenger today) — e.g. "這個人最近是不是變冷淡了", "我最近的人脈狀況", "有沒有PR風險", "這個群組在幹嘛" — or wants to add a new deep-analysis capability on top of one. Also use whenever the user asks for a specific analysis depth on a conversation/group — "輕量分析"/"中量分析"/"深度分析" or "light/medium/heavy analysis", "幫我對這幾個對話做中量分析" — this skill owns the light/medium/deep tier system (see 分析/分層.md) and its verbatim-quote/coverage verification scripts; don't hand-roll a one-off analysis pass without checking here first. Requires analysis/output/messages/data/thread_index.json to already exist (see social-export-analysis skill first if not).
---

# Social Export Insights

深度分析架構——把「候選排名 → 量化特徵 → [可選] LLM 範本化質性判讀 → 報告組頁」這套已在真實專案（一個 10GB 以上的 Facebook 匯出）驗證過的通用模式，封裝成可擴充的骨架＋一組已驗證的範例模組。**這個 skill 的核心產品是架構本身，不是任何單一領域**。三個範例模組（關係、群組、風險）示範這套架構在不同情境下該怎麼套用，而不是本 skill 唯一支援的功能清單。

## 跟 `social-export-analysis` 的邊界

- `social-export-analysis` 管「原始匯出 zip → 結構化 JSONL/derived 資料」。
- 本 skill 管「結構化資料 → 深度洞察」，疊在前者之上。
- 沒有現成的結構化資料時（`analysis/output/messages/data/thread_index.json` 不存在），先觸發 `social-export-analysis`，但只需要它的 identity/social/messages 三個 domain——細節見 `分析\前置.md`。**不要重新實作萃取/解析邏輯**，這是本 skill 最容易犯的邊界錯誤。

## 7 層通用模式

完整說明見 `分析\架構.md`；速查表：

| 層 | 做什麼 | 特徵 |
|---|---|---|
| L1 抽取 | 原始 HTML/JSON → `output/<domain>/data/*.jsonl` | 屬於 `social-export-analysis`，本 skill 只消費其產出 |
| L2 候選排名/篩選 | 便宜欄位（不重掃原始檔）算分、篩出 top-N | config.py 集中權重/門檻＋人工排除清單＋疊代優化紀錄表 |
| L3 跨領域 join | 合併多個 domain 的 JSONL | 姓名比對只在雙邊都唯一時算 confident，否則進 ambiguous，寫進 `_meta.caveats` |
| L4 量化特徵 | 逐目標算統計（關鍵詞/情緒/趨勢/規則式標籤） | 規則式自動標籤（top X% 給固定標籤）是好用的輕量替代方案，不一定要上 LLM |
| L5 LLM 範本化質性判讀 | 可編輯 markdown 範本＋分派獨立 subagent＋結構化輸出 | **無法腳本化的一層**；不是每個模組都需要，需要時才做，做的話務必範本化、可重跑，不要變成一次性手寫散文；投入多深看下方「三層分析深度」 |
| L6 報告/dashboard 組頁 | 只讀已算好的 JSON，不重新解析原始檔 | 共用元件庫、離線可用、對未完成對象優雅降級 |
| L7 跨領域紀律 | 貫穿全部層，非流程步驟 | sanity/regression check、config 集中、先查共用 lib 再寫新邏輯 |

## 三層分析深度（輕／中／深）

任何目標的分析投入分幾層做，完整定義、驗證門檻、群組全量通讀程序見 `分析\分層.md`；速記：

- **預設不分析**：新/擴充模組先只確保 L1 原始資料齊全、可依量體瀏覽（見下方 L1 說明），不要自動往下推進到任何一層——使用者明確指定要做到哪一層、對哪些目標，才動手。
- **輕**：L4 量化特徵/規則式標籤（附幾句便宜 NLP 摘要即可），通常不做 L5。
- **中**：質性敘事 ＋ 結構化事件時間軸／逐字語錄／語氣序列三份 JSON，語錄與涵蓋率**必須**過 `程式\共用\verify_quotes_template.py`／`verify_coverage_template.py` 驗證才算完成。
- **深**：中層全部 ＋ 完整量化建模（迴歸/PCA+KMeans/TF-IDF），只給少數手選的旗艦目標。

這取代了 `relationships/` 模組原本綁死「排名前 10 深層、11-30 輕層」的兩層規則——分層現在是依需求指定，不是排名自動決定；旗艦模組的深/輕質性範本仍可沿用，但中層才是「事件/語錄/語氣」這套結構化產出的標準做法。

`分析\分層.md` 還有一份「整包結構與選單」——依目標類型＋分層列出完整輸出目錄樹（選中層會拿到哪些檔案），交付前後都可以拿來核對範圍，不是要你另外跑一支生成器。

## 三個範例模組

| 模組 | 位置 | 示範什麼 |
|---|---|---|
| 關係 | `程式\關係\` | 旗艦範例，L1-L6 全套，尤其是成熟的 L5（深/輕兩層範本） |
| 群組 | `程式\群組\` | 刻意不做 L5 的對照範例——規則式標籤 pattern，何時該用純統計 |
| 風險 | `程式\風險\` | 示範把「手動寫散文」的判讀升級成範本化 L5（新範本，不是原專案原封不動搬過來的） |

`security`、`photo_library`、`messages` 查詢工具層、`reports` 彙整層目前只有方法論、還沒模組化——需要時照 `分析\擴充.md` 的步驟，複製最相近的範例模組調整即可。**`photo_library` 要先分清楚兩件事**：把照片依人/依時間重新整理成 hardlink 媒體庫，屬於 L1（原始資料重組），已經是 `social-export-analysis` skill 的範圍（`scripts/photo_library_template.py`）；本 skill 如果要做 `相片庫` 模組，指的是候選比對/查找工具（依參考照片找相似候選、依對話列出照片），是 L2 候選排名＋L8 查詢工具，不是重做媒體庫本身——見 `分析\擴充.md` 的判斷方式。

## 自然語言問答（預設互動模式）

依問題判斷最小必要步驟、走快取、直接在對話中回答，不強制寫檔——完整決策表、實體解析、快取/新鮮度機制見 `分析\問答.md`。選範疇式輸出（quant-only／完整筆記／人物側寫）是次要、明確要求才做的路徑。

## 新增模組

「幫我加一個新的分析領域」這類架構性請求，走 `分析\擴充.md` 的步驟。**不要**寫一個自動生成模組骨架的工具——目前只有 3 個真正落地的範例模組，做這種抽象化還太早；用「複製最相近範例模組＋改 config/範本」的手動流程。

## 已知坑

完整清單（含每條坑的成因與對策）見 `分析\踩坑.md`。最容易忘記檢查的三條：`recency` 類的時間基準要用語料庫自己的最新時間戳、不能用「今天」；候選排名第一次真跑幾乎一定會混進非目標對象（企業帳號、廣播群組…），要靠人工排除清單修，不是一次就能寫對規則；中層以上任何聲稱「已通讀」「語錄已核對」的產出，一律要跑 `程式\共用\` 的驗證腳本，不能只信任 agent 自我陳述的涵蓋率或逐字性。

## 實戰經驗補充（2026-10）

同一個人兩個帳號的匯出專案，連續做過多批補強之後，又累積了一些經驗。動手前先看對應的檔案：

| 什麼時候 | 讀哪份 | 最容易出事的一條 |
|---|---|---|
| 要把筆記寫成結論（知識庫、報告），或核對使用者／PM 給的數字 | `分析\查證與協作.md` | 抽樣筆記的語意錯誤率非常高，結論以全讀版為準；使用者說法跟資料衝突時兩邊都查、照實回報，不要跟著翻盤；事實題整理成一次問完的清單 |
| 讀訊息做質化判讀 | `分析\查證與協作.md` §5 | 文字欄只有「IP 位址」的那則是本人傳的貼圖，不是系統通知；事件換成當地時間；範本字句和 Meta AI 回答不是本人發言；「斷聯」先查是不是換帳號 |
| 有兩個以上帳號 | `social-export-analysis` 的 `references\multi-account.md` | 帳號看「哪一份匯出＋發言者別名」，時期看日期；共同串扣重複、只分析一次 |
| PR 風險審閱 | `分析\PR審閱.md` | 逐筆審閱、附錨點、`scope: segment`、待審歸零；判準跟使用者確認後維持；洗版的成因要問使用者 |
| 多個 agent 平行做分析 | `social-export-analysis` 的 `references\parallel-agents.md` | 每個 agent 只寫自己的範圍，主線統一跑 package／check／commit；回報彙整成檔案 |
| 讓使用者填確認清單再回寫，或確認跨帳號共同人物（2026-10-01 新增） | `分析\查證與協作.md` §6 | 回寫先 dry-run，讀到 0 筆是警訊；使用者確認要能覆蓋規則判定，而且要有「不同人」這一級 |
| 寫或驗證任何語錄、正文引號（2026-10 新增） | `分析\查證與協作.md` §8、`程式\共用\quotes_strict_template.py` | 全部模組共用同一支 strict 驗證器；正文引號用 `inline_terms`／`inline_source` 登記；抽樣處理會漏判，要全量 |
| 新寫任何敘事、時間軸、年度回顧（2026-10 新增） | `分析\查證與協作.md` §9、`分析\人生時間軸.md` | 一律派第二個 agent 回 L1 做語意複查（實測錯誤率兩到三成）；只收確定／高信心的事實；換成當地日期；回報日不是發生日；草稿不是已寄出 |
| 分很多批平行寫大量小對象，或把各批的事實線索彙整成勾選表（2026-10 新增） | `分析\查證與協作.md` §11 | 先設校準閘門，複查找到的錯誤類型立刻補進共同規則；最常犯的是「A 說 X，B 回 Y」順序壓錯；判「L1 沒有」前先全文搜尋；「我們」不能推成本人 |
| 專案收尾，把勾選表、回填表寫進事實表與知識庫，再做獨立查核（2026-10 新增） | `分析\查證與協作.md` §12 | 從中間表抄的日期要再換當地；看得到的時間點不是發生日；單次事件不寫成規則；新寫入逐筆查、已核的抽查 |
| 抽樣寫成的大型對象，使用者還沒決定要不要全讀（2026-10-01 新增） | `分析\查證與協作.md` §7 | 先做 strict 引文驗證（同一則、同一分鐘、心情回應不算），全讀前不寫新結論進知識庫 |

新踩的坑先寫進專案自己的經驗檔。同類問題第二次出現，或會讓結論錯的，就去掉個資、改成虛構例子，提煉進這裡或 `分析\踩坑.md`。
