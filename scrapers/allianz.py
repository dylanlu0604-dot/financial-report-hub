from bs4 import BeautifulSoup
import re
import os
import urllib.parse
from urllib.parse import urljoin, unquote
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def clean_title(title):
    return re.sub(r'\s+', ' ', title).strip()

def extract_date_from_text(text):
    months = {
        'january':'01','february':'02','march':'03','april':'04',
        'may':'05','june':'06','july':'07','august':'08',
        'september':'09','october':'10','november':'11','december':'12',
        'jan':'01','feb':'02','mar':'03','apr':'04',
        'jun':'06','jul':'07','aug':'08','sep':'09','oct':'10','nov':'11','dec':'12'
    }
    match = re.search(
        r'(january|february|march|april|may|june|july|august|september|october|november|december|'
        r'jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)'
        r'\s+([0-9]{1,2}),?\s+(20[2-3][0-9])',
        text, re.IGNORECASE
    )
    if match:
        mon = months.get(match.group(1).lower(), '01')
        return f"{match.group(3)}-{mon}-{int(match.group(2)):02d}"

    match = re.search(
        r'([0-9]{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)'
        r'\s+(20[2-3][0-9])',
        text, re.IGNORECASE
    )
    if match:
        mon = months.get(match.group(2).lower(), '01')
        return f"{match.group(3)}-{mon}-{int(match.group(1)):02d}"

    match = re.search(r'(20[2-3][0-9])[/\-\.]([0-9]{1,2})[/\-\.]([0-9]{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    return "未知日期"

def is_within_30_days(date_text):
    if not date_text or date_text == "未知日期":
        return True
    try:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return (datetime.now() - dt).days <= 30
    except:
        return True

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Allianz Trade (安聯貿易) - 🎯 啟動「精準按鈕鎖定」模式...")
    reports = []
    seen = set()

    list_url = "https://www.allianz-trade.com/en_global/news-insights/economic-insights.html"
    base_url  = "https://www.allianz-trade.com"
    pdf_folder = "all report pdf"
    os.makedirs(pdf_folder, exist_ok=True)

    # ── GitHub Raw base（與 main.py 一致）──
    GITHUB_USER     = "dylanlu0604-dot"
    GITHUB_REPO     = "financial-report-hub"
    GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/all%20report%20pdf"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={'width': 1920, 'height': 1080},
                accept_downloads=True,   # ← 允許下載
            )

            # ══════════════════════════════════════════
            # 步驟 1：載入列表頁，蒐集所有文章連結
            # ══════════════════════════════════════════
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            print("🌐 正在載入文章列表...")
            page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            for attempt in range(5):
                try:
                    btn = page.locator(
                        "button:has-text('Load more'), a:has-text('Load more'), "
                        "button:has-text('Show more'), [class*='load-more'], [class*='loadmore']"
                    )
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        page.wait_for_timeout(3000)
                    else:
                        break
                except:
                    break

            list_soup = BeautifulSoup(page.content(), 'html.parser')
            page.close()

            article_urls = []
            for a_tag in list_soup.find_all('a', href=True):
                href = a_tag['href']
                if not href:
                    continue
                full = urljoin(base_url, href)
                if (
                    'allianz-trade.com' in full
                    and 'economic-insights' in full
                    and full.rstrip('/') != list_url.rstrip('/')
                    and '.pdf' not in full.lower()
                    and full not in article_urls
                ):
                    article_urls.append(full)

            print(f"🎯 找到 {len(article_urls)} 篇文章，準備進入內頁尋找 PDF...")

            # ══════════════════════════════════════════
            # 步驟 2：逐篇點進文章頁，攔截下載 PDF
            # ══════════════════════════════════════════
            for idx, art_url in enumerate(article_urls, 1):
                art_page = None
                try:
                    art_page = context.new_page()
                    Stealth().apply_stealth_sync(art_page)

                    art_page.goto(art_url, wait_until="domcontentloaded", timeout=45000)
                    art_page.wait_for_timeout(3000)

                    art_soup = BeautifulSoup(art_page.content(), 'html.parser')

                    # ── 標題 ──
                    title = ""
                    for sel in ['h1', '.article__title', '.page-title', '.hero__title']:
                        el = art_soup.select_one(sel)
                        if el:
                            t = clean_title(el.get_text())
                            if len(t) > 5:
                                title = t
                                break
                    if not title:
                        tt = art_soup.find('title')
                        title = clean_title(tt.get_text().split('|')[0]) if tt else "Allianz Trade Report"

                    # ── 日期 ──
                    date_str = "未知日期"
                    time_el = art_soup.find('time')
                    if time_el:
                        raw = time_el.get('datetime', '') or time_el.get_text(strip=True)
                        date_str = extract_date_from_text(raw)
                    if date_str == "未知日期":
                        for el in art_soup.find_all(['span', 'p', 'div', 'li']):
                            txt = el.get_text(strip=True)
                            if 8 < len(txt) < 60 and re.search(r'20[2-3][0-9]', txt):
                                d = extract_date_from_text(txt)
                                if d != "未知日期":
                                    date_str = d
                                    break
                    if date_str == "未知日期":
                        date_str = extract_date_from_text(art_url)

                    if not is_within_30_days(date_str):
                        art_page.close()
                        continue

                    # ── 找 PDF 連結（靜態掃描）──
                    pdf_hrefs = []
                    for a_tag in art_soup.find_all('a', href=True):
                        href = a_tag['href']
                        if '.pdf' in href.lower():
                            pdf_hrefs.append(urljoin(base_url, href))

                    # ── 若靜態找不到，點 Download 按鈕後攔截下載 ──
                    downloaded_path = None
                    if not pdf_hrefs:
                        try:
                            dl_btn = art_page.locator(
                                "a:has-text('Download'), button:has-text('Download'), "
                                "a:has-text('Get the report'), a:has-text('Read the report'), "
                                "a[href*='.pdf'], [class*='download']"
                            )
                            if dl_btn.count() > 0 and dl_btn.first.is_visible():
                                print(f"🎯 成功鎖定官方報告按鈕！")
                                with art_page.expect_download(timeout=30000) as dl_info:
                                    dl_btn.first.click()
                                download = dl_info.value

                                safe_title = re.sub(r'[\\/*?:"<>|]', "_", title).strip()
                                local_filename = f"{safe_title}.pdf"
                                local_filepath = os.path.join(pdf_folder, local_filename)

                                download.save_as(local_filepath)
                                downloaded_path = local_filepath
                                print(f"✔️ 成功捕獲: {title[:40]}...")
                        except Exception as btn_e:
                            # 按鈕點了但不是觸發下載，而是開新頁顯示 PDF → 改用 API 請求
                            pass

                    # ── 處理靜態找到的 PDF 連結：用同一 context 帶 Cookie 下載 ──
                    if pdf_hrefs and not downloaded_path:
                        for pdf_url in pdf_hrefs:
                            if pdf_url in seen:
                                continue
                            seen.add(pdf_url)
                            try:
                                safe_title = re.sub(r'[\\/*?:"<>|]', "_", title).strip()
                                local_filename = f"{safe_title}.pdf"
                                local_filepath = os.path.join(pdf_folder, local_filename)

                                # 用同一 context 的 request API，帶著完整 Cookie / Session
                                response = context.request.get(
                                    pdf_url,
                                    headers={
                                        "Referer": art_url,
                                        "Accept": "application/pdf,*/*",
                                    }
                                )
                                body = response.body()
                                if body[:4] == b'%PDF' or body[:4] == b'\x25\x50\x44\x46':
                                    with open(local_filepath, 'wb') as f:
                                        f.write(body)
                                    downloaded_path = local_filepath
                                    print(f"✔️ 成功下載 PDF: {title[:40]}...")
                                else:
                                    print(f"  ⚠️ 回應非 PDF，改用網頁轉 PDF")
                            except Exception as dl_e:
                                print(f"  ⚠️ PDF 請求失敗: {str(dl_e)[:60]}")

                    # ── 組裝回傳資料 ──
                    if downloaded_path and os.path.exists(downloaded_path):
                        # 已下載到本地：直接告知 main.py 檔案已存在，Link 指向 GitHub
                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", title).strip()
                        encoded_filename = urllib.parse.quote(f"{safe_title}.pdf")
                        github_link = f"{GITHUB_RAW_BASE}/{encoded_filename}"

                        if github_link not in seen:
                            seen.add(github_link)
                            reports.append({
                                "Source":    "Allianz Trade",
                                "Date":      date_str,
                                "Name":      title,
                                "Link":      github_link,       # main.py 用來生成 HTML
                                "LocalPath": downloaded_path,   # main.py 用來算頁數 & AI 摘要
                                "PageCount": "未知",
                            })
                    else:
                        # 實在找不到 PDF → 網頁轉 PDF
                        if art_url not in seen:
                            seen.add(art_url)
                            reports.append({
                                "Source": "Allianz Trade",
                                "Date":   date_str,
                                "Name":   title,
                                "Link":   art_url,
                                "Type":   "Web",
                            })
                            print(f"  🌐 無 PDF，改用網頁轉 PDF: {title[:50]}")

                except Exception as e:
                    print(f"  ❌ [{idx}] 失敗: {str(e)[:80]}")
                finally:
                    if art_page:
                        try:
                            art_page.close()
                        except:
                            pass

            browser.close()

    except Exception as e:
        print(f"  ❌ Allianz Trade 整體爬取失敗: {e}")
        import traceback
        traceback.print_exc()

    print(f"  ✅ Allianz Trade 最終成功收錄 {len(reports)} 筆報告")
    return reports


if __name__ == "__main__":
    import pprint
    result = scrape()
    print("\n📊 測試爬取結果：")
    pprint.pprint(result)
