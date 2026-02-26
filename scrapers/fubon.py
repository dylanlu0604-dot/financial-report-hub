from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, unquote
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def is_within_30_days(date_text):
    if not date_text: return False
    try:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return (datetime.now() - dt).days <= 30
    except:
        return True # 若格式特殊無法解析，先放行

def clean_title(title):
    # 移除多餘空白、換行，以及可能的日期前綴
    title = title.replace('\n', ' ').strip()
    title = re.sub(r'^[0-9]{4}[/.-][0-9]{2}[/.-][0-9]{2}\s*', '', title)
    return title

def extract_date_from_text(text):
    # 尋找 2026/02/13 或 2026-02-13 這種格式
    match = re.search(r'([0-9]{4})[/.-]([0-9]{2})[/.-]([0-9]{2})', text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Fubon (富邦銀行)...")
    reports = []
    seen_urls = set()
    
    base_url = "https://www.fubon.com"
    target_urls = [
        "https://www.fubon.com/banking/Corporate/Financial_Market/research_project/research_project.htm",
        "https://www.fubon.com/banking/Corporate/Financial_Market/research_invest/research_invest.htm",
        "https://www.fubon.com/banking/Corporate/Financial_Market/research_report/research_report.htm"
    ]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, # 富邦通常不嚴格，可以直接用背景模式
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 依序爬取三個網頁
            for url in target_urls:
                print(f"  🌐 正在載入: {url.split('/')[-1]}...")
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000) # 給予基礎渲染時間
                
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # 尋找所有帶有 .pdf 的連結
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if '.pdf' in href.lower():
                        full_url = urljoin(base_url, href)
                        
                        if full_url in seen_urls:
                            continue
                        
                        # 1. 抓取標題
                        title = link.get_text(strip=True)
                        if not title or len(title) < 3:
                            title = link.get('title', '')
                        if not title or len(title) < 3:
                            # 若無標題，從網址檔名萃取
                            title = unquote(full_url.split('/')[-1].replace('.pdf', '').replace('.PDF', ''))
                        
                        # 2. 抓取日期
                        date_text = extract_date_from_text(title)
                        parent = link.parent
                        
                        # 如果標題裡沒日期，往外層父元素 (例如 li, div, tr) 尋找日期字串
                        if not date_text and parent:
                            parent_text = parent.get_text(strip=True)
                            date_text = extract_date_from_text(parent_text)
                            
                        # 如果上一層還沒有，再往上一層找
                        if not date_text and parent.parent:
                            date_text = extract_date_from_text(parent.parent.get_text(strip=True))
                        
                        # 3. 過濾 30 天內的報告
                        if date_text and not is_within_30_days(date_text):
                            continue
                            
                        # 清理標題，並將報告加入清單
                        title = clean_title(title)
                        
                        reports.append({
                            "Source": "Fubon",
                            "Date": date_text if date_text else "未知日期",
                            "Name": title,
                            "Link": full_url
                        })
                        seen_urls.add(full_url)
                        
            browser.close()

    except Exception as e:
        print(f"  ❌ Fubon 爬取失敗: {e}")

    print(f"  ✅ Fubon 最終成功收錄 {len(reports)} 筆報告")
    return reports