# NotebookLM 30-Source Report Importer

一鍵建立 NotebookLM 筆記本，匯入固定三十個 plain text 來源，命名筆記本，等待 30 秒後送出第一個總體經濟主題清單問題，並將步驟 1 的回答儲存至記事。筆記本名稱格式為：

```text
YYYY-MM-DD報告集(近30天報告)
```

## 安裝

1. 打開 Chrome：`chrome://extensions/`
2. 開啟右上角「開發人員模式」
3. 點「載入未封裝項目」
4. 選擇這個資料夾：`notebooklm-five-source-extension`

## 使用

1. 確認 Chrome 已登入可使用 NotebookLM 的 Google 帳號
2. 點工具列上的擴充套件圖示
3. 擴充套件會自動開啟 NotebookLM、建立新筆記本，並一次貼上三十個固定 `.txt` URL（每行一個連結）
4. 全部匯入後等待 30 秒，然後送出「步驟 1」問題
5. 等待回答完成後，點擊「儲存至記事」

如果 NotebookLM UI 改版導致找不到按鈕，頁面右下角的狀態面板會列出目前可點擊文字，方便調整 `content.js` 的文案匹配。

右下角狀態面板可以用右上角的 `x` 關閉；下一次點擴充套件執行時會重新出現。
