import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def extract_date(text):
    """從標題或欄位中萃取標準日期格式"""
    match = re.search(r'(20[1-3][0-9])[-/.]?(\d{1,2})[-/.]?(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    match_tw = re.search(r'(11[0-9])[-/.]?(\d{1,2})[-/.]?(\d{1,2})', text)
    if match_tw:
        year = int(match_tw.group(1)) + 1911
        return f"{year}-{int(match_tw.group(2)):02d}-{int(match_tw.group(3)):02d}"
    return "未知日期"

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

# ==========================================
# 🕷️ 主爬蟲程式：兆豐銀行 (Mega Bank)
# ==========================================
def scrape():
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 目標：匯率利率、投資週報、總經週報...")
    reports = []
    seen_links = set()
    
    base_url = "https://www.megabank.com.tw"
    target_url = "https://www.megabank.com.tw/personal/wealth/financial-service/bulletin/weekly-journal"
    
    # 🌟 完整的分類對應表
    categories = {
        "匯率利率資訊": "9eb52bb02dbf422c9d99fb9afa67136d",
        "投資研究週報": "444b35d4cbe64f1fa586fcf1b8211ac6",
        "國際經濟金融週報": "95afc2755857498aacd3ba2aadcc793b"
    }

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
            
            # 2. 依次切換三個分類
            for cat_name, cat_value in categories.items():
                print(f"  👉 切換分類至：『{cat_name}』...")
                
                selector = f'input[value="{cat_value}"]'
                if page.locator(selector).count() > 0:
                    # 強制點擊對應分類按鈕
                    page.locator(selector).evaluate("node => node.click()")
                    
                    # 3. 等待新分類的清單內容渲染完成
                    try:
                        # 等待 ul 下出現 li 項目
                        page.wait_for_selector('ul[data-wrapper-weekly-list] li', timeout=15000)
                        page.wait_for_timeout(1000) 
                    except:
                        print(f"    ⚠️ 分類『{cat_name}』無內容或載入超時，跳過...")
                        continue

                    # 4. 解析 HTML 內容
                    soup = BeautifulSoup(page.content(), 'html.parser')
                    list_items = soup.select('ul[data-wrapper-weekly-list] li.c-dataList__item')
                    
                    for item in list_items:
                        a_tag = item.select_one('a.c-dataItem')
                        if not a_tag: continue
                        
                        href = a_tag.get('href', '')
                        title_el = item.select_one('.c-dataItem__title')
                        date_el = item.select_one('.c-dataItem__date')
                        
                        if href and (".pdf" in href.lower() or "download" in href.lower()):
                            full_url = urljoin(base_url, href)
                            if full_url in seen_links: continue
                            
                            title_text = clean_text(title_el.get_text()) if title_el else "未命名報告"
                            date_text = clean_text(date_el.get_text()) if date_el else ""
                            
                            reports.append({
                                "Source": f"Mega Bank ({cat_name})", 
                                "Date": extract_date(date_text if date_text else title_text),
                                "Name": title_text,
                                "Link": full_url
                            })
                            seen_links.add(full_url)
                            print(f"    ✅ 成功收錄: [{cat_name}] {title_text[:25]}...")
                else:
                    print(f"  ❌ 無法定位分類 {cat_name} 的切換按鈕")

            browser.close()

    except Exception as e:
        print(f"  ❌ Mega Bank 執行異常: {e}")

    print(f"  ✅ Mega Bank 最終成功收錄 {len(reports)} 筆各類資料")
    return reports

if __name__ == "__main__":
    scrape()
