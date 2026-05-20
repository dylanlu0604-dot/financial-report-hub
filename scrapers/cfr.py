import os
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from datetime import datetime

# ==========================================
# ⚙️ 全域設定（與 main.py 保持一致）
# ==========================================
GITHUB_USER = "dylanlu0604-dot"
GITHUB_REPO = "financial-report-hub"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/all%20report%20pdf"
PDF_FOLDER = "all report pdf"

LIST_URL = "https://www.cfr.org/series/follow-the-money"
BASE_URL = "https://www.cfr.org"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# 最多收錄最近幾篇文章
MAX_ARTICLES = 10


def clean_title(title):
    return re.sub(r'\s+', ' ', title).strip() if title else ""


# ==========================================
# 🛠️ 從列表頁解析文章清單 (標題 / 連結 / 日期)
# CFR 沒有 PDF，文章日期放在 <time datetime="2026-05-18T...">
# ==========================================
def parse_list():
    resp = requests.get(LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    seen = set()
    for a in soup.select('a[href^="/articles/"]'):
        href = a.get("href", "")
        title = clean_title(a.get_text())
        if not title or href in seen:
            continue

        # 往上找最近的 <time> 取得日期
        date_str = "未知日期"
        node = a
        for _ in range(8):
            node = node.parent
            if node is None:
                break
            time_tag = node.find("time")
            if time_tag and time_tag.get("datetime"):
                try:
                    date_str = datetime.fromisoformat(
                        time_tag["datetime"].replace("Z", "+00:00")
                    ).strftime("%Y-%m-%d")
                except ValueError:
                    pass
                break

        seen.add(href)
        articles.append({
            "title": title,
            "url": urllib.parse.urljoin(BASE_URL, href),
            "date": date_str,
        })

    return articles


# ==========================================
# 🕷️ 主爬蟲程式：CFR Follow the Money (將網頁轉成 PDF)
# ==========================================
def scrape():
    print("🔍 正在爬取 CFR - Follow the Money (網頁轉 PDF 模式)...")
    reports = []

    os.makedirs(PDF_FOLDER, exist_ok=True)

    try:
        articles = parse_list()
    except Exception as e:
        print(f"  ❌ 列表頁載入失敗: {str(e)[:60]}")
        return reports

    articles = articles[:MAX_ARTICLES]
    print(f"  🎯 鎖定 {len(articles)} 篇文章，開始逐一轉 PDF...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(user_agent=HEADERS["User-Agent"])
            page = context.new_page()

            for i, item in enumerate(articles, 1):
                title = item["title"]
                url = item["url"]
                date_str = item["date"]

                safe_name = re.sub(r'[\\/*?:"<>|]', "_", f"{title} ({date_str})").strip()
                local_filename = f"{safe_name}.pdf"
                local_filepath = os.path.join(PDF_FOLDER, local_filename)
                encoded_filename = urllib.parse.quote(local_filename)
                github_link = f"{GITHUB_RAW_BASE}/{encoded_filename}"

                print(f"  [{i}/{len(articles)}] 📄 {title[:50]} ({date_str})")

                if os.path.exists(local_filepath):
                    print("    ✅ 已存在，跳過轉檔")
                else:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(3000)
                        page.emulate_media(media="screen")
                        page.pdf(
                            path=local_filepath,
                            format="A4",
                            print_background=True,
                            margin={"top": "15mm", "bottom": "15mm",
                                    "left": "10mm", "right": "10mm"},
                        )
                        print(f"    ✅ 轉檔成功: {os.path.getsize(local_filepath) // 1024} KB")
                    except Exception as e:
                        print(f"    ❌ 轉檔失敗: {str(e)[:60]}")
                        continue

                # 計算頁數
                page_count = "未知"
                try:
                    import pdfplumber
                    with pdfplumber.open(local_filepath) as pdf:
                        page_count = len(pdf.pages)
                except Exception:
                    pass

                reports.append({
                    "Source": "CFR (Follow the Money)",
                    "Date": date_str,
                    "Name": title,
                    "Link": github_link,
                    "Type": "PDF",
                    "PageCount": page_count,
                    "LocalPath": local_filepath,
                })

            browser.close()

    except Exception as e:
        print(f"  ❌ CFR 爬取異常: {str(e)[:60]}")

    print(f"  ✅ CFR 總共收錄 {len(reports)} 篇報告")
    return reports


if __name__ == "__main__":
    scrape()
