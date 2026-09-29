"""Collect Allianz Trade PDFs from official economic insight articles."""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.allianz-trade.com"
ARTICLE_ROOT = BASE_URL + "/en_global/news-insights/economic-insights/"
INDEX_URL = BASE_URL + "/en_global/news-insights/economic-insights.html"
SITEMAP_URL = BASE_URL + "/en_global.sitemap.xml"
MAX_AGE_DAYS = 25


def article_urls(session):
    urls = []
    try:
        response = session.get(INDEX_URL, timeout=30)
        response.raise_for_status()
        if not any(marker in response.text.lower() for marker in ("cf_chl", "challenge-platform")):
            for anchor in BeautifulSoup(response.text, "html.parser").find_all("a", href=True):
                url = urljoin(INDEX_URL, anchor["href"]).split("#", 1)[0].split("?", 1)[0]
                if url.startswith(ARTICLE_ROOT) and url.endswith(".html") and url not in urls:
                    urls.append(url)
    except requests.RequestException as exc:
        print(f"  ⚠️ 文章列表無法讀取：{exc}")
    if urls:
        return urls[:20]

    print("  🔄 改讀 Allianz Trade 官方 sitemap...")
    response = session.get(SITEMAP_URL, timeout=45)
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    cutoff = datetime.now().date() - timedelta(days=MAX_AGE_DAYS)
    entries = []
    for item in root.findall("s:url", ns):
        url = item.findtext("s:loc", default="", namespaces=ns)
        modified = item.findtext("s:lastmod", default="", namespaces=ns)
        if not url.startswith(ARTICLE_ROOT) or not url.endswith(".html"):
            continue
        try:
            if datetime.strptime(modified[:10], "%Y-%m-%d").date() >= cutoff:
                entries.append((modified, url))
        except ValueError:
            continue
    return [url for _, url in sorted(entries, reverse=True)[:30]]


def article_details(html, article_url):
    soup = BeautifulSoup(html, "html.parser")
    title, published = "", None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            items += data["@graph"]
        for item in items:
            if isinstance(item, dict) and item.get("datePublished"):
                try:
                    published = datetime.fromisoformat(item["datePublished"].replace("Z", "+00:00")).date()
                except ValueError:
                    continue
                title = item.get("headline") or item.get("name") or ""
                break
    if not title:
        heading = soup.find("h1") or soup.find("title")
        title = heading.get_text(" ", strip=True) if heading else ""
    title = re.sub(r"\s+", " ", title).strip()
    pdf_url = None
    for anchor in soup.find_all("a", href=True):
        url = urljoin(article_url, anchor["href"])
        if not urlparse(url).path.lower().endswith(".pdf"):
            continue
        label = anchor.get("aria-label") or anchor.get_text(" ", strip=True)
        if "Read the full report" in label:
            pdf_url = url
            break
        if "/erd/publications/pdf/" in url and pdf_url is None:
            pdf_url = url
    return title, published, pdf_url


def save_pdf(session, url, path, referer):
    temporary_path = None
    try:
        with session.get(url, headers={"Referer": referer}, timeout=45, stream=True) as response:
            response.raise_for_status()
            chunks = (chunk for chunk in response.iter_content(65536) if chunk)
            first_chunk = next(chunks, b"")
            if not first_chunk.startswith(b"%PDF"):
                raise ValueError("下載內容不是 PDF")
            with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), prefix=".allianz-", suffix=".pdf", delete=False) as output:
                temporary_path = output.name
                output.write(first_chunk)
                for chunk in chunks:
                    output.write(chunk)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def is_pdf_file(path):
    try:
        with open(path, "rb") as existing:
            return existing.read(4) == b"%PDF"
    except FileNotFoundError:
        return False


def scrape():
    print("🔍 正在爬取 Allianz Trade 經濟研究報告...")
    reports, seen = [], set()
    session = requests.Session()
    output_dir = os.path.abspath("all report pdf")
    os.makedirs(output_dir, exist_ok=True)
    cutoff = datetime.now().date() - timedelta(days=MAX_AGE_DAYS)
    try:
        urls = article_urls(session)
        print(f"  📋 找到 {len(urls)} 篇候選文章")
        for article_url in urls:
            try:
                response = session.get(article_url, timeout=30)
                response.raise_for_status()
                title, published, pdf_url = article_details(response.text, article_url)
                if not title or not published or not cutoff <= published <= datetime.now().date():
                    continue
                if not pdf_url or not pdf_url.startswith(BASE_URL + "/content/dam/") or pdf_url in seen:
                    continue
                seen.add(pdf_url)
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", title).strip(" .")[:120]
                digest = hashlib.sha1(pdf_url.encode()).hexdigest()[:8]
                path = os.path.join(output_dir, f"Allianz_{published}_{safe_title}_{digest}.pdf")
                if not is_pdf_file(path):
                    save_pdf(session, pdf_url, path, article_url)
                reports.append({"Source": "Allianz Trade", "Date": published.isoformat(),
                                "Name": title, "Link": pdf_url, "Type": "PDF", "LocalPath": path})
                print(f"    ✅ [{published}] {title[:65]}")
            except (requests.RequestException, OSError, ValueError) as exc:
                print(f"    ⚠️ {article_url}：{exc}")
    except (requests.RequestException, ElementTree.ParseError) as exc:
        print(f"  ❌ Allianz Trade 爬取失敗：{exc}")
    print(f"  ✅ Allianz Trade 最終收錄 {len(reports)} 份 PDF 報告")
    return reports


if __name__ == "__main__":
    scrape()
