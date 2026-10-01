import base64
import hashlib
import html
import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


BASE_URL = "https://www.mizuhobank.co.jp"
INDEX_URL = f"{BASE_URL}/corporate/mhri/research/report/index.html"
REPORTS_URL = f"{BASE_URL}/corporate/mhri/research/assets/json/reports.json"
PDF_FOLDER = "all report pdf"
MAX_AGE_DAYS = 25  # Match the retention filter in main.py.


def recent_reports(catalog, today=None):
    """Select dated reports from the official Mizuho research index."""
    today = today or datetime.now().date()
    cutoff = today - timedelta(days=MAX_AGE_DAYS)
    selected = []
    seen_paths = set()
    for item in catalog.get("reports", []):
        path = item.get("path", "")
        if not path.startswith("/corporate/mhri/research/") or path in seen_paths:
            continue
        try:
            published = datetime.strptime(item["published"], "%Y/%m/%d").date()
        except (KeyError, TypeError, ValueError):
            continue
        if not cutoff <= published <= today:
            continue
        title = re.sub(r"\s+", " ", html.unescape(item.get("title") or "")).strip()
        title = re.sub(r"\s*[（(]PDF/[^）)]+[）)]", "", title)
        if not title:
            continue
        seen_paths.add(path)
        selected.append((title, path, published))
    return selected


def report_pdf_url(page_html, article_url):
    """Find the report PDF on an article page, excluding footer documents."""
    soup = BeautifulSoup(page_html, "html.parser")
    candidates = []
    for anchor in soup.find_all("a", href=True):
        pdf_url = urljoin(article_url, anchor["href"])
        if not pdf_url.startswith(f"{BASE_URL}/corporate/mhri/research/"):
            continue
        if not pdf_url.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        label = anchor.get_text(" ", strip=True)
        if "本レポート" in label:
            return pdf_url
        candidates.append(pdf_url)
    return candidates[0] if candidates else None


def pdf_filename(title, date, pdf_url):
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title).strip(" .")
    # Keep the whole filename below common filesystem byte limits, including Japanese text.
    safe_title = safe_title.encode("utf-8")[:180].decode("utf-8", errors="ignore").rstrip(" .")
    suffix = hashlib.sha1(pdf_url.encode("utf-8")).hexdigest()[:8]
    return f"{date.isoformat()}_{safe_title}_{suffix}.pdf"


def is_pdf_file(path):
    try:
        with open(path, "rb") as existing:
            return existing.read(4) == b"%PDF"
    except FileNotFoundError:
        return False


def _remote_pdf_body(page, pdf_url):
    """Download through the remote browser's network, not the runner's blocked IP."""
    result = page.evaluate("""async (url) => {
        const response = await fetch(url, {credentials: 'include'});
        if (!response.ok) return {status: response.status};
        const blob = await response.blob();
        const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(blob);
        });
        return {status: response.status, data: dataUrl.split(',')[1]};
    }""", pdf_url)
    if result.get("status") != 200 or not result.get("data"):
        raise RuntimeError(f"遠端 PDF 下載失敗（HTTP {result.get('status')}）")
    return base64.b64decode(result["data"], validate=True)


def _scrape_with_context(context, output_dir=PDF_FOLDER, remote_download=False):
    reports = []
    page = context.new_page()
    try:
        response = page.goto(INDEX_URL, wait_until="domcontentloaded", timeout=45000)
        if not response or response.status != 200 or "Access Denied" in page.title():
            raise RuntimeError(f"瑞穗銀行研究頁無法存取（HTTP {response.status if response else '無回應'}）")

        catalog = page.evaluate("""async (url) => {
            const response = await fetch(url, {cache: 'no-store'});
            if (!response.ok) throw new Error(`reports.json HTTP ${response.status}`);
            return response.json();
        }""", REPORTS_URL)
        if not isinstance(catalog, dict) or not isinstance(catalog.get("reports"), list):
            raise ValueError("reports.json 缺少報告清單")

        items = recent_reports(catalog)
        print(f"  📋 官方索引共有 {len(catalog['reports'])} 篇，近 {MAX_AGE_DAYS} 天 {len(items)} 篇")
        os.makedirs(output_dir, exist_ok=True)
        for title, path, published in items:
            article_url = urljoin(BASE_URL, path)
            try:
                if path.lower().endswith(".pdf"):
                    pdf_url = article_url
                else:
                    article_response = page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
                    if not article_response or article_response.status != 200:
                        raise RuntimeError(f"報告頁 HTTP {article_response.status if article_response else '無回應'}")
                    pdf_url = report_pdf_url(page.content(), article_url)
                if not pdf_url:
                    print(f"    ⚠️ 找不到 PDF：{title[:50]}")
                    continue

                local_path = os.path.abspath(os.path.join(output_dir, pdf_filename(title, published, pdf_url)))
                if not is_pdf_file(local_path):
                    if remote_download:
                        body = _remote_pdf_body(page, pdf_url)
                    else:
                        pdf_response = context.request.get(
                            pdf_url, headers={"Referer": article_url}, timeout=45000
                        )
                        body = pdf_response.body()
                        if pdf_response.status != 200:
                            raise RuntimeError(f"PDF 下載失敗（HTTP {pdf_response.status}）")
                    if not body.startswith(b"%PDF"):
                        raise ValueError("下載內容不是 PDF")
                    with open(local_path, "wb") as output:
                        output.write(body)

                reports.append({
                    "Source": "Mizuho",
                    "Date": published.isoformat(),
                    "Name": title,
                    "Link": pdf_url,
                    "Type": "PDF",
                    "LocalPath": local_path,
                })
                print(f"    ✅ [{published}] {title[:50]}")
            except Exception as exc:
                print(f"    ⚠️ {title[:50]}：{exc}")
    finally:
        page.close()
    return reports


def _scrape_with_remote_browser(output_dir=PDF_FOLDER):
    """Use an authenticated remote browser when GitHub's IP is denied by Mizuho."""
    created = subprocess.run(
        ["tinyfish", "browser", "session", "create", "--url", INDEX_URL],
        check=True, capture_output=True, text=True, timeout=45,
    )
    cdp_url = json.loads(created.stdout)["cdp_url"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=30000)
        try:
            context = browser.contexts[0]
            return _scrape_with_context(context, output_dir, remote_download=True)
        finally:
            browser.close()


def scrape():
    print("🔍 正在爬取 Mizuho (瑞穗銀行研究報告)...")
    reports = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    locale="ja-JP",
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
                reports = _scrape_with_context(context)
            finally:
                browser.close()
    except Exception as exc:
        print(f"  ⚠️ 瑞穗銀行日本研究頁無法存取：{exc}")

    if not reports and os.environ.get("TINYFISH_API_KEY"):
        print("  🔄 改用遠端瀏覽器讀取瑞穗日本研究頁...")
        try:
            reports = _scrape_with_remote_browser()
        except Exception as exc:
            print(f"  ⚠️ 瑞穗日本研究頁遠端瀏覽器失敗（{type(exc).__name__}）")

    if reports:
        print(f"  ✅ Mizuho 最終收錄 {len(reports)} 份 PDF 報告（來源：{reports[0]['Source']}）")
    else:
        print("::error title=Mizuho research unavailable::瑞穗日本研究報告未取得；GitHub runner 受到 HTTP 403 阻擋")
    return reports


if __name__ == "__main__":
    scrape()
