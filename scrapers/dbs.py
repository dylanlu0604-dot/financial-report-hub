import os
import re
import json
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def scrape():
    print("🔍 正在爬取 DBS (星展銀行) - 🚀 執行「JS 注入暴力點擊」模式...")
    reports = []
    seen_links = set()
    download_path = os.path.abspath("all report pdf")
    os.makedirs(download_path, exist_ok=True)
    
    target_urls = [
        "https://www.dbs.com.tw/personal/aics/investment-strategy/index.page",
        "https://www.dbs.com.tw/personal/aics/economics/index.page"
    ]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                accept_downloads=True
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            for target_url in target_urls:
                category = "Investment Strategy" if "investment-strategy" in target_url else "Economics"
                print(f"  🌐 掃描目錄: {category}")
                page.goto(target_url, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                
                # 滾動加載
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(1000)

                # 提取連結
                links = page.evaluate("""
                    () => Array.from(document.querySelectorAll('a'))
                        .filter(a => a.href.includes('/aics/') && !a.href.includes('index.page'))
                        .map(a => a.href)
                """)
                
                for article_url in list(set(links))[:30]:
                    if article_url in seen_links: continue
                    seen_links.add(article_url)
                    
                    try:
                        page.goto(article_url, wait_until="networkidle", timeout=30000)
                        
                        # 🌟 1. 抓取 Next.js 裡的精準日期
                        raw_data = page.evaluate("() => document.getElementById('__NEXT_DATA__') ? document.getElementById('__NEXT_DATA__').innerText : ''")
                        final_date = datetime.now().strftime("%Y-%m-%d")
                        if raw_data:
                            date_match = re.search(r'"PublishedDate":"(\d{4}-\d{2}-\d{2})', raw_data)
                            if date_match: final_date = date_match.group(1)

                        # 🌟 2. 抓取標題
                        raw_title = page.title().split('|')[0].strip()
                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{raw_title} ({final_date})").strip()
                        
                        print(f"    🔎 正在尋找 Download PDF: {raw_title[:30]}...")

                        # 🌟 3. JS 暴力點擊：直接對著 data-testid 下手
                        try:
                            with page.expect_download(timeout=10000) as download_info:
                                success = page.evaluate("""
                                    () => {
                                        let btn = document.querySelector('[data-testid="download"]');
                                        if (btn) {
                                            btn.click();
                                            return true;
                                        }
                                        return false;
                                    }
                                """)
                                
                                if not success:
                                    print("      ❌ 找不到 data-testid='download' 標籤")
                                    continue
                                    
                            download = download_info.value
                            save_path = os.path.join(download_path, f"{safe_title}.pdf")
                            download.save_as(save_path)
                            
                            reports.append({
                                "Source": f"DBS ({category})",
                                "Date": final_date,
                                "Name": f"{raw_title} ({final_date})",
                                "Link": article_url,
                                "Type": "PDF"
                            })
                            print(f"    ✅ [下載成功] {final_date}")
                            
                        except Exception as e:
                            print(f"      ❌ 下載超時或失敗")
                                
                    except Exception:
                        continue
                        
            browser.close()
            
    except Exception as e:
        print(f"  ❌ 爬取異常: {e}")

    return reports

if __name__ == "__main__":
    scrape()