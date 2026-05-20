import html
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader


SRC_DIR = Path("merged_pdfs")
OUT_DIR = Path("merged_plain_text_html")
TEXT_DIR = OUT_DIR / "texts"
HTML_PATH = OUT_DIR / "index.html"
MANIFEST_PATH = OUT_DIR / "manifest.json"
SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_BOILERPLATE_FILTER_PATHS = [
    SCRIPT_DIR / "boilerplate_filter.py",
    Path("boilerplate_filter.py"),
]
FALLBACK_BOILERPLATE_FILTER_PATH = Path(
    "/Users/dylan/Library/Mobile Documents/com~apple~CloudDocs/報告向量樂觀/boilerplate_filter.py"
)
BOILERPLATE_THRESHOLD = 0.30


def load_boilerplate_filter():
    filter_path = next(
        (path for path in LOCAL_BOILERPLATE_FILTER_PATHS if path.exists()),
        FALLBACK_BOILERPLATE_FILTER_PATH,
    )
    if not filter_path.exists():
        raise FileNotFoundError(f"boilerplate filter not found: {filter_path}")

    spec = importlib.util.spec_from_file_location("project_boilerplate_filter", filter_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load boilerplate filter from {filter_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.is_boilerplate


IS_BOILERPLATE = load_boilerplate_filter()


def safe_name(value: str, fallback: str) -> str:
    name = value.strip() or fallback
    name = re.sub(r"[\0/\\:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or fallback


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
        if len(joined) >= 450 or IS_BOILERPLATE(joined, BOILERPLATE_THRESHOLD):
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
        if IS_BOILERPLATE(block, BOILERPLATE_THRESHOLD):
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

        parts.append(f"\n\n===== Page {page_number} =====\n\n{filtered_text}")

    return clean_text("\n".join(parts).strip() + "\n"), len(reader.pages), warnings, stats


def write_html_header(handle, generated_at: str, pdf_count: int) -> None:
    handle.write(
        """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Merged PDFs Plain Text</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fb;
      --ink: #18202f;
      --muted: #667085;
      --line: #d8dee9;
      --panel: #ffffff;
      --accent: #0f766e;
      --soft: #eef6f4;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    header {
      padding: 28px 32px 22px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      position: sticky;
      top: 0;
      z-index: 2;
    }
    h1 { margin: 0 0 8px; font-size: 24px; font-weight: 700; }
    .meta { margin: 0; color: var(--muted); font-size: 14px; }
    .toolbar {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) auto auto;
      gap: 10px;
      margin-top: 18px;
      max-width: 980px;
    }
    input, button {
      height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font: inherit;
    }
    input { padding: 0 12px; min-width: 0; }
    button {
      padding: 0 14px;
      background: var(--soft);
      color: var(--accent);
      cursor: pointer;
    }
    main { padding: 18px 32px 40px; }
    details {
      margin: 0 0 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }
    summary {
      cursor: pointer;
      padding: 14px 16px;
      font-weight: 650;
      list-style-position: outside;
    }
    .doc-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      padding: 0 16px 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .doc-meta a { color: var(--accent); text-decoration: none; }
    pre {
      margin: 0;
      padding: 16px;
      border-top: 1px solid var(--line);
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
      line-height: 1.55;
      background: #fbfcfe;
    }
    .hidden { display: none; }
    @media (max-width: 720px) {
      header, main { padding-left: 16px; padding-right: 16px; }
      .toolbar { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
"""
    )
    handle.write(
        f"""  <header>
    <h1>Merged PDFs Plain Text</h1>
    <p class="meta">Generated at {html.escape(generated_at)} from {pdf_count} PDFs in <code>merged_pdfs/</code>; boilerplate threshold {BOILERPLATE_THRESHOLD:.2f}.</p>
    <div class="toolbar">
      <input id="search" type="search" placeholder="Search file names in this HTML">
      <button type="button" id="expand">Expand all</button>
      <button type="button" id="collapse">Collapse all</button>
    </div>
  </header>
  <main id="docs">
"""
    )


def write_html_footer(handle) -> None:
    handle.write(
        """  </main>
  <script>
    const search = document.getElementById("search");
    const docs = Array.from(document.querySelectorAll("details[data-title]"));
    document.getElementById("expand").addEventListener("click", () => docs.forEach((doc) => doc.open = true));
    document.getElementById("collapse").addEventListener("click", () => docs.forEach((doc) => doc.open = false));
    search.addEventListener("input", () => {
      const query = search.value.trim().toLowerCase();
      docs.forEach((doc) => {
        const match = doc.dataset.title.toLowerCase().includes(query);
        doc.classList.toggle("hidden", query && !match);
      });
    });
  </script>
</body>
</html>
"""
    )


def main() -> None:
    pdfs = sorted(SRC_DIR.glob("*.pdf"), key=lambda path: path.name.casefold())
    if not pdfs:
        raise SystemExit(f"No PDFs found in {SRC_DIR}")

    OUT_DIR.mkdir(exist_ok=True)
    TEXT_DIR.mkdir(exist_ok=True)

    manifest = []
    generated_at = datetime.now().isoformat(timespec="seconds")

    with HTML_PATH.open("w", encoding="utf-8") as html_file:
        write_html_header(html_file, generated_at, len(pdfs))

        for index, pdf_path in enumerate(pdfs, 1):
            title = pdf_path.stem
            text_name = f"{index:03d}_{safe_name(title, f'document_{index:03d}')}.txt"
            text_path = TEXT_DIR / text_name

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

            text_path.write_text(text, encoding="utf-8")
            char_count = len(text)

            manifest.append(
                {
                    "pdf": str(pdf_path),
                    "txt": str(text_path),
                    "pages": page_count,
                    "characters": char_count,
                    **filter_stats,
                    "status": status,
                    "warnings": warnings,
                }
            )

            html_file.write(
                f"""    <details data-title="{html.escape(title, quote=True)}">
      <summary>{index:03d}. {html.escape(title)}</summary>
      <div class="doc-meta">
        <span>{page_count} pages</span>
        <span>{char_count:,} characters</span>
        <span>{filter_stats["removed_chunks"]} boilerplate chunks removed</span>
        <a href="{html.escape(text_path.relative_to(OUT_DIR).as_posix(), quote=True)}">plain text</a>
        <a href="../{html.escape(pdf_path.as_posix(), quote=True)}">source PDF</a>
      </div>
      <pre>{html.escape(text)}</pre>
    </details>
"""
            )

        write_html_footer(html_file)

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ok_count = sum(item["status"] == "ok" for item in manifest)
    error_count = len(manifest) - ok_count
    print(f"Done. Extracted {ok_count} PDFs with {error_count} errors.")
    print(f"HTML: {HTML_PATH}")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
