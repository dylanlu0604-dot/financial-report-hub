import os
import re
import urllib.parse
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from scrapers.utils import is_within_30_days

# ==========================================
# ⚙️ 全域設定（與 main.py 保持一致）
# ==========================================
GITHUB_USER = "dylanlu0604-dot"
GITHUB_REPO = "financial-report-hub"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/all%20report%20pdf"
PDF_FOLDER = "all report pdf"


def _safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", str(name or "Unknown")).strip() + ".pdf"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

EXTRA_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def normalize_date(date_text):
    if not date_text:
        return "未知日期"
    m = re.search(r'(20\d{2})年(\d{1,2})月(\d{1,2})日', date_text)
    if m:
        y, mo, d = m.groups()
        return f"{y}年{int(mo)}月{int(d)}日"
    m = re.search(r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})', date_text)
    if m:
        y, mo, d = m.groups()
        return f"{y}年{int(mo)}月{int(d)}日"
    return "未知日期"


def clean_title(t):
    return re.sub(r'\s+', ' ', t or "").strip()


def _is_access_denied(html, title):
    sample = (html or "")[:2000].lower()
    return (
        "access denied" in (title or "").lower()
        or "access denied" in sample
        or "akamai" in sample and "reference" in sample  # Akamai 拒絕頁的特徵
    )


