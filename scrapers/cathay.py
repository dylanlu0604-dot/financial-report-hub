from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, unquote
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def clean_title(title):
    return title.replace('\n', ' ').strip()

def extract_date_from_text(text):
    """嘗試從字串中萃取多種格式的日期"""
    # 1. 處理 YYYY年MM月DD日 (容許單數月/日)
    match = re.search(r'([0-9]{4})\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    # 2. 處理 民國年 (例如 115年2月5日 -> 2026-02-05)
    match = re.search(r'(11[0-9])\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日', text)
    if match:
        year = int(match.group(1)) + 1911
        return f"{year}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    # 3. 處理 YYYY/MM/DD 或 YYYY.MM.DD 或 YYYY-MM-DD (容許單數月/日)
    match = re.search(r'([0-9]{4})[/.-]([0-9]{1,2})[/.-]([0-9]{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    # 4. 處理 YYYYMMDD (連續8個數字)
    match = re.search(r'(20[1-3][0-9])([0-1][0-9])([0-3][0-9])', text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
    return "未知日期"

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Cathay (國泰世華) - 🎯 精準鎖定『投資研究週報』...")
    reports = []
    seen_pdfs = set()
    
    base_url = "https://www.cathaybk.com.tw"
    target_url = "https://www.cathaybk.com.tw/cathaybk/personal/wealth/market/report/#tab1"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000) 
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 🌟 核心修正：先在整個頁面中尋找共用的備註日期
            global_date_str = "未知日期"
            remark_div = soup.find('div', class_='cubinvest-l-remark__item', string=re.compile("資料日期"))
            if remark_div:
                global_date_str = extract_date_from_text(remark_div.get_text(strip=True))

            for a in soup.find_all('a', href=True):
                href = a['href']
                
                if '.pdf' in href.lower():
                    # 處理標題
                    title = a.get_text(strip=True)
                    if not title:
                        title = a.get('title', '')
                    if not title:
                        title = unquote(href.split('/')[-1].replace('.pdf', '').replace('.PDF', ''))
                        
                    if "投資研究週報" not in title and "投資研究週報" not in unquote(href):
                        continue
                        
                    full_url = urljoin(base_url, href)
                    if full_url in seen_pdfs:
                        continue
                        
                    # 依序套用日期尋找策略
                    date_str = extract_date_from_text(title)
                    
                    if date_str == "未知日期" and a.parent:
                        date_str = extract_date_from_text(a.parent.get_text(strip=True))
                    
                    if date_str == "未知日期":
                        date_str = extract_date_from_text(unquote(href))
                        
                    # 🌟 如果上面都找不到，套用剛剛找到的全域備註日期
                    if date_str == "未知日期":
                        date_str = global_date_str
                        
                    reports.append({
                        "Source": "Cathay",
                        "Date": date_str,
                        "Name": clean_title(title),
                        "Link": full_url
                    })
                    seen_pdfs.add(full_url)
                    
            browser.close()

    except Exception as e:
        print(f"  ❌ Cathay 爬取失敗: {e}")

    print(f"  ✅ Cathay 最終成功收錄 {len(reports)} 筆『投資研究週報』")
    return reports

if __name__ == "__main__":
    import pprint
    result = scrape()
    print("\n📊 測試爬取結果：")
    pprint.pprint(result)
