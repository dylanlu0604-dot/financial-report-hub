import html
import json
from pathlib import Path


SRC_DIR = Path("notebooklm_sources_under_500k/sources")
OUT_DIR = Path("notebooklm_html_under_500k")
HTML_DIR = OUT_DIR / "html"
MAX_BYTES = 500_000


def render_source_html(title: str, text: str) -> str:
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
</head>
<body>
<main>
<h1>{html.escape(title)}</h1>
<pre>{html.escape(text)}</pre>
</main>
</body>
</html>
"""


def write_index(manifest: list[dict]) -> None:
    rows = "\n".join(
        f"<tr><td><a href=\"{html.escape(item['file'], quote=True)}\">{html.escape(item['file'])}</a></td>"
        f"<td>{item['characters']:,}</td><td>{item['bytes']:,}</td></tr>"
        for item in manifest
    )
    OUT_DIR.joinpath("index.html").write_text(
        f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NotebookLM HTML Sources Under 500k</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #18202f; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 920px; }}
    th, td {{ border-bottom: 1px solid #d8dee9; padding: 8px 10px; text-align: left; }}
    th {{ background: #f7f8fb; }}
    code {{ background: #f7f8fb; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>NotebookLM HTML Sources Under 500k</h1>
  <p>Use the raw GitHub URLs in <code>raw_urls.txt</code>. Each HTML source is below {MAX_BYTES:,} bytes.</p>
  <table>
    <thead><tr><th>File</th><th>Characters</th><th>Bytes</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> None:
    if not SRC_DIR.exists():
        raise SystemExit(f"Missing source directory: {SRC_DIR}")

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    for old_file in HTML_DIR.glob("*.html"):
        old_file.unlink()

    manifest = []
    raw_urls = []
    base_raw_url = (
        "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/"
        "main/notebooklm_html_under_500k/html"
    )

    for txt_path in sorted(SRC_DIR.glob("*.txt"), key=lambda path: path.name.casefold()):
        title = txt_path.stem
        text = txt_path.read_text(encoding="utf-8")
        file_name = txt_path.with_suffix(".html").name
        content = render_source_html(title, text)
        byte_count = len(content.encode("utf-8"))
        if byte_count >= MAX_BYTES:
            raise RuntimeError(f"{file_name} is {byte_count:,} bytes, above {MAX_BYTES:,}")

        HTML_DIR.joinpath(file_name).write_text(content, encoding="utf-8")
        manifest.append(
            {
                "file": f"html/{file_name}",
                "characters": len(content),
                "bytes": byte_count,
                "source_text": f"../notebooklm_sources_under_500k/sources/{txt_path.name}",
            }
        )
        raw_urls.append(f"{base_raw_url}/{file_name}")

    OUT_DIR.joinpath("manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUT_DIR.joinpath("raw_urls.txt").write_text("\n".join(raw_urls) + "\n", encoding="utf-8")
    write_index(manifest)

    print(f"Built {len(manifest)} NotebookLM HTML sources in {OUT_DIR}")
    print(f"Largest HTML: {max(item['bytes'] for item in manifest):,} bytes")


if __name__ == "__main__":
    main()
