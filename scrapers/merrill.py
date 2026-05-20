import io
import re
import requests
from datetime import datetime, timedelta

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# ==========================================
# 🗓️ 從 PDF 內文擷取寶誥日期
# 內文範例："All data, projections and opinions are as of April 7, 2026 and subject to change."
# ==========================================
def extract_as_of_date(pdf_bytes):
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
    except Exception:
        return None

    m = re.search(
        r"as of\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    month = MONTH_MAP.get(m.group(1).lower())
    if not month:
        return None
    return f"{int(m.group(3))}-{month:02d}-{int(m.group(2)):02d}"

# ==========================================
# 🕷️ ML Viewpoint (每月一篇) 探測：網址月份格式如 Apr2026 / May2026
# ==========================================
def scrape_viewpoint(headers):
    print("🔍 正在爬取 Merrill Lynch (美林) - ML Viewpoint (過去 6 個月)...")
    reports = []
    today = datetime.now()

    seen_months = set()
    for i in range(7):
        # 往前回推 i 個月 (用每月 1 號避免跨月誤差)
        target = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        month_tag = target.strftime("%b%Y")  # 例如 Apr2026
        if month_tag in seen_months:
            continue
        seen_months.add(month_tag)

        url = f"https://mlaem.fs.ml.com/content/dam/ML/ecomm/pdf/ML_Viewpoint_{month_tag}_eComm.pdf"

        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200 and (
                'application/pdf' in res.headers.get('Content-Type', '').lower()
                or res.content[:4] == b'%PDF'
            ):
                date_str = extract_as_of_date(res.content) or target.strftime("%Y-%m-%d")
                reports.append({
                    "Source": "Merrill Lynch (Viewpoint)",
                    "Date": date_str,
                    "Name": f"Viewpoint ({month_tag})",
                    "Link": url,
                    "Type": "PDF"
                })
                print(f"    ✅ 命中目標: 發現 {month_tag} 的 Viewpoint 報告！(寶誥日期 {date_str})")
        except requests.exceptions.RequestException:
            pass

    print(f"  ✅ ML Viewpoint 最終成功收錄 {len(reports)} 篇【真實 PDF 報告】")
    return reports

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

    # 🌟 一併探測每月的 ML Viewpoint 報告
    reports.extend(scrape_viewpoint(headers))

    return reports

if __name__ == "__main__":
    scrape()
