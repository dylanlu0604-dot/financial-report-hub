import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.utils import HEADERS

# ==========================================
# 🕷️ 主爬蟲程式：華爾街見聞 (WallstreetCN Global)
# 🎯 目標：專攻全球宏觀板塊，深度滾動並過濾短篇快訊
# ==========================================
def scrape():
    print("🔍 正在爬取 華爾街見聞 (WallstreetCN Global) - 🚀 啟動深度滾動與【內文 200 字過濾】模式...")
    reports = []
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ❌ 尚未安裝 Playwright，請確認 requirements.txt")
        return reports

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 偽裝成一般使用者的瀏覽器，避免被反爬蟲機制擋下
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        try:
            # 🎯 1. 精準空降：直接鎖定全球宏觀板塊 (Global)
            page.goto("https://wallstreetcn.com/news/global", wait_until="networkidle", timeout=30000)
            
            # 🎯 2. 深度挖掘：瘋狂向下滾動 25 次，逼迫伺服器吐出更多歷史文章
            print("  [動作] 網頁載入完成，開始執行深度向下滾動 (預計耗時 35 秒)...")
            for i in range(25):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500) # 每次滾動後給網頁 1.5 秒載入新文章
                
            # 取得滾動載入後的「超長版」完整 HTML
            html_content = page.content()
            
        except Exception as e:
            print(f"  ❌ 華爾街見聞網頁載入或滾動失敗: {e}")
            html_content = ""
        finally:
            browser.close() # 任務完成，關閉無頭瀏覽器

    if not html_content:
        return reports

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 尋找所有文章的連結 (華爾街見聞的文章網址特徵為 /articles/ 加上一串數字)
    links = soup.find_all('a', href=re.compile(r'/articles/\d+'))
    seen_urls = set()
    
    print(f"  [掃描] 成功在 Global 頁面掃描到 {len(links)} 個潛在文章連結，開始進行字數審核...")
    
    for a in links:
        # 解除封印：將單次抓取上限提高到 150 篇
        if len(reports) >= 150: 
            print("  [煞車] 已達到 150 篇最高上限，停止萃取。")
            break
            
        url = urljoin("https://wallstreetcn.com", a['href'])
        
        # 避免重複抓取同一篇文章
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        # 抓取標題並清理多餘空白
        title = a.get_text(strip=True)
        # 剔除沒有標題或標題太短的雜訊
        if not title or len(title) < 5:
            continue

        # ==========================================
        # 🎯 3. 去蕪存菁：進入內頁檢查真正的內文字數是否達到 200 字
        # ==========================================
        try:
            # 使用輕量的 requests 快速進入文章內頁偷看
            art_res = requests.get(url, headers=HEADERS, timeout=5)
            if art_res.status_code == 200:
                art_soup = BeautifulSoup(art_res.text, 'html.parser')
                
                # 精準抓取文章中所有的段落 <p> 標籤來統計真正的內文字數
                p_tags = art_soup.find_all('p')
                article_length = sum(len(p.get_text(strip=True)) for p in p_tags)
                
                if article_length < 200:
                    print(f"    ⚠️ 剔除快訊: 字數僅 {article_length} 字 ({title[:15]}...)")
                    continue # 字數不足 200 字，直接跳過不收錄！
            else:
                continue # 如果遇到網頁錯誤 404/403，為了維持清單品質，直接跳過
                
        except Exception as e:
            print(f"    ❌ 進入內頁檢查字數失敗，略過: {url}")
            continue

        # 通過所有考驗，正式收錄！
        reports.append({
            "Source": "WallstreetCN (Global)",
            "Date": time.strftime("%Y-%m-%d"), # 標記當天日期
            "Name": title,
            "Link": url,
            "Type": "Web" # 標記為網頁，交給主程式轉印 PDF
        })
        time.sleep(0.3) # 稍微休息 0.3 秒，避免對伺服器造成壓力被封鎖

    print(f"  ✅ 華爾街見聞 最終成功收錄 {len(reports)} 篇【深度長文報導】！")
    return reports

if __name__ == "__main__":
    scrape()
