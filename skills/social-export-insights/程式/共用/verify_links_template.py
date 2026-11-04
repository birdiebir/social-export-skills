"""
驗證 analysis/output/ 底下所有 .html 檔案的相對連結（href/src）是否都能實際解析到存在的檔案。

用法:
    python verify_links.py <output 根目錄>

檢查邏輯:
    掃描 <output 根目錄> 底下所有 *.html，抓出所有 href="..."/src="..." 屬性，
    排除 http(s)/mailto/javascript/純錨點(#...) 之後，把剩下的相對路徑相對於該 html
    檔案所在資料夾解析，若解析後的檔案不存在，判定為壞連結。

    只檢查連結是否「存在」，不驗證內容是否正確（例如連到錯的人）——那是質性審閱
    該做的事，這支腳本只抓「點了完全打不開」這種最低層級但最容易被忽略的 bug。

為什麼需要這支腳本（2026-09-21 踩坑，見 `分析\踩坑.md`）：
    report.html 產生器（Python f-string 模板）裡的相對路徑深度（幾個 "../"）是手算的，
    只要輸出檔案的巢狀深度跟模板作者當初心算的不一樣（例如某個 quant/<slug>/report.html
    其實在 output/ 底下第 3 層，模板卻只寫了 "../../"），就會產生大量壞連結，且：
    - 開發時用瀏覽器點過幾個連結「看起來正常」就會誤判為沒問題（沒點到壞的那個）
    - CSS/JS 資源用 <link>/<script> 引入，資源載入失敗通常不會讓頁面明顯報錯，
      使用者只會覺得「這頁怎麼樣式跑掉/圖表不見了」，不會馬上聯想到連結路徑錯誤
    - 沒有自動化檢查的話，這類 bug 要等使用者實際點到壞掉的那個連結才會發現
    一次真實案例：relationships 模組數十個 quant/<slug>/report.html 的 CSS/JS/導覽連結、
    以及 messages 模組數百筆聊天存檔連結，全部因為模板裡 "../../" 少算一層而全部失效，
    產出時腳本本身沒有任何報錯或警告。

建議用法：每次新增或修改任何 report.html 產生器之後，重新產生輸出後立刻跑一次本腳本，
在 commit/交付前確認 0 broken links。
"""
import io
import os
import re
import sys
import glob
import urllib.parse

# See verify_quotes.py for why this is needed on Windows consoles.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HREF_SRC_RE = re.compile(r'(?:href|src)="([^"]+)"')
SKIP_PREFIXES = ("http://", "https://", "mailto:", "javascript:", "#")


def find_broken_links(root):
    broken = []
    for f in glob.glob(os.path.join(root, "**", "*.html"), recursive=True):
        dirpath = os.path.dirname(f)
        with open(f, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        for m in HREF_SRC_RE.finditer(content):
            link = m.group(1)
            if link.startswith(SKIP_PREFIXES):
                continue
            link_path = link.split("#")[0]
            if not link_path:
                continue
            link_path = urllib.parse.unquote(link_path)
            target = os.path.normpath(os.path.join(dirpath, link_path))
            if not os.path.exists(target):
                broken.append((os.path.relpath(f, root), link))
    return broken


def main():
    if len(sys.argv) != 2:
        print("用法: python verify_links.py <output 根目錄>")
        sys.exit(2)

    root = sys.argv[1]
    broken = find_broken_links(root)

    if broken:
        print(f"[FAIL] 發現 {len(broken)} 個壞連結：")
        for src, link in broken:
            print(f"  - {src} -> {link}")
        sys.exit(1)

    print("[PASS] 0 broken links")
    sys.exit(0)


if __name__ == "__main__":
    main()
