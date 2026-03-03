import os
import re
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🌟 特洛伊木馬：啟動本機微型伺服器
# ==========================================
_SERVER_STARTED = False
_PORT = 18033

def start_local_server():
    global _SERVER_STARTED
    if not _SERVER_STARTED:
        try:
            # 建立一個安靜的伺服器，不印出多餘的日誌干擾畫面
            class QuietHandler(SimpleHTTPRequestHandler):
                def log_message(self, format, *args):
                    pass 
            httpd = TCPServer(("127.0.0.1", _PORT), QuietHandler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            _SERVER_STARTED = True
        except Exception as e:
            pass

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
    print("🔍 正在爬取 Allianz Trade (安聯貿易) - 🛡️ 啟動「特洛伊木馬」本機伺服器策略...")
    reports = []
    seen_pdfs = set()
    
    base_url = "https://www.allianz-trade.com"
    list_url = "https://www.allianz-trade.com/en_global/news-insights/economic-insights.html"
    
    output_dir = "all report pdf"
    os.makedirs(output_dir, exist_ok=True)
    
    # 啟動本機伺服器來欺騙主程式
    start_local_server()
    
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
                    
                    print(f"    📥 正在繞過防火牆讀取 PDF...")
                    
                    # 🌟 第 1 步：使用帶有真實來源特徵的 API 取檔
                    headers = {
                        "Referer": article_url,
                        "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    }
                    pdf_res = context.request.get(pdf_link, headers=headers, timeout=20000)
                    pdf_bytes = b""
                    
                    if pdf_res.status == 200:
                        pdf_bytes = pdf_res.body()
                        
                    # 🌟 備案防護：如果 API 依然被擋，啟動瀏覽器真實導航
                    if not pdf_bytes.startswith(b'%PDF'):
                        print("    ⚠️ API 請求遭攔截，啟動原生導航備案...")
                        pdf_page_res = page.goto(pdf_link, referer=article_url, timeout=30000)
                        if pdf_page_res and pdf_page_res.status == 200:
                            pdf_bytes = pdf_page_res.body()
                            
                    # 🌟 第 2 步：檔案驗證與啟動木馬
                    if pdf_bytes.startswith(b'%PDF'):
                        safe_name = sanitize_filename(f"Allianz Trade_{date_text}_{clean_t}")
                        local_path = os.path.join(output_dir, f"{safe_name}.pdf")
                        
                        # 把檔案寫入硬碟
                        with open(local_path, "wb") as f:
                            f.write(pdf_bytes)
                            
                        # 將實體路徑轉為「本機伺服器網址」(主程式會去找這個網址下載)
                        url_path = urllib.parse.quote(f"{output_dir}/{safe_name}.pdf")
                        fake_local_url = f"http://127.0.0.1:{_PORT}/{url_path}"
                        
                        reports.append({
                            "Source": "Allianz Trade",
                            "Date": date_text,
                            "Name": clean_t,
                            "Link": fake_local_url, # 🤫 騙主程式連到這裡
                            "Type": "PDF"
                        })
                        print(f"    ✔️ 成功捕獲並啟動本機木馬連線: {clean_t[:20]}...")
                    else:
                        print(f"    ❌ 讀取失敗: 防火牆依然阻擋了實體檔案的讀取")
                    
                except Exception as inner_e:
                    print(f"    ⚠️ 進入內頁解析失敗 ({article_url}): {inner_e}")
                
            browser.close()

    except Exception as e:
        print(f"  ❌ Allianz Trade 爬取失敗: {e}")

    print(f"  ✅ Allianz Trade 最終成功收錄 {len(reports)} 筆 PDF 報告")
    return reports
