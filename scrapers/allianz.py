from bs4 import BeautifulSoup
import re
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
    """從字串萃取日期，支援多種英文格式"""
    months = {
        'january':'01','february':'02','march':'03','april':'04',
        'may':'05','june':'06','july':'07','august':'08',
        'september':'09','october':'10','november':'11','december':'12',
        'jan':'01','feb':'02','mar':'03','apr':'04',
        'jun':'06','jul':'07','aug':'08','sep':'09','oct':'10','nov':'11','dec':'12'
    }
    # "February 25, 2026" or "Feb 25, 2026"
    match = re.search(
        r'(january|february|march|april|may|june|july|august|september|october|november|december|'
        r'jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)'
        r'\s+([0-9]{1,2}),?\s+(20[2-3][0-9])',
        text, re.IGNORECASE
    )
    if match:
        mon = months.get(match.group(1).lower(), '01')
        return f"{match.group(3)}-{mon}-{int(match.group(2)):02d}"

    # "25 February 2026"
    match = re.search(
        r'([0-9]{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)'
        r'\s+(20[2-3][0-9])',
        text, re.IGNORECASE
    )
    if match:
        mon = months.get(match.group(2).lower(), '01')
        return f"{match.group(3)}-{mon}-{int(match.group(1)):02d}"

    # YYYY-MM-DD / YYYY/MM/DD
    match = re.search(r'(20[2-3][0-9])[/\-\.]([0-9]{1,2})[/\-\.]([0-9]{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    return "未知日期"

def is_within_30_days(date_text):
    if not date_text or date_text == "未知日期":
        return True  # 未知日期保留，讓 main.py 決定
    try:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return (datetime.now() - dt).days <= 30
    except:
        return True

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Allianz Trade - Economic Insights...")
    reports = []
    seen = set()

    list_url = "https://www.allianz-trade.com/en_global/news-insights/economic-insights.html"
    base_url  = "https://www.allianz-trade.com"

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
                viewport={'width': 1920, 'height': 1080}
            )

            # ══════════════════════════════════════════
            # 步驟 1：載入列表頁，蒐集所有文章連結
            # ══════════════════════════════════════════
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            print("  📋 步驟 1: 載入列表頁...")
            page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            # 嘗試多次點「Load more」展開全部文章
            for attempt in range(5):
                try:
                    btn = page.locator(
                        "button:has-text('Load more'), "
                        "a:has-text('Load more'), "
                        "button:has-text('Show more'), "
                        "[class*='load-more'], "
                        "[class*='loadmore']"
                    )
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        page.wait_for_timeout(3000)
                        print(f"    ↩ Load more 第 {attempt+1} 次")
                    else:
                        break
                except:
                    break

            list_soup = BeautifulSoup(page.content(), 'html.parser')
            page.close()

            # 收集站內文章連結（不是 PDF，必須包含 economic-insights）
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

            print(f"  🔗 列表頁共找到 {len(article_urls)} 篇文章，逐一點入尋找 PDF...\n")

            # ══════════════════════════════════════════
            # 步驟 2：逐篇點進文章頁，找 PDF 連結
            # ══════════════════════════════════════════
            for idx, art_url in enumerate(article_urls, 1):
                art_page = None
                try:
                    art_page = context.new_page()
                    Stealth().apply_stealth_sync(art_page)

                    print(f"  [{idx:02d}/{len(article_urls)}] 🌐 進入: {art_url}")
                    art_page.goto(art_url, wait_until="domcontentloaded", timeout=45000)
                    art_page.wait_for_timeout(3000)

                    # 若有「Download」/ 「PDF」按鈕，先點一下觸發載入
                    try:
                        dl = art_page.locator(
                            "a:has-text('Download'), "
                            "button:has-text('Download'), "
                            "a:has-text('PDF'), "
                            "[class*='download']"
                        )
                        if dl.count() > 0 and dl.first.is_visible():
                            dl.first.click()
                            art_page.wait_for_timeout(2000)
                    except:
                        pass

                    art_soup = BeautifulSoup(art_page.content(), 'html.parser')

                    # ── 取得標題 ──
                    title = ""
                    for sel in ['h1', '.article__title', '.page-title', '.hero__title', 'h2']:
                        el = art_soup.select_one(sel)
                        if el:
                            t = clean_title(el.get_text())
                            if len(t) > 5:
                                title = t
                                break
                    if not title:
                        title_tag = art_soup.find('title')
                        title = clean_title(title_tag.get_text()) if title_tag else "Allianz Trade Report"

                    # ── 取得日期 ──
                    date_str = "未知日期"
                    # 優先找 <time> 標籤
                    time_el = art_soup.find('time')
                    if time_el:
                        raw = time_el.get('datetime', '') or time_el.get_text(strip=True)
                        date_str = extract_date_from_text(raw)
                    # 再找含日期的短文字節點
                    if date_str == "未知日期":
                        for el in art_soup.find_all(['span', 'p', 'div', 'li']):
                            txt = el.get_text(strip=True)
                            if 10 < len(txt) < 60 and re.search(r'20[2-3][0-9]', txt):
                                d = extract_date_from_text(txt)
                                if d != "未知日期":
                                    date_str = d
                                    break
                    # 最後從 URL 試試
                    if date_str == "未知日期":
                        date_str = extract_date_from_text(art_url)

                    # 超過 30 天就跳過
                    if not is_within_30_days(date_str):
                        print(f"         ⏩ 超過 30 天 ({date_str})，跳過")
                        art_page.close()
                        continue

                    # ── 掃描頁面內所有 PDF 連結 ──
                    pdf_links_found = []
                    for a_tag in art_soup.find_all('a', href=True):
                        href = a_tag['href']
                        full_pdf = urljoin(base_url, href)
                        if '.pdf' in href.lower() and full_pdf not in seen:
                            pdf_links_found.append(full_pdf)
                            seen.add(full_pdf)

                    if pdf_links_found:
                        for pdf_url in pdf_links_found:
                            # 用 PDF 檔名作為備用標題
                            pdf_name = unquote(pdf_url.split('/')[-1])\
                                .replace('.pdf', '').replace('-', ' ').replace('_', ' ')
                            use_title = title if title else clean_title(pdf_name)
                            reports.append({
                                "Source": "Allianz Trade",
                                "Date":   date_str,
                                "Name":   use_title,
                                "Link":   pdf_url,
                            })
                            print(f"         ✅ PDF 找到: {use_title[:50]}  ({date_str})")
                    else:
                        # 找不到 PDF → 把文章頁標記為 Web，讓 main.py 網頁轉 PDF
                        if art_url not in seen:
                            seen.add(art_url)
                            reports.append({
                                "Source": "Allianz Trade",
                                "Date":   date_str,
                                "Name":   title,
                                "Link":   art_url,
                                "Type":   "Web",
                            })
                            print(f"         🌐 無 PDF，改用網頁轉 PDF: {title[:50]}")

                except Exception as e:
                    print(f"         ❌ 失敗: {str(e)[:80]}")
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

    print(f"\n  ✅ Allianz Trade 最終成功收錄 {len(reports)} 筆報告")
    return reports


if __name__ == "__main__":
    import pprint
    result = scrape()
    print("\n📊 測試爬取結果：")
    pprint.pprint(result)
