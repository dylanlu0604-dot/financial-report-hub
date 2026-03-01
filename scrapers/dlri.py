import re
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.utils import is_within_30_days

# ==========================================
# 🕷️ 主爬蟲程式：DLRI (第一生命)
# ==========================================
def scrape():
    print("🔍 正在爬取 DLRI (第一生命) - 🛡️ 啟動 CloudFront 終極穿透模式...")
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        # 🌟 攔截器：監聽背景 API 封包
        def handle_response(response):
            if "finder.api.mf.marsflag.com" in response.url:
                try:
                    text = response.text()
                    text = text.replace('\\/', '/') 
                    urls = re.findall(r'(?:https?://www\.dlri\.co\.jp)?/report/[a-zA-Z0-9_/-]+\.html', text)
                    for u in urls:
                        full_url = urljoin("https://www.dlri.co.jp", u)
                        report_urls.add(full_url)
                except:
                    pass
                    
        page.on("response", handle_response)
        
        try:
            page.goto("https://www.dlri.co.jp/report_index.html", wait_until="networkidle", timeout=20000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(4000) 
            
            hrefs = page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a => a.href)""")
            for href in hrefs:
                if "/report/" in href and href.endswith('.html'):
                    report_urls.add(href)
        except Exception as e:
            print(f"  ❌ 首頁讀取超時: {e}")
            
        # 清理雜訊網址
        clean_urls = set()
        for u in report_urls:
            if not any(kw in u for kw in ["report_index", "category", "type", "tag"]):
                clean_urls.add(u)

        print(f"  [偵探回報] 成功攔截到 {len(clean_urls)} 個網址，啟動 Playwright 無痕模式進入內頁...")

        # ==========================================
        # 🌟 關鍵修正：不關閉瀏覽器，繼續用 Playwright 讀取內頁，徹底繞過 CloudFront
        # ==========================================
        for url in clean_urls:
            try:
                # 使用同一個帶有合法 Cookie 與指紋的 page 進入內頁
                page.goto(url, wait_until="domcontentloaded", timeout=10000)
                html_content = page.content() # 取出真實的 HTML 內容
                soup = BeautifulSoup(html_content, 'html.parser')
                
                title_tag = soup.find('title')
                if not title_tag: continue
                title = title_tag.get_text(strip=True).split('|')[0].strip()
                
                if len(title) < 5 or any(kw in title for kw in ["一覧", "List", "執筆者", "【1分解説】","時事雑感"]): continue
                
                date_text = None
                time_tag = soup.find('time') or soup.find(class_=re.compile(r'date|time', re.I))
                if time_tag:
                    date_match = re.search(r'20\d{2}\s*[./年]\s*\d{1,2}\s*[./月]\s*\d{1,2}', time_tag.get_text())
                    if date_match:
                        date_text = date_match.group(0)
                
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
                time.sleep(0.5) # 模擬人類閱讀停頓，避免被抓包
            except Exception as e:
                pass

        browser.close() # 🌟 所有內頁都爬完後，才真正關閉瀏覽器

    print(f"  ✅ DLRI 最終成功收錄 {len(reports)} 筆報告")
    return reports
