import requests
from datetime import datetime, timedelta

# ==========================================
# 🕷️ 主爬蟲程式：凱基證券 (KGI)
# ==========================================
def scrape():
    print("🔍 正在爬取 KGI (凱基證券) - 🎯 啟動 URL 規律探測模式 (過去 30 天)...")
    reports = []
    
    # 確保月份名稱絕對是英文，避免作業系統語系干擾
    MONTH_NAMES = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }

    today = datetime.now()
    
    # 迴圈：從今天開始，往前推算 30 天 (共檢查 31 天)
    for i in range(31):
        target_date = today - timedelta(days=i)
        
        year = target_date.strftime("%Y")
        month_num = target_date.month
        month_name = MONTH_NAMES[month_num]
        mmdd = target_date.strftime("%m%d") # 例如 "0222"
        date_str = target_date.strftime("%Y-%m-%d") # 標準格式 "2026-02-22"
        
        # 根據您提供的規律組裝網址
        url = f"https://www.kgi.com.tw/zh-tw/-/media/files/kgis/strategy/ips/weekly_kickstart/{year}/{month_name}/{mmdd}.pdf"
        
        try:
            # 🌟 關鍵技巧：使用 requests.head() 只拿標頭不載內容，速度極快
            res = requests.head(url, headers=headers, timeout=5)
            
            # 如果 HTTP 狀態碼為 200，代表這天有發布報告
            if res.status_code == 200:
                title = f"KGI Weekly Kickstart ({date_str})"
                reports.append({
                    "Source": "KGI (凱基證券)",
                    "Date": date_str,
                    "Name": title,
                    "Link": url
                })
                print(f"    ✅ 成功探測到報告: {title}")
            else:
                # 404 Not Found 或是其他錯誤，直接 pass
                pass
                
        except requests.RequestException:
            # 遇到網路異常也跳過
            pass

    print(f"  ✅ KGI 最終成功收錄 {len(reports)} 筆報告")
    return reports

if __name__ == "__main__":
    import pprint
    pprint.pprint(scrape())
