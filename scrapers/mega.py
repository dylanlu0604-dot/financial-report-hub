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
    # 🌟🌟🌟 請注意這行字！等一下看日誌，一定要出現這行才代表更新成功！
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 啟動【API 終極直連模式】(解決標籤錯置版)...")
    
    reports = []
    seen_links = set()
    base_url = "https://www.megabank.com.tw"
    
    # 直接存取兆豐後台資料庫，不再依賴爛網頁按鈕
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
            
            # 1. 進入首頁取得合法連線權限
            page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
            
            # 2. 針對三個分類，直接發送封包拿資料庫最乾淨的資料
            for cat_name, cat_value in categories.items():
                print(f"  👉 正在呼叫兆豐後台 API 獲取：『{cat_name}』...")
                
                fetch_js = f"""
                async () => {{
                    const res = await fetch("/api/client/FinancialWeeklyReport/QueryReports?sc_lang=zh-TW&sc_site=bank-zh-tw&dic_lang=zh-TW", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json; charset=utf-8" }},
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
                    data = page.evaluate(fetch_js)
                    if data and data.get("result"):
                        items = data.get("data", [])
                        print(f"    📥 成功從資料庫攔截到 {len(items)} 筆真實資料！")
                        
                        for item in items:
                            title = item.get("title", "").strip()
                            href = item.get("link", "")
                            date_str = item.get("formattedDateStr", "")
                            
                            if href and (".pdf" in href.lower() or "download" in href.lower()):
                                full_url = urljoin(base_url, href)
                                if full_url not in seen_links:
                                    reports.append({
                                        "Source": f"Mega Bank ({cat_name})", 
                                        "Date": extract_date(date_str) if date_str else extract_date(title),
                                        "Name": title,
                                        "Link": full_url
                                    })
                                    seen_links.add(full_url)
                                    print(f"      ✅ 收錄: [{cat_name}] {title[:25]}...")
                    else:
                        print(f"    ⚠️ API 回傳無資料")
                except Exception as api_err:
                    print(f"    ❌ API 請求失敗: {api_err}")
            browser.close()
    except Exception as e:
        print(f"  ❌ Mega Bank 執行異常: {e}")

    print(f"  ✅ Mega Bank 最終收錄 {len(reports)} 筆正確報告")
    return reports

if __name__ == "__main__":
    scrape()
