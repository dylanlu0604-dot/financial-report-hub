import os
import re
import urllib.parse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def clean_title(title):
    return re.sub(r'\s+', ' ', title).strip() if title else ""

def parse_english_date(date_text):
    date_text = re.sub(r'\s+', ' ', date_text).strip().replace(',', '').replace('.', '')
    formats_to_try = ["%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y", "%B %Y", "%b %Y"]
    for fmt in formats_to_try:
        try: return datetime.strptime(date_text, fmt).strftime("%Y-%m-%d")
        except: continue
    return date_text

def extract_date_from_text(text):
    if not text: return "未知日期"
    
    # 找標準格式 YYYY/MM/DD 或 YYYY-MM-DD
    date_match = re.search(r'([0-9]{4}[/.-][0-9]{2}[/.-][0-9]{2})', text)
    if date_match: return date_match.group(1).replace('/', '-').replace('.', '-')
    
    # 🌟 新增：找美式格式 MM/DD/YYYY (例如 02/25/2026 或 2/5/2026)
    us_date_match = re.search(r'\b([0-9]{1,2})[/.-]([0-9]{1,2})[/.-]([0-9]{4})\b', text)
    if us_date_match:
        m, d, y = us_date_match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
        
    MONTHS = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    for pat in [rf'({MONTHS}\.?\s+\d{{1,2}},?\s+\d{{4}})', rf'(\d{{1,2}}\s+{MONTHS}\.?\s+\d{{4}})', rf'({MONTHS}\.?\s+\d{{4}})']:
        match = re.search(pat, text, re.IGNORECASE)
        if match: return parse_english_date(match.group(1))
        
    return "未知日期"

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Wells Fargo (富國銀行) - 🚀 啟用全視角無盲區轉印模式 (支援美式日期)...")
    reports = []
    seen_links = set()
    base_url = "https://www.wellsfargo.com"
    target_urls = [
        "https://www.wellsfargo.com/cib/insights/economics/weekly-commentary/",
        "https://www.wellsfargo.com/cib/insights/economics/special-reports/",
        "https://www.wellsfargo.com/cib/insights/economics/us-outlook/",
        "https://www.wellsfargo.com/cib/insights/economics/indicators/",
        "https://www.wellsfargo.com/cib/insights/economics/international-outlook/",
        "https://www.wellsfargo.com/cib/insights/economics/international-reports/"
    ]
    
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
            
            for url in target_urls:
                category = url.strip('/').split('/')[-1].replace('-', ' ').title()
                print(f"  🌐 正在掃描分類: {category}...")
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    print("    ⏳ 網頁已連線，強制等待 8 秒讓 JavaScript 渲染報告清單...")
                    page.wait_for_timeout(4000) 
                    page.evaluate("window.scrollBy(0, 1000)") 
                    page.wait_for_timeout(4000)
                except Exception as e:
                    print(f"  ⚠️ {category} 載入發生超時: {e}")
                
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                all_links = soup.find_all('a', href=True)
                
                potential_articles = []
                for a in all_links:
                    href = a.get('href', '').strip()
                    if not href or href.lower().startswith('javascript'):
                        continue
                        
                    full_url = urllib.parse.urljoin(url, href)
                    
                    # 🌟 修正：去除網址最後的錨點 (#) 與結尾斜線，確保比對精準
                    clean_full_url = full_url.split('#')[0].rstrip('/')
                    clean_target_url = url.split('#')[0].rstrip('/')
                    
                    # 🌟 修正：只要這個網址「不等於」當前目錄頁，我們就認為它是潛在的文章！
                    if clean_full_url == clean_target_url or clean_full_url in seen_links:
                        continue
                    
                    # 排除明顯無關的雜訊連結
                    if any(x in clean_full_url.lower() for x in ['privacy', 'terms', 'security', 'contact', 'about', 'login', 'subscribe', 'facebook', 'twitter', 'linkedin']):
                        continue
                        
                    # 取得周圍文字來判斷是不是報告
                    container = a.find_parent(['article', 'li', 'tr', 'div'])
                    parent_text = container.get_text(separator=' ', strip=True) if container else a.get_text(strip=True)
                    if len(parent_text) > 400: parent_text = a.get_text(separator=' ', strip=True)
                        
                    date_str = extract_date_from_text(parent_text)
                    
                    # 🌟 寬鬆判定：只要有日期，或是網址包含 insights，就收錄！
                    if date_str != "未知日期" or '/insights/' in clean_full_url.lower():
                        potential_articles.append((a, clean_full_url, date_str))
                        seen_links.add(clean_full_url)
                
                if len(potential_articles) == 0:
                    print(f"    ⚠️ 找不到半篇報告！雷達探測模式啟動 (印出前 3 個網址供除錯):")
                    for debug_a in all_links[:3]:
                        print(f"      - {urllib.parse.urljoin(url, debug_a.get('href', ''))}")
                else:
                    print(f"    🎯 此頁面共找到 {len(potential_articles)} 篇潛在網頁報告，開始解析...")
                
                for a, full_url, date_str in potential_articles[:15]: 
                    try:
                        title = clean_title(a.get_text())
                        
                        if not title or len(title) < 5 or title.lower() in ['read more', 'download', 'learn more']:
                            container = a.find_parent(['article', 'li', 'tr', 'div'])
                            h_tag = container.find(['h2', 'h3', 'h4', 'strong']) if container else None
                            if h_tag: title = clean_title(h_tag.get_text())
                            elif container: title = clean_title(container.get_text(separator=' ', strip=True)[:100])
                        
                        if not title or len(title) < 5:
                            title = urllib.parse.unquote(full_url.split('/')[-1].replace('-', ' ').replace('.html', ''))
                            
                        # 清理標題中殘留的日期
                        date_match = re.search(r'([A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s+\d{4})', title, re.IGNORECASE)
                        if date_match: title = title.replace(date_match.group(1), '').strip()
                        title = re.sub(r'^[|\- ]+|[|\- ]+$', '', title).strip()
                        
                        if not title or len(title) < 3:
                            title = f"Wells Fargo {category} Report {date_str}"
                            
                        reports.append({
                            "Source": f"Wells Fargo ({category})",
                            "Date": date_str,
                            "Name": title,
                            "Link": full_url
                            # HTML 轉印模式，沒有 Type: PDF
                        })
                        print(f"    🌐 [網頁轉印] 收錄: [{date_str}] {title[:40]}...")
                        
                    except Exception as loop_e:
                        print(f"    ⚠️ 單一報告解析錯誤跳過: {loop_e}")
                        continue
                        
            browser.close()
            
    except Exception as e:
        print(f"  ❌ Wells Fargo 爬取異常: {e}")

    print(f"  ✅ 總共收錄 {len(reports)} 篇 Wells Fargo 網頁報告")
    return reports

if __name__ == "__main__":
    scrape()
