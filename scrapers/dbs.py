import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.dbs.com.tw"
ARCHIVE_URL = f"{BASE_URL}/personal/aics/archive/index.page"
API_ROOT = f"{BASE_URL}/twgenericcontent/v1/contentapi"
PAGE_SIZE = 10
MAX_AGE_DAYS = 25  # The main pipeline uses the same age limit for DBS reports.


def find_initial_articles(node):
    """Locate the archive's server-rendered first page in __NEXT_DATA__."""
    if isinstance(node, dict):
        initial = node.get("fetchedInitialArticles")
        if isinstance(initial, dict) and isinstance(initial.get("hits"), list):
            return initial
        for value in node.values():
            found = find_initial_articles(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_initial_articles(value)
            if found is not None:
                return found
    return None


def article_hits(session, index, offset):
    """Use the POST search endpoint used by the archive's pagination control."""
    payload = {
        "query": {"bool": {"filter": [
            {"range": {"date_sort.PublishedDate": {"lte": "now+1d/d"}}},
            {"range": {"date_sort.ExpiryDate": {"gte": "now/d"}}},
            {"term": {"meta.type": "article/generic"}},
            {"nested": {"path": "string_facet", "query": {"bool": {"filter": [
                {"term": {"string_facet.facet-type": "Segment"}},
                {"term": {"string_facet.facet-value": "personal"}},
            ]}}}},
            {"term": {"meta.Country": "tw"}},
        ]}},
        "sort": {"date_sort.PublishedDate": {"order": "desc"}},
        "from": offset,
        "size": PAGE_SIZE,
    }
    response = session.post(f"{API_ROOT}/{index}/search", json=payload, timeout=25)
    response.raise_for_status()
    return response.json().get("hits", {}).get("hits", [])


def parse_hit(hit):
    source = hit.get("_source") or {}
    result = source.get("results_data") or {}
    title = (result.get("Title") or "").strip()
    relative_path = (result.get("RelativeDCRPath") or "").strip()
    if not title or not relative_path or (result.get("Format") or "").lower() == "video":
        return None
    video_url = ((source.get("search_data") or {}).get("VideoDetails") or {}).get("VideoURL") or ""
    if "youtube" in video_url.lower():
        return None
    try:
        date = datetime.strptime((source.get("date_sort") or {})["PublishedDate"][:10], "%Y-%m-%d").date()
    except (KeyError, TypeError, ValueError):
        return None
    article_url = urljoin(f"{BASE_URL}/personal/aics/archive/", relative_path)
    return title, article_url, date


def pdf_link(session, article_url):
    response = session.get(article_url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "wrapperapi" in href and "download-pdf" in href:
            return urljoin(article_url, href)
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/article/pdf/" in href and href.lower().endswith(".pdf"):
            return urljoin(article_url, href)
    return None


def save_pdf(session, pdf_url, path):
    """Save only a real PDF, so an error page cannot be mistaken for a report."""
    temporary_path = None
    try:
        with session.get(pdf_url, timeout=45, stream=True) as response:
            response.raise_for_status()
            chunks = (chunk for chunk in response.iter_content(chunk_size=65536) if chunk)
            first_chunk = next(chunks, b"")
            if not first_chunk.startswith(b"%PDF"):
                raise ValueError("下載內容不是 PDF")
            with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), prefix=".dbs-", suffix=".pdf", delete=False) as output:
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
    print("🔍 正在爬取 DBS (星展銀行)...")
    reports = []
    output_dir = os.path.abspath("all report pdf")
    os.makedirs(output_dir, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": ARCHIVE_URL})

    try:
        response = session.get(ARCHIVE_URL, timeout=30)
        response.raise_for_status()
        script = BeautifulSoup(response.text, "html.parser").find("script", id="__NEXT_DATA__")
        if script is None or not script.string:
            raise ValueError("Archive 頁面沒有 __NEXT_DATA__")
        initial = find_initial_articles(json.loads(script.string))
        if initial is None:
            raise ValueError("Archive 頁面沒有 fetchedInitialArticles")

        hits = initial["hits"]
        total = (initial.get("total") or {}).get("value", len(hits))
        index = hits[0].get("_index", "") if hits else ""
        if not re.fullmatch(r"[\w-]+", index):
            raise ValueError("無法從首頁取得文章索引")
        print(f"  📊 Archive 共 {total} 篇，首頁提供 {len(hits)} 篇")

        cutoff = datetime.now().date() - timedelta(days=MAX_AGE_DAYS)
        recent_articles = []
        seen_urls = set()
        offset = 0
        while hits:
            dated_hits = []
            for hit in hits:
                article = parse_hit(hit)
                if not article:
                    continue
                title, article_url, date = article
                dated_hits.append(date)
                if date >= cutoff and article_url not in seen_urls:
                    recent_articles.append(article)
                    seen_urls.add(article_url)
            if dated_hits and min(dated_hits) < cutoff:
                break
            offset += PAGE_SIZE
            if offset >= total:
                break
            hits = article_hits(session, index, offset)
            print(f"  📥 第 {offset // PAGE_SIZE + 1} 頁取得 {len(hits)} 篇")

        print(f"  📋 近 {MAX_AGE_DAYS} 天有 {len(recent_articles)} 篇非影片文章")
        for title, article_url, date in recent_articles:
            try:
                pdf_url = pdf_link(session, article_url)
                if not pdf_url:
                    print(f"    ⚠️ 無 PDF 連結：{title[:60]}")
                    continue
                name = f"{title} ({date.isoformat()})"
                safe_name = re.sub(r'[\\/*?:"<>|]', "_", name).strip()[:180]
                local_path = os.path.join(output_dir, f"{safe_name}.pdf")
                if not is_pdf_file(local_path):
                    save_pdf(session, pdf_url, local_path)
                reports.append({
                    "Source": "DBS",
                    "Date": date.isoformat(),
                    "Name": name,
                    "Link": pdf_url,
                    "Type": "PDF",
                    "LocalPath": local_path,
                })
                print(f"    ✅ [{date}] {title[:60]}")
            except (requests.RequestException, OSError, ValueError) as exc:
                print(f"    ⚠️ {title[:60]}：{exc}")
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        print(f"  ❌ DBS 爬取失敗：{exc}")

    if reports:
        print(f"✅ DBS 最終收錄 {len(reports)} 份 PDF 報告")
    else:
        print("⚠️ DBS 沒有取得近期 PDF 報告")
    return reports


if __name__ == "__main__":
    scrape()
