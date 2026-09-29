import re
from datetime import datetime
from urllib.parse import urljoin

import requests


PAGE_URL = "https://www.cathay-cube.com.tw/cathaybk/personal/product/wealth/market/report"
MODEL_URL = f"{PAGE_URL}.model.json"


def extract_date(text):
    """Read the publication date shown beside the investment report button."""
    match = re.search(r"(20\d{2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})", text or "")
    if not match:
        return None
    try:
        return datetime(int(match[1]), int(match[2]), int(match[3])).strftime("%Y-%m-%d")
    except ValueError:
        return None


def investment_report_buttons(node):
    """Find report buttons in Cathay's AEM page model, including nested tabs."""
    if isinstance(node, dict):
        button = (node.get("btnContent") or {}).get("main") or {}
        if (button.get("text") or "").strip() == "投資研究報告":
            yield button.get("link"), node.get("noteText")
        for value in node.values():
            yield from investment_report_buttons(value)
    elif isinstance(node, list):
        for value in node:
            yield from investment_report_buttons(value)


def scrape():
    print("🔍 正在爬取 Cathay (國泰世華) - 投資研究報告...")
    reports = []
    seen_pdfs = set()

    try:
        response = requests.get(MODEL_URL, timeout=30)
        response.raise_for_status()
        model = response.json()

        for link, note in investment_report_buttons(model):
            if not link or not link.lower().endswith(".pdf"):
                continue
            pdf_url = urljoin(PAGE_URL, link)
            if pdf_url in seen_pdfs:
                continue

            date = extract_date(note)
            if not date:
                print(f"  ⚠️ 找不到投資研究報告的資料日期，略過: {pdf_url}")
                continue

            year, month, day = date.split("-")
            reports.append({
                "Source": "Cathay",
                "Date": date,
                "Name": f"{year}年{int(month)}月{int(day)}日國泰世華投資研究報告",
                "Link": pdf_url,
            })
            seen_pdfs.add(pdf_url)
    except (requests.RequestException, ValueError) as exc:
        print(f"  ❌ Cathay 爬取失敗: {exc}")

    if reports:
        print(f"  ✅ Cathay 最終收錄 {len(reports)} 筆投資研究報告")
    else:
        print("  ⚠️ Cathay 未收錄投資研究報告，請檢查頁面模型與資料日期")
    return reports


if __name__ == "__main__":
    from pprint import pprint

    pprint(scrape())
