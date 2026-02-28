import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 華爾街見聞 (WallstreetCN) - 🎯 全球宏觀新聞 (限量前 10 篇)...")
    reports = []
    seen_links = set()
    base_url = "https://wallstreetcn.com"
    target_url = "https://wallstreetcn.com/news/global"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 進入目標頁面
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            # 2. 模擬向下滾動 (只翻 1 次就好，因為 1 次通常就有十幾篇了)
            print("  👉 正在載入最新文章...")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)

            # 3. 解析 HTML
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 抓取所有文章連結
            article_links = soup.find_all('a', href=re.compile(r'/articles/\d+'))
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            for a in article_links:
                # 🌟 加入數量限制煞車：如果已經抓滿 30 篇，就提早結束迴圈！
                if len(reports) >= 30:
                    break

                href = a.get('href')
                full_url = urljoin(base_url, href)
                
                # 排除重複網址與評論區連結
                if full_url in seen_links or '#comments' in full_url:
                    continue
                
                # 抓取標題
                title = clean_text(a.get_text())
                if not title or len(title) < 5:  
                    continue
                
                reports.append({
                    "Source": "華爾街見聞",
                    "Date": today_str,
                    "Name": title,
                    "Link": full_url,
                    "Type": "Web"  # 標記為網頁，供 main.py 轉 PDF
                })
                seen_links.add(full_url)
                
            browser.close()
            
    except Exception as e:
        print(f"  ❌ WallstreetCN 爬取異常: {e}")

    print(f"  ✅ 華爾街見聞 成功收錄 {len(reports)} 篇文章")
    return reports

if __name__ == "__main__":
    scrape()
