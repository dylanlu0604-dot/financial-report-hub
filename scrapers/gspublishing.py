import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers.utils import HEADERS


BASE_URL = "https://www.gspublishing.com"
LIST_URL = "https://www.gspublishing.com/content/public.html"


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip() if text else ""


def parse_report_date(text):
    match = re.search(
        r"\b(\d{1,2})\s+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
        r"\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return "未知日期"

    day, month, year = match.groups()
    try:
        return datetime.strptime(
            f"{day} {month[:3].title()} {year}",
            "%d %b %Y",
        ).strftime("%Y-%m-%d")
    except ValueError:
        return "未知日期"


def pdf_url_from_report_url(report_url):
    if report_url.lower().endswith(".pdf"):
        return report_url
    if report_url.lower().endswith(".html"):
        return report_url[:-5] + ".pdf"
    return report_url


def scrape():
    print("🔍 正在爬取 Goldman Sachs Publishing (Public Research) - 直接擷取 PDF...")
    reports = []
    seen_links = set()

    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        links = soup.find_all(
            "a",
            href=re.compile(r"/content/research/en/reports/\d{4}/\d{2}/\d{2}/[^\"']+\.html$"),
        )

        for tag in links:
            title = clean_text(tag.get_text(separator=" "))
            if len(title) < 5:
                continue

            report_url = urljoin(BASE_URL, tag["href"])
            pdf_url = pdf_url_from_report_url(report_url)
            if pdf_url in seen_links:
                continue

            container = tag.find_parent(attrs={"data-testid": "query-list-item-container"})
            parent = tag.find_parent()
            context_node = container or parent or tag
            context_text = context_node.get_text(separator=" ", strip=True)
            date_text = parse_report_date(context_text)

            reports.append({
                "Source": "Goldman Sachs Publishing",
                "Date": date_text,
                "Name": title,
                "Link": pdf_url,
                "Type": "PDF",
            })
            seen_links.add(pdf_url)

    except Exception as e:
        print(f"  ❌ Goldman Sachs Publishing 爬取失敗: {e}")

    print(f"  ✅ Goldman Sachs Publishing 找到 {len(reports)} 筆 PDF 報告")
    return reports


if __name__ == "__main__":
    scrape()
