# 最新財經報告總覽 (Financial Report Hub)

本專案是一個自動化財經報告爬蟲與整合工具。它能夠自動從各大家金融機構（如中國信託、國泰、富邦、瑞穗、大和等）抓取最新的財經分析報告與 PDF 檔案，並自動生成便於閱讀的 HTML 總覽頁面、Markdown 清單以及 RSS 訂閱源。

## 🌟 功能亮點

1. **多來源自動抓取**：支援動態加載 `scrapers/` 目錄下的所有爬蟲模組，可自動抓取各家機構最新發布的財經報告。
2. **反爬蟲機制突破**：內建使用 `playwright` 與 `playwright-stealth`，透過隱身模式模擬真實瀏覽器行為，有效解決網頁防爬驗證機制（如部分銀行網站）。
3. **物理隔離下載**：精準攔截並獨立抓取 PDF 檔案，避免傳統爬蟲遇到的內容重複或抓取失敗問題。
4. **多格式自動輸出**：
   - 帶有排序功能與互動介面的靜態 `index.html`。
   - 各機構專屬的 RSS 訂閱檔案 (`data/*.xml`)。
   - 適合匯入 NotebookLM 或其他 AI 大語言模型的 Markdown 內容 (`data/reports_for_notebooklm.md`)。
   - 結構化的 JSON 資料歸檔 (`data/reports.json`)。
5. **PDF 元數據讀取**：使用 `pdfplumber` 解析下載的 PDF，自動標示報告的總頁數以便參考。

## 📁 目錄結構

- `main.py`：專案主程式。負責調用各個爬蟲模組，抓取網頁資料後統一下載 PDF 檔案，並動態生成 HTML、Markdown、JSON 與 RSS 等各式輸出檔案。
- `download_pdf.py`：獨立的批量 PDF 下載工具（補充用）。能讀取已生成的 Markdown 清單，並透過 Playwright 進行實體的批量 PDF 下載。
- `scrapers/`：各機構的爬蟲模組目錄。目前包含中信、國泰、富邦、瑞穗等多家機構的處理邏輯與原始碼。
- `data/`：存放爬蟲產生的結構化輸出檔案（如 JSON, Markdown, XML 源）。
- `all report pdf/`：統一存放從各家機構成功下載的實體 PDF 檔案。
- `index.html`：自動生成的靜態網頁與報告檢視總覽儀表板。
- `requirements.txt`：Python 相依套件清單。

## 🚀 安裝與環境設定

1. **建立虛擬環境（建議）並安裝依賴套件：**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **安裝 Playwright 瀏覽器引擎：**
   這是一項必須執行的步驟，主要提供後台真實瀏覽器環境以順利下載 PDF：
   ```bash
   playwright install chromium
   ```

3. **環境變數設定：**
   如有需要使用 AI 摘要功能或其他進階設定，請設定 `.env` 環境變數檔。本程式已預載 `python-dotenv` 支援讀取。

## ⚙️ 執行與使用指南

### 1. 執行主自動化爬蟲程式
```bash
python main.py
```
此步驟會自動清理過期資料，完整調用所有爬蟲，下載並驗證 PDF 檔案，最後生成所有的前端儀表板 (`index.html`)、Markdown 及 RSS 檔案。

### 2. 執行補充下載腳本 (如果有需要)
若你只想透過已經整理好的 Markdown 清單 (`data/reports_for_notebooklm.md`) 單純進行實體 PDF 真實下載：
```bash
python download_pdf.py
```
執行後會自動攔截下載流，並將檔案存入 `downloaded_reports/` 目錄。

## 🏗 開發與貢獻

- 若要新增來源抓取器，請在 `scrapers/` 目錄新增對應的 `.py` 模組，並宣告 `scrape()` 函式。主程式會透過模組動態加載機制，自動將新的爬蟲加入執行流程，並整合其結果。
- 為了確保網站版面資源指向正確，如果您想要使用自己的 GitHub Repositories（例如用來提供 GitHub Raw 的穩定的 PDF 連結），請先在 `main.py` 頂部的全域設定區域，將 `GITHUB_USER` 與 `GITHUB_REPO` 修改為您的資訊。

## 📜 聯絡與授權

如需協助或討論功能擴編，請開啟 issue 或是聯絡專案維護者。
