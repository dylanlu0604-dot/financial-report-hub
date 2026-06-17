import os
from pathlib import Path


PDF_DIRS = (Path("all report pdf"), Path("merged_pdfs"))
WARN_LIMIT_BYTES = int(os.getenv("GITHUB_PDF_WARN_LIMIT_BYTES", str(50 * 1024 * 1024)))
BLOCK_LIMIT_BYTES = int(os.getenv("GITHUB_PDF_BLOCK_LIMIT_BYTES", str(95 * 1024 * 1024)))


def format_bytes(byte_count):
    size = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024


def iter_generated_pdfs():
    for folder in PDF_DIRS:
        if not folder.exists():
            continue
        yield from sorted(folder.glob("*.pdf"), key=lambda path: path.as_posix().casefold())


def main():
    oversized = []
    warned = []

    for pdf_path in iter_generated_pdfs():
        size = pdf_path.stat().st_size
        if size >= BLOCK_LIMIT_BYTES:
            oversized.append((pdf_path, size))
        elif size >= WARN_LIMIT_BYTES:
            warned.append((pdf_path, size))

    for pdf_path, size in warned:
        print(
            f"::warning file={pdf_path.as_posix()}::PDF is {format_bytes(size)}, "
            "above GitHub's recommended 50 MB size."
        )

    if oversized:
        for pdf_path, size in oversized:
            print(
                f"::error file={pdf_path.as_posix()}::PDF is {format_bytes(size)}, "
                f"above the configured upload block limit of {format_bytes(BLOCK_LIMIT_BYTES)}."
            )
        print(f"Found {len(oversized)} oversized PDF file(s). Refusing to commit generated artifacts.")
        return 1

    print(f"PDF size check passed for {len(warned)} warning-size file(s) and no blocked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
