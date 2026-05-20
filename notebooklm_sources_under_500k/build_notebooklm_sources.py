import html
import json
import re
from pathlib import Path


SRC_TEXT_DIR = Path("merged_plain_text_html/texts")
OUT_DIR = Path("notebooklm_sources_under_500k")
MAX_CHARS = 180_000
SECTION_TEXT_LIMIT = MAX_CHARS - 2_000


def split_large_text(title: str, text: str) -> list[tuple[str, str]]:
    pages = re.split(r"(?=^===== Page \d+ =====$)", text, flags=re.MULTILINE)
    pages = [page.strip() for page in pages if page.strip()]
    if not pages:
        pages = [text.strip()]

    parts = []
    current = []
    current_len = 0
    part_number = 1

    for page in pages:
        page_block = page.strip() + "\n"
        if len(page_block) > SECTION_TEXT_LIMIT:
            if current:
                parts.append((f"{title} part {part_number}", "\n\n".join(current).strip() + "\n"))
                part_number += 1
                current = []
                current_len = 0

            for start in range(0, len(page_block), SECTION_TEXT_LIMIT):
                parts.append((f"{title} part {part_number}", page_block[start : start + SECTION_TEXT_LIMIT]))
                part_number += 1
            continue

        next_len = current_len + len(page_block) + 2
        if current and next_len > SECTION_TEXT_LIMIT:
            parts.append((f"{title} part {part_number}", "\n\n".join(current).strip() + "\n"))
            part_number += 1
            current = []
            current_len = 0

        current.append(page_block)
        current_len += len(page_block) + 2

    if current:
        parts.append((f"{title} part {part_number}", "\n\n".join(current).strip() + "\n"))

    return parts


def add_section(chunks: list[dict], title: str, text: str) -> None:
    body = f"# {title}\n\n{text.strip()}\n"
    if len(body) > MAX_CHARS:
        for part_title, part_text in split_large_text(title, text):
            add_section(chunks, part_title, part_text)
        return

    if not chunks or chunks[-1]["characters"] + len(body) + 2 > MAX_CHARS:
        chunks.append({"sections": [], "characters": 0})

    chunks[-1]["sections"].append({"title": title, "characters": len(body), "text": body})
    chunks[-1]["characters"] += len(body) + 2


def write_index(manifest: list[dict]) -> None:
    rows = "\n".join(
        f"<tr><td>{item['file']}</td><td>{item['characters']:,}</td><td>{item['sections']}</td></tr>"
        for item in manifest
    )
    OUT_DIR.joinpath("index.html").write_text(
        f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NotebookLM Sources Under 500k</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #18202f; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 920px; }}
    th, td {{ border-bottom: 1px solid #d8dee9; padding: 8px 10px; text-align: left; }}
    th {{ background: #f7f8fb; }}
    code {{ background: #f7f8fb; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>NotebookLM Sources Under 500k</h1>
  <p>Upload the files in <code>sources/</code> to NotebookLM. Each source is kept below {MAX_CHARS:,} characters.</p>
  <table>
    <thead><tr><th>File</th><th>Characters</th><th>Sections</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> None:
    if not SRC_TEXT_DIR.exists():
        raise SystemExit(f"Missing source text directory: {SRC_TEXT_DIR}")

    source_dir = OUT_DIR / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    for old_file in source_dir.glob("*.txt"):
        old_file.unlink()

    chunks = []
    for path in sorted(SRC_TEXT_DIR.glob("*.txt"), key=lambda item: item.name.casefold()):
        title = path.stem
        text = path.read_text(encoding="utf-8")
        add_section(chunks, title, text)

    manifest = []
    raw_urls = []
    base_raw_url = (
        "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/"
        "main/notebooklm_sources_under_500k/sources"
    )
    for index, chunk in enumerate(chunks, 1):
        file_name = f"notebooklm_source_{index:02d}.txt"
        content = "\n\n".join(section["text"] for section in chunk["sections"]).strip() + "\n"
        if len(content) > MAX_CHARS:
            raise RuntimeError(f"{file_name} exceeds {MAX_CHARS}: {len(content)}")

        source_dir.joinpath(file_name).write_text(content, encoding="utf-8")
        manifest.append(
            {
                "file": f"sources/{file_name}",
                "characters": len(content),
                "sections": len(chunk["sections"]),
                "titles": [section["title"] for section in chunk["sections"]],
            }
        )
        raw_urls.append(f"{base_raw_url}/{html.escape(file_name, quote=False)}")

    OUT_DIR.joinpath("manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUT_DIR.joinpath("raw_urls.txt").write_text("\n".join(raw_urls) + "\n", encoding="utf-8")
    write_index(manifest)

    print(f"Built {len(manifest)} NotebookLM sources in {OUT_DIR}")
    print(f"Largest source: {max(item['characters'] for item in manifest):,} characters")
    print(f"Total characters: {sum(item['characters'] for item in manifest):,}")


if __name__ == "__main__":
    main()
