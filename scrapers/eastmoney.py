import json
import re
import urllib.parse
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🕷️ 东方财富 (Eastmoney) 宏观研报爬虫
# ==========================================
def scrape():
    print("🔍 正在爬取 Eastmoney (東方財富) - 🎯 鎖定『宏觀研究』...")
    reports = []
    
    # 目標列表頁
    target_url = "https://data.eastmoney.com/report/macresearch.jshtml"
    
    # 取得 30 天前的日期，用來過濾舊報告
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 訪問列表頁
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            html_content = page.content()
            
            # 2. 利用 Regex 提取內嵌的 JSON 資料
            match = re.search(r'var\s+initdata\s*=\s*(\{.*?\});', html_content, re.DOTALL)
            if not match:
                print("  ❌ 找不到 initdata，可能網頁結構已改變")
                browser.close()
                return reports
                
            json_data = json.loads(match.group(1))
            items = json_data.get("data", [])
            
            print(f"  📊 列表頁解析成功，找到 {len(items)} 筆報告，開始篩選並獲取 PDF 連結...")
            
            # 3. 遍歷每一篇報告
            for idx, item in enumerate(items, 1):
                title = item.get("title", "").strip()
                date_str = item.get("publishDate", "")[:10] 
                org_name = item.get("orgSName", "未知機構")
                encode_url = item.get("encodeUrl", "")
                
                if not encode_url or not date_str:
                    continue
                    
                # 時間過濾
                try:
                    publish_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if publish_date < thirty_days_ago:
                        continue
                except ValueError:
                    pass
                
                # 🌟 修正點：使用正確的詳情頁網址結構，並將 encode_url 進行 URL 編碼
                safe_encode_url = urllib.parse.quote(encode_url)
                detail_url = f"https://data.eastmoney.com/report/zw_macresearch.jshtml?encodeUrl={safe_encode_url}"
                pdf_url = ""
                
                # 4. 進入詳情頁抓取真實的 PDF 下載連結
                try:
                    page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
                    
                    # 🌟 修正點：直接尋找包含「查看PDF原文」的連結，並加上等待機制確保元素載入
                    page.wait_for_selector('a:has-text("查看PDF原文")', timeout=10000)
                    pdf_element = page.locator('a:has-text("查看PDF原文")').first
                    pdf_url = pdf_element.get_attribute("href")
                        
                except Exception as e:
                    print(f"  ⚠️ 獲取 PDF 連結失敗 ({title}): 找不到按鈕或載入超時")
                
                if pdf_url:
                    reports.append({
                        "Source": f"{org_name}", 
                        "Date": date_str,
                        "Name": title,
                        "Link": pdf_url
                    })
                    print(f"    ✅ [{idx}/{len(items)}] 成功抓取: {title[:20]}...")
            
            browser.close()

    except Exception as e:
        print(f"  ❌ Eastmoney 爬取過程發生錯誤: {e}")

    print(f"  ✅ Eastmoney 最終成功收錄 {len(reports)} 筆近期宏觀研報")
    return reports

if __name__ == "__main__":
    import pprint
    result = scrape()
    print("\n📊 測試爬取結果：")
    pprint.pprint(result)
