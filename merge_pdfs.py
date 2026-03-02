import os
import json
from pypdf import PdfMerger

def merge_reports_by_source():
    json_path = "data/reports.json"
    output_folder = "merged_pdfs"

    print("==================================================")
    print(" 📚 啟動 PDF 自動合併模組 (依機構分類)")
    print("==================================================")

    # 1. 檢查是否有報告資料庫可以讀取
    if not os.path.exists(json_path):
        print("❌ 找不到 data/reports.json，請先執行主程式 (main.py) 抓取報告！")
        return

    # 2. 建立儲存合併檔案的新資料夾
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"📁 已建立全新資料夾：{output_folder}")

    # 3. 讀取 JSON 資料
    with open(json_path, 'r', encoding='utf-8') as f:
        reports = json.load(f)

    # 4. 根據機構 (Source) 將 PDF 路徑進行分組
    source_groups = {}
    for report in reports:
        source = report.get("Source", "Unknown_Source")
        local_path = report.get("LocalPath")
        
        # 確保該報告有成功下載實體 PDF 檔案
        if local_path and os.path.exists(local_path):
            if source not in source_groups:
                source_groups[source] = []
            # 將檔案路徑加入該機構的清單中
            source_groups[source].append(local_path)

    # 5. 開始逐一合併各機構的 PDF
    for source, pdf_paths in source_groups.items():
        if len(pdf_paths) == 0:
            continue
            
        print(f"🔄 正在處理【{source}】... 共發現 {len(pdf_paths)} 份報告")
        merger = PdfMerger()
        
        # 清理機構名稱，避免作為檔名時出現無效字元 (例如斜線)
        safe_source_name = source.replace("/", "_").replace("\\", "_").replace(" ", "_")
        output_filename = os.path.join(output_folder, f"{safe_source_name}_Merged.pdf")

        try:
            # 依序把該機構的所有 PDF 塞進合併器
            for pdf in pdf_paths:
                merger.append(pdf)
                
            # 寫出成為一個大檔案
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
