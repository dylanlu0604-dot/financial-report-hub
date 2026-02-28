import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Merrill Lynch (美林) - 🎯 Capital Market Outlook...")
    reports = []
    seen_links = set()
    base_url = "https://www.ml.com"
    target_url = "https://www.ml.com/capital-market-outlook.html"

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
                page.goto(target_url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                pass # 就算超時，只要主要內容出來了就好
                
            page.wait_for_timeout(3000) # 給動態框架 (JavaScript) 渲染文章清單的時間
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            # 美林的網頁通常將 PDF 放在 <a> 標籤中，且 href 包含 .pdf
            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf', re.IGNORECASE))
            
            for a in pdf_links:
                href = a.get('href')
                full_url = urljoin(base_url, href)
                
                # 排除重複網址，並只抓包含 capital-market-outlook 的主要報告
                if full_url in seen_links or 'capital-market-outlook' not in href.lower():
                    continue
                
                # 2. 抓取標題：美林的結構有時文字不在 <a> 裡面，而在它的父節點周圍
                raw_title = clean_text(a.get_text(separator=' '))
                parent_container = a.find_parent('div') or a.find_parent('li')
                
                if not raw_title or len(raw_title) < 5:
                    # 嘗試從附近的標題標籤 (h2, h3, h4, 或是 strong) 提取報告名稱
                    if parent_container:
                        headings = parent_container.find_all(['h2', 'h3', 'h4', 'strong'])
                        if headings:
                            raw_title = clean_text(headings[0].get_text())
                
                clean_title = raw_title.replace("Download", "").replace("PDF", "").replace("pdf", "").strip()
                
                # 如果找不到合適標題，給予預設名稱
                if not clean_title or len(clean_title) < 5:
                    clean_title = "Capital Market Outlook"
                
                # 3. 抓取日期：使用我們寫好的強大正則表達式
                report_date = datetime.now().strftime("%Y-%m-%d") # 預設今天
                parent_text = clean_text(parent_container.get_text(separator=' ') if parent_container else "")
                
                date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})', parent_text, re.IGNORECASE)
                
                if date_match:
                    try:
                        month_str = date_match.group(1)[:3].title()
                        day_str = date_match.group(2)
                        year_str = date_match.group(3)
                        date_obj = datetime.strptime(f"{month_str} {day_str}, {year_str}", "%b %d, %Y")
                        report_date = date_obj.strftime("%Y-%m-%d")
                        
                        # 把標題裡的日期文字清乾淨
                        clean_title = re.sub(date_match.group(0), "", clean_title).strip()
                    except:
                        pass
                
                reports.append({
                    "Source": "Merrill Lynch (CMO)",
                    "Date": report_date,
                    "Name": clean_title,
                    "Link": full_url,
                    "Type": "PDF"
                })
                seen_links.add(full_url)
                print(f"    ✅ 收錄: [{report_date}] {clean_title[:30]}...")

            browser.close()
            
    except Exception as e:
        print(f"  ❌ Merrill Lynch 爬取異常: {e}")

    print(f"  ✅ 美林最終成功收錄 {len(reports)} 篇報告")
    return reports

if __name__ == "__main__":
    scrape()
