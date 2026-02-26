import os
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def bulk_download_with_playwright():
    # 設定路徑
    source_file = os.path.join("data", "reports_for_notebooklm.md")
    output_folder = "downloaded_reports"
    
    # 建立存檔資料夾
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"已建立資料夾：{output_folder}")

    # 檢查來源檔案是否存在
    if not os.path.exists(source_file):
        print(f"錯誤：找不到檔案 {source_file}")
        return

    # 讀取 Markdown 內容
    with open(source_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 區塊解析法 (精準抓取標題與網址)
    matches = []
    blocks = content.split("---")
    for block in blocks:
        title_match = re.search(r"### ([^\n]+)", block)
        url_match = re.search(r"- \[查看原始報告\]\((https?://[^\)]+)\)", block)
        if title_match and url_match:
            matches.append((title_match.group(1).strip(), url_match.group(1).strip()))

    if not matches:
        print("未偵測到任何有效的 PDF 連結，請檢查 Markdown 格式。")
        return

    print(f"🚀 開始透過 Playwright 隱身模式下載，共計 {len(matches)} 個檔案...")

    # ==========================================
    # 🌟 啟動 Playwright 真實瀏覽器來執行下載
    # ==========================================
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,  # 可以在背景執行
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            accept_downloads=True # 允許下載檔案
        )
        
        page = context.new_page()
        # 披上隱身披風
        Stealth().apply_stealth_sync(page)

        print("  🔑 步驟 1: 前往首頁取得防爬蟲通行證 (Cookie)...")
        page.goto("https://www.ctbcbank.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000) # 讓 JS 執行完畢，確保拿到最高權限 Cookie

        print("  📥 步驟 2: 開始循序下載報告...")
        for i, (title, url) in enumerate(matches, 1):
            clean_title = re.sub(r'[\\/*?:"<>|]', "_", title).strip()
            file_path = os.path.join(output_folder, f"{clean_title}.pdf")

            print(f"[{i}/{len(matches)}] 嘗試下載: {clean_title[:30]}...")

            try:
                # 🌟 關鍵修正：使用 Playwright 專屬的「攔截下載」機制
                with page.expect_download(timeout=30000) as download_info:
                    try:
                        # 當網址直接觸發強制下載時，goto 會拋出 "Download is starting" 的錯誤，我們直接忽略它
                        page.goto(url, timeout=15000)
                    except:
                        pass
                
                # 取得下載下來的檔案物件
                download = download_info.value
                
                # 另存新檔到我們指定的路徑
                download.save_as(file_path)
                print("    ✅ 下載成功！")

            except Exception as e:
                print(f"    ❌ 下載發生異常: {e}")

            # 禮貌性延遲，避免連續轟炸伺服器又被封鎖
            page.wait_for_timeout(2500) 

        browser.close()

    print(f"\n🎉 任務完成！所有真實 PDF 已存於: {os.path.abspath(output_folder)}")

if __name__ == "__main__":
    bulk_download_with_playwright()