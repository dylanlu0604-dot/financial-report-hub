if (!window.__fiveSourceNotebookLmImporterLoaded) {
  window.__fiveSourceNotebookLmImporterLoaded = true;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const norm = (value) => (value || "").replace(/\s+/g, " ").trim();

  function ensureStatusPanel() {
    let panel = document.getElementById("five-source-nlm-status");
    if (panel) return panel;

    panel = document.createElement("div");
    panel.id = "five-source-nlm-status";
    panel.style.cssText = [
      "position:fixed",
      "right:16px",
      "bottom:16px",
      "z-index:2147483647",
      "width:360px",
      "max-height:45vh",
      "overflow:auto",
      "padding:12px",
      "border-radius:10px",
      "box-shadow:0 8px 28px rgba(0,0,0,.22)",
      "background:#fff",
      "color:#202124",
      "font:12px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      "white-space:pre-wrap"
    ].join(";");
    panel.textContent = "NotebookLM 匯入器準備中...\n";
    document.documentElement.appendChild(panel);
    return panel;
  }

  function progress(text, cls = "") {
    const panel = ensureStatusPanel();
    const line = document.createElement("div");
    line.textContent = text;
    if (cls === "ok") line.style.color = "#188038";
    if (cls === "warn") line.style.color = "#b06000";
    if (cls === "err") line.style.color = "#d93025";
    panel.appendChild(line);
    panel.scrollTop = panel.scrollHeight;
    console.log("[NotebookLM 5-source importer]", text);
  }

  async function waitFor(fn, timeoutMs = 20000, stepMs = 300) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const value = fn();
      if (value) return value;
      await sleep(stepMs);
    }
    return null;
  }

  function isVisible(el) {
    if (!el) return false;
    const style = getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none") return false;
    return Boolean(el.offsetParent || el.getClientRects().length);
  }

  function labelOf(el) {
    return norm(
      el?.innerText ||
      el?.textContent ||
      el?.getAttribute?.("aria-label") ||
      el?.getAttribute?.("title") ||
      el?.getAttribute?.("placeholder") ||
      ""
    );
  }

  function clickableElements() {
    return Array.from(document.querySelectorAll([
      "button",
      "a",
      "[role='button']",
      "[role='link']",
      "[role='menuitem']",
      "[tabindex]:not([tabindex='-1'])"
    ].join(","))).filter(isVisible);
  }

  function listClickableLabels(limit = 80) {
    const seen = new Set();
    const labels = [];
    for (const el of clickableElements()) {
      const label = labelOf(el);
      if (!label || seen.has(label)) continue;
      seen.add(label);
      labels.push(label);
      if (labels.length >= limit) break;
    }
    return labels;
  }

  function findClickable(texts) {
    const elements = clickableElements();
    for (const text of texts) {
      const exact = elements.find((el) => labelOf(el) === text);
      if (exact) return exact;
    }
    for (const text of texts) {
      const lower = text.toLowerCase();
      const partial = elements.find((el) => labelOf(el).toLowerCase().includes(lower));
      if (partial) return partial;
    }
    return null;
  }

  async function clickText(texts, description, timeoutMs = 20000) {
    const button = await waitFor(() => findClickable(texts), timeoutMs);
    if (!button) {
      progress(`找不到 ${description}。目前可點文字：${listClickableLabels().join(" | ")}`, "warn");
      throw new Error(`找不到 ${description}`);
    }
    progress(`點擊 ${description}：${labelOf(button)}`);
    button.click();
    await sleep(900);
    return button;
  }

  function visibleText() {
    return norm(document.body?.innerText || "");
  }

  async function createNotebook() {
    progress("等待 NotebookLM 首頁載入...");
    await waitFor(() => document.body && visibleText().length > 20, 30000);

    await clickText([
      "建立筆記本",
      "建立新的筆記本",
      "新增筆記本",
      "建立新筆記本",
      "Create new notebook",
      "New notebook",
      "Create",
      "建立"
    ], "建立筆記本按鈕", 30000);

    const ready = await waitFor(() => (
      findClickable(["新增來源", "Add source", "新增", "Add"]) ||
      /新增來源|Add source|Sources|來源/.test(visibleText())
    ), 45000);

    if (!ready) throw new Error("已點建立筆記本，但等不到筆記本頁面或新增來源按鈕");
    progress("新筆記本已建立", "ok");
  }

  async function openAddSourceDialog() {
    if (findUrlTextbox()) return;
    const sourceChoiceVisible = findClickable(["網站", "Website", "網址", "YouTube", "貼上文字", "Paste text", "Copied text"]);
    if (sourceChoiceVisible && /Google Drive|YouTube|Paste text|Copied text|貼上文字|網站|Website|網址/.test(visibleText())) return;
    await clickText([
      "新增來源",
      "新增來源 +",
      "Add source",
      "Add sources",
      "Add",
      "新增"
    ], "新增來源按鈕", 25000);
  }

  async function selectWebsiteSource() {
    const existingTextbox = findUrlTextbox();
    if (existingTextbox) return existingTextbox;

    const website = findClickable([
      "網站",
      "網站連結",
      "網址",
      "Website",
      "Web",
      "Link",
      "URL"
    ]);

    if (website) {
      progress(`選擇網址/網站來源：${labelOf(website)}`);
      website.click();
      await sleep(800);
    }

    const textbox = await waitFor(findUrlTextbox, 15000);
    if (!textbox) {
      progress(`找不到 URL 輸入欄。頁面可點文字：${listClickableLabels().join(" | ")}`, "warn");
      throw new Error("找不到 URL 輸入欄");
    }
    return textbox;
  }

  function findUrlTextbox() {
    const fields = Array.from(document.querySelectorAll("input, textarea, [contenteditable='true'], [role='textbox']"))
      .filter(isVisible);

    const urlLike = fields.find((field) => {
      const label = [
        field.getAttribute("aria-label"),
        field.getAttribute("placeholder"),
        field.getAttribute("title"),
        field.textContent
      ].map(norm).join(" ").toLowerCase();
      return /url|網址|連結|link|website|http/.test(label);
    });
    if (urlLike) return urlLike;

    return fields.find((field) => {
      const tag = field.tagName;
      const type = (field.getAttribute("type") || "text").toLowerCase();
      return tag === "TEXTAREA" || type === "url" || type === "text" || field.getAttribute("contenteditable") === "true";
    }) || null;
  }

  function setFieldValue(field, value) {
    field.focus();
    field.click();
    if (field.getAttribute("contenteditable") === "true") {
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, value);
      field.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
      return;
    }

    const proto = field.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    setter ? setter.call(field, value) : (field.value = value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function submitSourceUrl(url) {
    await openAddSourceDialog();
    const textbox = await selectWebsiteSource();
    progress(`填入 URL：${url}`);
    setFieldValue(textbox, url);
    await sleep(500);

    const submit = await waitFor(() => findClickable([
      "插入",
      "新增",
      "新增來源",
      "匯入",
      "Import",
      "Insert",
      "Add",
      "Submit",
      "Add source"
    ]), 15000);

    if (submit) {
      progress(`送出來源：${labelOf(submit)}`);
      submit.click();
    } else {
      progress("找不到送出按鈕，改用 Enter 嘗試送出", "warn");
      textbox.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
    }

    await sleep(2500);
  }

  async function importUrls(urls) {
    for (let i = 0; i < urls.length; i += 1) {
      progress(`匯入第 ${i + 1}/${urls.length} 個來源...`);
      await submitSourceUrl(urls[i]);
      progress(`第 ${i + 1}/${urls.length} 個來源已送出`, "ok");
      await sleep(1400);
    }
  }

  async function renameNotebook(title) {
    progress(`嘗試命名筆記本：${title}`);
    await sleep(1500);

    const candidates = Array.from(document.querySelectorAll([
      "input",
      "textarea",
      "[contenteditable='true']",
      "[role='textbox']",
      "h1",
      "h2"
    ].join(","))).filter(isVisible);

    const titleEl = candidates.find((el) => {
      const text = labelOf(el) || norm(el.value || "");
      return /未命名|Untitled|Untitled notebook|source|報告|notebook|筆記本/i.test(text);
    }) || candidates.find((el) => /h1|h2/i.test(el.tagName)) || null;

    if (!titleEl) {
      progress(`找不到標題欄，請手動改名為：${title}`, "warn");
      return;
    }

    try {
      titleEl.scrollIntoView({ block: "center", inline: "center" });
      titleEl.click();
      await sleep(300);
      if ("value" in titleEl && /INPUT|TEXTAREA/.test(titleEl.tagName)) {
        titleEl.select?.();
        setFieldValue(titleEl, title);
      } else if (titleEl.getAttribute("contenteditable") === "true" || titleEl.getAttribute("role") === "textbox") {
        setFieldValue(titleEl, title);
      } else {
        titleEl.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
        await sleep(300);
        const active = document.activeElement;
        if (active && active !== titleEl && ("value" in active || active.getAttribute("contenteditable") === "true")) {
          setFieldValue(active, title);
        } else {
          progress(`標題看起來不可直接編輯，請手動改名為：${title}`, "warn");
          return;
        }
      }
      document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
      document.activeElement?.blur?.();
      progress("筆記本命名已送出", "ok");
    } catch (error) {
      progress(`自動命名失敗，請手動改名為：${title}`, "warn");
    }
  }

  async function run({ title, urls }) {
    ensureStatusPanel().textContent = "";
    progress("開始建立 NotebookLM 報告集...");
    progress(`目標名稱：${title}`);
    await createNotebook();
    await importUrls(urls);
    await renameNotebook(title);
    progress("流程完成。若 NotebookLM 還在處理來源，請等待它完成解析。", "ok");
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "RUN_NOTEBOOKLM_REPORT_IMPORT") return false;

    (async () => {
      try {
        await run(message);
        sendResponse({ ok: true });
      } catch (error) {
        progress(`錯誤：${error.message}`, "err");
        sendResponse({ ok: false, error: error.message });
      }
    })();
    return true;
  });
}
