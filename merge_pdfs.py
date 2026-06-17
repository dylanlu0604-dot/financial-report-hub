import os
import json
from pypdf import PdfWriter  # 🌟 修正點 1：改用最新版的 PdfWriter

MAX_MERGED_PDF_BYTES = int(os.getenv("MAX_MERGED_PDF_BYTES", str(45 * 1024 * 1024)))
GITHUB_UPLOAD_BLOCK_BYTES = int(os.getenv("GITHUB_UPLOAD_BLOCK_BYTES", str(95 * 1024 * 1024)))

MIN_SOURCE_PARTS = {
    "line報告備份": 3,
}


def format_bytes(byte_count):
    size = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024


def split_paths_by_size(pdf_paths, max_bytes=MAX_MERGED_PDF_BYTES, min_part_count=1):
    total_bytes = sum(os.path.getsize(path) for path in pdf_paths)
    target_bytes = max_bytes
    if min_part_count > 1:
        target_bytes = min(max_bytes, max(total_bytes / min_part_count, 1))

    buckets = []
    current_paths = []
    current_bytes = 0

    for pdf_path in pdf_paths:
        pdf_size = os.path.getsize(pdf_path)
        if current_paths and current_bytes + pdf_size > target_bytes:
            buckets.append(current_paths)
            current_paths = []
            current_bytes = 0

        current_paths.append(pdf_path)
        current_bytes += pdf_size

    if current_paths:
        buckets.append(current_paths)

    return buckets

def clear_old_merged_pdfs(output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"📁 已建立全新資料夾：{output_folder}")
        return

    removed_count = 0
    for filename in os.listdir(output_folder):
        if filename.lower().endswith(".pdf"):
            os.remove(os.path.join(output_folder, filename))
            removed_count += 1
    if removed_count:
        print(f"🧹 已清除 {removed_count} 個舊合併 PDF")

def write_merged_pdf(pdf_paths, output_filename):
    merger = PdfWriter()
    try:
        for pdf in pdf_paths:
            merger.append(pdf)
        merger.write(output_filename)
    finally:
        merger.close()
    return os.path.getsize(output_filename)


def write_source_merged_pdfs(source, pdf_paths, output_folder):
    safe_source_name = source.replace("/", "_").replace("\\", "_").replace(" ", "_")
    min_part_count = MIN_SOURCE_PARTS.get(source, 1)
    pending_chunks = split_paths_by_size(
        pdf_paths,
        max_bytes=MAX_MERGED_PDF_BYTES,
        min_part_count=min_part_count,
    )
    temp_outputs = []
    skipped_outputs = []
    temp_index = 1

    while pending_chunks:
        chunk_paths = pending_chunks.pop(0)
        temp_filename = os.path.join(output_folder, f".{safe_source_name}_{temp_index}.tmp.pdf")
        output_size = write_merged_pdf(chunk_paths, temp_filename)

        if output_size > MAX_MERGED_PDF_BYTES and len(chunk_paths) > 1:
            os.remove(temp_filename)
            split_at = max(1, len(chunk_paths) // 2)
            pending_chunks = [chunk_paths[:split_at], chunk_paths[split_at:]] + pending_chunks
            print(
                f"  ↪ 分卷仍偏大 ({format_bytes(output_size)})，自動再切分為更小批次。"
            )
            continue

        if output_size >= GITHUB_UPLOAD_BLOCK_BYTES:
            os.remove(temp_filename)
            skipped_outputs.append((chunk_paths, output_size))
            print(
                f"  ⚠️ 跳過過大分卷 ({format_bytes(output_size)})，避免 GitHub push 失敗。"
            )
            continue

        temp_outputs.append((temp_filename, chunk_paths, output_size))
        temp_index += 1

    multiple_parts = len(temp_outputs) > 1
    for part_index, (temp_filename, chunk_paths, output_size) in enumerate(temp_outputs, 1):
        if multiple_parts:
            output_filename = os.path.join(output_folder, f"{safe_source_name}_Merged_part{part_index}.pdf")
        else:
            output_filename = os.path.join(output_folder, f"{safe_source_name}_Merged.pdf")
        os.replace(temp_filename, output_filename)
        print(
            f"  ✅ 合併成功！{len(chunk_paths)} 份，{format_bytes(output_size)}，已儲存至 ➔ {output_filename}"
        )

    return len(temp_outputs), skipped_outputs

def merge_reports_by_source():
    json_path = "data/reports.json"
    output_folder = "merged_pdfs"

    print("==================================================")
    print(" 📚 啟動 PDF 自動合併模組 (依機構分類)")
    print("==================================================")

    if not os.path.exists(json_path):
        print("❌ 找不到 data/reports.json，請先確認是否有報告資料庫！")
        return

    clear_old_merged_pdfs(output_folder)

    with open(json_path, 'r', encoding='utf-8') as f:
        reports = json.load(f)

    source_groups = {}
    for report in reports:
        source = report.get("Source", "Unknown_Source")
        local_path = report.get("LocalPath")
        
        if local_path and os.path.exists(local_path):
            if source not in source_groups:
                source_groups[source] = []
            source_groups[source].append(local_path)

    for source, pdf_paths in source_groups.items():
        if len(pdf_paths) == 0:
            continue
            
        print(f"🔄 正在處理【{source}】... 共發現 {len(pdf_paths)} 份報告")
        
        try:
            part_count, skipped_outputs = write_source_merged_pdfs(source, pdf_paths, output_folder)
            if skipped_outputs:
                print(f"  ⚠️ 【{source}】有 {len(skipped_outputs)} 個分卷因超過上傳限制未輸出。")
            elif part_count > 1:
                print(f"  📦 【{source}】已自動分成 {part_count} 個 GitHub 友善大小的 PDF。")
        except Exception as e:
            print(f"  ❌ 合併【{source}】時發生錯誤: {e}")

    print("==================================================")
    print(" 🎉 所有機構 PDF 合併作業完成！")
    print("==================================================")

if __name__ == "__main__":
    merge_reports_by_source()
