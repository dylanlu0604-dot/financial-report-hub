import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def extract_date(text):
    match = re.search(r'(20[1-3][0-9])[-/.]?(\d{1,2})[-/.]?(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return "未知日期"

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

# ==========================================
# 🕷️ 主爬蟲程式：兆豐銀行 (Mega Bank)
# ==========================================
def scrape():
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 切換分類並等待 API 渲染...")
    reports = []
    seen_links = set()
    
    base_url = "https://www.megabank.com.tw"
    target_url = "https://www.megabank.com.tw/personal/wealth/financial-service/bulletin/weekly-journal"
    # 🌟 關鍵 ID：國際經濟金融週報的 Radio Button Value
    target_category_value = "95afc2755857498aacd3ba2aadcc793b"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 進入頁面
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            # 2. 🌟 動作：點擊「國際經濟金融週報」選項
            # 我們透過標籤內容與 Value 來定位那個 Radio input
            selector = f'input[value="{target_category_value}"]'
            if page.locator(selector).count() > 0:
                print("  🖱️ 正在切換分類至『國際經濟金融週報』...")
                # 有些時候 input 被隱藏，點擊它的父層 Label
                page.locator(selector).evaluate("node => node.click()")
                
                # 3. 🌟 等待：等待列表容器內長出內容
                # 根據 HTML，列表會放在 ul[data-wrapper-weekly-list]
                page.wait_for_selector('ul[data-wrapper-weekly-list] li', timeout=20000)
                print("  ✅ 列表渲染完成")
            else:
                print("  ❌ 找不到分類選項，請檢查網頁是否改版")

            # 4. 解析渲染後的內容
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 找到列表容器
            list_container = soup.select_one('ul[data-wrapper-weekly-list]')
            if list_container:
                items = list_container.select('li.c-dataList__item')
                for item in items:
                    a_tag = item.select_one('a.c-dataItem')
                    if not a_tag: continue
                    
                    title = clean_text(item.select_one('.c-dataItem__title').get_text())
                    date_raw = clean_text(item.select_one('.c-dataItem__date').get_text())
                    href = a_tag.get('href')
                    
                    if href and (".pdf" in href.lower() or "download" in href.lower()):
                        full_url = urljoin(base_url, href)
                        if full_url in seen_links: continue
                        
                        reports.append({
                            "Source": "Mega Bank (兆豐銀行)",
                            "Date": extract_date(date_raw if date_raw else title),
                            "Name": title,
                            "Link": full_url
                        })
                        seen_links.add(full_url)
                        print(f"    📄 抓取成功: {title}")

            browser.close()

    except Exception as e:
        print(f"  ❌ Mega Bank 執行異常: {e}")

    print(f"  ✅ Mega Bank 最終收錄 {len(reports)} 筆週報")
    return reports

if __name__ == "__main__":
    scrape()
