import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def extract_date(text):
    """嘗試從字串中萃取西元年或民國年格式的日期"""
    # 1. 處理 YYYY/MM/DD 或 YYYY-MM-DD 或 YYYY.MM.DD
    match = re.search(r'(20[1-3][0-9])[-/.]?(\d{1,2})[-/.]?(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    # 2. 處理 民國年 (例如 115.02.28 -> 2026-02-28)
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
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 鎖定『國際經濟金融週報』...")
    reports = []
    seen_links = set()
    
    base_url = "https://www.megabank.com.tw"
    target_url = "https://www.megabank.com.tw/personal/wealth/financial-service/bulletin/weekly-journal"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)  # 等待動態內容與列表渲染
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = clean_text(a.get_text())
                
                if '.pdf' in href.lower() or 'download' in href.lower() or 'file' in href.lower():
                    full_url = urljoin(base_url, href)
                    
                    if full_url in seen_links:
                        continue
                        
                    # 嘗試萃取標題
                    title = text
                    if not title or "下載" in title or "PDF" in title.upper():
                        if a.parent:
                            title = clean_text(a.parent.get_text()).replace("下載", "").replace("PDF", "").strip()
                            
                    if not title:
                        title = full_url.split('/')[-1]
                        
                    # 🌟 關鍵過濾條件：必須包含「國際經濟金融週報」
                    if "國際經濟金融週報" not in title and "國際經濟金融週報" not in text:
                        continue
                        
                    # 萃取日期
                    date_str = extract_date(title)
                    if date_str == "未知日期" and a.parent:
                        parent_text = clean_text(a.parent.get_text())
                        date_str = extract_date(parent_text)
                        
                    reports.append({
                        "Source": "Mega Bank (兆豐銀行)",
                        "Date": date_str,
                        "Name": title,
                        "Link": full_url
                    })
                    seen_links.add(full_url)
                    
            browser.close()

    except Exception as e:
        print(f"  ❌ Mega Bank 爬取發生錯誤: {e}")

    print(f"  ✅ Mega Bank 最終成功收錄 {len(reports)} 筆『國際經濟金融週報』")
    return reports

if __name__ == "__main__":
    import pprint
    result = scrape()
    print("\n📊 測試爬取結果：")
    pprint.pprint(result)
