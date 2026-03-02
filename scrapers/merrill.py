import requests
from datetime import datetime, timedelta

# ==========================================
# 🕷️ 主爬蟲程式：Merrill Lynch (美林 CMO)
# ==========================================
def scrape():
    print("🔍 正在爬取 Merrill Lynch (美林) - 🎯 啟動 URL 規律盲測探測模式 (過去 30 天)...")
    reports = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        # 加入 Referer 避免被伺服器阻擋直連
        "Referer": "https://www.ml.com/capital-market-outlook.html"
    }

    today = datetime.now()
    
    # 迴圈：從今天開始，往前推算 30 天 (共檢查 31 天)
    for i in range(31):
        target_date = today - timedelta(days=i)
        
        # 美林 CMO 的網址日期格式為：MM-DD-YYYY (例如 02-17-2026)
        mm_dd_yyyy = target_date.strftime("%m-%d-%Y")
        
        # 報告輸出的標準日期格式：YYYY-MM-DD
        date_str = target_date.strftime("%Y-%m-%d")
        
        # 根據您提供的規律組裝網址
        url = f"https://mlaem.fs.ml.com/content/dam/ML/ecomm/pdf/CMO_Merrill_{mm_dd_yyyy}_ada.pdf"
        
        try:
            # 🌟 關鍵技巧：使用 requests.head() 只拿標頭不載內容，速度極快
            res = requests.head(url, headers=headers, timeout=5)
            
            # 如果 HTTP 狀態碼為 200，代表這天有發布報告
            if res.status_code == 200:
                title = f"Capital Market Outlook ({date_str})"
                reports.append({
                    "Source": "Merrill Lynch (CMO)",
                    "Date": date_str,
                    "Name": title,
                    "Link": url,
                    "Type": "PDF"
                })
                print(f"    ✅ 命中目標: 發現 {date_str} 的 CMO 報告！")
                
        except requests.exceptions.RequestException as e:
            # 發生超時或連線錯誤時略過
            pass

    print(f"  ✅ Merrill Lynch 最終成功收錄 {len(reports)} 篇【真實 PDF 報告】")
    return reports

if __name__ == "__main__":
    scrape()
