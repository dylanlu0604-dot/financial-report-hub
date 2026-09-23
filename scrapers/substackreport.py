import re
import requests
from datetime import datetime
from xml.etree import ElementTree as ET
from scrapers.utils import HEADERS

# ==========================================
# RSS 來源設定
# ==========================================
RSS_URL = "https://notifier.in/rss/k8nfj5wzwfnaa53nf495lfevyxedsrco.xml"
SOURCE_NAME = "Substack Reports"

# 篩選關鍵字（不分大小寫比對）
FILTER_KEYWORDS = ["yardeni", "Andrew Lu on global","FOMO研究"]

# 排除條件（不分大小寫，命中任一則跳過該筆）
EXCLUDE_KEYWORDS = ["verification code", "請複製連結並貼到新的瀏覽器視窗中"]


def _matches_filter(text):
    """檢查文字是否包含任一篩選關鍵字（不分大小寫）"""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in FILTER_KEYWORDS)


def _matches_exclude(text):
    """檢查文字是否命中任一排除關鍵字（不分大小寫）"""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in EXCLUDE_KEYWORDS)


def _parse_rss_date(pub_date_str):
    """將 RSS pubDate（RFC 2822）轉換為 YYYY-MM-DD 格式"""
    if not pub_date_str:
        return "未知日期"
    # RFC 2822: "Fri, 11 Sep 2026 04:21:44 +0000"
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(pub_date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # fallback: 嘗試用 regex 抽取日期
    match = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", pub_date_str)
    if match:
        try:
            dt = datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return "未知日期"


def _strip_html(html_text):
    """簡易移除 HTML 標籤，取得純文字"""
    if not html_text:
        return ""
    return re.sub(r"<[^>]+>", "", html_text)


def scrape():
    print(f"🔍 正在爬取 {SOURCE_NAME} (篩選: {', '.join(FILTER_KEYWORDS)})...")
    reports = []

    try:
        resp = requests.get(RSS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ❌ 無法取得 RSS: {e}")
        return reports

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"  ❌ RSS XML 解析失敗: {e}")
        return reports

    # 處理可能帶有命名空間的標籤
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}

    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        description = item.findtext("description", "").strip()
        content_encoded = item.findtext("content:encoded", "", ns).strip()

        # 合併所有文字欄位做篩選
        searchable_text = f"{title} {_strip_html(description)} {_strip_html(content_encoded)}"

        # 排除條件：命中則跳過
        if _matches_exclude(searchable_text):
            continue

        # 篩選條件：未命中則跳過
        if not _matches_filter(searchable_text):
            continue

        # 通過篩選，加入報告清單
        report_name = title if title else "Untitled"
        report_date = _parse_rss_date(pub_date)

        reports.append({
            "Source": SOURCE_NAME,
            "Date": report_date,
            "Name": report_name,
            "Link": link if link else RSS_URL,
            "Type": "web",
        })

    print(f"  ✅ {SOURCE_NAME} 找到 {len(reports)} 筆符合條件的報告")
    return reports
