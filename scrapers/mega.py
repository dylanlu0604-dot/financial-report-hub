import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def extract_date(text):
    """精準萃取報告中的日期"""
    match = re.search(r'(\d{4})[^\d]*(\d{1,2})[^\d]*(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return "未知日期"

def scrape():
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 修正分類內容同步問題...")
    reports = []
    seen_links = set()
    base_url = "https://www.megabank.com.tw"
    target_url = "https://www.megabank.com.tw/personal/wealth/financial-service/bulletin/weekly-journal"
    
    # 我們要抓這三個分類
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
                print(f"  👉 正在執行：切換至『{cat_name}』分類...")
                
                # 🌟 核心修正點：點擊前先截取目前列表的第一筆標題文字
                # 用來判斷點擊後，網頁內容是否真的「變了」
                old_title = ""
                first_item_title = page.locator('ul[data-wrapper-weekly-list] li .c-dataItem__title').first
                if first_item_title.count() > 0:
                    old_title = first_item_title.inner_text().strip()

                # 執行點擊分類
                selector = f'input[value="{cat_value}"]'
                page.locator(selector).evaluate("node => node.click()")

                # 🌟 核心修正點：強制等待內容更新
                # 必須滿足兩個條件：1. API跑完 2. 畫面上第一筆資料的標題與點擊前不同
                try:
                    if old_title:
                        # 等待直到第一個標題文字不等於 old_title
                        page.wait_for_function(
                            f"document.querySelector('ul[data-wrapper-weekly-list] li .c-dataItem__title').innerText.trim() !== '{old_title}'",
                            timeout=15000
                        )
                    else:
                        # 如果原本沒內容，就等內容長出來
                        page.wait_for_selector('ul[data-wrapper-weekly-list] li', timeout=15000)
                    
                    page.wait_for_timeout(2000) # 給予額外緩衝確保 PDF 連結渲染完成
                except:
                    print(f"    ⚠️ 分類『{cat_name}』載入超時，可能內容未更新或本來就沒資料")

                # 2. 解析當前標籤內容
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                items = soup.select('ul[data-wrapper-weekly-list] li.c-dataList__item')
                
                print(f"    📊 偵測到 {len(items)} 筆原始資料，開始處理...")
                
                for item in items:
                    a_tag = item.select_one('a.c-dataItem')
                    title_el = item.select_one('.c-dataItem__title')
                    date_el = item.select_one('.c-dataItem__date')
                    
                    if not a_tag or not title_el: continue
                    
                    href = a_tag.get('href', '')
                    title = title_el.get_text(strip=True)
                    date_raw = date_el.get_text(strip=True) if date_el else title
                    
                    # 再次確認標題是否包含分類關鍵字（二次驗證，防止標籤錯置）
                    # 例如：在「國際週報」分類下，標題卻出現「匯率利率」，就該報錯或跳過
                    if "匯率" in cat_name and "週報" in title and "匯率" not in title: continue
                    
                    full_url = urljoin(base_url, href)
                    if ".pdf" in href.lower() and full_url not in seen_links:
                        reports.append({
                            "Source": f"Mega Bank ({cat_name})", 
                            "Date": extract_date(date_raw),
                            "Name": title,
                            "Link": full_url
                        })
                        seen_links.add(full_url)
                        print(f"      ✅ 成功收錄: {title[:20]}...")

            browser.close()
    except Exception as e:
        print(f"  ❌ Mega Bank 執行異常: {e}")

    print(f"  ✅ 任務結束！Mega Bank 最後提交 {len(reports)} 筆不重覆且正確標記的報告")
    return reports
