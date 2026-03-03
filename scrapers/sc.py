import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Standard Chartered (渣打銀行) - 🎯 Latest Market Views...")
    reports = []
    seen_links = set()
    base_url = "https://www.sc.com"
    target_url = "https://www.sc.com/en/wealth-retail-banking/private-banking/latest-market-views/"
    
    # 🚫 定義黑名單關鍵字 (只要標題包含這些字眼，就會被直接略過)
    blacklist_keywords = [
        "Refocusing on growth and earnings",
        "Modern slavery statement",
        "Our Code of Conduct and Ethics"
    ]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 進入目標頁面
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000) # 給網頁 3 秒鐘渲染文章清單
            except Exception as e:
                print(f"  ⚠️ 渣打主頁載入超時，嘗試強制解析...")
                
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            # 2. 渣打的 PDF 通常直接附在列表的 <a> 標籤上，我們直接找包含 .pdf 的連結
            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf', re.IGNORECASE))
            
            for a in pdf_links:
                href = a.get('href')
                full_url = urljoin(base_url, href)
                
                if full_url in seen_links:
                    continue
                
                # 取得標題並清理無用的系統文字
                raw_title = clean_text(a.get_text(separator=' '))
                if not raw_title or len(raw_title) < 3:
                    # 如果連結剛好綁在 icon 上，就往父節點找文字
                    if a.parent:
                        raw_title = clean_text(a.parent.get_text(separator=' '))
                
                clean_title = raw_title.replace("(Opens in a new window)", "").replace("pdf", "").replace("|", "").strip()
                
                # 🌟🌟🌟 新增黑名單過濾機制 🌟🌟🌟
                # 檢查清理後的標題是否包含任何黑名單關鍵字 (忽略大小寫以確保精準攔截)
                is_blacklisted = False
                for keyword in blacklist_keywords:
                    if keyword.lower() in clean_title.lower():
                        is_blacklisted = True
                        break
                        
                if is_blacklisted:
                    print(f"    🚫 觸發黑名單，跳過非報告文件: {clean_title[:40]}...")
                    continue # 直接跳過這個迴圈，不收錄此檔案
                
                # 3. 抓取日期：往父節點尋找 (例如 February 27, 2026)
                report_date = datetime.now().strftime("%Y-%m-%d") # 預設今天
                parent_container = a.find_parent('div') or a.find_parent('li')
                parent_text = clean_text(parent_container.get_text(separator=' ') if parent_container else raw_title)
                
                date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})', parent_text, re.IGNORECASE)
                
                if date_match:
                    try:
                        month_str = date_match.group(1)[:3].title()
                        day_str = date_match.group(2)
                        year_str = date_match.group(3)
                        date_obj = datetime.strptime(f"{month_str} {day_str}, {year_str}", "%b %d, %Y")
                        report_date = date_obj.strftime("%Y-%m-%d")
                        
                        # 把標題裡的日期文字也清掉，保持標題乾淨
                        clean_title = re.sub(date_match.group(0), "", clean_title).strip()
                    except:
                        pass
                
                # 清除標題前後可能殘留的符號
                clean_title = re.sub(r'^[|\- ]+|[|\- ]+$', '', clean_title).strip()
                
                # 4. 偵測渣打的專屬分類標籤
                category = "Market Views" # 預設分類
                if "Weekly Market Views" in parent_text: category = "Weekly Market Views"
                elif "Market Watch" in parent_text: category = "Market Watch"
                elif "Global Market Outlook" in parent_text: category = "Global Market Outlook"
                elif "Thematic Reports" in parent_text: category = "Thematic Reports"

                reports.append({
                    "Source": f"渣打銀行 ({category})",
                    "Date": report_date,
                    "Name": clean_title,
                    "Link": full_url,
                    "Type": "PDF"
                })
                seen_links.add(full_url)
                print(f"    ✅ 收錄: [{report_date}] {clean_title[:30]}...")

            browser.close()
            
    except Exception as e:
        print(f"  ❌ Standard Chartered 爬取異常: {e}")

    print(f"  ✅ 渣打銀行最終成功收錄 {len(reports)} 篇報告")
    return reports

if __name__ == "__main__":
    scrape()
