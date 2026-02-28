import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式 (處理日期與標題)
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
# 🕷️ 主爬蟲程式：元大銀行 (Yuanta)
# ==========================================
def scrape():
    print("🔍 正在爬取 Yuanta (元大銀行) - 🎯 包含日報、週報、月報與市場評論...")
    reports = []
    seen_links = set()
    
    base_url = "https://www.yuantabank.com.tw"
    
    # 四個目標網址分類
    target_urls = {
        "投資週報": "https://www.yuantabank.com.tw/bank/invest/research/list.do?dataType=%E6%8A%95%E8%B3%87%E9%80%B1%E5%A0%B1",
        "投資月報": "https://www.yuantabank.com.tw/bank/invest/research/list.do?dataType=%E6%8A%95%E8%B3%87%E6%9C%88%E5%A0%B1",
        "市場評論": "https://www.yuantabank.com.tw/bank/invest/research/list.do?dataType=%E5%B8%82%E5%A0%B4%E8%A9%95%E8%AB%96",
        "每日焦點": "https://www.yuantabank.com.tw/bank/invest/research/list.do?dataType=%E6%AF%8F%E6%97%A5%E7%84%A6%E9%BB%9E"
    }
    
    # 🌟 新增：允許的標題關鍵字
    allowed_keywords = ["投資週報", "投資月報", "投研報告"]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            for category, url in target_urls.items():
                print(f"  👉 進入分類: {category}...")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(3000) 
                    
                    html_content = page.content()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        text = clean_text(a.get_text())
                        
                        if '.pdf' in href.lower() or 'download' in href.lower() or 'file' in href.lower():
                            full_url = urljoin(base_url, href)
                            
                            if full_url in seen_links:
                                continue
                                
                            # 日期萃取
                            date_str = extract_date(text)
                            if date_str == "未知日期" and a.parent:
                                parent_text = clean_text(a.parent.get_text())
                                date_str = extract_date(parent_text)
                            
                            # 標題萃取
                            title = text
                            if not title or "下載" in title or "PDF" in title.upper():
                                if a.parent:
                                    title = clean_text(a.parent.get_text()).replace("下載", "").replace("PDF", "").strip()
                            
                            if not title:
                                title = full_url.split('/')[-1]
                                
                            # 🌟 關鍵新增：檢查標題是否包含指定關鍵字
                            if not any(kw in title for kw in allowed_keywords):
                                continue
                                
                            reports.append({
                                "Source": f"Yuanta ({category})",
                                "Date": date_str,
                                "Name": title,
                                "Link": full_url
                            })
                            seen_links.add(full_url)
                            
                except Exception as cat_e:
                    print(f"  ⚠️ 分類 {category} 爬取失敗: {str(cat_e)[:50]}")
                    
            browser.close()

    except Exception as e:
        print(f"  ❌ Yuanta 爬取過程發生致命錯誤: {e}")

    print(f"  ✅ Yuanta 最終成功收錄 {len(reports)} 筆報告")
    return reports

if __name__ == "__main__":
    import pprint
    result = scrape()
    print("\n📊 測試爬取結果：")
    pprint.pprint(result)
