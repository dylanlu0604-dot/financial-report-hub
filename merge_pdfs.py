import os
import json
from pypdf import PdfWriter  # 🌟 修正點 1：改用最新版的 PdfWriter

def merge_reports_by_source():
    json_path = "data/reports.json"
    output_folder = "merged_pdfs"

    print("==================================================")
    print(" 📚 啟動 PDF 自動合併模組 (依機構分類)")
    print("==================================================")

    if not os.path.exists(json_path):
        print("❌ 找不到 data/reports.json，請先確認是否有報告資料庫！")
        return

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"📁 已建立全新資料夾：{output_folder}")

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
        
        # 🌟 修正點 2：使用 PdfWriter 來執行合併
        merger = PdfWriter()
        
        safe_source_name = source.replace("/", "_").replace("\\", "_").replace(" ", "_")
        output_filename = os.path.join(output_folder, f"{safe_source_name}_Merged.pdf")

        try:
            for pdf in pdf_paths:
                merger.append(pdf)
                
            merger.write(output_filename)
            print(f"  ✅ 合併成功！已儲存至 ➔ {output_filename}")
        except Exception as e:
            print(f"  ❌ 合併【{source}】時發生錯誤: {e}")
        finally:
            merger.close()

    print("==================================================")
    print(" 🎉 所有機構 PDF 合併作業完成！")
    print("==================================================")

if __name__ == "__main__":
    merge_reports_by_source()
