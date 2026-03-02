import requests
from datetime import datetime, timedelta

# ==========================================
# 🕷️ 主爬蟲程式：Merrill Lynch (美林 CMO)
# ==========================================
def scrape():
    print("🔍 正在爬取 Merrill Lynch (美林) - 🎯 啟動 URL 規律盲測探測模式 (過去 30 天)...")
    reports = []
    
    # 🌟 升級版 Headers：加入更多的瀏覽器特徵，讓自己看起來像個正常人
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.ml.com/",
        "Connection": "keep-alive"
    }

    today = datetime.now()
    
    # 迴圈：從今天開始，往前推算 30 天 (共檢查 31 天)
    for i in range(31):
        target_date = today - timedelta(days=i)
        
        # 美林 CMO 的網址日期格式為：MM-DD-YYYY (例如 02-17-2026)
        mm_dd_yyyy = target_date.strftime("%m-%d-%Y")
        date_str = target_date.strftime("%Y-%m-%d")
        
        url = f"https://mlaem.fs.ml.com/content/dam/ML/ecomm/pdf/CMO_Merrill_{mm_dd_yyyy}_ada.pdf"
        
        try:
            # 🌟 終極破解：改用 GET 請求並開啟 stream=True
            # 這樣伺服器會以為我們真的要下載，但我們拿到底部狀態碼後就立刻切斷連線！
            res = requests.get(url, headers=headers, stream=True, timeout=5)
            
            if res.status_code == 200:
                # 雙重確認：確保它回傳的真的是 PDF，而不是一個寫著 "找不到網頁" 的 HTML 錯誤頁面
                if 'application/pdf' in res.headers.get('Content-Type', '').lower() or url.endswith('.pdf'):
                    title = f"Capital Market Outlook ({date_str})"
                    reports.append({
                        "Source": "Merrill Lynch (CMO)",
                        "Date": date_str,
                        "Name": title,
                        "Link": url,
                        "Type": "PDF"
                    })
                    print(f"    ✅ 命中目標: 發現 {date_str} 的 CMO 報告！")
            
            # 偵錯機制：如果還是被擋，印出 403 讓我們知道是防火牆的問題
            elif res.status_code == 403:
                pass # print(f"    ⚠️ {date_str} 遭遇 403 阻擋") # 若嫌太吵可註解掉
                
            res.close() # 🌟 拿完狀態碼就立刻切斷串流，不浪費頻寬下載檔案
                
        except requests.exceptions.RequestException as e:
            pass

    print(f"  ✅ Merrill Lynch 最終成功收錄 {len(reports)} 篇【真實 PDF 報告】")
    return reports

if __name__ == "__main__":
    scrape()
