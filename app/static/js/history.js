// 历史记录模块（单用例 + 执行集）

(function () {
  const { Elements, AppState, Common } = window;
  const {
    taskHistoryTableSingle,
    taskHistoryTableExecSet,
    historyTabSingle,
    historyTabExecSet,
    historyPanelSingle,
    historyPanelExecSet,
    clearHistoryBtn,
    viewReportBtn,
  } = Elements || {};
  const { addTaskLog, saveHistory, loadHistory } = Common || {};

  function renderSingleHistory(singleTasks) {
    if (!taskHistoryTableSingle) return;
    if (!singleTasks.length) {
      taskHistoryTableSingle.innerHTML = `
        <tr>
          <td colspan="6" class="text-center py-8 text-light">
            <i class="fa fa-history text-2xl mb-2"></i>
            <p>暂无任务历史记录</p>
          </td>
        </tr>
      `;
      return;
    }
    taskHistoryTableSingle.innerHTML = singleTasks
      .map(
        (task) => `
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 px-4">${task.id}</td>
        <td class="py-3 px-4">${task.device}</td>
        <td class="py-3 px-4">${task.suite}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-1 rounded-full text-xs ${
            task.status === "成功"
              ? "bg-success/10 text-success"
              : task.status === "失败"
              ? "bg-danger/10 text-danger"
              : "bg-warning/10 text-warning"
          }">
            ${task.status}
          </span>
        </td>
        <td class="py-3 px-4">${task.time}</td>
        <td class="py-3 px-4">
          ${
            task.reportUrl
              ? `<button class="text-primary hover:text-primary/80 text-sm"
                        onclick="window.open('${task.reportUrl}', '_blank')">
                     <i class="fa fa-file-text-o mr-1"></i>查看报告
                 </button>`
              : `<span class="text-light text-sm">无报告</span>`
          }
        </td>
      </tr>
    `
      )
      .join("");
  }

  function renderExecSetHistory(execSetTasks) {
    if (!taskHistoryTableExecSet) return;
    if (!execSetTasks.length) {
      taskHistoryTableExecSet.innerHTML = `
        <tr>
          <td colspan="6" class="text-center py-8 text-light">
            <i class="fa fa-history text-2xl mb-2"></i>
            <p>暂无执行集历史记录</p>
          </td>
        </tr>
      `;
      return;
    }
    taskHistoryTableExecSet.innerHTML = execSetTasks
      .map(
        (task) => `
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 px-4">${task.id}</td>
        <td class="py-3 px-4">${task.device}</td>
        <td class="py-3 px-4">${task.execSetName || "-"}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-1 rounded-full text-xs ${
            task.status === "成功"
              ? "bg-success/10 text-success"
              : task.status === "失败"
              ? "bg-danger/10 text-danger"
              : "bg-warning/10 text-warning"
          }">
            ${task.status}
          </span>
        </td>
        <td class="py-3 px-4">${task.time}</td>
        <td class="py-3 px-4">
          ${
            task.reportUrl
              ? `<button class="text-primary hover:text-primary/80 text-sm"
                        onclick="window.open('${task.reportUrl}', '_blank')">
                     <i class="fa fa-file-text-o mr-1"></i>查看报告
                 </button>`
              : `<span class="text-light text-sm">无报告</span>`
          }
        </td>
      </tr>
    `
      )
      .join("");
  }

  function renderHistory() {
    const singleTasks = (AppState.taskHistory || []).filter(
      (t) => !t.type || t.type === "single"
    );
    const execSetTasks = (AppState.taskHistory || []).filter(
      (t) => t.type === "exec_set"
    );
    renderSingleHistory(singleTasks);
    renderExecSetHistory(execSetTasks);
    if (viewReportBtn) {
      viewReportBtn.disabled = !AppState.taskHistory.length;
    }
  }

  function appendTask(task) {
    AppState.taskHistory.unshift(task);
    saveHistory();
    renderHistory();
  }

  function initTabs() {
    if (!historyTabSingle || !historyTabExecSet) return;
    historyTabSingle.addEventListener("click", () => {
      historyTabSingle.classList.add("border-primary", "text-primary");
      historyTabSingle.classList.remove("text-light");
      historyTabExecSet.classList.remove("border-primary", "text-primary");
      historyTabExecSet.classList.add("text-light");
      historyPanelSingle &&
        historyPanelSingle.classList.remove("hidden");
      historyPanelExecSet &&
        historyPanelExecSet.classList.add("hidden");
    });
    historyTabExecSet.addEventListener("click", () => {
      historyTabExecSet.classList.add("border-primary", "text-primary");
      historyTabExecSet.classList.remove("text-light");
      historyTabSingle.classList.remove("border-primary", "text-primary");
      historyTabSingle.classList.add("text-light");
      historyPanelExecSet &&
        historyPanelExecSet.classList.remove("hidden");
      historyPanelSingle &&
        historyPanelSingle.classList.add("hidden");
    });
  }

  function initClearButton() {
    if (!clearHistoryBtn) return;
    clearHistoryBtn.addEventListener("click", () => {
      if (
        !confirm("确定要清空所有任务历史记录吗？此操作不可恢复！")
      ) {
        return;
      }
      AppState.taskHistory = [];
      saveHistory();
      renderHistory();
      addTaskLog && addTaskLog("[提示] 任务历史已清空", "info");
    });
  }

  function initHistory() {
    loadHistory();
    // 兼容旧结构
    AppState.taskHistory = (AppState.taskHistory || []).map((t) => ({
      ...t,
      reportUrl: t.reportUrl || t.report_url || "",
      status: t.status || "未知",
    }));
    renderHistory();
    initTabs();
    initClearButton();
  }

  window.History = {
    initHistory,
    renderHistory,
    appendTask,
  };
})();

