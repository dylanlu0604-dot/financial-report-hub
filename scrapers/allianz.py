import os
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, unquote
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import requests

# ==========================================
# 🌟 魔法攔截器：防止主程式 (main.py) 破壞檔案
# ==========================================
_ALLIANZ_CACHE = {}
_original_request = requests.Session.request

class MockResponse:
    """偽造的網路回應，用來欺騙主程式"""
    def __init__(self, content):
        self.content = content
        self.status_code = 200
        self.headers = {'Content-Type': 'application/pdf', 'content-type': 'application/pdf'}
        self.text = ""
    def iter_content(self, chunk_size=1024):
        yield self.content
    def raise_for_status(self):
        pass
    def close(self):
        pass

def _patched_request(self, method, url, *args, **kwargs):
    """攔截主程式的下載請求，直接把硬碟裡的檔案交給它"""
    if method.lower() == 'get' and url in _ALLIANZ_CACHE:
        local_path = _ALLIANZ_CACHE[url]
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                return MockResponse(f.read())
    # 如果是別家銀行的報告，就放行給原本的網路模組處理
    return _original_request(self, method, url, *args, **kwargs)

# 偷天換日：強制替換 Python 底層的連線模組
requests.Session.request = _patched_request
requests.get = lambda url, **kwargs: requests.Session().request('get', url, **kwargs)

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def clean_title(title):
    return title.replace('\n', ' ').strip()

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Allianz Trade (安聯貿易) - 🛡️ 啟動原生下載與魔法攔截模式...")
    reports = []
    seen_pdfs = set()
    
    base_url = "https://www.allianz-trade.com"
    list_url = "https://www.allianz-trade.com/en_global/news-insights/economic-insights.html"
    
    output_dir = "all report pdf"
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                accept_downloads=True
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            print(f"  🌐 正在載入文章列表...")
            page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000) 
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            article_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/news-insights/economic-insights/' in href and href.endswith('.html'):
                    full_url = urljoin(base_url, href)
                    if full_url != list_url and full_url not in article_links:
                        article_links.append(full_url)
            
            print(f"  🎯 找到 {len(article_links)} 篇文章，準備進入內頁尋找 PDF...")
            
            for article_url in article_links[:15]: 
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500) 
                    
                    inner_html = page.content()
                    inner_soup = BeautifulSoup(inner_html, 'html.parser')
                    
                    pdf_link = None
                    for a in inner_soup.find_all('a', href=True):
                        if '.pdf' in a['href'].lower():
                            pdf_link = urljoin(base_url, a['href'])
                            break 
                    
                    if not pdf_link or pdf_link in seen_pdfs:
                        continue
                        
                    title_tag = inner_soup.find('h1')
                    title = title_tag.get_text(strip=True) if title_tag else unquote(pdf_link.split('/')[-1].replace('.pdf', ''))
                    
                    date_text = "未知日期"
                    meta_date = inner_soup.find('meta', {'property': 'article:published_time'})
                    if meta_date and meta_date.get('content'):
                        date_text = meta_date['content'].split('T')[0]
                    if date_text == "未知日期":
                        time_tag = inner_soup.find('time')
                        if time_tag and time_tag.get('datetime'):
                            date_text = time_tag['datetime'].split('T')[0]
                    if date_text == "未知日期":
                        date_match = re.search(r'([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4})', inner_html)
                        if date_match:
                            raw_date = date_match.group(1).replace(',', '').strip()
                            formats_to_try = ["%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"]
                            for fmt in formats_to_try:
                                try:
                                    dt = datetime.strptime(raw_date, fmt)
                                    date_text = dt.strftime("%Y-%m-%d")
                                    break
                                except ValueError:
                                    continue
                    
                    seen_pdfs.add(pdf_link)
                    clean_t = clean_title(title)
                    
                    print(f"    📥 正在驅動瀏覽器原生下載機制...")
                    try:
                        with page.expect_download(timeout=30000) as download_info:
                            page.evaluate(f"""
                                () => {{
                                    const a = document.createElement('a');
                                    a.href = '{pdf_link}';
                                    a.download = 'report.pdf';
                                    document.body.appendChild(a);
                                    a.click();
                                }}
                            """)
                        
                        download = download_info.value
                        safe_name = sanitize_filename(f"Allianz Trade_{date_text}_{clean_t}")
                        local_path = os.path.join(output_dir, f"{safe_name}.pdf")
                        
                        download.save_as(local_path)
                        
                        # 驗證 PDF 真偽
                        is_valid_pdf = False
                        with open(local_path, "rb") as f:
                            if f.read(4) == b'%PDF':
                                is_valid_pdf = True
                                
                        if is_valid_pdf:
                            # 🌟🌟🌟 關鍵：將網址與本機路徑綁定，讓攔截器發揮作用 🌟🌟🌟
                            _ALLIANZ_CACHE[pdf_link] = local_path
                            
                            reports.append({
                                "Source": "Allianz Trade",
                                "Date": date_text,
                                "Name": clean_t,
                                "Link": pdf_link,
                                "Type": "PDF"
                            })
                            print(f"    ✔️ 成功保存實體 PDF，已裝載魔法攔截盾: {clean_t[:20]}...")
                        else:
                            print(f"    ❌ 下載失敗: 伺服器回傳的不是 PDF")
                            os.remove(local_path)
                            
                    except Exception as dl_e:
                        print(f"    ❌ 瀏覽器下載程序失敗: {dl_e}")
                    
                except Exception as inner_e:
                    print(f"    ⚠️ 進入內頁解析失敗 ({article_url}): {inner_e}")
                
            browser.close()

    except Exception as e:
        print(f"  ❌ Allianz Trade 爬取失敗: {e}")

    print(f"  ✅ Allianz Trade 最終成功收錄 {len(reports)} 筆 PDF 報告")
    return reports
