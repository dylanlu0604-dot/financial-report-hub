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

  function scopedClickableElements(root) {
    return Array.from(root.querySelectorAll([
      "button",
      "a",
      "[role='button']",
      "[role='link']",
      "[role='menuitem']",
      "[tabindex]:not([tabindex='-1'])"
    ].join(","))).filter(isVisible);
  }

  function findClickableIn(root, texts, options = {}) {
    const elements = scopedClickableElements(root).filter((el) => !options.exclude?.(el));
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

  function listLabelsIn(root, limit = 60) {
    const seen = new Set();
    const labels = [];
    for (const el of scopedClickableElements(root)) {
      const label = labelOf(el);
      if (!label || seen.has(label)) continue;
      seen.add(label);
      labels.push(label);
      if (labels.length >= limit) break;
    }
    return labels;
  }

  function activeSourceDialog() {
    const roots = Array.from(document.querySelectorAll([
      "[role='dialog']",
      "mat-dialog-container",
      ".cdk-overlay-pane",
      "[class*='dialog']",
      "[class*='Dialog']",
      "[class*='modal']",
      "[class*='Modal']"
    ].join(",")))
      .filter((el) => isVisible(el) && el.id !== "five-source-nlm-status")
      .filter((el) => /來源|source|網站|website|url|網址|YouTube|Drive|貼上|paste/i.test(norm(el.innerText || el.textContent || "")));
    return roots.at(-1) || null;
  }

  function dialogOrDocument() {
    return activeSourceDialog() || document;
  }

  function sourceRootForField(field) {
    return activeSourceDialog() ||
      field.closest?.("[role='dialog'], mat-dialog-container, .cdk-overlay-pane, [class*='dialog'], [class*='Dialog'], [class*='modal'], [class*='Modal']") ||
      document;
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
    const currentRoot = activeSourceDialog();
    if (currentRoot && (findUrlTextbox(currentRoot) || findClickableIn(currentRoot, ["網站", "Website", "網址", "YouTube", "貼上文字", "Paste text", "Copied text"]))) return;
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
    let root = dialogOrDocument();
    const existingTextbox = findUrlTextbox(root);
    if (existingTextbox) return existingTextbox;

    const website = findClickableIn(root, [
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

    const textbox = await waitFor(() => {
      root = dialogOrDocument();
      return findUrlTextbox(root);
    }, 15000);
    if (!textbox) {
      progress(`找不到 URL 輸入欄。對話框可點文字：${listLabelsIn(root).join(" | ")}`, "warn");
      throw new Error("找不到 URL 輸入欄");
    }
    return textbox;
  }

  function findUrlTextbox(root = document) {
    const fields = Array.from(root.querySelectorAll("input, textarea, [contenteditable='true'], [role='textbox']"))
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

  function textFieldValue(field) {
    if (!field) return "";
    return "value" in field ? field.value : field.textContent || "";
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

  function chatInputCandidates() {
    return Array.from(document.querySelectorAll("textarea, [contenteditable='true'], [role='textbox'], input"))
      .filter(isVisible)
      .filter((field) => {
        const tag = field.tagName;
        const type = (field.getAttribute("type") || "text").toLowerCase();
        if (tag === "INPUT" && !["text", "search"].includes(type)) return false;

        const label = [
          field.getAttribute("aria-label"),
          field.getAttribute("placeholder"),
          field.getAttribute("title"),
          field.getAttribute("name"),
          field.getAttribute("data-placeholder"),
          field.textContent
        ].map(norm).join(" ").toLowerCase();

        if (/url|網址|連結|link|website|source|來源|title|標題|notebook|筆記本/.test(label)) return false;
        return true;
      });
  }

  function findChatTextbox() {
    const fields = chatInputCandidates();
    const preferred = fields.find((field) => {
      const label = [
        field.getAttribute("aria-label"),
        field.getAttribute("placeholder"),
        field.getAttribute("title"),
        field.getAttribute("data-placeholder"),
        field.textContent
      ].map(norm).join(" ").toLowerCase();
      return /ask|question|chat|message|prompt|提問|問題|詢問|訊息|輸入|傳送/.test(label);
    });
    if (preferred) return preferred;

    return fields.find((field) => {
      const rect = field.getBoundingClientRect();
      return rect.width >= 240 && rect.bottom > window.innerHeight * 0.45;
    }) || fields.at(-1) || null;
  }

  function nearestChatRoot(field) {
    let current = field;
    for (let i = 0; current && i < 6; i += 1) {
      if (current.querySelectorAll?.("button, [role='button']").length) return current;
      current = current.parentElement;
    }
    return document;
  }

  function findSubmitQuestionButton(field) {
    const root = nearestChatRoot(field);
    const labels = [
      "送出",
      "傳送",
      "提交",
      "Send",
      "Submit",
      "Ask",
      "arrow_upward",
      "arrow_upward_alt",
      "send"
    ];

    const exclude = (el) => {
      const label = labelOf(el).toLowerCase();
      return el.disabled ||
        el.getAttribute("aria-disabled") === "true" ||
        /新增來源|add source|建立|create|分享|share|設定|settings|mic|麥克風|來源|source/.test(label);
    };

    const labeled = findClickableIn(root, labels, { exclude });
    if (labeled) return labeled;

    const rootButtons = scopedClickableElements(root).filter((el) => !exclude(el));
    const fieldRect = field.getBoundingClientRect();
    return rootButtons
      .map((el) => ({ el, rect: el.getBoundingClientRect() }))
      .filter(({ rect }) => rect.left >= fieldRect.left && rect.top >= fieldRect.top - 40)
      .sort((a, b) => (a.rect.top - b.rect.top) || (b.rect.left - a.rect.left))[0]?.el || null;
  }

  async function submitFirstQuestion(firstQuestion) {
    if (!firstQuestion) return;

    progress("等待 30 秒，讓 NotebookLM 處理來源...");
    await sleep(30000);
    progress("準備輸入第一個問題...");

    const textbox = await waitFor(() => findChatTextbox(), 30000, 500);
    if (!textbox) {
      progress(`找不到 NotebookLM 提問欄。目前可點文字：${listClickableLabels().join(" | ")}`, "warn");
      throw new Error("找不到 NotebookLM 提問欄");
    }

    textbox.scrollIntoView({ block: "center", inline: "center" });
    await sleep(300);
    setFieldValue(textbox, firstQuestion);
    await sleep(900);

    const submit = await waitFor(() => findSubmitQuestionButton(textbox), 10000, 300);
    if (submit) {
      progress(`送出第一個問題：${labelOf(submit) || "送出按鈕"}`);
      submit.click();
    } else {
      progress("找不到送出問題按鈕，改用 Ctrl+Enter 嘗試送出", "warn");
      textbox.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, ctrlKey: true, bubbles: true }));
      textbox.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, ctrlKey: true, bubbles: true }));
    }

    const sent = await waitFor(() => {
      const value = norm(textFieldValue(textbox));
      if (!value || !value.includes("步驟 1")) return true;
      if (visibleText().includes("你想先展開哪個地區")) return true;
      return null;
    }, 15000, 500);

    if (!sent) {
      progress("第一個問題可能尚未送出，請確認提問欄是否仍保留文字。", "warn");
      throw new Error("第一個問題送出未完成");
    }

    progress("第一個問題已送出", "ok");
  }

  async function submitSourceUrl(url) {
    await openAddSourceDialog();
    const textbox = await selectWebsiteSource();
    const dialog = activeSourceDialog();
    progress(`填入 URL：${url}`);
    setFieldValue(textbox, url);
    await sleep(900);

    const root = dialog || sourceRootForField(textbox);
    const submit = await waitFor(() => {
      const currentRoot = activeSourceDialog() || sourceRootForField(textbox);
      return findClickableIn(currentRoot, [
        "插入",
        "Insert",
        "匯入",
        "Import",
        "新增來源",
        "Add source",
        "新增",
        "Add",
        "Submit"
      ], {
        exclude: (el) => {
          const label = labelOf(el).toLowerCase();
          return el.disabled ||
            el.getAttribute("aria-disabled") === "true" ||
            (currentRoot === document && (label.includes("新增來源") || label.includes("add source")));
        }
      });
    }, 15000);

    if (submit) {
      progress(`送出來源：${labelOf(submit)}`);
      submit.click();
    } else {
      progress("找不到送出按鈕，改用 Enter 嘗試送出", "warn");
      textbox.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
    }

    const submitted = await waitFor(() => {
      const stillSameDialog = dialog && isVisible(dialog);
      const bodyText = visibleText();
      if (/無法|失敗|錯誤|invalid|failed|error|too long|字數|來源過長/i.test(bodyText)) return "error";
      if (!stillSameDialog) return "closed";
      const currentValue = textFieldValue(textbox);
      if (!norm(currentValue).includes(url.slice(0, 40))) return "cleared";
      return null;
    }, 20000, 500);

    if (submitted === "error") {
      throw new Error("NotebookLM 顯示來源匯入錯誤，請看頁面上的錯誤訊息");
    }
    if (!submitted) {
      progress("送出後對話框沒有關閉，可能沒有真正匯入。", "warn");
      throw new Error("URL 送出未完成");
    }

    await sleep(1500);
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

  async function run({ title, urls, firstQuestion }) {
    ensureStatusPanel().textContent = "";
    progress("開始建立 NotebookLM 報告集...");
    progress(`目標名稱：${title}`);
    await createNotebook();
    await importUrls(urls);
    await renameNotebook(title);
    await submitFirstQuestion(firstQuestion);
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
