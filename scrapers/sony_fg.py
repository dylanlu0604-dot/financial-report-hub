import requests
from datetime import datetime, timedelta
from scrapers.utils import HEADERS, DAYS_LIMIT

def scrape():
    print("🔍 正在爬取 Sony FG (ソニーフィナンシャルグループ)...")
    base_url = "https://www.sonyfg.co.jp"
    reports = []
    now = datetime.now()
    report_types = [
        ("Monthly Global Market Report", "m"),
        ("グローバル経済・金利ウォッチ", "g"),
        ("Special Report", "sp"),
        ("Quarterly Market Outlook", "q"),
        ("金融・経済見通し", "kkm")
    ]
    
    for days_ago in range(DAYS_LIMIT):
        check_date = now - timedelta(days=days_ago)
        date_str = f"{check_date.year % 100:02d}{check_date.month:02d}{check_date.day:02d}"
        
        for report_name, prefix in report_types:
            pdf_url = f"{base_url}/ja/market_report/pdf/{prefix}_{date_str}_{'1' if prefix=='q' else '01'}.pdf"
            try:
                if requests.head(pdf_url, headers=HEADERS, timeout=3).status_code == 200:
                    date_formatted = f"{check_date.year}年{check_date.month:02d}月{check_date.day:02d}日"
                    reports.append({"Source": "Sony FG", "Date": date_formatted, "Name": report_name, "Link": pdf_url})
            except: pass
            
    print(f"  ✅ Sony FG 找到 {len(reports)} 筆報告")
    return reports
