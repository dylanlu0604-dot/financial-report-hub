import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 華爾街見聞 (WallstreetCN) - 🎯 全球宏觀新聞 (前三頁)...")
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
            
            # 2. 模擬向下滾動 (翻三頁)
            print("  👉 正在向下滾動加載文章...")
            for i in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)  # 等待新文章透過 API 載入

            # 3. 解析加載後的 HTML
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 華爾街見聞的文章列表通常包在 class 包含 list-item 或 article 的區塊中
            # 我們直接尋找所有指向 /articles/ 的連結
            article_links = soup.find_all('a', href=re.compile(r'^/articles/\d+'))
            
            for a in article_links:
                href = a.get('href')
                full_url = urljoin(base_url, href)
                
                # 排除重複網址與評論區連結
                if full_url in seen_links or '#comments' in full_url:
                    continue
                
                # 抓取標題
                title = clean_text(a.get_text())
                if not title or len(title) < 5:  # 過濾掉只有圖片沒有文字的標籤
                    continue
                
                # 抓取日期 (華爾街見聞通常在標題附近會有 span class="time" 或類似的標籤)
                # 為了確保系統穩定，若抓不到具體日期，預設標記為今日或提取網頁中的時間字串
                date_str = "最新文章"
                parent = a.find_parent('div')
                if parent:
                    time_el = parent.find(string=re.compile(r'\d{4}-\d{2}-\d{2}|\d{2}-\d{2} \d{2}:\d{2}'))
                    if time_el:
                        match = re.search(r'(\d{4}-\d{2}-\d{2})', time_el)
                        if match:
                            date_str = match.group(1)
                
                reports.append({
                    "Source": "華爾街見聞 (Global)",
                    "Date": date_str,
                    "Name": title,
                    "Link": full_url  # 🌟 這裡是一般的網頁 HTML 連結，不是 PDF
                })
                seen_links.add(full_url)
                
            browser.close()
            
    except Exception as e:
        print(f"  ❌ WallstreetCN 爬取異常: {e}")

    print(f"  ✅ 華爾街見聞 成功收錄 {len(reports)} 篇文章")
    return reports

if __name__ == "__main__":
    scrape()
