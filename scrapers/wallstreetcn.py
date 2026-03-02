import time
import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.utils import HEADERS

# ==========================================
# 🕷️ 主爬蟲程式：華爾街見聞 (Global) - 終極 JSON 解析版
# ==========================================
def scrape():
    print("🔍 正在爬取 華爾街見聞 (Global) - 🚀 啟動 JSON 底層資料庫直擊模式...")
    reports = []
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ❌ 尚未安裝 Playwright，請確認 requirements.txt")
        return reports

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        try:
            # 1. 抓取清單頁：一樣用滾動的方式獲取大量連結
            page.goto("https://wallstreetcn.com/news/global", wait_until="networkidle", timeout=30000)
            print("  [動作] 網頁載入完成，開始執行深度向下滾動 (預計耗時 35 秒)...")
            for i in range(2):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
            html_content = page.content()
        except Exception as e:
            print(f"  ❌ 華爾街見聞清單頁載入失敗: {e}")
            html_content = ""
        finally:
            browser.close()

    if not html_content:
        return reports

    soup = BeautifulSoup(html_content, 'html.parser')
    links = soup.find_all('a', href=re.compile(r'/articles/\d+'))
    seen_urls = set()
    
    print(f"  [掃描] 成功掃描到 {len(links)} 個潛在文章連結，啟動 JSON 深度解析...")
    
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
        # 🌟 終極殺手鐧：直接抓取網頁原始碼，挖出 JSON 資料庫
        # ==========================================
        try:
            # 使用 requests 快速取得原始碼 (不渲染)
            res = requests.get(url, headers=HEADERS, timeout=5)
            if res.status_code == 200:
                # 在原始碼中尋找那包隱藏的 INITIAL_STATE
                match = re.search(r'window\.INITIAL_STATE\s*=\s*({.*?});</script>', res.text, re.DOTALL)
                
                if match:
                    json_str = match.group(1)
                    # 把網頁底層的資料庫轉成 Python 字典
                    data = json.loads(json_str)
                    
                    # 嘗試從錯綜複雜的 JSON 結構中，把 "content" (文章純文字) 挖出來
                    # 華爾街見聞的結構通常在：data -> articles -> (文章ID) -> content
                    content_text = ""
                    try:
                        # 暴力搜尋 JSON 裡面的 content 欄位
                        match_content = re.search(r'"content":"(.*?)"', json_str)
                        if match_content:
                            # 這是 HTML 格式的字串，我們把它清乾淨只留文字
                            raw_html = match_content.group(1).replace('\\"', '"').replace('\\n', '')
                            clean_text = BeautifulSoup(raw_html, "html.parser").get_text(strip=True)
                            article_length = len(clean_text)
                            
                            if article_length < 200:
                                print(f"    ⚠️ 剔除快訊: 字數僅 {article_length} 字 ({title[:15]}...)")
                                continue
                            else:
                                pass # 字數夠多，過關！
                        else:
                             # 如果找不到 content，可能被混淆了，預設放行避免誤殺
                             pass 
                    except Exception as json_e:
                        pass # JSON 解析失敗，預設放行
                else:
                    # 如果連 INITIAL_STATE 都找不到，可能是遇到付費牆或特殊版面，預設放行
                    pass 
            else:
                continue
                
        except Exception as e:
            print(f"    ❌ 檢查內頁失敗，略過: {url}")
            continue

        # 正式收錄！
        reports.append({
            "Source": "WallstreetCN (Global)",
            "Date": time.strftime("%Y-%m-%d"), 
            "Name": title,
            "Link": url,
            "Type": "Web" 
        })
        time.sleep(0.2)

    print(f"  ✅ 華爾街見聞 最終成功收錄 {len(reports)} 篇【深度長文報導】！")
    return reports

if __name__ == "__main__":
    scrape()
