import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scrapers.utils import HEADERS


SOURCE = "line報告備份"
FOLDER_ID = "1TsDz-JwKnsIpIeZedjmOhvh9ExEoSike"
EMBEDDED_FOLDER_URL = f"https://drive.google.com/embeddedfolderview?id={FOLDER_ID}"
RECENT_DAYS = 14
MAX_REPORTS = 200

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _clean_title(title):
    title = re.sub(r"\s+", " ", title or "").strip()
    return re.sub(r"\.pdf$", "", title, flags=re.IGNORECASE)


def _parse_date_from_title(title, today):
    patterns = [
        r"(?<!\d)(20\d{2})[-_.年]?(\d{1,2})[-_.月]?(\d{1,2})(?:日)?(?!\d)",
        r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, title or ""):
            parts = match.groups()
            if len(parts[0]) == 2:
                year, month, day = 2000 + int(parts[0]), int(parts[1]), int(parts[2])
            else:
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])

            try:
                parsed = datetime(year, month, day)
            except ValueError:
                continue

            if parsed.date() > (today + timedelta(days=31)).date():
                try:
                    parsed = datetime(year - 100, month, day)
                except ValueError:
                    continue
            return parsed

    return None


def _parse_last_modified(text, today):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return None

    if re.search(r"\d{1,2}:\d{2}", text):
        return today

    match = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:,\s*(\d{4}))?\b", text)
    if match:
        month = MONTHS.get(match.group(1).lower()[:3])
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year
        if month:
            try:
                parsed = datetime(year, month, day)
                if not match.group(3) and parsed.date() > (today + timedelta(days=1)).date():
                    parsed = datetime(year - 1, month, day)
                return parsed
            except ValueError:
                return None

    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    return None


def _extract_file_id(url):
    match = re.search(r"/file/d/([^/]+)", urlparse(url).path)
    return match.group(1) if match else None


def scrape():
    print(f"🔍 正在爬取 {SOURCE} (Google Drive)...")
    reports = []
    seen_file_ids = set()
    today = datetime.now()
    cutoff = today - timedelta(days=RECENT_DAYS)

    try:
        response = requests.get(EMBEDDED_FOLDER_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for entry in soup.select(".flip-entry"):
            link_tag = entry.select_one("a[href*='/file/d/']")
            title_tag = entry.select_one(".flip-entry-title")
            modified_tag = entry.select_one(".flip-entry-last-modified div")
            if not link_tag or not title_tag:
                continue

            raw_title = title_tag.get_text(" ", strip=True)
            if not raw_title.lower().endswith(".pdf"):
                continue

            file_id = _extract_file_id(link_tag.get("href", ""))
            if not file_id or file_id in seen_file_ids:
                continue

            modified_text = modified_tag.get_text(" ", strip=True) if modified_tag else ""
            parsed_date = _parse_date_from_title(raw_title, today) or _parse_last_modified(modified_text, today)
            if parsed_date and parsed_date < cutoff:
                continue

            reports.append({
                "Source": SOURCE,
                "Date": parsed_date.strftime("%Y-%m-%d") if parsed_date else "未知日期",
                "Name": _clean_title(raw_title),
                "Link": f"https://drive.google.com/uc?export=download&id={file_id}",
                "_sort_date": parsed_date or datetime.min,
            })
            seen_file_ids.add(file_id)

    except Exception as e:
        print(f"  ❌ {SOURCE} 失敗: {e}")

    reports.sort(key=lambda report: report["_sort_date"], reverse=True)
    reports = reports[:MAX_REPORTS]
    for report in reports:
        report.pop("_sort_date", None)

    print(f"  ✅ {SOURCE} 找到 {len(reports)} 筆報告")
    return reports


if __name__ == "__main__":
    for report in scrape():
        print(report)
