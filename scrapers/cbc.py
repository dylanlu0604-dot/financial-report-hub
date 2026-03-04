import os
import re
import urllib.parse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

# ==========================================
# ⚙️ 全域設定（與 main.py 保持一致）
# ==========================================
GITHUB_USER = "dylanlu0604-dot"
GITHUB_REPO = "financial-report-hub"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/all%20report%20pdf"
PDF_FOLDER = "all report pdf"

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def clean_title(title):
    return re.sub(r'\s+', ' ', title).strip() if title else ""

def parse_roc_date(text):
    """解析民國年日期，例如 113年3月21日 → 2024-03-21"""
    match = re.search(r'(\d{2,3})[年/](\d{1,2})[月/](\d{1,2})日?', text)
    if match:
        roc_year = int(match.group(1))
        western_year = roc_year + 1911
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{western_year}-{month:02d}-{day:02d}"
    match2 = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', text)
    if match2:
        return f"{match2.group(1)}-{int(match2.group(2)):02d}-{int(match2.group(3)):02d}"
    return "未知日期"

def is_pdf_link(a_tag):
    """
    CBC 的 PDF 下載連結 href 是 .html 結尾的路由，不是直接 .pdf
    需要靠 class、title 屬性來辨識
    """
    href = a_tag.get('href', '')
    title_attr = a_tag.get('title', '')
    classes = a_tag.get('class', [])
    text = a_tag.get_text(strip=True).upper()
    return (
        '.pdf' in href.lower() or
        '.pdf' in title_attr.lower() or
        'pdf' in [c.lower() for c in classes] or
        (text == 'PDF' and '/dl-' in href.lower())
    )

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 中央銀行 (CBC) 會後記者會參考資料...")
    reports = []
    seen_links = set()

    list_url = "https://www.cbc.gov.tw/tw/lp-357-1.html"
    base_url = "https://www.cbc.gov.tw"
    keyword = "會後記者會參考資料"

    os.makedirs(PDF_FOLDER, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                accept_downloads=True  # ✅ 必須開啟才能攔截下載
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)

            # ── Step 1: 載入列表頁，找含關鍵字的文章連結 ──
            print(f"  🌐 載入列表頁: {list_url}")
            page.goto(list_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            soup = BeautifulSoup(page.content(), 'html.parser')
            article_links = []
            for a in soup.find_all('a', href=True):
                title_text = clean_title(a.get_text())
                if keyword in title_text:
                    full_url = urllib.parse.urljoin(base_url, a.get('href'))
                    if full_url not in seen_links:
                        article_links.append((title_text, full_url))
                        seen_links.add(full_url)

            print(f"  🎯 找到 {len(article_links)} 篇含「{keyword}」的文章，開始進入內頁...")

            # ── Step 2: 進入每篇文章，找 PDF 連結並下載 ──
            for title, article_url in article_links[:10]:
                print(f"  📄 進入: {title[:50]}")
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)

                    inner_soup = BeautifulSoup(page.content(), 'html.parser')

                    # 抓日期（民國年格式）
                    date_str = "未知日期"
                    candidate = parse_roc_date(inner_soup.get_text()[:3000])
                    if candidate != "未知日期":
                        date_str = candidate

                    # 找 PDF 連結
                    pdf_links_found = []
                    for a in inner_soup.find_all('a', href=True):
                        if is_pdf_link(a):
                            dl_url = urllib.parse.urljoin(base_url, a.get('href'))
                            link_title = a.get('title', '') or clean_title(a.get_text()) or title
                            link_title = re.sub(r'\.pdf$', '', link_title, flags=re.IGNORECASE).strip()
                            if dl_url not in seen_links:
                                pdf_links_found.append((link_title, dl_url))
                                seen_links.add(dl_url)

                    if not pdf_links_found:
                        print(f"    ⚠️ 找不到 PDF 連結，跳過")
                        continue

                    # ── Step 3: 下載 PDF ──
                    for pdf_title, dl_url in pdf_links_found:
                        report_name = title if len(title) > 5 else pdf_title
                        safe_name = re.sub(r'[\\/*?:"<>|]', "_", report_name).strip()
                        local_filename = f"{safe_name}.pdf"
                        local_filepath = os.path.join(PDF_FOLDER, local_filename)
                        encoded_filename = urllib.parse.quote(local_filename)
                        github_link = f"{GITHUB_RAW_BASE}/{encoded_filename}"

                        if os.path.exists(local_filepath):
                            print(f"    ✅ 已存在，跳過下載: {safe_name[:40]}")
                        else:
                            downloaded = False

                            # 方法1：expect_download 攔截瀏覽器下載行為
                            try:
                                with page.expect_download(timeout=30000) as dl_info:
                                    page.goto(dl_url, wait_until="domcontentloaded", timeout=30000)
                                download = dl_info.value
                                download.save_as(local_filepath)
                                with open(local_filepath, 'rb') as f:
                                    header = f.read(4)
                                if header == b'%PDF':
                                    print(f"    ✅ 下載成功 (方法1): {safe_name[:40]}")
                                    downloaded = True
                                else:
                                    os.remove(local_filepath)
                                    raise ValueError(f"非 PDF，前4字節: {header}")
                            except Exception as dl_e:
                                print(f"    ⚠️ 方法1失敗: {dl_e}")

                            # 方法2：直接用 context.request 抓原始位元組
                            if not downloaded:
                                try:
                                    res = context.request.get(dl_url, headers={"Referer": article_url})
                                    body = res.body()
                                    if body[:4] == b'%PDF':
                                        with open(local_filepath, 'wb') as f:
                                            f.write(body)
                                        print(f"    ✅ 下載成功 (方法2): {safe_name[:40]}")
                                        downloaded = True
                                    else:
                                        print(f"    ❌ 方法2回傳非 PDF，放棄")
                                        continue
                                except Exception as e2:
                                    print(f"    ❌ 方法2也失敗: {e2}")
                                    continue

                        # 計算頁數
                        page_count = "未知"
                        if os.path.exists(local_filepath):
                            try:
                                import pdfplumber
                                with pdfplumber.open(local_filepath) as pdf:
                                    page_count = len(pdf.pages)
                            except:
                                pass

                        reports.append({
                            "Source": "中央銀行 (CBC)",
                            "Date": date_str,
                            "Name": report_name,
                            "Link": github_link,        # ✅ 直接給 GitHub Raw 連結，main.py 不需再下載
                            "Type": "PDF",
                            "PageCount": page_count,    # ✅ 直接填好，main.py 不需重讀
                            "LocalPath": local_filepath
                        })
                        print(f"    📦 收錄: [{date_str}] {report_name[:50]} ({page_count}頁)")

                except Exception as inner_e:
                    print(f"    ❌ 內頁處理失敗: {inner_e}")

            browser.close()

    except Exception as e:
        print(f"  ❌ CBC 爬取異常: {e}")

    print(f"  ✅ 總共收錄 {len(reports)} 篇 CBC 報告")
    return reports

if __name__ == "__main__":
    scrape()