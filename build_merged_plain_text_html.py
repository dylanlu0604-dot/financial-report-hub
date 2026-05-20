import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from boilerplate_filter import is_boilerplate
from pypdf import PdfReader


SRC_DIR = Path("merged_pdfs")
OUT_DIR = Path("merged_plain_text_html")
SOURCE_COUNT = 5
BOILERPLATE_THRESHOLD = 0.30
RAW_URL_BASE = (
    "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/"
    "refs/heads/main/merged_plain_text_html"
)


def safe_title(value: str, fallback: str) -> str:
    title = value.strip() or fallback
    title = re.sub(r"[\0/\\:*?\"<>|]+", "_", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title[:180] or fallback


def clean_text(value: str) -> str:
    return value.encode("utf-8", "replace").decode("utf-8")


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
    kept = []
    removed_chunks = 0
    removed_characters = 0

    for block in split_blocks(text):
        if is_boilerplate(block, BOILERPLATE_THRESHOLD):
            removed_chunks += 1
            removed_characters += len(block)
            continue
        kept.append(block)

    return "\n\n".join(kept).strip(), {
        "removed_chunks": removed_chunks,
        "removed_characters": removed_characters,
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
        parts.append(f"===== Page {page_number} =====\n\n{filtered_text}".strip())

    return clean_text("\n\n".join(parts).strip() + "\n"), len(reader.pages), warnings, stats


def render_source_html(index: int, documents: list[dict]) -> str:
    sections = []
    for doc in documents:
        sections.append(
            f"""<section>
<h2>{html.escape(doc["title"])}</h2>
<pre>{html.escape(doc["text"])}</pre>
</section>"""
        )

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Financial Report Source {index}</title>
</head>
<body>
<main>
<h1>Financial Report Source {index}</h1>
{chr(10).join(sections)}
</main>
</body>
</html>
"""


def render_index(manifest: list[dict], generated_at: str) -> str:
    rows = "\n".join(
        f"""<tr>
  <td><a href="{html.escape(item["file"], quote=True)}">{html.escape(item["file"])}</a></td>
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
  <p>Generated at {html.escape(generated_at)} from <code>merged_pdfs/</code>. Fixed output: 5 HTML sources.</p>
  <table>
    <thead>
      <tr><th>File</th><th>Documents</th><th>Characters</th><th>First</th><th>Last</th></tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
</body>
</html>
"""


def split_documents(documents: list[dict]) -> list[list[dict]]:
    buckets = [{"documents": [], "characters": 0} for _ in range(SOURCE_COUNT)]
    total_chars = sum(doc["characters"] for doc in documents)
    target_chars = max(total_chars / SOURCE_COUNT, 1)
    bucket_index = 0

    for doc in documents:
        remaining_docs = len(documents) - sum(len(bucket["documents"]) for bucket in buckets)
        remaining_buckets = SOURCE_COUNT - bucket_index
        must_leave_for_later = remaining_docs <= remaining_buckets - 1

        current = buckets[bucket_index]
        if (
            current["documents"]
            and current["characters"] >= target_chars
            and bucket_index < SOURCE_COUNT - 1
            and not must_leave_for_later
        ):
            bucket_index += 1
            current = buckets[bucket_index]

        current["documents"].append(doc)
        current["characters"] += doc["characters"]

    return [bucket["documents"] for bucket in buckets]


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
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for index, pdf_path in enumerate(pdfs, 1):
        title = safe_title(pdf_path.stem, f"document_{index:03d}")
        numbered_title = f"{index:03d}_{title}"
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
                "title": numbered_title,
                "pdf": str(pdf_path),
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
        file_name = f"source{index}.html"
        html_content = render_source_html(index, bucket)
        out_path = OUT_DIR / file_name
        out_path.write_text(html_content, encoding="utf-8")
        first_title = bucket[0]["title"] if bucket else ""
        last_title = bucket[-1]["title"] if bucket else ""
        manifest.append(
            {
                "file": file_name,
                "documents": len(bucket),
                "characters": sum(doc["characters"] for doc in bucket),
                "bytes": out_path.stat().st_size,
                "first_title": first_title,
                "last_title": last_title,
            }
        )
        raw_urls.append(f"{RAW_URL_BASE}/{file_name}")

    (OUT_DIR / "index.html").write_text(render_index(manifest, generated_at), encoding="utf-8")
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "raw_urls.txt").write_text("\n".join(raw_urls) + "\n", encoding="utf-8")

    print(f"Built {SOURCE_COUNT} HTML sources in {OUT_DIR}")
    print(f"Total documents: {len(documents)}")
    print(f"Total characters: {sum(item['characters'] for item in manifest):,}")
    print(f"Largest HTML file: {max(item['bytes'] for item in manifest):,} bytes")


if __name__ == "__main__":
    main()
