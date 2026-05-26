import os
import json
from pypdf import PdfWriter  # 🌟 修正點 1：改用最新版的 PdfWriter

SPLIT_SOURCE_PARTS = {
    "line報告備份": 3,
}

def split_paths_by_size(pdf_paths, part_count):
    total_bytes = sum(os.path.getsize(path) for path in pdf_paths)
    target_bytes = max(total_bytes / part_count, 1)
    buckets = []
    current_paths = []
    current_bytes = 0

    for pdf_path in pdf_paths:
        current_paths.append(pdf_path)
        current_bytes += os.path.getsize(pdf_path)
        if current_bytes >= target_bytes and len(buckets) < part_count - 1:
            buckets.append(current_paths)
            current_paths = []
            current_bytes = 0

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
        
        safe_source_name = source.replace("/", "_").replace("\\", "_").replace(" ", "_")
        split_part_count = SPLIT_SOURCE_PARTS.get(source)

        try:
            if split_part_count:
                chunks = split_paths_by_size(pdf_paths, split_part_count)
                for part_index, chunk_paths in enumerate(chunks, 1):
                    output_filename = os.path.join(
                        output_folder,
                        f"{safe_source_name}_Merged_part{part_index}.pdf"
                    )
                    write_merged_pdf(chunk_paths, output_filename)
                    print(f"  ✅ 分卷 {part_index}/{len(chunks)} 合併成功！已儲存至 ➔ {output_filename}")
            else:
                output_filename = os.path.join(output_folder, f"{safe_source_name}_Merged.pdf")
                write_merged_pdf(pdf_paths, output_filename)
                print(f"  ✅ 合併成功！已儲存至 ➔ {output_filename}")
        except Exception as e:
            print(f"  ❌ 合併【{source}】時發生錯誤: {e}")

    print("==================================================")
    print(" 🎉 所有機構 PDF 合併作業完成！")
    print("==================================================")

if __name__ == "__main__":
    merge_reports_by_source()
