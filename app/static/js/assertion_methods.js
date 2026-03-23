// 断言方法目录（只读，数据来自 /api/test/assertion-methods）

(function () {
  const { Common } = window;
  const { apiGet, addTaskLog } = Common || {};

  /** @type {Record<string, object>} */
  let assertionCatalogById = {};

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadAssertionMethodList() {
    const tbody = document.getElementById("assertion-method-list-tbody");
    if (!tbody) return;
    if (!apiGet) {
      tbody.innerHTML =
        '<tr><td colspan="5" class="text-center py-4 text-danger">API 未就绪</td></tr>';
      return;
    }
    tbody.innerHTML =
      '<tr><td colspan="5" class="text-center py-4 text-light">加载中…</td></tr>';
    try {
      const data = await apiGet("/api/test/assertion-methods");
      if (data.code !== 200 || !Array.isArray(data.data)) {
        throw new Error(data.msg || "加载失败");
      }
      const rows = data.data;
      if (!rows.length) {
        tbody.innerHTML =
          '<tr><td colspan="5" class="text-center py-4 text-light">暂无数据（请确认数据库已初始化）</td></tr>';
        return;
      }
      tbody.innerHTML = rows
        .map((r) => {
          const ex = r.example_code
            ? `<pre class="text-[11px] font-mono whitespace-pre-wrap break-words text-dark m-0 max-w-md">${escapeHtml(
                r.example_code
              )}</pre>`
            : '<span class="text-xs text-light">—</span>';
          return `
        <tr class="border-b border-gray-100 align-top hover:bg-gray-50/80">
          <td class="py-2 px-3 text-xs text-light whitespace-nowrap">${escapeHtml(
            r.category || ""
          )}</td>
          <td class="py-2 px-3 text-xs font-mono text-dark whitespace-nowrap">${escapeHtml(
            r.method_key || ""
          )}</td>
          <td class="py-2 px-3 text-xs font-medium text-dark">${escapeHtml(
            r.name || ""
          )}</td>
          <td class="py-2 px-3 text-xs text-light leading-snug">${escapeHtml(
            r.description || ""
          )}</td>
          <td class="py-2 px-3">${ex}</td>
        </tr>`;
        })
        .join("");
    } catch (e) {
      console.error(e);
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">加载失败：${escapeHtml(
        e.message || String(e)
      )}</td></tr>`;
    }
  }

  async function refreshSuiteEditorAssertionSelect() {
    const sel = document.getElementById("suite-editor-assertion-method-select");
    if (!sel || !apiGet) return;
    try {
      const data = await apiGet("/api/test/assertion-methods");
      if (data.code !== 200 || !Array.isArray(data.data)) return;
      const rows = data.data;
      assertionCatalogById = {};
      for (const r of rows) {
        if (r && r.id != null) {
          assertionCatalogById[String(r.id)] = r;
        }
      }
      const opts = rows
        .map((r) => {
          const tail = r.category
            ? ` — ${escapeHtml(String(r.category).slice(0, 24))}`
            : "";
          return `<option value="${r.id}">${escapeHtml(r.name || "")}${tail}</option>`;
        })
        .join("");
      sel.innerHTML =
        '<option value="">请选择断言条目…</option>' + opts;
    } catch (e) {
      console.error("刷新断言方法下拉失败", e);
    }
  }

  function insertSelectedAssertionIntoSuiteEditor() {
    const sel = document.getElementById("suite-editor-assertion-method-select");
    const id = sel && sel.value;
    if (!id) {
      addTaskLog &&
        addTaskLog("[提示] 请先在下拉框中选择断言条目", "info");
      return;
    }
    const cm = window.SuiteCodeEditor;
    if (!cm) {
      addTaskLog && addTaskLog("[错误] 代码编辑器未就绪", "danger");
      return;
    }
    const row = assertionCatalogById[String(id)];
    if (!row) {
      addTaskLog &&
        addTaskLog("[错误] 断言条目数据未加载，请关闭并重新打开编辑窗口", "danger");
      return;
    }
    const raw = (row.example_code != null && String(row.example_code).trim())
      ? String(row.example_code).trimEnd()
      : "";
    if (!raw) {
      addTaskLog &&
        addTaskLog(
          `[提示]「${row.name || id}」暂无参考代码，请见「断言方法配置」页说明`,
          "info"
        );
      return;
    }
    const block = raw;
    const cur = cm.getCursor();
    const prefix = cur.ch > 0 ? cm.getLine(cur.line).slice(0, cur.ch) : "";
    const needsLead = cur.line > 0 || prefix.trim().length > 0 ? "\n\n" : "";
    cm.replaceRange(needsLead + block + "\n", cur);
    addTaskLog &&
      addTaskLog(
        `[成功] 已插入断言参考「${row.name || id}」`,
        "success"
      );
  }

  function init() {
    document
      .getElementById("insert-assertion-method-code-btn")
      ?.addEventListener("click", () => insertSelectedAssertionIntoSuiteEditor());
    refreshSuiteEditorAssertionSelect();
  }

  window.AssertionMethods = {
    init,
    loadAssertionMethodList,
    refreshSuiteEditorAssertionSelect,
    insertSelectedAssertionIntoSuiteEditor,
  };
})();
