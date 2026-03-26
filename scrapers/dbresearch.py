import os
import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ⚙️ 與 main.py 保持一致
GITHUB_USER = "dylanlu0604-dot"
GITHUB_REPO = "financial-report-hub"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/all%20report%20pdf"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ==========================================
# 🛠️ 輔助工具：英文月份日期 → YYYY-MM-DD
# ==========================================
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

def parse_english_date(date_text):
    """解析 'March 24, 2026' 格式 → '2026-03-24'"""
    if not date_text:
        return "未知日期"
    match = re.match(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', date_text.strip())
    if match:
        month = MONTH_MAP.get(match.group(1).lower())
        if month:
            return f"{int(match.group(3))}-{month:02d}-{int(match.group(2)):02d}"
    return "未知日期"


def is_recent(date_str, days=30):
    """檢查日期是否在近 N 天內"""
    try:
        return (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days <= days
    except:
        return True


# ==========================================
# 🕷️ 主爬蟲程式：DB Research (德意志銀行研究所)
# ==========================================
def scrape():
    print("🔍 正在爬取 DB Research (德意志銀行研究所) - 🚀 啟動「PDFVIEWER Token 破解」模式...")
    reports = []
    seen_ids = set()
    download_path = os.path.abspath("all report pdf")
    os.makedirs(download_path, exist_ok=True)

    base_url = "https://www.dbresearch.com"
    list_url = "https://www.dbresearch.com/PROD/IE-PROD/RI_FEA.alias"

    session = requests.Session()

    # ==========================================
    # 步驟 1：載入報告列表頁面，提取報告清單
    # ==========================================
    try:
        resp = session.get(list_url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"  ❌ 列表頁面載入失敗 (HTTP {resp.status_code})")
            return reports
    except Exception as e:
        print(f"  ❌ 列表頁面連線失敗: {str(e)[:50]}")
        return reports

    soup = BeautifulSoup(resp.text, "html.parser")

    # 🌟 核心：從 h2 > a 提取每篇報告的 PROD ID、標題、日期
    h2_links = soup.select('h2 a[href*="PROD0000000000"]')
    print(f"  📋 列表頁面找到 {len(h2_links)} 篇報告標題")

    report_list = []
    for link in h2_links:
        href = link.get("href", "")
        title = link.get_text(strip=True)

        # 提取 PROD ID (16 位數字)
        prod_match = re.search(r"(PROD\d{16})", href)
        if not prod_match:
            continue
        prod_id = prod_match.group(1)

        if prod_id in seen_ids:
            continue
        seen_ids.add(prod_id)

        # 🌟 日期提取：往父層尋找 "Month DD, YYYY" 格式
        date_text = ""
        parent = link.parent
        for _ in range(10):
            if parent is None:
                break
            text = parent.get_text()
            date_match = re.search(
                r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
                r"\s+\d{1,2},?\s+\d{4})",
                text,
            )
            if date_match:
                date_text = date_match.group(1)
                break
            parent = parent.parent

        final_date = parse_english_date(date_text)

        # 過濾：只保留近 30 天
        if final_date != "未知日期" and not is_recent(final_date, 30):
            continue

        report_list.append({
            "prod_id": prod_id,
            "title": title,
            "date": final_date,
        })

    print(f"  🎯 篩選後鎖定 {len(report_list)} 篇近期報告，開始逐一下載...")

    # ==========================================
    # 步驟 2 + 3：進入 PDFVIEWER 取得 directLoad Token → 下載 PDF
    # ==========================================
    for i, item in enumerate(report_list, 1):
        prod_id = item["prod_id"]
        raw_title = item["title"]
        final_date = item["date"]

        safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{raw_title} ({final_date})").strip()
        local_filename = f"{safe_title}.pdf"
        save_path = os.path.join(download_path, local_filename)

        print(f"  [{i}/{len(report_list)}] 📄 {raw_title[:40]}... ({final_date})")

        # ----- 步驟 2：造訪 PDFVIEWER 頁面，提取帶 directLoad 簽名的真實 PDF URL -----
        viewer_url = f"{base_url}/PROD/IE-PROD/PDFVIEWER.calias?pdfViewerPdfUrl={prod_id}&rwnode=REPORT"
        try:
            viewer_resp = session.get(viewer_url, headers=HEADERS, timeout=15)
            if viewer_resp.status_code != 200:
                print(f"    ❌ Viewer 頁面載入失敗 (HTTP {viewer_resp.status_code})")
                continue

            # 🌟 關鍵：從 JS 變數中提取帶簽名的 PDF 路徑
            # 格式: var pdfUrl = '/PROD/IE-PROD/PRODxxxxxx.pdf?download=true&directLoad=TOKEN';
            token_match = re.search(r"var\s+pdfUrl\s*=\s*'([^']+)'", viewer_resp.text)
            if not token_match:
                print(f"    ❌ 找不到 directLoad Token，跳過")
                continue

            pdf_path = token_match.group(1)
            full_pdf_url = base_url + pdf_path

        except Exception as e:
            print(f"    ❌ Viewer 頁面存取失敗: {str(e)[:40]}")
            continue

        # ----- 步驟 3：用帶 Token 的 URL 下載真正的 PDF -----
        try:
            pdf_resp = session.get(
                full_pdf_url,
                headers={**HEADERS, "Referer": viewer_url, "Accept": "application/pdf,*/*"},
                timeout=20,
            )

            if pdf_resp.status_code == 200 and b"%PDF" in pdf_resp.content[:10]:
                with open(save_path, "wb") as f:
                    f.write(pdf_resp.content)

                encoded_filename = urllib.parse.quote(local_filename)
                github_link = f"{GITHUB_RAW_BASE}/{encoded_filename}"

                reports.append({
                    "Source": "DB Research",
                    "Date": final_date,
                    "Name": f"{raw_title} ({final_date})",
                    "Link": github_link,
                    "Type": "PDF",
                    "LocalPath": save_path,
                })
                print(f"    ✅ [下載成功] {len(pdf_resp.content) // 1024} KB")
            else:
                print(f"    ❌ [下載失敗] HTTP {pdf_resp.status_code}, 內容非 PDF")

        except Exception as e:
            print(f"    ❌ [下載出錯] {str(e)[:40]}")

        time.sleep(0.5)  # 禮貌性延遲

    print(f"  ✅ 任務結束：總共實體收錄 {len(reports)} 篇 DB Research 報告")
    return reports


if __name__ == "__main__":
    scrape()