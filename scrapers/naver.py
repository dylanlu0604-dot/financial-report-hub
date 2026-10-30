"""Scrape research PDFs from Naver Securities."""

from datetime import date, datetime, timedelta
import random
import re
import time

import requests

from scrapers.utils import REPORT_WINDOW_DAYS


SOURCE = "Naver Securities"
SOURCE_NAME = SOURCE
RSS_FILENAME = "rss_naver_securities.xml"

BASE_URL = "https://stock.naver.com"
API_BASE_URL = f"{BASE_URL}/api/stockSecurity/researches/v2"
MARKET_RANK_API_URL = f"{BASE_URL}/api/domestic/market/stock/default"
MARKET_RANK_PAGE_URL = f"{BASE_URL}/market/stock/kr/stocklist/capitalization"
CATEGORIES = (
    ("company", "公司"),
    ("industry", "產業"),
    ("invest", "投資"),
    ("economy", "總經"),
    ("debenture", "債券"),
)
PAGE_SIZE = 50
TOP_COMPANY_COUNT = 5
MARKET_RANK_PAGE_SIZE = 100
REQUEST_TIMEOUT = 30
MAX_ATTEMPTS = 4
REQUEST_DELAY_SECONDS = (0.8, 1.5)

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
}

_session = requests.Session()
_session.headers.update(HEADERS)


class NaverAccessError(RuntimeError):
    """Raised when Naver rejects or rate-limits the scraper."""


def _get_json(url, params=None, referer=None):
    """Fetch JSON and retry transient server errors and rate limits."""
    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            time.sleep(random.uniform(*REQUEST_DELAY_SECONDS))
            headers = {"Referer": referer} if referer else None
            response = _session.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
            if response.status_code in (401, 403):
                raise NaverAccessError(
                    f"Naver rejected the request (HTTP {response.status_code})"
                )
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = min(float(retry_after), 30)
                except (TypeError, ValueError):
                    delay = 2 ** attempt
                if attempt + 1 < MAX_ATTEMPTS:
                    time.sleep(delay)
                    continue
                if response.status_code == 429:
                    raise NaverAccessError("Naver rate-limited the scraper (HTTP 429)")
                if response.status_code >= 500:
                    raise NaverAccessError(
                        f"Naver API remained unavailable after retries "
                        f"(HTTP {response.status_code})"
                    )
            response.raise_for_status()
            return response.json()
        except NaverAccessError:
            raise
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if 400 <= status < 500 and status != 429:
                raise
            last_error = exc
            if attempt + 1 < MAX_ATTEMPTS:
                time.sleep(2 ** attempt)
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt + 1 < MAX_ATTEMPTS:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Naver API request failed: {url}: {last_error}")


def _as_date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _normalize_item_code(value):
    code = str(value or "").strip()
    return code.zfill(6) if code.isdigit() else code


def _is_preferred_share(name):
    """Treat Korean preferred-share listings as the same company as common stock."""
    normalized = re.sub(r"\s+", "", str(name or "")).upper()
    return bool(re.search(r"\d*우[A-Z]?$", normalized))


def _get_top_company_codes():
    """Return the five largest Korean listed companies by Naver market cap."""
    items = _get_json(
        MARKET_RANK_API_URL,
        params={
            "tradeType": "KRX",
            "marketType": "ALL",
            "orderType": "marketSum",
            "startIdx": 0,
            "pageSize": MARKET_RANK_PAGE_SIZE,
        },
        referer=MARKET_RANK_PAGE_URL,
    )
    if not isinstance(items, list):
        raise RuntimeError("Naver market-cap ranking returned an unexpected payload")

    codes = []
    seen_codes = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "ST" or _is_preferred_share(
            item.get("itemname")
        ):
            continue
        code = _normalize_item_code(item.get("itemcode"))
        if not code or code in seen_codes:
            continue
        codes.append(code)
        seen_codes.add(code)
        if len(codes) == TOP_COMPANY_COUNT:
            return set(codes)

    raise RuntimeError(
        f"Naver market-cap ranking returned fewer than {TOP_COMPANY_COUNT} companies"
    )


def _list_recent_items(category, start_date, end_date):
    """Read all reports for one Naver category within the retention window."""
    items = []
    index = 0
    page_url = f"{BASE_URL}/research/{category}"

    while True:
        payload = _get_json(
            f"{API_BASE_URL}/{category}",
            params={
                "index": index,
                "size": PAGE_SIZE,
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
            },
            referer=page_url,
        )
        page_items = payload.get("items", [])
        if not isinstance(page_items, list) or not page_items:
            break

        items.extend(page_items)
        oldest_date = _as_date(page_items[-1].get("writeDate"))
        if oldest_date and oldest_date < start_date:
            break
        if not payload.get("hasNext"):
            break
        index += 1

    return items


