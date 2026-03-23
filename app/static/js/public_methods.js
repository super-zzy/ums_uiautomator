// 公共方法配置（列表、弹窗代码编辑器、用例编辑器内快速插入）

(function () {
  const { Common } = window;
  const { apiGet, apiPost, apiPut, addTaskLog } = Common || {};

  let pmCodeEditor = null;
  let pmEditorMode = null;
  let pmCurrentId = null;

  function ensurePublicMethodCodeEditor() {
    const ta = document.getElementById("public-method-content");
    if (!ta || typeof window.CodeMirror === "undefined") {
      return null;
    }
    if (!pmCodeEditor) {
      pmCodeEditor = window.CodeMirror.fromTextArea(ta, {
        mode: "python",
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        lineWrapping: true,
      });
    }
    return pmCodeEditor;
  }

  function closePublicMethodModal() {
    const modal = document.getElementById("public-method-editor-modal");
    if (modal) modal.classList.add("hidden");
    pmEditorMode = null;
    pmCurrentId = null;
  }

  async function loadPublicMethodList() {
    const tbody = document.getElementById("public-method-list-tbody");
    if (!tbody) return;
    try {
      const data = await apiGet("/api/test/public-methods");
      if (data.code !== 200 || !Array.isArray(data.data)) {
        throw new Error(data.msg || "加载失败");
      }
      const rows = data.data;
      if (!rows.length) {
        tbody.innerHTML =
          '<tr><td colspan="5" class="text-center py-4 text-light">暂无公共方法，点击「新建」添加</td></tr>';
        return;
      }
      tbody.innerHTML = rows
        .map(
          (r) => `
        <tr class="border-b border-gray-100 hover:bg-gray-50">
          <td class="py-2 px-4 text-xs">${r.id}</td>
          <td class="py-2 px-4 text-xs font-mono">${escapeHtml(r.name || "")}</td>
          <td class="py-2 px-4 text-xs text-light">${escapeHtml(
            r.description || ""
          )}</td>
          <td class="py-2 px-4 text-xs text-light">${escapeHtml(
            r.updated_at || ""
          )}</td>
          <td class="py-2 px-4 text-xs">
            <button type="button" class="text-primary hover:text-primary/80 mr-2" data-pm-action="edit" data-id="${r.id}">
              <i class="fa fa-edit"></i> 编辑
            </button>
            <button type="button" class="text-danger hover:text-danger/80" data-pm-action="delete" data-id="${r.id}" data-name="${escapeAttr(
            r.name || ""
          )}">
              <i class="fa fa-trash"></i> 删除
            </button>
          </td>
        </tr>
      `
        )
        .join("");
    } catch (e) {
      console.error(e);
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">加载失败：${escapeHtml(
        e.message || String(e)
      )}</td></tr>`;
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  async function refreshSuiteEditorPicker() {
    const sel = document.getElementById("suite-editor-public-method-select");
    if (!sel || !apiGet) return;
    try {
      const data = await apiGet("/api/test/public-methods");
      if (data.code !== 200 || !Array.isArray(data.data)) return;
      const opts = data.data
        .map(
          (r) =>
            `<option value="${r.id}">${escapeHtml(r.name || "")}${
              r.description
                ? " — " + escapeHtml(String(r.description).slice(0, 40))
                : ""
            }</option>`
        )
        .join("");
      sel.innerHTML =
        '<option value="">请选择公共方法…</option>' + opts;
    } catch (e) {
      console.error("刷新公共方法下拉失败", e);
    }
  }

  function openPublicMethodModalNew() {
    pmEditorMode = "new";
    pmCurrentId = null;
    const title = document.getElementById("public-method-editor-title");
    if (title) title.textContent = "新建公共方法";
    const nameEl = document.getElementById("public-method-name");
    const descEl = document.getElementById("public-method-desc");
    if (nameEl) nameEl.value = "";
    if (descEl) descEl.value = "";
    const editor = ensurePublicMethodCodeEditor();
    if (editor) {
      editor.setValue("");
    }
    const modal = document.getElementById("public-method-editor-modal");
    if (modal) modal.classList.remove("hidden");
    if (editor) setTimeout(() => editor.refresh(), 0);
  }

  async function openPublicMethodModalEdit(id) {
    pmEditorMode = "edit";
    pmCurrentId = id;
    const title = document.getElementById("public-method-editor-title");
    if (title) title.textContent = "编辑公共方法";
    try {
      const data = await apiGet(`/api/test/public-methods/${id}`);
      if (data.code !== 200 || !data.data) {
        throw new Error(data.msg || "加载失败");
      }
      const row = data.data;
      const nameEl = document.getElementById("public-method-name");
      const descEl = document.getElementById("public-method-desc");
      if (nameEl) nameEl.value = row.name || "";
      if (descEl) descEl.value = row.description || "";
      const editor = ensurePublicMethodCodeEditor();
      if (editor) {
        editor.setValue(row.content || "");
      }
      const modal = document.getElementById("public-method-editor-modal");
      if (modal) modal.classList.remove("hidden");
      if (editor) setTimeout(() => editor.refresh(), 0);
    } catch (e) {
      addTaskLog &&
        addTaskLog(`[错误] 加载公共方法失败：${e.message}`, "danger");
    }
  }

  async function savePublicMethod() {
    const nameEl = document.getElementById("public-method-name");
    const descEl = document.getElementById("public-method-desc");
    const name = nameEl ? nameEl.value.trim() : "";
    const description = descEl ? descEl.value.trim() : "";
    const editor = ensurePublicMethodCodeEditor();
    const content = editor ? editor.getValue() || "" : "";
    if (!name) {
      addTaskLog && addTaskLog("[错误] 请填写方法名称", "danger");
      return;
    }
    if (!content.trim()) {
      addTaskLog && addTaskLog("[错误] 请填写方法代码", "danger");
      return;
    }
    try {
      if (pmEditorMode === "new") {
        const data = await apiPost("/api/test/public-methods", {
          name,
          description,
          content,
        });
        if (data.code === 200) {
          addTaskLog && addTaskLog("[成功] 公共方法已创建", "success");
          closePublicMethodModal();
          await loadPublicMethodList();
          await refreshSuiteEditorPicker();
        } else {
          throw new Error(data.msg || "创建失败");
        }
      } else if (pmEditorMode === "edit" && pmCurrentId != null) {
        const data = await apiPut(`/api/test/public-methods/${pmCurrentId}`, {
          name,
          description,
          content,
        });
        if (data.code === 200) {
          addTaskLog && addTaskLog("[成功] 公共方法已保存", "success");
          closePublicMethodModal();
          await loadPublicMethodList();
          await refreshSuiteEditorPicker();
        } else {
          throw new Error(data.msg || "保存失败");
        }
      }
    } catch (e) {
      addTaskLog && addTaskLog(`[错误] ${e.message}`, "danger");
    }
  }

  async function insertSelectedIntoSuiteEditor() {
    const sel = document.getElementById("suite-editor-public-method-select");
    const id = sel && sel.value;
    if (!id) {
      addTaskLog && addTaskLog("[提示] 请先在下拉框中选择公共方法", "info");
      return;
    }
    const cm = window.SuiteCodeEditor;
    if (!cm) {
      addTaskLog && addTaskLog("[错误] 代码编辑器未就绪", "danger");
      return;
    }
    try {
      const data = await apiGet(`/api/test/public-methods/${id}`);
      if (data.code !== 200 || !data.data) {
        throw new Error(data.msg || "获取代码失败");
      }
      const block = (data.data.content || "").trimEnd();
      if (!block) {
        addTaskLog && addTaskLog("[提示] 该方法代码为空", "info");
        return;
      }
      const cur = cm.getCursor();
      const prefix = cur.ch > 0 ? cm.getLine(cur.line).slice(0, cur.ch) : "";
      const needsLead =
        cur.line > 0 || prefix.trim().length > 0 ? "\n\n" : "";
      cm.replaceRange(needsLead + block + "\n", cur);
      addTaskLog &&
        addTaskLog(
          `[成功] 已插入公共方法「${data.data.name || id}」代码`,
          "success"
        );
    } catch (e) {
      addTaskLog && addTaskLog(`[错误] 插入失败：${e.message}`, "danger");
    }
  }

  function init() {
    const newBtn = document.getElementById("new-public-method-btn");
    if (newBtn) {
      newBtn.addEventListener("click", () => openPublicMethodModalNew());
    }

    const tbody = document.getElementById("public-method-list-tbody");
    if (tbody && !tbody._pmBound) {
      tbody.addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-pm-action]");
        if (!btn) return;
        const action = btn.dataset.pmAction;
        const id = btn.dataset.id;
        if (!id) return;
        if (action === "edit") {
          openPublicMethodModalEdit(parseInt(id, 10));
        } else if (action === "delete") {
          const n = btn.dataset.name || id;
          if (!confirm(`确定删除公共方法「${n}」吗？`)) return;
          (async () => {
            try {
              const resp = await fetch(`/api/test/public-methods/${id}`, {
                method: "DELETE",
              });
              const data = await resp.json();
              if (data.code === 200) {
                addTaskLog && addTaskLog("[成功] 已删除公共方法", "success");
                await loadPublicMethodList();
                await refreshSuiteEditorPicker();
              } else {
                throw new Error(data.msg || "删除失败");
              }
            } catch (err) {
              addTaskLog &&
                addTaskLog(`[错误] 删除失败：${err.message}`, "danger");
            }
          })();
        }
      });
      tbody._pmBound = true;
    }

    document
      .getElementById("close-public-method-editor-btn")
      ?.addEventListener("click", closePublicMethodModal);
    document
      .getElementById("cancel-public-method-btn")
      ?.addEventListener("click", closePublicMethodModal);
    document
      .getElementById("save-public-method-btn")
      ?.addEventListener("click", () => savePublicMethod());

    document
      .getElementById("insert-public-method-code-btn")
      ?.addEventListener("click", () => insertSelectedIntoSuiteEditor());
  }

  window.PublicMethods = {
    init,
    loadPublicMethodList,
    refreshSuiteEditorPicker,
  };
})();
