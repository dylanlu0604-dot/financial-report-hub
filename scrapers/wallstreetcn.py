import email.utils
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scrapers.utils import HEADERS

RSS_URL = "https://feed.wallstreetcn.com/wallstreetcn/news/global"
API_URL = "https://api-one-wscn.awtmt.com/apiv1/content/information-flow"
MAX_REPORTS = 100
MAX_API_PAGES = 6
API_PAGE_LIMIT = 20
API_HEADERS = {
    **HEADERS,
    "X-Ivanka-App": "wscn|web|0.40.40|0.0|0",
}


def parse_rss_date(pub_date):
    try:
        parsed = email.utils.parsedate_to_datetime(pub_date)
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return time.strftime("%Y-%m-%d")


def description_text(description_html):
    return BeautifulSoup(description_html or "", "html.parser").get_text(" ", strip=True)


def parse_api_date(display_time):
    try:
        return datetime.fromtimestamp(int(display_time)).strftime("%Y-%m-%d")
    except Exception:
        return time.strftime("%Y-%m-%d")


def is_public_article_link(link):
    return bool(link) and "/articles/" in link and "/member/" not in link


def scrape_api_reports():
    reports = []
    seen_links = set()
    cursor = ""

    for page_no in range(1, MAX_API_PAGES + 1):
        params = {
            "channel": "global",
            "accept": "article",
            "cursor": cursor,
            "limit": API_PAGE_LIMIT,
            "action": "upglide",
        }
        response = requests.get(API_URL, params=params, headers=API_HEADERS, timeout=30)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        items = data.get("items") or []
        print(f"  [API] 第 {page_no} 頁讀取 {len(items)} 筆")

        for item in items:
            if len(reports) >= MAX_REPORTS:
                break

            if item.get("resource_type") != "article":
                continue

            resource = item.get("resource") or {}
            title = (resource.get("title") or "").strip()
            link = (resource.get("uri") or "").strip()
            short_text = (resource.get("content_short") or resource.get("subtitle") or "").strip()

            if not title or link in seen_links or not is_public_article_link(link):
                continue
            if len(short_text) < 20:
                print(f"    ⚠️ 剔除摘要過短項目: {title[:20]}...")
                continue

            seen_links.add(link)
            reports.append({
                "Source": "WallstreetCN (Global)",
                "Date": parse_api_date(resource.get("display_time")),
                "Name": title,
                "Link": link,
                "Type": "Web",
            })

        if len(reports) >= MAX_REPORTS:
            break

        cursor = data.get("next_cursor") or ""
        if not cursor:
            break

    return reports


def scrape_rss_reports():
    reports = []
    seen_links = set()
    try:
        response = requests.get(RSS_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as e:
        print(f"  ❌ 華爾街見聞 RSS 載入失敗: {e}")
        return reports

    items = root.findall("./channel/item")
    print(f"  [RSS] 成功讀取 {len(items)} 筆最新項目，開始篩選長文...")

    for item in items:
        if len(reports) >= MAX_REPORTS:
            break

        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = item.findtext("pubDate") or ""
        text = description_text(item.findtext("description") or "")

        if not title or not link or link in seen_links:
            continue
        seen_links.add(link)

        # 跳過快訊、圖表與會員牆頁面；保留可轉印的公開長文。
        if not is_public_article_link(link) or len(text) < 200:
            print(f"    ⚠️ 剔除非長文或受限內容: {title[:20]}...")
            continue

        reports.append({
            "Source": "WallstreetCN (Global)",
            "Date": parse_rss_date(pub_date),
            "Name": title,
            "Link": link,
            "Type": "Web",
        })

    return reports


def scrape():
    print("🔍 正在爬取 華爾街見聞 (Global) - 🚀 啟動 API 分頁 + RSS 備援模式...")

    try:
        reports = scrape_api_reports()
        print(f"  ✅ 華爾街見聞 最終成功收錄 {len(reports)} 篇【API 分頁長文】！")
        return reports
    except Exception as e:
        print(f"  ⚠️ 華爾街見聞 API 分頁失敗，改用 RSS 備援: {e}")

    reports = scrape_rss_reports()
    print(f"  ✅ 華爾街見聞 最終成功收錄 {len(reports)} 篇【RSS 長文報導】！")
    return reports


if __name__ == "__main__":
    scrape()
