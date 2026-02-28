import re
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def extract_date(text):
    match = re.search(r'(\d{4})[^\d]*(\d{1,2})[^\d]*(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return "未知日期"

def scrape():
    print("🔍 正在爬取 Mega Bank (兆豐銀行) - 🎯 終極 API 網路封包直接抽取模式...")
    reports = []
    seen_links = set()
    base_url = "https://www.megabank.com.tw"
    target_url = "https://www.megabank.com.tw/personal/wealth/financial-service/bulletin/weekly-journal"
    
    # 兆豐後台資料庫真實的分類 ID
    categories = {
        "9eb52bb02dbf422c9d99fb9afa67136d": "匯率利率資訊",
        "444b35d4cbe64f1fa586fcf1b8211ac6": "投資研究週報",
        "95afc2755857498aacd3ba2aadcc793b": "國際經濟金融週報"
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 1. 進入首頁取得合法的連線權限
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            # 2. 直接透過底層網路請求，向兆豐的 API 索取 3 個分類的乾淨資料
            for cat_id, cat_name in categories.items():
                print(f"  👉 正在直接向兆豐資料庫抽取：『{cat_name}』真實檔案...")
                
                # 直接發送 POST 請求，完全繞過前端按鈕點擊
                fetch_script = f"""
                async () => {{
                    const res = await fetch("/api/client/FinancialWeeklyReport/QueryReports?sc_lang=zh-TW&sc_site=bank-zh-tw&dic_lang=zh-TW", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json; charset=utf-8" }},
                        body: JSON.stringify({{
                            "categoryId": "{cat_id}",
                            "yearId": "ALL_OPTIONS_VALUE-6cb0b16f9562457a8b64e358d1b3cbc4",
                            "monthId": "ALL_OPTIONS_VALUE-6cb0b16f9562457a8b64e358d1b3cbc4",
                            "page": 1
                        }})
                    }});
                    return await res.json();
                }}
                """
                
                try:
                    json_data = page.evaluate(fetch_script)
                    
                    if json_data and json_data.get("result"):
                        items = json_data.get("data", [])
                        
                        for item in items:
                            title = item.get("title", "").strip()
                            href = item.get("link", "")
                            date_str = item.get("formattedDateStr", "")
                            
                            if not href or not title: continue
                            
                            full_url = urljoin(base_url, href)
                            # 這次抓回來的 full_url 絕對是各自獨立的 PDF 網址，絕不重複！
                            if (".pdf" in href.lower() or "download" in href.lower()) and full_url not in seen_links:
                                reports.append({
                                    "Source": f"Mega Bank ({cat_name})", 
                                    "Date": extract_date(date_str) if date_str else extract_date(title),
                                    "Name": title,
                                    "Link": full_url
                                })
                                seen_links.add(full_url)
                                print(f"    ✅ 成功提取真實檔案: [{cat_name}] {title[:20]}...")
                except Exception as api_err:
                    print(f"    ❌ API 請求失敗 ({cat_name}): {api_err}")

            browser.close()
    except Exception as e:
        print(f"  ❌ Mega Bank 執行異常: {e}")

    print(f"  ✅ Mega Bank 最終完美收錄 {len(reports)} 筆不重複的報告")
    return reports

if __name__ == "__main__":
    scrape()
