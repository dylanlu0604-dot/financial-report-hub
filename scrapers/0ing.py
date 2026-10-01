"""Collect recent ING Think articles and linked report PDFs."""

from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://think.ing.com/"
MAX_AGE_DAYS = 25


def scrape():
    print("🔍 正在爬取 ING Think 經濟與金融分析報告...")
    reports = []
    session = requests.Session()
    cutoff = datetime.now().date() - timedelta(days=MAX_AGE_DAYS)
    try:
        response = session.get(BASE_URL, timeout=25)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        article_urls = []
        for anchor in soup.find_all("a", href=True):
            url = urljoin(BASE_URL, anchor["href"]).split("?", 1)[0].split("#", 1)[0]
            path = urlparse(url).path
            if url.startswith(BASE_URL) and path.startswith(("/articles/", "/reports/")):
                if path not in ("/articles/", "/reports/") and url not in article_urls:
                    article_urls.append(url)
        print(f"  📋 找到 {len(article_urls)} 篇候選文章")

        for article_url in article_urls[:15]:
            try:
                response = session.get(article_url, timeout=25)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                meta = soup.find("meta", attrs={"name": "date_published"})
                if not meta or not meta.get("content"):
                    continue
                published = datetime.strptime(meta["content"][:10], "%Y-%m-%d").date()
                if not cutoff <= published <= datetime.now().date():
                    continue
                heading = soup.find("h1")
                title = heading.get_text(" ", strip=True) if heading else ""
                if len(title) < 5:
                    continue
                pdf_url = next((urljoin(article_url, a["href"])
                                for a in soup.find_all("a", href=True)
                                if urlparse(urljoin(article_url, a["href"])).path.lower().endswith(".pdf")), None)
                reports.append({
                    "Source": "ING Think", "Date": published.isoformat(), "Name": title,
                    "Link": pdf_url or article_url, "Type": "PDF" if pdf_url else "WEB",
                })
                print(f"    ✅ [{published}] {title[:65]}")
            except (requests.RequestException, ValueError) as exc:
                print(f"    ⚠️ {article_url}：{exc}")
    except requests.RequestException as exc:
        print(f"  ❌ ING Think 爬取失敗：{exc}")
    print(f"  ✅ ING Think 最終收錄 {len(reports)} 筆報告")
    return reports
