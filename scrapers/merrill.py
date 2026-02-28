import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    # 🌟 請認明這行字：智能等待防漏版
    print("🔍 正在爬取 Merrill Lynch (美林) - 🎯 Capital Market Outlook (智能等待防漏版)...")
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
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass 
                
            # 🌟 關鍵修正 1：智能等待動態腳本 (JavaScript) 載入報告清單
            print("  👉 正在等待美林伺服器傳送報告資料 (等待 {{title}} 變數解析)...")
            try:
                # 盯著網頁看，直到代表未載入完成的 {{title}} 消失，且畫面上的 <a> 標籤夠多為止
                page.wait_for_function("() => !document.body.innerText.includes('{{title}}') && document.querySelectorAll('a').length > 20", timeout=20000)
                page.wait_for_timeout(3000) # 給它額外 3 秒鐘讓 PDF 連結完整掛載
            except Exception:
                print("  ⚠️ 智能等待超時，嘗試強制解析當前畫面...")
                page.wait_for_timeout(5000)
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            # 找出所有包含 .pdf 的連結
            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf', re.IGNORECASE))
            
            for a in pdf_links:
                href = a.get('href', '')
                full_url = urljoin(base_url, href)
                
                # 排除重複網址
                if full_url in seen_links:
                    continue
                    
                # 🌟 關鍵修正 2：放寬過濾條件，只要檔名包含 capital 或 outlook 即可 (不抓底線或連字號的語病)
                is_cmo_pdf = 'capital' in href.lower() or 'outlook' in href.lower() or 'cmo' in href.lower()
                
                # 抓取這顆按鈕周圍的文字容器
                parent_container = a.find_parent('div', class_=re.compile(r'content|text|article', re.I)) or a.find_parent('li') or a.parent
                parent_text = clean_text(parent_container.get_text(separator=' ')) if parent_container else ""
                
                # 尋找標準日期格式 (例如 February 23, 2026)
                date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})', parent_text, re.IGNORECASE)
                
                # 如果這份 PDF 不是 CMO 檔名，周圍也沒有日期，很可能是隱私權條款，直接跳過
                if not is_cmo_pdf and not date_match:
                    continue

                # 3. 抓取標題
                raw_title = clean_text(a.get_text(separator=' '))
                if not raw_title or len(raw_title) < 5:
                    if parent_container:
                        # 從周圍的標題標籤提取文字
                        headings = parent_container.find_all(['h2', 'h3', 'h4', 'strong', 'p'])
                        for h in headings:
                            t = clean_text(h.get_text())
                            # 找出夠長且不只是寫著 "Capital Market Outlook" 的真實文章標題
                            if len(t) > 10 and t.lower() != 'capital market outlook':
                                raw_title = t
                                break
                
                clean_title = raw_title.replace("Download", "").replace("PDF", "").replace("pdf", "").strip()
                
                if not clean_title or len(clean_title) < 5:
                    clean_title = "Weekly Market Insights"
                
                # 4. 解析日期並清理標題中的殘留日期文字
                report_date = datetime.now().strftime("%Y-%m-%d")
                
                if date_match:
                    try:
                        month_str = date_match.group(1)[:3].title()
                        day_str = date_match.group(2)
                        year_str = date_match.group(3)
                        date_obj = datetime.strptime(f"{month_str} {day_str}, {year_str}", "%b %d, %Y")
                        report_date = date_obj.strftime("%Y-%m-%d")
                        
                        clean_title = re.sub(date_match.group(0), "", clean_title).strip()
                    except:
                        pass
                
                # 清除標題前後的無意義符號
                clean_title = re.sub(r'^[|\- ]+|[|\- ]+$', '', clean_title).strip()

                reports.append({
                    "Source": "Merrill Lynch (CMO)",
                    "Date": report_date,
                    "Name": f"CMO - {clean_title[:60]}", # 加上 CMO 前綴讓報表更整齊
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
