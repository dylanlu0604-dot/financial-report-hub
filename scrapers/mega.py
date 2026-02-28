import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def extract_date(text):
    match = re.search(r'(\d{4})[^\d]*(\d{1,2})[^\d]*(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return "未知日期"

def scrape():
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 真人點擊與 API 監聽模式...")
    reports = []
    seen_links = set()
    base_url = "https://www.megabank.com.tw"
    target_url = "https://www.megabank.com.tw/personal/wealth/financial-service/bulletin/weekly-journal"
    
    # 這是畫面上實際顯示的按鈕文字
    categories = ["匯率利率資訊", "投資研究週報", "國際經濟金融週報"]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 進入頁面
            page.goto(target_url, wait_until="networkidle", timeout=60000)

            for cat_name in categories:
                print(f"  👉 正在執行：點擊『{cat_name}』並等待資料庫回應...")
                
                try:
                    if cat_name != "匯率利率資訊":
                        # 🌟 核心修正：同時執行「點擊真實文字」與「等待兆豐的 API 回傳新資料」
                        # 兆豐的資料 API 網址包含 QueryReports
                        with page.expect_response(lambda r: "QueryReports" in r.url and r.status == 200, timeout=15000):
                            # 像真人一樣點擊畫面上的文字標籤
                            page.get_by_text(cat_name, exact=True).click()
                        
                        # API 回傳後，給網頁 2 秒鐘把新的 PDF 連結畫到畫面上
                        page.wait_for_timeout(2000)
                    else:
                        # 第一個選項預設已載入
                        page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"    ⚠️ 切換『{cat_name}』時未收到新資料，可能網站架構有變。")

                # 2. 抓取真正更新後的內容
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                items = soup.select('ul[data-wrapper-weekly-list] li.c-dataList__item')
                
                for item in items:
                    a_tag = item.select_one('a.c-dataItem')
                    title_el = item.select_one('.c-dataItem__title')
                    date_el = item.select_one('.c-dataItem__date')
                    
                    if not a_tag or not title_el: continue
                    
                    href = a_tag.get('href', '')
                    title = title_el.get_text(strip=True)
                    date_raw = date_el.get_text(strip=True) if date_el else title
                    
                    full_url = urljoin(base_url, href)
                    
                    if ".pdf" in href.lower() and full_url not in seen_links:
                        reports.append({
                            "Source": f"Mega Bank ({cat_name})", 
                            "Date": extract_date(date_raw),
                            "Name": title,
                            "Link": full_url
                        })
                        seen_links.add(full_url)
                        print(f"      ✅ 成功收錄: [{cat_name}] {title[:20]}...")

            browser.close()
    except Exception as e:
        print(f"  ❌ Mega Bank 執行異常: {e}")

    print(f"  ✅ Mega Bank 任務結束！共取得 {len(reports)} 筆獨立報告")
    return reports

if __name__ == "__main__":
    scrape()
