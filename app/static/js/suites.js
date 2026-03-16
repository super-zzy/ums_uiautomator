// 用例管理与单用例执行模块

(function () {
  const { Elements, AppState, Common } = window;
  const {
    testSuiteSelect,
    startTestBtn,
    stopTestBtn,
    viewReportBtn,
    editSuiteBtn,
    newSuiteBtn,
    deleteSuiteBtn,
    suiteEditorModal,
    closeEditorBtn,
    cancelEditBtn,
    saveSuiteBtn,
    suiteContent,
    editorModalTitle,
    newSuiteNameContainer,
    newSuiteName,
  } = Elements || {};
  const { apiGet, apiPost, addTaskLog } = Common || {};

  // 用例编辑状态
  let editorMode = null; // "edit" | "new"
  let currentEditingSuiteId = null;
  let codeEditor = null; // CodeMirror 实例（用于Python语法高亮）
  let currentEditingSuiteName = ""; // 当前编辑用例的原始文件名（含.py）

  function ensureCodeEditor() {
    if (!suiteContent || typeof window.CodeMirror === "undefined") {
      return null;
    }
    if (!codeEditor) {
      codeEditor = window.CodeMirror.fromTextArea(suiteContent, {
        mode: "python",
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        lineWrapping: true,
      });
      window.SuiteCodeEditor = codeEditor;
    }
    return codeEditor;
  }

  async function validatePythonSyntax(code) {
    if (!code || !code.trim()) {
      return { ok: true, message: "代码为空，跳过语法校验" };
    }
    try {
      const resp = await fetch("/api/test/validate-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await resp.json();
      if (data.code === 200 && data.data?.valid) {
        return { ok: true, message: data.msg || "语法校验通过" };
      }
      // 语法错误
      const err = (data.data && data.data.errors && data.data.errors[0]) || {};
      const line = err.lineno || "-";
      const col = err.offset || "-";
      const msg = err.msg || data.msg || "未知语法错误";
      return {
        ok: false,
        message: `第 ${line} 行，第 ${col} 列：${msg}`,
      };
    } catch (e) {
      console.error("语法校验接口异常:", e);
      return { ok: false, message: `语法校验异常：${e.message || e}` };
    }
  }

  async function loadTestSuites() {
    if (!testSuiteSelect) return;
    try {
      testSuiteSelect.innerHTML =
        '<option value="" disabled selected>加载用例中...</option>';
      const data = await apiGet("/api/test/suites");
      if (data.code === 200 && Array.isArray(data.data)) {
        const suites = data.data;
        Elements.testSuiteCount &&
          (Elements.testSuiteCount.textContent = suites.length);
        if (!suites.length) {
          testSuiteSelect.innerHTML =
            '<option value="" disabled selected>暂无可用测试用例</option>';
          startTestBtn && (startTestBtn.disabled = true);
          return;
        }
        testSuiteSelect.innerHTML =
          '<option value="" disabled selected>请选择测试用例</option>' +
          suites
            .map(
              (suite) =>
                `<option value="${suite.id}" data-abs-path="${suite.abs_path}">
                   ${suite.name} (${suite.rel_path})
                 </option>`
            )
            .join("");
        updateStartBtnStatus();
      } else {
        throw new Error(data.msg || "加载测试用例失败");
      }
    } catch (e) {
      console.error("加载测试用例失败:", e);
      testSuiteSelect.innerHTML =
        '<option value="" disabled selected>加载用例失败</option>';
      startTestBtn && (startTestBtn.disabled = true);
      addTaskLog &&
        addTaskLog(`[错误] 加载测试用例失败: ${e.message}`, "danger");
    }
  }

  async function loadRunningTasks() {
    try {
      const data = await apiGet("/api/test/running");
      if (data.code === 200) {
        Elements.runningTaskCount &&
          (Elements.runningTaskCount.textContent = data.data.length);
        if (!AppState.currentTaskId && data.data.length > 0) {
          const sorted = [...data.data].sort(
            (a, b) => new Date(b.start_time) - new Date(a.start_time)
          );
          AppState.currentTaskId = sorted[0].task_id;
          startTaskStatusPolling();
          addTaskLog &&
            addTaskLog(
              `[信息] 自动跟踪最新运行中任务：${AppState.currentTaskId}`,
              "info"
            );
        }
      }
    } catch (e) {
      console.error("加载运行中任务失败:", e);
    }
  }

  function updateStartBtnStatus() {
    if (!startTestBtn || !testSuiteSelect) return;
    const deviceId = window.Devices?.getSelectedDeviceId?.();
    const selectedSuite = testSuiteSelect.value;
    const isRunning = AppState.currentTaskId !== null;
    startTestBtn.disabled = !deviceId || !selectedSuite || isRunning;
    if (viewReportBtn) {
      viewReportBtn.disabled = !(AppState.taskHistory || []).length;
    }
  }

  async function startTestTask() {
    try {
      const deviceId = window.Devices?.getSelectedDeviceId?.();
      const selectedSuiteId = testSuiteSelect?.value;
      if (!deviceId || !selectedSuiteId) {
        addTaskLog &&
          addTaskLog("[错误] 请先选择设备和测试用例", "danger");
        return;
      }
      const suiteName =
        testSuiteSelect.options[testSuiteSelect.selectedIndex].text;
      addTaskLog &&
        addTaskLog(
          `[信息] 正在启动测试任务（设备：${deviceId}，用例：${suiteName}）`,
          "info"
        );
      const data = await apiPost("/api/test/start", {
        device_id: deviceId,
        suite_id: parseInt(selectedSuiteId, 10),
      });
      if (data.code === 200 && data.data?.task_id) {
        AppState.currentTaskId = data.data.task_id;
        addTaskLog &&
          addTaskLog(
            `[成功] 测试任务已启动，任务ID：${AppState.currentTaskId}`,
            "success"
          );
        startTestBtn && (startTestBtn.disabled = true);
        stopTestBtn && (stopTestBtn.disabled = false);
        startTaskStatusPolling();
      } else {
        throw new Error(data.msg || "启动测试任务失败");
      }
    } catch (e) {
      addTaskLog &&
        addTaskLog(`[错误] 启动测试任务失败: ${e.message}`, "danger");
      console.error("启动测试任务失败:", e);
    }
  }

  function startTaskStatusPolling() {
    if (AppState.refreshInterval) {
      clearInterval(AppState.refreshInterval);
    }
    const poll = async () => {
      if (!AppState.currentTaskId) {
        clearInterval(AppState.refreshInterval);
        return;
      }
      try {
        const data = await apiGet(
          `/api/test/status/${AppState.currentTaskId}`
        );
        if (data.code === 200 && data.data) {
          const task = data.data;
          if (task.status === "running") {
            addTaskLog &&
              addTaskLog(
                `[信息] 任务${AppState.currentTaskId}正在执行...`,
                "info"
              );
          } else if (
            task.status.includes("success") ||
            task.status.includes("failed")
          ) {
            const suiteInfo = task.suite_info || {};
            const isSuccess = task.status.includes("success");
            addTaskLog &&
              addTaskLog(
                `[信息] 任务${AppState.currentTaskId}已${
                  isSuccess ? "成功" : "失败"
                }`,
                isSuccess ? "success" : "danger"
              );
            const newTask = {
              id: AppState.currentTaskId,
              device: task.device_id,
              suite: suiteInfo.name || "未知用例",
              status: isSuccess ? "成功" : "失败",
              time:
                task.start_time ||
                new Date().toLocaleString("zh-CN"),
              type: "single",
              reportUrl: task.report_url || "",
            };
            window.History?.appendTask?.(newTask);
            clearInterval(AppState.refreshInterval);
            AppState.currentTaskId = null;
            stopTestBtn && (stopTestBtn.disabled = true);
            startTestBtn && (startTestBtn.disabled = false);
            viewReportBtn && (viewReportBtn.disabled = false);
          }
        } else {
          throw new Error(data.msg || "获取任务状态失败");
        }
      } catch (e) {
        addTaskLog &&
          addTaskLog(`[错误] 获取任务状态失败: ${e.message}`, "danger");
        console.error("获取任务状态失败:", e);
      }
    };
    poll();
    AppState.refreshInterval = setInterval(poll, 3000);
  }

  async function stopCurrentTask() {
    if (!AppState.currentTaskId) {
      addTaskLog && addTaskLog("[错误] 没有正在运行的任务", "danger");
      return;
    }
    if (
      !confirm(`确定要停止任务 ${AppState.currentTaskId} 吗？`)
    ) {
      return;
    }
    try {
      stopTestBtn && (stopTestBtn.disabled = true);
      addTaskLog &&
        addTaskLog(
          `[信息] 正在停止任务 ${AppState.currentTaskId}...`,
          "info"
        );
      const data = await apiPost(
        `/api/test/stop/${AppState.currentTaskId}`
      );
      if (data.code === 200) {
        addTaskLog &&
          addTaskLog(
            `[成功] 任务 ${AppState.currentTaskId} 已停止`,
            "success"
          );
      } else {
        throw new Error(data.msg || "停止任务失败");
      }
    } catch (e) {
      addTaskLog &&
        addTaskLog(
          `[错误] 停止任务时发生错误：${e.message}`,
          "danger"
        );
      console.error("停止任务错误:", e);
      stopTestBtn && (stopTestBtn.disabled = false);
      return;
    }
    AppState.currentTaskId = null;
    clearInterval(AppState.refreshInterval);
    stopTestBtn && (stopTestBtn.disabled = true);
    startTestBtn && (startTestBtn.disabled = false);
    testSuiteSelect && (testSuiteSelect.disabled = false);
    document.querySelectorAll(".device-item").forEach((item) => {
      item.style.pointerEvents = "auto";
      item.classList.remove("opacity-50");
    });
    updateStartBtnStatus();
  }

  function initSuiteEvents() {
    // 兜底获取关键 DOM 元素，避免 Elements 映射异常导致事件未绑定
    const suiteSelectEl =
      testSuiteSelect || document.getElementById("test-suite-select");
    const startBtnEl =
      startTestBtn || document.getElementById("start-test-btn");
    const stopBtnEl = stopTestBtn || document.getElementById("stop-test-btn");
    const viewReportBtnEl =
      viewReportBtn || document.getElementById("view-report-btn");
    const editSuiteBtnEl =
      editSuiteBtn || document.getElementById("edit-suite-btn");
    const newSuiteBtnEl =
      newSuiteBtn || document.getElementById("new-suite-btn");
    const deleteSuiteBtnEl =
      deleteSuiteBtn || document.getElementById("delete-suite-btn");
    const suiteEditorModalEl =
      suiteEditorModal || document.getElementById("suite-editor-modal");
    const closeEditorBtnEl =
      closeEditorBtn || document.getElementById("close-editor-btn");
    const cancelEditBtnEl =
      cancelEditBtn || document.getElementById("cancel-edit-btn");

    if (suiteSelectEl) {
      suiteSelectEl.addEventListener("change", () => {
        updateStartBtnStatus();
        // 同时更新编辑/删除按钮状态（简化：只看是否有值）
        const hasValue = !!suiteSelectEl.value;
        if (editSuiteBtnEl) {
          editSuiteBtnEl.disabled = !hasValue;
        }
        if (deleteSuiteBtnEl) {
          deleteSuiteBtnEl.disabled = !hasValue;
        }
      });
    }

    if (startBtnEl) {
      startBtnEl.addEventListener("click", startTestTask);
    }
    if (stopBtnEl) {
      stopBtnEl.addEventListener("click", stopCurrentTask);
    }

    if (viewReportBtnEl) {
      viewReportBtnEl.addEventListener("click", () => {
        const history = AppState.taskHistory || [];
        if (!history.length) {
          addTaskLog &&
            addTaskLog("[错误] 暂无测试报告可查看", "danger");
          return;
        }
        const latest = history[0];
        if (latest.reportUrl) {
          window.open(latest.reportUrl, "_blank");
        } else {
          addTaskLog &&
            addTaskLog("[错误] 最新任务无报告可查看", "danger");
        }
      });
    }

    // 新建用例
    if (newSuiteBtnEl) {
      newSuiteBtnEl.addEventListener("click", () => {
        editorMode = "new";
        currentEditingSuiteId = null;
        currentEditingSuiteName = "";
        if (editorModalTitle) {
          editorModalTitle.textContent = "新建测试用例";
        }
        if (newSuiteNameContainer) {
          newSuiteNameContainer.style.display = "block";
        }
        if (newSuiteName) {
          newSuiteName.value = "";
        }
        const editor = ensureCodeEditor();
        if (editor) {
          editor.setValue("");
        } else if (suiteContent) {
          suiteContent.value = "";
        }
        if (suiteEditorModalEl) {
          suiteEditorModalEl.classList.remove("hidden");
        }
        if (editor) {
          setTimeout(() => editor.refresh(), 0);
        }
      });
    }

    // 编辑用例
    if (editSuiteBtnEl) {
      editSuiteBtnEl.addEventListener("click", async () => {
        const selectedSuiteId = suiteSelectEl?.value;
        if (!selectedSuiteId) {
          addTaskLog &&
            addTaskLog("[错误] 请先选择要编辑的用例", "danger");
          return;
        }
        editorMode = "edit";
        currentEditingSuiteId = parseInt(selectedSuiteId, 10);
        if (editorModalTitle) {
          editorModalTitle.textContent = "编辑测试用例";
        }
        if (newSuiteNameContainer) {
          newSuiteNameContainer.style.display = "block";
        }
        if (newSuiteName) {
          newSuiteName.value = "";
        }
        try {
          const data = await apiGet(
            `/api/test/suite/${currentEditingSuiteId}`
          );
          if (data.code === 200 && data.data) {
            currentEditingSuiteName = data.data.name || "";
            if (newSuiteName) {
              // 去掉.py后缀只展示基础名
              const baseName = currentEditingSuiteName.endsWith(".py")
                ? currentEditingSuiteName.slice(0, -3)
                : currentEditingSuiteName;
              newSuiteName.value = baseName;
            }
            const editor = ensureCodeEditor();
            if (editor) {
              editor.setValue(data.data.content || "");
            } else if (suiteContent) {
              suiteContent.value = data.data.content || "";
            }
            if (suiteEditorModalEl) {
              suiteEditorModalEl.classList.remove("hidden");
            }
            if (editor) {
              setTimeout(() => editor.refresh(), 0);
            }
          } else {
            throw new Error(data.msg || "获取用例内容失败");
          }
        } catch (e) {
          addTaskLog &&
            addTaskLog(
              `[错误] 加载用例内容失败：${e.message}`,
              "danger"
            );
          console.error("加载用例内容失败:", e);
        }
      });
    }

    // 删除用例
    if (deleteSuiteBtnEl) {
      deleteSuiteBtnEl.addEventListener("click", async () => {
        const selectedSuiteId = suiteSelectEl?.value;
        if (!selectedSuiteId) {
          addTaskLog &&
            addTaskLog("[错误] 请先选择要删除的用例", "danger");
          return;
        }
        if (
          !confirm(
            "确定要删除当前选中的用例吗？该操作不可恢复！"
          )
        ) {
          return;
        }
        try {
          const resp = await fetch(
            `/api/test/suite/${parseInt(selectedSuiteId, 10)}`,
            {
              method: "DELETE",
            }
          );
          const data = await resp.json();
          if (data.code === 200) {
            addTaskLog &&
              addTaskLog("[成功] 用例删除成功", "success");
            // 重新加载用例列表
            await loadTestSuites();
          } else {
            throw new Error(data.msg || "删除用例失败");
          }
        } catch (e) {
          addTaskLog &&
            addTaskLog(
              `[错误] 删除用例失败：${e.message}`,
              "danger"
            );
          console.error("删除用例失败:", e);
        }
      });
    }

    // 关闭/取消编辑
    const closeEditor = () => {
      editorMode = null;
      currentEditingSuiteId = null;
      currentEditingSuiteName = "";
      if (suiteEditorModalEl) {
        suiteEditorModalEl.classList.add("hidden");
      }
    };

    if (closeEditorBtnEl) {
      closeEditorBtnEl.addEventListener("click", closeEditor);
    }
    if (cancelEditBtnEl) {
      cancelEditBtnEl.addEventListener("click", closeEditor);
    }

    // 保存用例
    if (saveSuiteBtn) {
      saveSuiteBtn.addEventListener("click", async () => {
        try {
          const editor = ensureCodeEditor();
          const content = editor
            ? editor.getValue() || ""
            : suiteContent
            ? suiteContent.value || ""
            : "";
          const syntaxResult = await validatePythonSyntax(content);
          if (!syntaxResult.ok) {
            addTaskLog &&
              addTaskLog(
                `[错误] Python 语法校验失败：${syntaxResult.message}`,
                "danger"
              );
            return;
          }
          addTaskLog &&
            addTaskLog(
              `[信息] Python 语法校验通过：${syntaxResult.message}`,
              "info"
            );

          if (editorMode === "new") {
            let name = newSuiteName ? newSuiteName.value.trim() : "";
            if (!name) {
              addTaskLog &&
                addTaskLog("[错误] 请填写用例文件名", "danger");
              return;
            }
            if (!name.endsWith(".py")) {
              name = `${name}.py`;
            }
            const resp = await fetch("/api/test/suite", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name, content }),
            });
            const data = await resp.json();
            if (data.code === 200) {
              addTaskLog &&
                addTaskLog("[成功] 新建用例成功", "success");
              closeEditor();
              await loadTestSuites();
            } else {
              throw new Error(data.msg || "新建用例失败");
            }
          } else if (editorMode === "edit") {
            if (currentEditingSuiteId === null) {
              addTaskLog &&
                addTaskLog(
                  "[错误] 未找到当前编辑的用例ID",
                  "danger"
                );
              return;
            }
            let name = newSuiteName ? newSuiteName.value.trim() : "";
            if (!name) {
              addTaskLog &&
                addTaskLog("[错误] 请填写用例文件名", "danger");
              return;
            }
            const resp = await fetch(
              `/api/test/suites/${currentEditingSuiteId}`,
              {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  name,
                  content,
                }),
              }
            );
            const data = await resp.json();
            if (data.code === 200) {
              addTaskLog &&
                addTaskLog("[成功] 用例保存成功", "success");
              closeEditor();
              await loadTestSuites();
            } else {
              throw new Error(data.msg || "保存用例失败");
            }
          } else {
            addTaskLog &&
              addTaskLog(
                "[错误] 当前用例编辑状态未知，无法保存",
                "danger"
              );
          }
        } catch (e) {
          addTaskLog &&
            addTaskLog(
              `[错误] 保存用例失败：${e.message}`,
              "danger"
            );
          console.error("保存用例失败:", e);
        }
      });
    }
  }

  function initSuites() {
    initSuiteEvents();
    // 10 秒刷新运行中任务数量
    setInterval(loadRunningTasks, 10000);
  }

  window.Suites = {
    initSuites,
    loadTestSuites,
    loadRunningTasks,
    updateStartBtnStatus,
  };
})();

