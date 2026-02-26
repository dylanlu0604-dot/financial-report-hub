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
    """將英文日期轉換為 YYYY-MM-DD"""
    date_text = re.sub(r'\s+', ' ', date_text).strip()
    formats_to_try = [
        "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", 
        "%d %B %y", "%d %b %y"
    ]
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
    print("🔍 正在爬取 ING Think - 🎯 鎖定最新經濟與金融分析報告...")
    reports = []
    seen_urls = set()
    
    base_url = "https://think.ing.com"
    list_url = "https://think.ing.com/"
    
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
            
            print(f"  🌐 正在載入 ING Think 列表頁...")
            page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 1. 蒐集所有文章的內頁連結
            article_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                
                # 🌟 修正：嚴格過濾掉目錄頁與分頁
                if '/articles/' in href or '/reports/' in href:
                    clean_href = href.split('?')[0].strip('/')
                    # 排除首頁目錄、分頁、作者介紹頁面
                    if clean_href in ['articles', 'reports'] or '/page/' in href or 'author' in href:
                        continue
                        
                    full_url = urljoin(base_url, href)
                    if full_url != list_url and full_url not in article_links:
                        article_links.append(full_url)
            
            print(f"  🎯 找到 {len(article_links)} 篇潛在文章，準備進入內頁尋找資料...")
            
            # 2. 逐一進入內頁尋找 PDF 及細節 (設定只抓前 12 篇)
            for article_url in article_links[:12]: 
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)
                    
                    inner_html = page.content()
                    inner_soup = BeautifulSoup(inner_html, 'html.parser')
                    
                    pdf_link = None
                    for a in inner_soup.find_all('a', href=True):
                        href_lower = a['href'].lower()
                        if '.pdf' in href_lower or '/downloads/pdf/' in href_lower:
                            pdf_link = urljoin(base_url, a['href'])
                            break
                    
                    final_link = pdf_link if pdf_link else article_url
                    if final_link in seen_urls:
                        continue
                        
                    title_tag = inner_soup.find('h1')
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                    else:
                        title = unquote(article_url.split('/')[-1].replace('-', ' '))
                    
                    # 🌟 修正：二次檢查，如果標題太短或是剛好等於分類名稱，就跳過
                    if len(title) < 5 or title.lower() in ['articles', 'reports', 'think']:
                        continue

                    date_text = "未知日期"
                    date_match = re.search(r'(\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4})', inner_html)
                    if not date_match:
                        date_match = re.search(r'([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4})', inner_html)
                        
                    if date_match:
                        date_text = parse_english_date(date_match.group(1))
                    
                    reports.append({
                        "Source": "ING Think",
                        "Date": date_text,
                        "Name": clean_title(title),
                        "Link": final_link
                    })
                    seen_urls.add(final_link)
                    
                    link_type = "PDF" if pdf_link else "網頁"
                    print(f"    ✔️ 成功捕獲 ({link_type}): {clean_title(title)[:30]}...")
                    
                except Exception as inner_e:
                    print(f"    ⚠️ 進入內頁解析失敗 ({article_url}): {inner_e}")
                
            browser.close()

    except Exception as e:
        print(f"  ❌ ING Think 爬取失敗: {e}")

    print(f"  ✅ ING Think 最終成功收錄 {len(reports)} 筆報告")
    return reports