def _make_report(category, item, start_date, end_date):
    """Resolve an index row to its official attachment URL and hub record."""
    category_label = dict(CATEGORIES)[category]
    page_url = f"{BASE_URL}/research/{category}"
    api_url = f"{API_BASE_URL}/{category}"
    nid = str(item.get("nid") or "").strip()
    report_date = _as_date(item.get("writeDate"))
    if not nid or not report_date or not start_date <= report_date <= end_date:
        return None

    detail_url = f"{page_url}/{nid}"
    detail = _get_json(f"{api_url}/{nid}", referer=page_url)
    pdf_url = str(detail.get("attachUrl") or "").strip()
    if not pdf_url.startswith("https://"):
        return None

    title = str(detail.get("title") or item.get("title") or "").strip()
    company = str(detail.get("itemName") or item.get("itemName") or "").strip()
    ticker = str(detail.get("itemCode") or item.get("itemCode") or "").strip()
    broker = str(detail.get("brokerName") or item.get("brokerName") or "").strip()
    if not title:
        return None

    report_name = " - ".join(part for part in (company, title, broker) if part)
    if ticker:
        report_name = f"[{ticker}] {report_name}"
    report_name = f"[{category_label}] {report_name}"

    report = {
        "Source": SOURCE,
        "Category": category_label,
        "Date": report_date.isoformat(),
        "Name": report_name,
        "Link": pdf_url,
        "OriginalLink": detail_url,
        "Type": "PDF",
    }
    if broker:
        report["Broker"] = broker
    if ticker:
        report["Ticker"] = ticker
    return report


def _make_report_safely(category, item, start_date, end_date):
    nid = str(item.get("nid") or "?")
    try:
        return _make_report(category, item, start_date, end_date)
    except NaverAccessError:
        raise
    except Exception as exc:
        print(f"  ⚠️ Naver 報告 {nid} 取得 PDF 連結失敗：{exc}")
        return None


def scrape():
    """Return recent Naver research PDFs across all supported categories."""
    today = date.today()
    start_date = today - timedelta(days=REPORT_WINDOW_DAYS)
    print(
        f"🔍 正在爬取 Naver Securities 研究報告 "
        f"({start_date.isoformat()} 至 {today.isoformat()})..."
    )

    reports = []
    seen_links = set()
    for category, category_label in CATEGORIES:
        print(f"  📂 正在取得 {category_label}（{category}）分類...")
        top_company_codes = None
        if category == "company":
            try:
                top_company_codes = _get_top_company_codes()
            except Exception as exc:
                print(
                    f"  ⚠️ 無法取得市值前五大公司，為避免擴大抓取量，"
                    f"跳過公司研究：{exc}"
                )
                continue
            print(f"  🎯 公司研究將只保留市值前 {TOP_COMPANY_COUNT} 大公司")

        try:
            items = _list_recent_items(category, start_date, today)
        except NaverAccessError as exc:
            print(f"  ⚠️ Naver {category_label} 分類請求遭拒或持續錯誤，跳過此分類：{exc}")
            continue
        listed_count = len(items)
        if top_company_codes is not None:
            items = [
                item for item in items
                if _normalize_item_code(item.get("itemCode")) in top_company_codes
            ]
            print(
                f"  📋 列表 API 回傳 {listed_count} 筆近期報告，前五大公司符合 "
                f"{len(items)} 筆，正在取得 PDF 連結..."
            )
        else:
            print(f"  📋 列表 API 回傳 {listed_count} 筆近期報告，正在取得 PDF 連結...")

        for item in items:
            try:
                report = _make_report_safely(category, item, start_date, today)
            except NaverAccessError as exc:
                print(f"  ⚠️ Naver 拒絕請求或持續錯誤，停止 {category_label} 後續報告：{exc}")
                break
            if not report or report["Link"] in seen_links:
                continue
            reports.append(report)
            seen_links.add(report["Link"])

    print(f"  ✅ Naver Securities 最終收錄 {len(reports)} 份 PDF 報告（{len(CATEGORIES)} 個分類）")
    return reports


if __name__ == "__main__":
    for report in scrape():
        print(f"{report['Date']} | {report['Name']} | {report['Link']}")
