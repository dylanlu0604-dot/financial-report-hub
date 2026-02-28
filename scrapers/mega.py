import re
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def extract_date(text):
    match = re.search(r'(20[1-3][0-9])[^\d]*(\d{1,2})[^\d]*(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return "未知日期"

def scrape():
    # 🌟 只要看到這行字，就代表您成功更新到最新版了！
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 啟用【後台 API 直連模式】(絕對不抓錯版)...")
    reports = []
    seen_links = set()
    base_url = "https://www.megabank.com.tw"
    
    # 兆豐後台真實的分類 ID
    categories = {
        "匯率利率資訊": "9eb52bb02dbf422c9d99fb9afa67136d",
        "投資研究週報": "444b35d4cbe64f1fa586fcf1b8211ac6",
        "國際經濟金融週報": "95afc2755857498aacd3ba2aadcc793b"
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 進入首頁取得合法的連線權限
            page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
            
            # 2. 針對三個分類，直接用 JavaScript 呼叫兆豐的底層 API
            for cat_name, cat_value in categories.items():
                print(f"  👉 正在直接向兆豐後台請求：『{cat_name}』...")
                
                # 直接發送封包拿資料，徹底繞過前端爛網頁
                fetch_js = f"""
                async () => {{
                    const res = await fetch("/api/client/FinancialWeeklyReport/QueryReports?sc_lang=zh-TW&sc_site=bank-zh-tw&dic_lang=zh-TW", {{
                        method: "POST",
                        headers: {{
                            "Content-Type": "application/json; charset=utf-8"
                        }},
                        body: JSON.stringify({{
                            "categoryId": "{cat_value}",
                            "yearId": "ALL_OPTIONS_VALUE-6cb0b16f9562457a8b64e358d1b3cbc4",
                            "monthId": "ALL_OPTIONS_VALUE-6cb0b16f9562457a8b64e358d1b3cbc4",
                            "page": 1
                        }})
                    }});
                    return await res.json();
                }}
                """
                
                try:
                    response_data = page.evaluate(fetch_js)
                    
                    if response_data and response_data.get("result"):
                        items = response_data.get("data", [])
                        
                        for item in items:
                            title = item.get("title", "").strip()
                            href = item.get("link", "")
                            date_str = item.get("formattedDateStr", "")
                            
                            if not href or not title: continue
                            
                            full_url = urljoin(base_url, href)
                            
                            if ".pdf" in href.lower() or "download" in href.lower():
                                if full_url not in seen_links:
                                    reports.append({
                                        "Source": f"Mega Bank ({cat_name})", 
                                        "Date": extract_date(date_str) if date_str else extract_date(title),
                                        "Name": title,
                                        "Link": full_url
                                    })
                                    seen_links.add(full_url)
                                    print(f"    ✅ 成功提取: [{cat_name}] {title[:20]}...")
                    else:
                        print(f"    ⚠️ API 回傳失敗或無資料")
                except Exception as api_err:
                    print(f"    ❌ API 請求發生錯誤: {api_err}")

            browser.close()
    except Exception as e:
        print(f"  ❌ Mega Bank 爬取發生嚴重錯誤: {e}")

    print(f"  ✅ Mega Bank 最終完美收錄 {len(reports)} 筆報告！")
    return reports

if __name__ == "__main__":
    scrape()
