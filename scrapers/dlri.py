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
        # 偽裝成一般的 Windows Chrome 瀏覽器
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        # 🌟 魔法攔截器：監聽瀏覽器在背景收發的所有網路封包
        def handle_response(response):
            # 如果發現這是 MarsFlag API 傳回來的資料夾
            if "finder.api.mf.marsflag.com" in response.url:
                try:
                    text = response.text()
                    text = text.replace('\\/', '/') # 把 JSON 裡的跳脫斜線還原
                    
                    # 暴力解析：直接從封包字串裡，挖出所有 DLRI 報告的網址
                    urls = re.findall(r'https?://www\.dlri\.co\.jp/report/[a-zA-Z0-9_/-]+\.html', text)
                    for u in urls:
                        report_urls.add(u)
                except:
                    pass
                    
        # 掛上攔截器
        page.on("response", handle_response)
        
        try:
            # 讓瀏覽器真正去造訪網頁，觸發 CloudFront 放行與 API 請求
            page.goto("https://www.dlri.co.jp/report_index.html", wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(4000) # 給網頁 4 秒鐘的時間下載封包
            
            # 備用方案：也順便抓取畫面上能看到的傳統連結
            hrefs = page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a => a.href)""")
            for href in hrefs:
                if "/report/" in href and href.endswith('.html'):
                    report_urls.add(href)
        except Exception as e:
            print(f"  ❌ Playwright 執行過程發生超時: {e}")
        finally:
            browser.close()

    # 清理不要的雜訊網址
    clean_urls = set()
    for u in report_urls:
        if not any(kw in u for kw in ["report_index", "category", "type", "tag"]):
            clean_urls.add(u)

    print(f"  [偵探回報] 成功攔截到 {len(clean_urls)} 個真實報告網址，準備進入內頁提取...")

    # ==========================================
    # 逐一進入報告內頁，無視首頁排版，直接抓取精確資料
    # ==========================================
    for url in clean_urls:
        try:
            # DLRI 的內頁沒有擋一般爬蟲，我們用輕量的 requests 快速抓取
            resp = requests.get(url, headers=HEADERS, timeout=5)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # 1. 抓標題 (通常 <title> 標籤是最乾淨的)
            title_tag = soup.find('title')
            if not title_tag: continue
            title = title_tag.get_text(strip=True).split('|')[0].strip()
            
            # 排除非報告的網頁
            if len(title) < 5 or any(kw in title for kw in ["一覧", "List", "執筆者","【1分解説】"]): continue
            
            # 2. 抓日期 (暴力在原始碼內尋找日期格式，容許空白)
            date_text = None
            date_match = re.search(r'20\d{2}\s*[./年]\s*\d{1,2}\s*[./月]\s*\d{1,2}', resp.text)
            if date_match:
                date_text = date_match.group(0)
                
            # 嚴格守門員：沒日期或超過30天就踢掉
            if not date_text or not is_within_30_days(date_text):
                continue
                
            # 3. 找 PDF 下載連結
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
            time.sleep(0.3) # 禮貌性延遲
        except Exception as e:
            pass

    print(f"  ✅ DLRI 最終成功收錄 {len(reports)} 筆報告")
    return reports
