import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


BASE_URL = "https://www.goldmansachs.com"
TOP_OF_MIND_URL = "https://www.goldmansachs.com/insights/top-of-mind"


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip() if text else ""


def parse_us_date(text):
    match = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
        r"(\d{1,2}),\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return "未知日期", text

    month, day, year = match.groups()
    try:
        parsed = datetime.strptime(
            f"{month[:3].title()} {int(day)} {year}",
            "%b %d %Y",
        ).strftime("%Y-%m-%d")
    except ValueError:
        parsed = "未知日期"

    return parsed, text[:match.start()].strip()


def clean_title(raw_text):
    _, title_without_date = parse_us_date(raw_text)
    title = re.sub(
        r"^(Top of Mind\s*-?\s*)+",
        "",
        title_without_date,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"^[:\-\s]+", "", title)
    return clean_text(title)


def parse_meta_date(soup):
    candidates = []
    for attrs in (
        {"property": "article:published_time"},
        {"name": "article:published_time"},
        {"name": "date"},
        {"name": "publishdate"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            candidates.append(tag["content"])

    time_tag = soup.find("time")
    if time_tag:
        candidates.extend(
            value
            for value in [time_tag.get("datetime"), time_tag.get_text(" ", strip=True)]
            if value
        )

    for value in candidates:
        iso_match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
        if iso_match:
            return (
                f"{iso_match.group(1)}-"
                f"{int(iso_match.group(2)):02d}-"
                f"{int(iso_match.group(3)):02d}"
            )

        parsed, _ = parse_us_date(value)
        if parsed != "未知日期":
            return parsed

    return "未知日期"


def is_top_of_mind_article(href):
    clean_href = href.split("?")[0].rstrip("/")
    return (
        "/insights/top-of-mind/" in clean_href
        and clean_href != "/insights/top-of-mind"
    )


def find_pdf_url(article_soup):
    for tag in article_soup.find_all("a", href=True):
        href = tag.get("href", "")
        link_text = clean_text(tag.get_text(separator=" ")).lower()
        href_lower = href.lower()

        if (
            ".pdf" in href_lower
            or "download pdf" in link_text
            or "download report" in link_text
        ):
            return urljoin(BASE_URL, href)

    return None


def scrape():
    print("🔍 正在爬取 Goldman Sachs Top of Mind - 文章/PDF 雙模式...")
    reports = []
    seen_articles = set()
    seen_links = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)

            try:
                page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in {"image", "media", "font"}
                    else route.continue_(),
                )
            except Exception:
                pass

            page.goto(TOP_OF_MIND_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)

            soup = BeautifulSoup(page.content(), "html.parser")
            valid_articles = []

            for tag in soup.find_all("a", href=True):
                href = tag["href"]
                if not is_top_of_mind_article(href):
                    continue

                article_url = urljoin(BASE_URL, href.split("?")[0])
                if article_url in seen_articles:
                    continue

                raw_text = clean_text(tag.get_text(separator=" "))
                parsed_date, _ = parse_us_date(raw_text)
                title = clean_title(raw_text)
                if not title or len(title) < 5:
                    title = article_url.rstrip("/").split("/")[-1].replace("-", " ").title()

                valid_articles.append((title, parsed_date, article_url))
                seen_articles.add(article_url)

            valid_articles = valid_articles[:10]
            print(f"  👉 找到 {len(valid_articles)} 篇 Top of Mind 文章，準備檢查 PDF/網頁...")

            for title, article_date, article_url in valid_articles:
                print(f"    🕵️ 檢查文章: {title[:35]}... ({article_date})")
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=25000)
                    page.wait_for_timeout(1500)
                    article_soup = BeautifulSoup(page.content(), "html.parser")

                    if article_date == "未知日期":
                        article_date = parse_meta_date(article_soup)

                    pdf_url = find_pdf_url(article_soup)
                    if pdf_url:
                        final_link = pdf_url
                        report_type = "PDF"
                        print("      ✅ 找到官方 PDF 連結")
                    else:
                        final_link = article_url
                        report_type = "Web"
                        print("      ✅ 未提供 PDF，保留文章頁給主程式轉 PDF")

                    if final_link in seen_links:
                        continue

                    reports.append(
                        {
                            "Source": "Goldman Sachs (Top of Mind)",
                            "Date": article_date,
                            "Name": f"Top of Mind - {title}",
                            "Link": final_link,
                            "Type": report_type,
                        }
                    )
                    seen_links.add(final_link)
                except Exception as e:
                    print(f"      ❌ 文章檢查失敗: {str(e)[:60]}")

            browser.close()
    except Exception as e:
        print(f"  ❌ Goldman Sachs Top of Mind 爬取異常: {e}")

    print(f"  ✅ Goldman Sachs Top of Mind 收錄 {len(reports)} 篇")
    return reports


if __name__ == "__main__":
    scrape()
