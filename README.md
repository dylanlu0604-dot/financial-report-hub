# 報告平台 (Report Platform)

本專案為一個輕量級的報告抓取與整理平台，收集多家機構的報告資料，並將其轉換為可供分析與展示的格式。

**功能重點**
- 自動抓取（`scrapers/`）多家機構的報告資料
- 將原始資料儲存在 `data/`，提供 JSON 與 Markdown 檔
- 可透過 `main.py` 快速執行主要流程或範例

**目錄結構**
- `main.py`：專案主執行檔（示範或整合流程）
- `scrapers/`：各機構的爬蟲與處理邏輯
- `data/`：儲存抓取後的資料，如 `reports.json`、`reports_for_notebooklm.md`
- `requirements.txt`：Python 相依套件

安裝與執行

1. 建議建立虛擬環境（venv / conda），然後安裝相依套件：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 執行主程式（範例）：

```bash
python main.py
```

資料說明

- `data/reports.json`：統一的報告資料結構（JSON）
- `data/reports_for_notebooklm.md`：可直接供 NotebookLM 或其他 LLM 使用的 Markdown 摘要

關於 `scrapers/`

每個檔案對應一個機構或來源，負責抓取與標準化資料。主要檔案包含：
- `ctbc.py`, `dlri.py`, `jri.py`, `mizuho.py`, `murc.py`, `nli.py`, `sony_fg.py`, `dir_report.py`

開發與貢獻

- 若要新增抓取器，請在 `scrapers/` 新增對應模組，並遵循專案既有的資料結構與回傳格式。
- 提交 PR 前請在本地執行主要流程以確認無誤。

聯絡與授權

如需協助、提出議題或討論功能，請開啟 issue 或聯絡專案維護者。

