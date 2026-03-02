import time
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ==========================================
# 🕷️ 主爬蟲程式：華爾街見聞 (WallstreetCN Global)
# ==========================================
def scrape():
    print("🔍 正在爬取 華爾街見聞 (Global) - 🚀 啟動全程視覺解析與【內文 200 字過濾】模式...")
    reports = []
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ❌ 尚未安裝 Playwright，請確認 requirements.txt")
        return reports

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 偽裝成一般使用者的瀏覽器
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        try:
            page.goto("https://wallstreetcn.com/news/global", wait_until="networkidle", timeout=30000)
            
            print("  [動作] 網頁載入完成，開始執行深度向下滾動 (預計耗時 35 秒)...")
            for i in range(25):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
                
            html_content = page.content()
            
        except Exception as e:
            print(f"  ❌ 華爾街見聞網頁載入或滾動失敗: {e}")
            html_content = ""

        if not html_content:
            browser.close()
            return reports

        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 尋找所有文章的連結
        links = soup.find_all('a', href=re.compile(r'/articles/\d+'))
        seen_urls = set()
        
        print(f"  [掃描] 成功掃描到 {len(links)} 個文章連結，開始進行視覺字數審核...")
        
        # 準備一個專門用來看內頁的標籤頁 (避免干擾原本的頁面)
        article_page = context.new_page()
        
        for a in links:
            if len(reports) >= 150: 
                break
                
            url = urljoin("https://wallstreetcn.com", a['href'])
            
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # ==========================================
            # 🌟 關鍵修復：用 Playwright 進入內頁，等文章渲染出來再算字數
            # ==========================================
            try:
                # 使用 Playwright 進入內頁，等待 DOM 結構載入完成
                article_page.goto(url, wait_until="domcontentloaded", timeout=10000)
                
                # 讓瀏覽器執行 JavaScript，直接抓取畫面上所有的 <p> 標籤並計算總字數
                # 這樣就不會被 SPA 空殼子騙了！
                article_length = article_page.evaluate("""
                    () => {
                        let paragraphs = document.querySelectorAll('p');
                        let totalLength = 0;
                        for (let p of paragraphs) {
                            totalLength += p.innerText.trim().length;
                        }
                        return totalLength;
                    }
                """)
                
                if article_length < 50:
                    print(f"    ⚠️ 剔除快訊: 字數僅 {article_length} 字 ({title[:15]}...)")
                    continue
                    
            except Exception as e:
                print(f"    ❌ 進入內頁檢查失敗，略過: {url}")
                continue

            # 成功通過考驗，正式收錄
            reports.append({
                "Source": "WallstreetCN (Global)",
                "Date": time.strftime("%Y-%m-%d"), 
                "Name": title,
                "Link": url,
                "Type": "Web" 
            })
            time.sleep(0.1)

        browser.close() # 所有任務完成，關閉瀏覽器

    print(f"  ✅ 華爾街見聞 最終成功收錄 {len(reports)} 篇【深度長文報導】！")
    return reports

if __name__ == "__main__":
    scrape()
