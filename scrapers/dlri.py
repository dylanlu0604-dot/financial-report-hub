import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
import time
from scrapers.utils import HEADERS, is_within_30_days

def scrape():
    print("🔍 正在爬取 DLRI (第一生命) - 🕵️‍♂️ 封包攔截與內頁直擊模式...")
    reports = []
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ❌ 尚未安裝 Playwright，請確認 requirements.txt")
        return reports

    report_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        def handle_response(response):
            if "finder.api.mf.marsflag.com" in response.url:
                try:
                    text = response.text()
                    text = text.replace('\\/', '/') 
                    # 🌟 修復 1: 放寬 URL 擷取規則，同時支援絕對路徑與相對路徑
                    urls = re.findall(r'(?:https?://www\.dlri\.co\.jp)?/report/[a-zA-Z0-9_/-]+\.html', text)
                    for u in urls:
                        # 將相對路徑轉為完整的絕對路徑
                        full_url = urljoin("https://www.dlri.co.jp", u)
                        report_urls.add(full_url)
                except:
                    pass
                    
        page.on("response", handle_response)
        
        try:
            page.goto("https://www.dlri.co.jp/report_index.html", wait_until="networkidle", timeout=20000)
            # 讓網頁稍微往下滾動，確保觸發所有 Lazy-load 或 API
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(4000) 
            
            hrefs = page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a => a.href)""")
            for href in hrefs:
                if "/report/" in href and href.endswith('.html'):
                    report_urls.add(href)
        except Exception as e:
            print(f"  ❌ Playwright 執行過程發生超時: {e}")
        finally:
            browser.close()

    clean_urls = set()
    for u in report_urls:
        if not any(kw in u for kw in ["report_index", "category", "type", "tag"]):
            clean_urls.add(u)

    print(f"  [偵探回報] 成功攔截到 {len(clean_urls)} 個真實報告網址，準備進入內頁提取...")

    for url in clean_urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=5)
            
            # 🌟 新增防護: 確保沒有被網站 403 阻擋
            if resp.status_code != 200:
                continue
                
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            title_tag = soup.find('title')
            if not title_tag: continue
            title = title_tag.get_text(strip=True).split('|')[0].strip()
            
            if len(title) < 5 or any(kw in title for kw in ["一覧", "List", "執筆者", "【1分解説】"]): continue
            
            # 🌟 修復 2: 放棄危險的 resp.text，改從網頁「可見內文」或「時間標籤」精準尋找日期
            date_text = None
            
            # 優先尋找標準的 <time> 標籤或 class 帶有 date 的元素
            time_tag = soup.find('time') or soup.find(class_=re.compile(r'date|time', re.I))
            if time_tag:
                date_match = re.search(r'20\d{2}\s*[./年]\s*\d{1,2}\s*[./月]\s*\d{1,2}', time_tag.get_text())
                if date_match:
                    date_text = date_match.group(0)
            
            # 如果找不到標籤，退而求其次只在 <body> 的純文字中尋找 (避開 HTML Header 的干擾)
            if not date_text and soup.body:
                body_text = soup.body.get_text()
                date_match = re.search(r'20\d{2}\s*[./年]\s*\d{1,2}\s*[./月]\s*\d{1,2}', body_text)
                if date_match:
                    date_text = date_match.group(0)
                
            if not date_text or not is_within_30_days(date_text):
                continue
                
            pdf_tag = soup.find('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
            if not pdf_tag:
                pdf_tag = soup.find('a', string=re.compile(r'PDF', re.IGNORECASE))
                
            final_pdf = urljoin(url, pdf_tag['href']) if (pdf_tag and pdf_tag.get('href')) else url
            
            reports.append({
                "Source": "DLRI", 
                "Date": date_text, 
                "Name": title, 
                "Link": final_pdf
            })
            time.sleep(0.3) 
        except Exception as e:
            pass

    print(f"  ✅ DLRI 最終成功收錄 {len(reports)} 筆報告")
    return reports
