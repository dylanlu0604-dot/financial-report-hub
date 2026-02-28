import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def extract_date(text):
    """從標題或行內文字萃取日期"""
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
# 🕷️ 主爬蟲程序：兆豐銀行 (Mega Bank)
# ==========================================
def scrape():
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 修正動態載入與標題匹配...")
    reports = []
    seen_links = set()
    
    base_url = "https://www.megabank.com.tw"
    target_url = "https://www.megabank.com.tw/personal/wealth/financial-service/bulletin/weekly-journal"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 進入頁面並等待網路穩定
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            # 🌟 修正點 A：等待列表表格出現 (兆豐的列表通常在 table 或 .list 內)
            try:
                page.wait_for_selector("tr", timeout=15000)
            except:
                print("  ⚠️ 等待列表超時，嘗試直接解析...")

            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 🌟 修正點 B：改以「列 (tr)」或「包裝容器」為單位掃描
            # 兆豐的結構通常是一行 row 裡面有日期、標題、跟一個 PDF 下載按鈕
            rows = soup.find_all(['tr', 'li', 'div'], class_=re.compile(r'item|row|list', re.I))
            
            # 如果找不到特定的 row，就退回找所有的連結，但檢查其父層文字
            targets = rows if rows else soup.find_all('a', href=True)

            for item in targets:
                item_text = clean_text(item.get_text())
                
                # 檢查這一區塊是否包含關鍵字
                if "國際經濟金融週報" in item_text:
                    # 在這個區塊內尋找 PDF 連結
                    a_tag = item if item.name == 'a' else item.find('a', href=True)
                    
                    if a_tag and a_tag.has_attr('href'):
                        href = a_tag['href']
                        # 只要是 PDF 或有 download 字樣都收
                        if '.pdf' in href.lower() or 'download' in href.lower():
                            full_url = urljoin(base_url, href)
                            
                            if full_url in seen_links:
                                continue
                            
                            # 萃取日期與標題
                            date_str = extract_date(item_text)
                            title = item_text.split('\n')[0].strip() # 抓取區塊文字的第一行作為標題
                            
                            # 保底：如果標題太長，修剪一下
                            if len(title) > 100:
                                title = "國際經濟金融週報" + (re.search(r'第\d+期', item_text).group(0) if re.search(r'第\d+期', item_text) else "")
                            
                            reports.append({
                                "Source": "Mega Bank (兆豐銀行)",
                                "Date": date_str,
                                "Name": title if title else "國際經濟金融週報",
                                "Link": full_url
                            })
                            seen_links.add(full_url)
                            print(f"    ✅ 成功抓取: {title}")

            browser.close()

    except Exception as e:
        print(f"  ❌ Mega Bank 爬取發生錯誤: {e}")

    # 🌟 最終保底：如果真的還是 0 筆，回傳一個空列表但印出偵錯資訊
    if len(reports) == 0:
        print("  💡 提示：抓到 0 筆，可能是關鍵字完全不匹配或頁面結構大改。")

    print(f"  ✅ Mega Bank 最終成功收錄 {len(reports)} 筆報告")
    return reports

if __name__ == "__main__":
    scrape()
