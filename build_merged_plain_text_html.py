import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from boilerplate_filter import filter_boilerplate_chunks, is_boilerplate
from pypdf import PdfReader


SRC_DIR = Path("all report pdf")
OUT_DIR = Path("merged_plain_text_html")
REPORTS_JSON = Path("data/reports.json")
SOURCE_COUNT = 30
GENERAL_SOURCE_COUNT = 25
LINE_BACKUP_SOURCE = "line報告備份"
SOURCE_DIGITS = 2
BOILERPLATE_THRESHOLD = 0.30
RAW_URL_BASE = (
    "https://cdn.jsdelivr.net/gh/dylanlu0604-dot/financial-report-hub"
    "@main/merged_plain_text_html"
)


def safe_title(value: str, fallback: str) -> str:
    title = value.strip() or fallback
    title = re.sub(r"[\0/\\:*?\"<>|]+", "_", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title[:180] or fallback


def clean_text(value: str) -> str:
    return value.encode("utf-8", "replace").decode("utf-8")


def load_report_metadata() -> dict[str, dict[str, str]]:
    if not REPORTS_JSON.exists():
        return {}

    try:
        reports = json.loads(REPORTS_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Warning: could not read {REPORTS_JSON}: {exc}")
        return {}

    metadata = {}
    for report in reports:
        local_path = report.get("LocalPath")
        if not local_path:
            continue
        metadata[Path(local_path).name] = {
            "source": str(report.get("Source") or ""),
            "date": str(report.get("Date") or "未知日期"),
            "name": str(report.get("Name") or ""),
        }
    return metadata


def split_blocks(text: str) -> list[str]:
    text = clean_text(text).replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", text) if block.strip()]
    if len(blocks) > 1:
        return blocks

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return [text.strip()] if text.strip() else []

    grouped = []
    buffer = []
    for line in lines:
        buffer.append(line)
        joined = " ".join(buffer)
        if len(joined) >= 450 or is_boilerplate(joined, BOILERPLATE_THRESHOLD):
            grouped.append("\n".join(buffer))
            buffer = []
    if buffer:
        grouped.append("\n".join(buffer))
    return grouped


def filter_page_text(text: str) -> tuple[str, dict[str, int]]:
    chunks = [{"text": block} for block in split_blocks(text)]
    kept_chunks = filter_boilerplate_chunks(chunks, threshold=BOILERPLATE_THRESHOLD)
    kept_ids = {id(chunk) for chunk in kept_chunks}
    kept = [chunk["text"] for chunk in kept_chunks]
    removed = [chunk["text"] for chunk in chunks if id(chunk) not in kept_ids]

    return "\n\n".join(kept).strip(), {
        "removed_chunks": len(removed),
        "removed_characters": sum(len(block) for block in removed),
    }


def extract_pdf_text(pdf_path: Path) -> tuple[str, int, list[str], dict[str, int]]:
    warnings = []
    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            warnings.append(f"encrypted PDF could not be decrypted: {exc}")

    parts = []
    stats = {
        "original_characters": 0,
        "filtered_characters": 0,
        "removed_characters": 0,
        "removed_chunks": 0,
    }

    for page_number, page in enumerate(reader.pages, 1):
        try:
            raw_text = page.extract_text() or ""
        except Exception as exc:
            raw_text = ""
            warnings.append(f"page {page_number}: {exc}")

        filtered_text, page_stats = filter_page_text(raw_text)
        stats["original_characters"] += len(clean_text(raw_text))
        stats["filtered_characters"] += len(filtered_text)
        stats["removed_characters"] += page_stats["removed_characters"]
        stats["removed_chunks"] += page_stats["removed_chunks"]
        if filtered_text:
            parts.append(f"### Page {page_number}\n\n{filtered_text}".strip())

    text = "\n\n".join(parts).strip()
    if not text:
        text = "[No extractable text after boilerplate filtering.]"
    return clean_text(text + "\n"), len(reader.pages), warnings, stats


def render_source_html(index: int, documents: list[dict]) -> str:
    sections = []
    for doc in documents:
        warning_html = ""
        if doc["warnings"]:
            warning_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in doc["warnings"])
            warning_html = f"<details><summary>Extraction warnings</summary><ul>{warning_items}</ul></details>"
        sections.append(
            f"""<section>
<h2>Document {doc["document_number"]:03d}: {html.escape(doc["display_title"])}</h2>
<p><strong>Source PDF:</strong> {html.escape(doc["pdf"])}<br>
<strong>Report source:</strong> {html.escape(doc["source"] or "Unknown")}<br>
<strong>Date:</strong> {html.escape(doc["date"])}<br>
<strong>Pages:</strong> {doc["pages"]}<br>
<strong>Status:</strong> {html.escape(doc["status"])}</p>
{warning_html}
<pre>{html.escape(doc["text"])}</pre>
</section>"""
        )

    label = f"{index:0{SOURCE_DIGITS}d}"
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Financial Report Source {label}</title>
</head>
<body>
<main>
<h1>Financial Report Source {label}</h1>
{chr(10).join(sections)}
</main>
</body>
</html>
"""


def render_source_text(index: int, documents: list[dict]) -> str:
    label = f"{index:0{SOURCE_DIGITS}d}"
    sections = [
        f"# Financial Report Source {label}",
        "NotebookLM import text with Markdown headings for each report, source PDF, and page boundary.",
    ]
    for doc in documents:
        metadata = [
            f"Source PDF: {doc['pdf']}",
            f"Report source: {doc['source'] or 'Unknown'}",
            f"Date: {doc['date']}",
            f"Pages: {doc['pages']}",
            f"Extraction status: {doc['status']}",
        ]
        if doc["warnings"]:
            metadata.append("Extraction warnings:")
            metadata.extend(f"- {item}" for item in doc["warnings"])
        sections.append(
            "\n".join(
                [
                    "---",
                    f"## Document {doc['document_number']:03d}: {doc['display_title']}",
                    "",
                    *metadata,
                    "",
                    doc["text"].strip(),
                ]
            ).strip()
        )
    return "\n\n".join(sections).strip() + "\n"


def render_index(manifest: list[dict], generated_at: str) -> str:
    rows = "\n".join(
        f"""<tr>
  <td><a href="{html.escape(item["html_file"], quote=True)}">{html.escape(item["html_file"])}</a></td>
  <td><a href="{html.escape(item["text_file"], quote=True)}">{html.escape(item["text_file"])}</a></td>
  <td>{item["documents"]}</td>
  <td>{item["characters"]:,}</td>
  <td>{html.escape(item["first_title"])}</td>
  <td>{html.escape(item["last_title"])}</td>
</tr>"""
        for item in manifest
    )
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Merged Plain Text HTML Sources</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #18202f; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #d8dee9; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f7f8fb; }}
  </style>
</head>
<body>
  <h1>Merged Plain Text HTML Sources</h1>
  <p>Generated at {html.escape(generated_at)} from <code>{html.escape(str(SRC_DIR))}/</code>. Fixed output: {SOURCE_COUNT} HTML sources plus {SOURCE_COUNT} plain text sources for NotebookLM URL import.</p>
  <table>
    <thead>
      <tr><th>HTML</th><th>NotebookLM TXT</th><th>Documents</th><th>Characters</th><th>First</th><th>Last</th></tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
</body>
</html>
"""


def distribute_documents(documents: list[dict], bucket_count: int) -> list[list[dict]]:
    buckets = [{"documents": [], "characters": 0} for _ in range(bucket_count)]
    for doc in sorted(documents, key=lambda item: item["characters"], reverse=True):
        current = min(buckets, key=lambda bucket: (bucket["characters"], len(bucket["documents"])))
        current["documents"].append(doc)
        current["characters"] += doc["characters"]

    for bucket in buckets:
        bucket["documents"].sort(key=lambda doc: doc["document_number"])

    return [bucket["documents"] for bucket in buckets]


def split_documents(documents: list[dict]) -> list[list[dict]]:
    general_documents = [doc for doc in documents if doc["source"] != LINE_BACKUP_SOURCE]
    line_backup_documents = [doc for doc in documents if doc["source"] == LINE_BACKUP_SOURCE]
    line_bucket_count = SOURCE_COUNT - GENERAL_SOURCE_COUNT

    return [
        *distribute_documents(general_documents, GENERAL_SOURCE_COUNT),
        *distribute_documents(line_backup_documents, line_bucket_count),
    ]


def remove_old_outputs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_file in OUT_DIR.iterdir():
        if old_file.is_file() and old_file.name not in {".gitkeep"}:
            old_file.unlink()
        elif old_file.is_dir():
            shutil.rmtree(old_file)


def main() -> None:
    pdfs = sorted(SRC_DIR.glob("*.pdf"), key=lambda path: path.name.casefold())
    if not pdfs:
        raise SystemExit(f"No PDFs found in {SRC_DIR}")

    remove_old_outputs()
    documents = []
    report_metadata = load_report_metadata()
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for index, pdf_path in enumerate(pdfs, 1):
        title = safe_title(pdf_path.stem, f"document_{index:03d}")
        metadata = report_metadata.get(pdf_path.name, {})
        print(f"[{index:03d}/{len(pdfs):03d}] extracting {pdf_path.name}", flush=True)
        try:
            text, page_count, warnings, filter_stats = extract_pdf_text(pdf_path)
            status = "ok"
        except Exception as exc:
            text = f"Extraction failed: {exc}\n"
            page_count = 0
            warnings = [str(exc)]
            filter_stats = {
                "original_characters": 0,
                "filtered_characters": 0,
                "removed_characters": 0,
                "removed_chunks": 0,
            }
            status = "error"

        documents.append(
            {
                "document_number": index,
                "display_title": title,
                "title": f"{index:03d}_{title}",
                "pdf": str(pdf_path),
                "source": metadata.get("source", ""),
                "date": metadata.get("date", "未知日期"),
                "pages": page_count,
                "characters": len(text),
                "text": text,
                "status": status,
                "warnings": warnings,
                **filter_stats,
            }
        )

    buckets = split_documents(documents)
    manifest = []
    raw_urls = []

    for index, bucket in enumerate(buckets, 1):
        source_label = f"{index:0{SOURCE_DIGITS}d}"
        html_file_name = f"source{source_label}.html"
        text_file_name = f"source{source_label}.txt"
        html_content = render_source_html(index, bucket)
        text_content = render_source_text(index, bucket)
        html_path = OUT_DIR / html_file_name
        text_path = OUT_DIR / text_file_name
        html_path.write_text(html_content, encoding="utf-8")
        text_path.write_text(text_content, encoding="utf-8")
        first_title = bucket[0]["title"] if bucket else ""
        last_title = bucket[-1]["title"] if bucket else ""
        manifest.append(
            {
                "html_file": html_file_name,
                "text_file": text_file_name,
                "documents": len(bucket),
                "characters": sum(doc["characters"] for doc in bucket),
                "html_bytes": html_path.stat().st_size,
                "text_bytes": text_path.stat().st_size,
                "first_title": first_title,
                "last_title": last_title,
            }
        )
        raw_urls.append(f"{RAW_URL_BASE}/{text_file_name}")

    (OUT_DIR / "index.html").write_text(render_index(manifest, generated_at), encoding="utf-8")
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "raw_urls.txt").write_text("\n".join(raw_urls) + "\n", encoding="utf-8")

    print(f"Built {SOURCE_COUNT} HTML sources in {OUT_DIR}")
    print(f"Built {SOURCE_COUNT} plain text sources in {OUT_DIR}")
    print(f"Total documents: {len(documents)}")
    print(f"Total characters: {sum(item['characters'] for item in manifest):,}")
    print(f"Largest HTML file: {max(item['html_bytes'] for item in manifest):,} bytes")
    print(f"Largest text file: {max(item['text_bytes'] for item in manifest):,} bytes")


if __name__ == "__main__":
    main()
