import os
import re
import urllib.parse
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ⚙️ 與 main.py 保持一致
GITHUB_USER = "dylanlu0604-dot"
GITHUB_REPO = "financial-report-hub"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/all%20report%20pdf"
KBSV_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}

# ==========================================
# 🛠️ 輔助工具：越南日期轉西元
# ==========================================
def convert_vn_date(date_text):
    if not date_text: return datetime.now().strftime("%Y-%m-%d")
    match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_text)
    if match:
        d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return f"{y}-{m:02d}-{d:02d}"
    return datetime.now().strftime("%Y-%m-%d")

def is_recent_date(date_text, days=35):
    try:
        report_date = datetime.strptime(date_text, "%Y-%m-%d")
        return report_date >= datetime.now() - timedelta(days=days)
    except Exception:
        return True

def fetch_category_items(category_url):
    try:
        response = requests.get(category_url, headers=KBSV_HEADERS, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"    ⚠️ 靜態 HTML 載入失敗: {str(e)[:80]}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    containers = soup.select(".itemNews .item")
    results = []

    for item in containers:
        pdf_anchor = item.find("a", href=re.compile(r"\.pdf(?:$|\?)", re.IGNORECASE))
        if not pdf_anchor:
            continue

        title_anchor = item.select_one("h3 a[href]") or pdf_anchor
        title = (
            title_anchor.get("title")
            or title_anchor.get_text(" ", strip=True)
            or os.path.basename(pdf_anchor.get("href", "")).replace(".pdf", "")
        )
        date_el = item.select_one(".thongKe .date, .date")
        date_text = date_el.get_text(" ", strip=True) if date_el else ""
        pdf_url = urljoin(category_url, pdf_anchor.get("href"))

        results.append({
            "title": title.strip(),
            "pdf_url": pdf_url,
            "date_text": date_text.strip(),
        })

    return results

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 KBSV (越南 KB 證券) - 🚀 啟動「靜態 HTML 解析 + 前 5 篇」模式...")
    reports = []
    seen_pdfs = set()
    download_path = os.path.abspath("all report pdf")
    os.makedirs(download_path, exist_ok=True)
    
    target_categories = [
        {"name": "Weekly", "url": "https://www.kbsec.com.vn/vi/ban-tin-tuan.htm"},
        {"name": "Company", "url": "https://www.kbsec.com.vn/vi/bao-cao-cong-ty.htm"},
        {"name": "Sector", "url": "https://www.kbsec.com.vn/vi/bao-cao-nganh.htm"},
        {"name": "Macro", "url": "https://www.kbsec.com.vn/vi/bao-cao-trien-vong-kinh-te-vi-mo.htm"},
        {"name": "Strategy", "url": "https://www.kbsec.com.vn/vi/bao-cao-chien-luoc-thi-truong.htm"},
        {"name": "Thematic", "url": "https://www.kbsec.com.vn/vi/bao-cao-chuyen-de.htm"}
    ]
    
    for cat in target_categories:
        print(f"  🌐 分類掃描: {cat['name']}...")

        items_data = fetch_category_items(cat["url"])
        top_5 = items_data[:5]
        print(f"    🎯 找到 {len(items_data)} 篇，鎖定前 {len(top_5)} 篇下載...")

        for data in top_5:
            pdf_url = data['pdf_url']
            if pdf_url in seen_pdfs:
                continue
            seen_pdfs.add(pdf_url)

            final_date = convert_vn_date(data['date_text'])
            if not is_recent_date(final_date):
                print(f"    ↩️ 跳過舊報告: {data['title'][:20]}... ({final_date})")
                continue

            raw_title = data['title']
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{raw_title} ({final_date})").strip()
            save_path = os.path.join(download_path, f"{safe_title}.pdf")

            print(f"    📄 物理下載: {raw_title[:20]}... ({final_date})")

            try:
                headers = {**KBSV_HEADERS, "Referer": cat["url"]}
                response = requests.get(pdf_url, headers=headers, timeout=30)
                body = response.content
                if response.status_code == 200 and body[:4] == b'%PDF':
                    with open(save_path, "wb") as f:
                        f.write(body)

                    encoded_filename = urllib.parse.quote(os.path.basename(save_path))
                    github_link = f"{GITHUB_RAW_BASE}/{encoded_filename}"
                    reports.append({
                        "Source": f"KBSV ({cat['name']})",
                        "Date": final_date,
                        "Name": f"{raw_title} ({final_date})",
                        "Link": github_link,
                        "Type": "PDF",
                        "LocalPath": save_path
                    })
                    print(f"      ✅ [下載成功]")
                else:
                    print(f"      ❌ [檔案無效] HTTP {response.status_code}")
            except Exception as e:
                print(f"      ❌ [出錯] {str(e)[:50]}")

    print(f"  ✅ 任務結束：總共實體收錄 {len(reports)} 篇越南報告")
    return reports

if __name__ == "__main__":
    scrape()
