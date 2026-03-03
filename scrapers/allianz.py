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
            class QuietHandler(SimpleHTTPRequestHandler):
                def log_message(self, format, *args):
                    pass # 隱藏伺服器存取紀錄，保持畫面乾淨
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
    print("🔍 正在爬取 Allianz Trade - 🎯 完美組合：精準鎖定 + 本機伺服器下載模式...")
    reports = []
    seen_pdfs = set()
    
    base_url = "https://www.allianz-trade.com"
    list_url = "https://www.allianz-trade.com/en_global/news-insights/economic-insights.html"
    
    # 建立一個專屬的暫存資料夾給本機伺服器讀取
    temp_dir = "allianz_temp_pdf"
    os.makedirs(temp_dir, exist_ok=True)
    start_local_server()
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                accept_downloads=True # 允許無頭瀏覽器下載檔案
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            print(f"  🌐 正在載入文章列表...")
            page.goto(list_url, wait_until="networkidle", timeout=60000)
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
            
            print(f"  🎯 找到 {len(article_links)} 篇文章，準備進入內頁...")
            
            for article_url in article_links[:15]: 
                try:
                    page.goto(article_url, wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(2000) 
                    
                    inner_html = page.content()
                    inner_soup = BeautifulSoup(inner_html, 'html.parser')
                    
                    pdf_link = None
                    
                    # 🎯 策略 1：精準打擊 "Read the full report" 隱藏按鈕
                    target_btn = inner_soup.find('a', {'aria-label': re.compile('Read the full report', re.I)})
                    if not target_btn:
                        target_btn = inner_soup.find('a', {'data-component-name': re.compile('Read the full report', re.I)})
                    
                    if target_btn and target_btn.get('href') and '.pdf' in target_btn.get('href').lower():
                        pdf_link = urljoin(base_url, target_btn['href'])
                        
                    # 🎯 策略 2：常規掃描 (備用)
                    if not pdf_link:
                        for a in inner_soup.find_all('a', href=True):
                            if '.pdf' in a['href'].lower() and 'publication' in a['href'].lower():
                                pdf_link = urljoin(base_url, a['href'])
                                break 
                    
                    if not pdf_link or pdf_link in seen_pdfs:
                        continue
                        
                    title_tag = inner_soup.find('h1')
                    title = title_tag.get_text(strip=True) if title_tag else unquote(pdf_link.split('/')[-1].replace('.pdf', ''))
                    
                    # === 提取日期 ===
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
                    
                    # 🌟🌟🌟 新增：瀏覽器原生下載並丟進特洛伊木馬伺服器 🌟🌟🌟
                    print(f"    📥 成功鎖定按鈕，正在用瀏覽器原生下載 PDF...")
                    try:
                        # 觸發原生下載
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
                        safe_name = sanitize_filename(f"Allianz_{date_text}_{clean_t}")
                        local_path = os.path.join(temp_dir, f"{safe_name}.pdf")
                        
                        # 存入本機暫存資料夾
                        download.save_as(local_path)
                        
                        # 驗證下載的檔案前 4 個 Bytes 是不是真的 PDF (%PDF)
                        is_valid_pdf = False
                        with open(local_path, "rb") as f:
                            if f.read(4) == b'%PDF':
                                is_valid_pdf = True
                                
                        if is_valid_pdf:
                            # 🌟 將網址改為本機伺服器位址，主程式就會跟這台伺服器要檔案 🌟
                            url_path = urllib.parse.quote(f"{temp_dir}/{safe_name}.pdf")
                            fake_local_url = f"http://127.0.0.1:{_PORT}/{url_path}"
                            
                            reports.append({
                                "Source": "Allianz Trade",
                                "Date": date_text,
                                "Name": clean_t,
                                "Link": fake_local_url,  # 欺騙主程式去連 localhost
                                "Type": "PDF"
                            })
                            print(f"    ✔️ 已載入本機伺服器備妥: {clean_t[:20]}...")
                        else:
                            print(f"    ❌ 下載失敗: 拿到的不是 PDF")
                            os.remove(local_path)
                            
                    except Exception as dl_e:
                        print(f"    ❌ 瀏覽器下載失敗: {dl_e}")
                    
                except Exception as inner_e:
                    print(f"    ⚠️ 進入內頁解析失敗 ({article_url}): {inner_e}")
                
            browser.close()

    except Exception as e:
        print(f"  ❌ Allianz Trade 爬取失敗: {e}")

    print(f"  ✅ Allianz Trade 最終成功收錄 {len(reports)} 筆 PDF 報告")
    return reports
