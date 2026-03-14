import os
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

# ==========================================
# 🕷️ 主爬蟲程式：Archive 彙整模式
# ==========================================
def scrape():
    print("🔍 正在爬取 DBS (星展銀行) - 📂 Archive 彙整模式 (自動跳過 YouTube影片)...")
    reports = []
    seen_links = set()
    download_path = os.path.abspath("all report pdf")
    os.makedirs(download_path, exist_ok=True)
    
    # 🎯 直接鎖定你提供的 Archive 頁面
    target_url = "https://www.dbs.com.tw/personal/aics/archive/index.page"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                accept_downloads=True
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            print(f"  🌐 掃描目錄: Archive 總表")
            
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
            except Exception as e:
                print(f"    ⚠️ 目錄載入超時: {str(e)[:30]}")
                return reports
            
            # 滾動加載更多歷史報告 (調高次數以確保抓到足夠的 Archive 資料)
            for _ in range(5):
                page.evaluate("window.scrollBy(0, 1000)")
                page.wait_for_timeout(1000)

            # 提取內頁連結，並過濾掉明確的外部 YouTube 連結
            links = page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                    .filter(a => {
                        let h = a.href.toLowerCase();
                        let isAics = h.includes('/aics/');
                        let isNotMenu = !h.includes('index.page');
                        let isNotYoutube = !h.includes('youtube.com') && !h.includes('youtu.be');
                        return isAics && isNotMenu && isNotYoutube;
                    })
                    .map(a => a.href)
            """)
            
            valid_links = list(set(links))
            print(f"    🎯 發現 {len(valid_links)} 篇潛在連結，準備進入內頁檢查與下載...")
            
            for article_url in valid_links[:30]:  # 根據需求可調整最大抓取數量
                if article_url in seen_links: continue
                seen_links.add(article_url)
                
                success = False
                for attempt in range(2):
                    try:
                        page.goto(article_url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(3000)
                        
                        # 🌟 核心防禦：偵測內頁是否嵌有 YouTube 影片，有的話直接跳過！
                        has_youtube_iframe = page.evaluate("""
                            () => document.querySelectorAll('iframe[src*="youtube"]').length > 0
                        """)
                        if has_youtube_iframe:
                            print("    ⏭️ 偵測到 YouTube 影片內容，自動跳過本篇。")
                            success = True  # 標記為成功處理 (跳過)，不須重試
                            break
                        
                        # 1. 抓取 Next.js 裡的精準日期
                        raw_data = page.evaluate("() => document.getElementById('__NEXT_DATA__') ? document.getElementById('__NEXT_DATA__').innerText : ''")
                        final_date = datetime.now().strftime("%Y-%m-%d")
                        if raw_data:
                            date_match = re.search(r'"PublishedDate":"(\d{4}-\d{2}-\d{2})', raw_data)
                            if date_match: final_date = date_match.group(1)

                        # 2. 抓取標題
                        raw_title = page.title().split('|')[0].strip()
                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{raw_title} ({final_date})").strip()
                        
                        print(f"    🔎 尋找 Download PDF: {raw_title[:25]}...")

                        # 3. JS 暴力點擊：直接對著 data-testid 下手
                        try:
                            with page.expect_download(timeout=10000) as download_info:
                                clicked = page.evaluate("""
                                    () => {
                                        let btn = document.querySelector('[data-testid="download"]');
                                        if (btn) {
                                            btn.click();
                                            return true;
                                        }
                                        return false;
                                    }
                                """)
                                
                            if not clicked:
                                print("      ❌ 找不到 Download PDF 按鈕 (非 PDF 報告)")
                                success = True 
                                break
                                
                            download = download_info.value
                            save_path = os.path.join(download_path, f"{safe_title}.pdf")
                            download.save_as(save_path)
                            
                            reports.append({
                                "Source": "DBS",
                                "Date": final_date,
                                "Name": f"{raw_title} ({final_date})",
                                "Link": article_url,
                                "Type": "PDF"
                            })
                            print(f"      ✅ [下載成功] {final_date}")
                            success = True
                            break 
                            
                        except Exception as de:
                            print(f"      ❌ 下載超時或攔截失敗: {str(de)[:30]}")
                            success = True 
                            break
                            
                    except Exception as e:
                        print(f"    ⚠️ 內頁載入失敗 (第 {attempt+1} 次): {str(e)[:30]}")
                        page.wait_for_timeout(1000)
                        
                if not success:
                    print(f"    ❌ 內頁最終放棄: {article_url}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ 爬取總體異常: {e}")

    return reports

if __name__ == "__main__":
    scrape()
