import os
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

def sanitize_filename(filename):
    """清除會導致存檔失敗的特殊字元"""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Allianz Trade (安聯貿易) - 🛡️ 原生瀏覽器強制下載模式 (終極版)...")
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
                accept_downloads=True # 🌟 確保瀏覽器允許下載行為
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
                    
                    # 🌟🌟🌟 全新大絕招：原生 JS 強制下載 🌟🌟🌟
                    print(f"    📥 正在驅動瀏覽器原生下載機制...")
                    try:
                        # 告訴 Playwright 準備攔截接下來發生的下載事件
                        with page.expect_download(timeout=30000) as download_info:
                            # 注入 JS 創造一個按鈕並立刻點擊
                            page.evaluate(f"""
                                () => {{
                                    const a = document.createElement('a');
                                    a.href = '{pdf_link}';
                                    a.download = 'report.pdf';
                                    document.body.appendChild(a);
                                    a.click();
                                }}
                            """)
                        
                        # 取得下載好的檔案物件
                        download = download_info.value
                        safe_name = sanitize_filename(f"Allianz Trade_{date_text}_{clean_t}")
                        local_path = os.path.join(output_dir, f"{safe_name}.pdf")
                        
                        # 將瀏覽器暫存的檔案正式存入我們的資料夾
                        download.save_as(local_path)
                        
                        # 最後一道防線：打開檔案前 4 個 Bytes 檢查是不是真的 PDF
                        is_valid_pdf = False
                        with open(local_path, "rb") as f:
                            if f.read(4) == b'%PDF':
                                is_valid_pdf = True
                                
                        if is_valid_pdf:
                            reports.append({
                                "Source": "Allianz Trade",
                                "Date": date_text,
                                "Name": clean_t,
                                "Link": pdf_link,
                                "Type": "Pre-Downloaded",
                                "LocalPath": local_path
                            })
                            print(f"    ✔️ 成功捕獲並保存實體 PDF: {clean_t[:20]}...")
                        else:
                            print(f"    ❌ 下載失敗: 伺服器回傳的不是 PDF")
                            os.remove(local_path) # 把假檔刪掉
                            
                    except Exception as dl_e:
                        print(f"    ❌ 瀏覽器下載程序失敗: {dl_e}")
                    
                except Exception as inner_e:
                    print(f"    ⚠️ 進入內頁解析失敗 ({article_url}): {inner_e}")
                
            browser.close()

    except Exception as e:
        print(f"  ❌ Allianz Trade 爬取失敗: {e}")

    print(f"  ✅ Allianz Trade 最終成功收錄 {len(reports)} 筆 PDF 報告")
    return reports
