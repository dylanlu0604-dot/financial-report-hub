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
    if not text:
        return "未知日期"
        
    # 1. 處理西元年 (如 2026/02/28, 2026-02-28, 2026.02.28)
    match = re.search(r'(20[1-3][0-9])[^\d]*(\d{1,2})[^\d]*(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    # 2. 處理民國年 (如 115/02/28)
    match_tw = re.search(r'(11[0-9])[^\d]*(\d{1,2})[^\d]*(\d{1,2})', text)
    if match_tw:
        year = int(match_tw.group(1)) + 1911
        return f"{year}-{int(match_tw.group(2)):02d}-{int(match_tw.group(3)):02d}"
        
    return "未知日期"

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

# ==========================================
# 🕷️ 主爬蟲程式：YesFund (好好證券)
# ==========================================
def scrape():
    print("🔍 正在爬取 YesFund (好好證券) - 🎯 啟動框架穿透模式...")
    reports = []
    seen_links = set()
    
    base_url = "https://www.yesfund.com.tw"
    target_url = "https://www.yesfund.com.tw/n/MarketInfo.djhtm"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 進入目標頁面，等待網路穩定
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)  # 給予 MoneyDJ 系統額外的渲染時間
            
            # 🌟 2. 核心邏輯：建立一個通用的 HTML 解析與抓取流程
            def parse_html_for_reports(html_source, source_url):
                soup = BeautifulSoup(html_source, 'html.parser')
                found_count = 0
                
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    text = clean_text(a.get_text())
                    
                    # 判斷是否為 PDF 或是下載連結
                    if '.pdf' in href.lower() or 'download' in href.lower() or 'file' in href.lower():
                        # 排除掉明顯無關的連結 (例如 css, js, 圖片)
                        if any(ext in href.lower() for ext in ['.jpg', '.png', '.css', '.js']):
                            continue
                            
                        full_url = urljoin(source_url, href)
                        
                        if full_url in seen_links:
                            continue
                            
                        # 嘗試抓取標題
                        title = text
                        # 如果連結文字只有「下載」、「PDF」或是空白，往父節點找
                        if not title or title.upper() == "PDF" or "下載" in title:
                            if a.parent:
                                title = clean_text(a.parent.get_text()).replace("下載", "").replace("PDF", "").strip()
                                
                        if not title:
                            title = full_url.split('/')[-1] # 保底用檔名當標題
                            
                        # 嘗試抓取日期：先從標題找，找不到再從父節點整行文字找
                        date_str = extract_date(title)
                        if date_str == "未知日期":
                            if a.parent and a.parent.parent:
                                row_text = clean_text(a.parent.parent.get_text())
                                date_str = extract_date(row_text)
                                
                        reports.append({
                            "Source": "YesFund",
                            "Date": date_str,
                            "Name": title,
                            "Link": full_url
                        })
                        seen_links.add(full_url)
                        found_count += 1
                        print(f"    ✅ 成功收錄: {title[:30]}...")
                return found_count

            # 3. 先掃描主頁面
            total_found = parse_html_for_reports(page.content(), base_url)
            
            # 4. 🌟 穿透掃描 iframe 框架 (針對 MoneyDJ 系統的必殺技)
            for frame in page.frames:
                try:
                    # 如果 iframe 是有效的網址，且不是主網頁自己
                    if frame.url and frame.url != target_url and frame.url != "about:blank":
                        # print(f"  👉 偵測到 iframe: {frame.url[:50]}...")
                        total_found += parse_html_for_reports(frame.content(), frame.url)
                except Exception as frame_err:
                    pass # 忽略跨域讀取權限等報錯
                    
            browser.close()

    except Exception as e:
        print(f"  ❌ YesFund 爬取發生異常: {e}")

    print(f"  ✅ YesFund 最終完美收錄 {len(reports)} 筆報告")
    return reports

if __name__ == "__main__":
    scrape()
