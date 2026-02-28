import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def extract_date(text):
    match = re.search(r'(20[1-3][0-9])[-/.]?(\d{1,2})[-/.]?(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return "未知日期"

def scrape():
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 全分類深度同步模式...")
    reports = []
    seen_links = set()
    base_url = "https://www.megabank.com.tw"
    target_url = "https://www.megabank.com.tw/personal/wealth/financial-service/bulletin/weekly-journal"
    
    categories = {
        "匯率利率資訊": "9eb52bb02dbf422c9d99fb9afa67136d",
        "投資研究週報": "444b35d4cbe64f1fa586fcf1b8211ac6",
        "國際經濟金融週報": "95afc2755857498aacd3ba2aadcc793b"
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 進入頁面
            page.goto(target_url, wait_until="networkidle", timeout=60000)

            for cat_name, cat_value in categories.items():
                print(f"  👉 正在切換至：『{cat_name}』...")
                
                # 取得切換前的第一個標題，用來判斷內容是否真的更新了
                old_first_title = ""
                first_el = page.locator('ul[data-wrapper-weekly-list] li .c-dataItem__title').first
                if first_el.count() > 0:
                    old_first_title = first_el.inner_text()

                # 點擊分類
                selector = f'input[value="{cat_value}"]'
                page.locator(selector).evaluate("node => node.click()")

                # 🌟 核心等待邏輯：等待 API 回傳且 DOM 內容與舊標題不同
                try:
                    page.wait_for_function(
                        f"""() => {{
                            const el = document.querySelector('ul[data-wrapper-weekly-list] li .c-dataItem__title');
                            return el && el.innerText !== "{old_first_title}";
                        }}""", timeout=15000
                    )
                except:
                    pass # 如果本來就沒內容或內容剛好一樣，就繼續

                # 2. 解析當前標籤頁
                soup = BeautifulSoup(page.content(), 'html.parser')
                items = soup.select('ul[data-wrapper-weekly-list] li.c-dataList__item')
                
                for item in items:
                    a_tag = item.select_one('a.c-dataItem')
                    if not a_tag: continue
                    
                    href = a_tag.get('href', '')
                    if not ('.pdf' in href.lower() or 'download' in href.lower()): continue
                    
                    title = item.select_one('.c-dataItem__title').get_text(strip=True)
                    date_raw = item.select_one('.c-dataItem__date').get_text(strip=True)
                    
                    full_url = urljoin(base_url, href)
                    if full_url in seen_links: continue

                    reports.append({
                        "Source": f"Mega Bank ({cat_name})", 
                        "Date": extract_date(date_raw if date_raw else title),
                        "Name": title,
                        "Link": full_url
                    })
                    seen_links.add(full_url)
                    print(f"    ✅ 已收錄: {title[:20]}...")

            browser.close()
    except Exception as e:
        print(f"  ❌ Mega Bank 錯誤: {e}")

    return reports
