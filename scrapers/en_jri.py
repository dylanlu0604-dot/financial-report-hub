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

def parse_english_date(date_text):
    """將英文日期 (如 February 25, 2026) 轉換為 YYYY-MM-DD"""
    date_text = re.sub(r'\s+', ' ', date_text).strip()
    formats_to_try = ["%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"]
    for fmt in formats_to_try:
        try:
            return datetime.strptime(date_text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_text

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 JRI (日本綜合研究所 英文版)...")
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
                
                # 掃描當前頁面所有的 a 連結
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    full_url = urljoin(base_url, href)
                    
                    # 🎯 情況 A: 連結直接就是 PDF
                    if '.pdf' in href.lower():
                        if full_url in seen_pdfs:
                            continue
                            
                        title = a.get_text(strip=True)
                        if not title or len(title) < 5:
                            title = unquote(href.split('/')[-1].replace('.pdf', ''))
                            
                        # 尋找鄰近的日期
                        parent_text = a.parent.get_text(strip=True) if a.parent else ""
                        date_str = "未知日期"
                        
                        # 找 YYYY/MM/DD 格式
                        date_match = re.search(r'([0-9]{4}[/.-][0-9]{2}[/.-][0-9]{2})', parent_text)
                        if date_match:
                            date_str = date_match.group(1).replace('/', '-').replace('.', '-')
                        else:
                            # 找英文日期格式 (例如 Jan 01, 2026)
                            date_match_en = re.search(r'([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})', parent_text)
                            if date_match_en:
                                date_str = parse_english_date(date_match_en.group(1))
                                
                        reports.append({
                            "Source": "JRI (EN)",
                            "Date": date_str,
                            "Name": clean_title(title),
                            "Link": full_url
                        })
                        seen_pdfs.add(full_url)
                        
                    # 🎯 情況 B: 連結是指向其他報告的「內頁」
                    elif ('/en/reports/' in href or '/en/media/' in href) and not href.endswith('.pdf') and not href.startswith('#'):
                        # 排除掉自己(列表頁)跟首頁
                        if full_url not in target_urls and full_url not in article_links:
                            article_links.append(full_url)
                
                # 若發現有內頁，啟動深度挖掘 (這裡設定只挖前 10 篇，可自行修改數字)
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
                                        # 抓大標題
                                        title_tag = inner_soup.find('h1')
                                        title = title_tag.get_text(strip=True) if title_tag else unquote(inner_href.split('/')[-1])
                                        
                                        # 抓內頁的日期
                                        date_str = "未知日期"
                                        date_match = re.search(r'([0-9]{4}[/.-][0-9]{2}[/.-][0-9]{2})', inner_html)
                                        if date_match:
                                            date_str = date_match.group(1).replace('/', '-').replace('.', '-')
                                        else:
                                            date_match_en = re.search(r'([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})', inner_html)
                                            if date_match_en:
                                                date_str = parse_english_date(date_match_en.group(1))

                                        reports.append({
                                            "Source": "JRI (EN)",
                                            "Date": date_str,
                                            "Name": clean_title(title),
                                            "Link": pdf_full_url
                                        })
                                        seen_pdfs.add(pdf_full_url)
                                        print(f"    ✔️ 成功捕獲 (內頁): {clean_title(title)[:30]}...")
                                    break # 通常一個內頁只對應一個主要 PDF
                                    
                        except Exception as e:
                            pass # 忽略內頁的超時或壞軌
                            
            browser.close()

    except Exception as e:
        print(f"  ❌ JRI (EN) 爬取失敗: {e}")

    print(f"  ✅ JRI (EN) 最終成功收錄 {len(reports)} 筆報告")
    return reports