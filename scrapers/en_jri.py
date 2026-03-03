import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def clean_title(title):
    return title.replace('\n', ' ').strip()

def parse_english_date(date_text):
    """將英文日期轉換為 YYYY-MM-DD"""
    date_text = re.sub(r'\s+', ' ', date_text).strip()
    date_text = date_text.replace(',', '').replace('.', '')
    
    formats_to_try = [
        "%B %d %Y", "%b %d %Y", 
        "%d %B %Y", "%d %b %Y",
        "%B %Y", "%b %Y"
    ]
    for fmt in formats_to_try:
        try:
            return datetime.strptime(date_text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_text

def extract_date_from_text(text):
    """從一段純文字中，精準提取出日期格式"""
    date_match = re.search(r'([0-9]{4}[/.-][0-9]{2}[/.-][0-9]{2})', text)
    if date_match:
        return date_match.group(1).replace('/', '-').replace('.', '-')
        
    MONTHS = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    pattern1 = rf'({MONTHS}\.?\s+\d{{1,2}},?\s+\d{{4}})'
    pattern2 = rf'(\d{{1,2}}\s+{MONTHS}\.?\s+\d{{4}})'
    pattern3 = rf'({MONTHS}\.?\s+\d{{4}})'
    
    for pat in [pattern1, pattern2, pattern3]:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return parse_english_date(match.group(1))
            
    return "未知日期"

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 JRI (日本綜合研究所 英文版) - 📅 啟用增強標題與日期萃取引擎...")
    reports = []
    seen_pdfs = set()
    
    base_url = "https://www.jri.co.jp"
    target_urls = [
        "https://www.jri.co.jp/en/reports/asia/",
        "https://www.jri.co.jp/en/reports/reports/"
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
                print(f"  🌐 正在載入: {url.split('/')[-2]}...")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                
                article_links = []
                
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    full_url = urljoin(base_url, href)
                    
                    # 🎯 情況 A: 連結直接就是 PDF
                    if '.pdf' in href.lower():
                        if full_url in seen_pdfs:
                            continue
                            
                        # 找日期
                        container = a.find_parent(['li', 'tr', 'div', 'dd', 'p'])
                        parent_text = container.get_text(separator=' ', strip=True) if container else a.get_text(separator=' ', strip=True)
                        date_str = extract_date_from_text(parent_text)
                        
                        # 找標題
                        title = a.get_text(strip=True)
                        if not title or len(title) < 3:
                            img = a.find('img')
                            if img and img.get('alt'):
                                title = img.get('alt').strip()
                        if not title or len(title) < 3:
                            title = unquote(href.split('/')[-1].replace('.pdf', ''))
                        
                        # 🌟 終極保險
                        if not title or len(clean_title(title)) < 3:
                            title = f"JRI (EN) Report {date_str}"
                            
                        reports.append({
                            "Source": "JRI (EN)",
                            "Date": date_str,
                            "Name": clean_title(title),
                            "Link": full_url,
                            "Type": "PDF"
                        })
                        seen_pdfs.add(full_url)
                        
                    # 🎯 情況 B: 連結是指向其他報告的「內頁」
                    elif ('/en/reports/' in href or '/en/media/' in href) and not href.endswith('.pdf') and not href.startswith('#'):
                        if full_url not in target_urls and full_url not in article_links:
                            article_links.append(full_url)
                
                if article_links:
                    print(f"  🎯 發現 {len(article_links)} 個潛在內頁，準備深度挖掘...")
                    for article_url in article_links[:10]:
                        try:
                            page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_timeout(1000)
                            
                            inner_html = page.content()
                            inner_soup = BeautifulSoup(inner_html, 'html.parser')
                            
                            for inner_a in inner_soup.find_all('a', href=True):
                                inner_href = inner_a['href']
                                if '.pdf' in inner_href.lower():
                                    pdf_full_url = urljoin(base_url, inner_href)
                                    
                                    if pdf_full_url not in seen_pdfs:
                                        # 找日期
                                        for script in inner_soup(["script", "style", "noscript", "meta", "header", "footer", "nav"]):
                                            script.extract()
                                        time_elem = inner_soup.find('time') or inner_soup.find(class_=re.compile(r'date|time', re.I))
                                        visible_text = time_elem.get_text(separator=' ', strip=True) if time_elem else inner_soup.get_text(separator=' ', strip=True)
                                        date_str = extract_date_from_text(visible_text)

                                        # 找標題
                                        title = ""
                                        title_tag = inner_soup.find('h1')
                                        if title_tag:
                                            title = title_tag.get_text(strip=True)
                                        if not title or len(title) < 3:
                                            title_tag = inner_soup.find('title')
                                            if title_tag:
                                                title = title_tag.get_text(strip=True).split('|')[0].strip()
                                        if not title or len(title) < 3:
                                            title = unquote(inner_href.split('/')[-1].replace('.pdf', ''))
                                            
                                        # 🌟 終極保險
                                        if not title or len(clean_title(title)) < 3:
                                            title = f"JRI (EN) Report {date_str}"

                                        reports.append({
                                            "Source": "JRI (EN)",
                                            "Date": date_str,
                                            "Name": clean_title(title),
                                            "Link": pdf_full_url,
                                            "Type": "PDF"
                                        })
                                        seen_pdfs.add(pdf_full_url)
                                        print(f"    ✔️ 成功捕獲 (內頁): {clean_title(title)[:30]}... ({date_str})")
                                    break 
                        except Exception as e:
                            pass 
                            
            browser.close()

    except Exception as e:
        print(f"  ❌ JRI (EN) 爬取失敗: {e}")

    print(f"  ✅ JRI (EN) 最終成功收錄 {len(reports)} 筆報告")
    return reports