def _fetch_with_browser(page, target_url, referer=None):
    """單頁抓取，回傳 (soup, html)；遇到拒絕則回傳 (None, None)。"""
    try:
        if referer:
            page.set_extra_http_headers({**EXTRA_HEADERS, "Referer": referer})
        else:
            page.set_extra_http_headers(EXTRA_HEADERS)
        page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        # 模擬使用者行為
        try:
            page.mouse.move(400, 300)
            page.evaluate("window.scrollBy(0, 400)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(800)
        except Exception:
            pass

        html = page.content()
        title = page.title()
        if _is_access_denied(html, title):
            return None, None
        return BeautifulSoup(html, "html.parser"), html
    except Exception as e:
        print(f"  ⚠️ Mizuho 頁面載入失敗: {target_url} ({str(e)[:80]})")
        return None, None


def _find_pdf_in_article(inner_soup):
    """從文章內頁挖 PDF 連結。優先抓「本レポート/こちら/PDF」字眼的連結。"""
    candidates = inner_soup.find_all('a', href=True)

    # 第一優先：anchor text 含關鍵字
    for a in candidates:
        text = (a.get_text(" ", strip=True) or "")
        href = a.get('href', '')
        if any(k in text for k in ["本レポート", "こちら", "PDFデータ", "ダウンロード"]) and ".pdf" in href.lower():
            return a['href']

    # 第二優先：href 含 .pdf
    for a in candidates:
        if re.search(r'\.pdf(\?|$)', a['href'], re.IGNORECASE):
            return a['href']

    return None


def _download_pdf(context, pdf_url, referer, local_filepath):
    """用熱好的 session 直接抓 PDF（保留 Akamai cookies）。回傳 True 表示成功。"""
    try:
        res = context.request.get(
            pdf_url,
            headers={
                "Referer": referer,
                "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
            },
            timeout=30000,
        )
        body = res.body()
        if body[:4] == b'%PDF':
            os.makedirs(os.path.dirname(local_filepath) or ".", exist_ok=True)
            with open(local_filepath, "wb") as f:
                f.write(body)
            return True
        return False
    except Exception:
        return False


def _extract_reports(soup, page_url, page, context, seen_links):
    found = []
    os.makedirs(PDF_FOLDER, exist_ok=True)

    for link_tag in soup.find_all('a', href=True):
        title = clean_title(link_tag.get_text(" ", strip=True))
        href = link_tag.get('href', '')
        if not href or href.startswith('#') or href.startswith('javascript'):
            continue

        full_link = urljoin(page_url, href)
        if full_link in seen_links:
            continue
        if "mizuhobank.co.jp" not in full_link and "mizuho-rt.co.jp" not in full_link:
            continue

        item = link_tag.find_parent(['li', 'article', 'div', 'tr'])
        item_text = item.get_text(" ", strip=True) if item else title
        date_text = normalize_date(item_text)
        if date_text == "未知日期":
            date_text = normalize_date(full_link)
        if date_text == "未知日期":
            continue
        if not is_within_30_days(date_text):
            continue

        if len(title) < 5:
            title = clean_title(full_link.rsplit('/', 1)[-1].replace('.pdf', ''))
        if len(title) < 5 or any(kw in title for kw in ["採用", "お問い合わせ", "個人情報", "プライバシー"]):
            continue

        # 🌟 找出真正的 PDF URL（list 頁 link 已是 .pdf 就直接用；否則進文章頁挖）
        pdf_url = full_link
        article_referer = page_url
        if not pdf_url.lower().split('?', 1)[0].endswith('.pdf'):
            try:
                page.set_extra_http_headers({**EXTRA_HEADERS, "Referer": page_url})
                page.goto(full_link, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(900)
                inner_html = page.content()
                if _is_access_denied(inner_html, page.title()):
                    continue
                inner_soup = BeautifulSoup(inner_html, 'html.parser')
                pdf_href = _find_pdf_in_article(inner_soup)
                if not pdf_href:
                    continue
                pdf_url = urljoin(full_link, pdf_href)
                article_referer = full_link
            except Exception:
                continue

        if pdf_url in seen_links:
            continue

        # 🌟 立刻在熱 session 內把 PDF 抓下來存檔（避開 main.py 重抓被 Akamai 擋）
        local_filename = _safe_filename(title)
        local_filepath = os.path.join(PDF_FOLDER, local_filename)
        if os.path.exists(local_filepath):
            print(f"    ✅ 已存在，跳過下載: {title[:35]}")
        else:
            if not _download_pdf(context, pdf_url, article_referer, local_filepath):
                print(f"    ❌ PDF 下載失敗（Akamai 擋）: {title[:35]}")
                continue
            print(f"    ✅ 已抓 PDF: {title[:35]}")

        github_link = f"{GITHUB_RAW_BASE}/{urllib.parse.quote(local_filename)}"
        seen_links.add(full_link)
        seen_links.add(pdf_url)
        found.append({
            "Source": "Mizuho",
            "Date": date_text,
            "Name": title,
            "Link": github_link,
            "Type": "PDF",
            "LocalPath": local_filepath,
        })
    return found


def scrape():
    print("🔍 正在爬取 Mizuho RT (瑞穗) - 🚀 啟用 Cookie 預熱 + 真實 fingerprint...")
    current_year = datetime.now().year
    target_urls = [
        ("https://www.mizuhobank.co.jp/corporate/mhri/research/report/index.html", "https://www.mizuhobank.co.jp/"),
        ("https://www.mizuhobank.co.jp/corporate/mhri/research/report/archive/index.html", "https://www.mizuhobank.co.jp/corporate/mhri/research/report/index.html"),
        (f"https://www.mizuho-rt.co.jp/publication/{current_year}/index.html", "https://www.mizuho-rt.co.jp/"),
    ]
    reports = []
    seen_links = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            context = browser.new_context(
                user_agent=UA,
                viewport={"width": 1440, "height": 900},
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
                extra_http_headers=EXTRA_HEADERS,
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)

            # 🌟 Cookie 預熱：先進兩個官網首頁，避免 Akamai 直接擋研究頁
            warmup_pages = [
                "https://www.mizuhobank.co.jp/",
                "https://www.mizuho-rt.co.jp/",
            ]
            for wu in warmup_pages:
                try:
                    page.goto(wu, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)
                    page.evaluate("window.scrollBy(0, 600)")
                    page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"  ⚠️ 預熱頁載入失敗: {wu} ({str(e)[:60]})")

            blocked_urls = []
            for target_url, referer in target_urls:
                soup, _ = _fetch_with_browser(page, target_url, referer=referer)
                if soup is None:
                    print(f"  ⚠️ Mizuho 官方站拒絕自動化請求，略過: {target_url}")
                    blocked_urls.append(target_url)
                    continue
                found = _extract_reports(soup, target_url, page, context, seen_links)
                if found:
                    print(f"  ✅ {target_url.rsplit('/', 2)[-2]} 收錄 {len(found)} 篇")
                    reports.extend(found)

            browser.close()

            # 🌟 最後一道防線：對被擋的頁面用 requests 試一次（共用 Playwright UA）
            if blocked_urls:
                _fallback_requests(blocked_urls, reports, seen_links)

    except Exception as e:
        print(f"  ❌ Mizuho 失敗: {e}")

    print(f"  ✅ Mizuho 找到 {len(reports)} 筆報告")
    return reports


def _fallback_requests(urls, reports, seen_links):
    """Playwright 被擋時，用 requests 試一次（Akamai 偶爾只擋 headless Chromium）。"""
    import requests
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, **EXTRA_HEADERS})
    # 先打首頁拿 cookie
    for warmup in ("https://www.mizuhobank.co.jp/", "https://www.mizuho-rt.co.jp/"):
        try:
            sess.get(warmup, timeout=15)
        except Exception:
            pass

    for url in urls:
        try:
            resp = sess.get(url, timeout=20)
            if resp.status_code != 200 or _is_access_denied(resp.text, ""):
                print(f"  ⚠️ requests 備援仍被擋: {url}")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            count_before = len(reports)
            for link_tag in soup.find_all('a', href=True):
                title = clean_title(link_tag.get_text(" ", strip=True))
                href = link_tag.get('href', '')
                if not href or href.startswith('#'):
                    continue
                full_link = urljoin(url, href)
                if full_link in seen_links:
                    continue
                if "mizuhobank.co.jp" not in full_link and "mizuho-rt.co.jp" not in full_link:
                    continue
                item = link_tag.find_parent(['li', 'article', 'div', 'tr'])
                item_text = item.get_text(" ", strip=True) if item else title
                date_text = normalize_date(item_text) if item_text else "未知日期"
                if date_text == "未知日期":
                    date_text = normalize_date(full_link)
                if date_text == "未知日期":
                    continue
                if not is_within_30_days(date_text):
                    continue
                if len(title) < 5:
                    title = clean_title(full_link.rsplit('/', 1)[-1].replace('.pdf', ''))
                if len(title) < 5:
                    continue
                # requests 模式下不再嘗試進入內頁，僅收已是 .pdf 的連結
                if not full_link.lower().split('?', 1)[0].endswith('.pdf'):
                    continue
                seen_links.add(full_link)
                reports.append({
                    "Source": "Mizuho",
                    "Date": date_text,
                    "Name": title,
                    "Link": full_link,
                })
            added = len(reports) - count_before
            if added:
                print(f"  ✅ requests 備援成功收錄 {added} 筆 ({url})")
        except Exception as e:
            print(f"  ⚠️ requests 備援錯誤: {url} ({str(e)[:80]})")
