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
    historySinglePagination,
    historySinglePageInfo,
    historySinglePrevPage,
    historySingleNextPage,
    historyExecSetPagination,
    historyExecSetPageInfo,
    historyExecSetPrevPage,
    historyExecSetNextPage,
  } = Elements || {};
  const { addTaskLog, saveHistory, loadHistory, apiGet, formatDuration } =
    Common || {};

  const HistoryState = {
    activeTab: "single",
    single: { page: 1, pageSize: 10, totalPages: 1, total: 0 },
    execSet: { page: 1, pageSize: 10, totalPages: 1, total: 0 },
  };

  function statusBadge(status) {
    const s = String(status || "").trim().toLowerCase();
    if (s === "success") {
      return {
        cls: "bg-success/10 text-success",
        text: "成功",
      };
    }
    if (s === "stop") {
      return {
        cls: "bg-danger/10 text-danger",
        text: "停止",
      };
    }
    if (s === "failure") {
      return {
        cls: "bg-warning/10 text-warning",
        text: "失败",
      };
    }
    return { cls: "bg-warning/10 text-warning", text: s || "-" };
  }

  function renderSingleHistory(items) {
    if (!taskHistoryTableSingle) return;
    if (!items.length) {
      taskHistoryTableSingle.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-8 text-light">
            <i class="fa fa-history text-2xl mb-2"></i>
            <p>暂无任务历史记录</p>
          </td>
        </tr>
      `;
      return;
    }
    taskHistoryTableSingle.innerHTML = items
      .map(
        (h, index) => `
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 px-4">${h.task_id || "-"}</td>
        <td class="py-3 px-4">${h.device_id || "-"}</td>
        <td class="py-3 px-4">${h.case_name || h.case_id || "-"}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-1 rounded-full text-xs ${statusBadge(h.status).cls}">
            ${statusBadge(h.status).text}
          </span>
        </td>
        <td class="py-3 px-4">${h.start_time || h.create_time || "-"}</td>
        <td class="py-3 px-4">${formatDuration ? formatDuration(h.exec_duration) : (h.exec_duration || "-")}</td>
        <td class="py-3 px-4">
          ${
            h.report_index_path
              ? `<button class="text-primary hover:text-primary/80 text-sm"
                        onclick="window.open('/api/report/files/${encodeURIComponent(
                          h.task_id
                        )}/index.html', '_blank')">
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

  function renderExecSetHistory(items) {
    if (!taskHistoryTableExecSet) return;
    if (!items.length) {
      taskHistoryTableExecSet.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-8 text-light">
            <i class="fa fa-history text-2xl mb-2"></i>
            <p>暂无执行集历史记录</p>
          </td>
        </tr>
      `;
      return;
    }
    taskHistoryTableExecSet.innerHTML = items
      .map(
        (h, index) => `
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 px-4">${h.task_id || "-"}</td>
        <td class="py-3 px-4">${h.device_id || "-"}</td>
        <td class="py-3 px-4">${h.exec_set_name || h.exec_set_id || "-"}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-1 rounded-full text-xs ${statusBadge(h.status).cls}">
            ${statusBadge(h.status).text}
          </span>
        </td>
        <td class="py-3 px-4">${h.start_time || h.create_time || "-"}</td>
        <td class="py-3 px-4">${formatDuration ? formatDuration(h.exec_duration) : (h.exec_duration || "-")}</td>
        <td class="py-3 px-4">
          ${
            h.report_index_path
              ? `<button class="text-primary hover:text-primary/80 text-sm"
                        onclick="window.open('/api/report/files/${encodeURIComponent(
                          h.task_id
                        )}/index.html', '_blank')">
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

  function updatePaginationUI(tabKey, page, totalPages, total) {
    if (tabKey === "single") {
      historySinglePageInfo &&
        (historySinglePageInfo.textContent = `第 ${page} 页 / 共 ${totalPages} 页（${total} 条）`);
      if (historySinglePrevPage) historySinglePrevPage.disabled = page <= 1;
      if (historySingleNextPage)
        historySingleNextPage.disabled = page >= totalPages;
      historySinglePagination &&
        historySinglePagination.classList.remove("hidden");
    } else {
      historyExecSetPageInfo &&
        (historyExecSetPageInfo.textContent = `第 ${page} 页 / 共 ${totalPages} 页（${total} 条）`);
      if (historyExecSetPrevPage) historyExecSetPrevPage.disabled = page <= 1;
      if (historyExecSetNextPage)
        historyExecSetNextPage.disabled = page >= totalPages;
      historyExecSetPagination &&
        historyExecSetPagination.classList.remove("hidden");
    }
  }

  function appendTask(task) {
    AppState.taskHistory.unshift(task);
    saveHistory();
    // 新版历史列表以数据库为准，这里触发刷新第一页（让用户立刻看到最新记录）
    refreshActiveTab(true);
  }

  async function loadSinglePage(page) {
    const ps = HistoryState.single.pageSize;
    const url = `/api/test/history?page=${page}&page_size=${ps}`;
    const data = await apiGet(url);
    if (data.code !== 200 || !data.data) {
      throw new Error(data.msg || "加载执行历史失败");
    }
    const items = Array.isArray(data.data.items) ? data.data.items : [];
    HistoryState.single.page = data.data.page || page;
    HistoryState.single.totalPages = data.data.total_pages || 1;
    HistoryState.single.total = data.data.total || 0;
    renderSingleHistory(items);
    updatePaginationUI(
      "single",
      HistoryState.single.page,
      HistoryState.single.totalPages,
      HistoryState.single.total
    );
  }

  async function loadExecSetPage(page) {
    const ps = HistoryState.execSet.pageSize;
    const url = `/api/test/exec-set/history?page=${page}&page_size=${ps}`;
    const data = await apiGet(url);
    if (data.code !== 200 || !data.data) {
      throw new Error(data.msg || "加载执行集执行历史失败");
    }
    const items = Array.isArray(data.data.items) ? data.data.items : [];
    HistoryState.execSet.page = data.data.page || page;
    HistoryState.execSet.totalPages = data.data.total_pages || 1;
    HistoryState.execSet.total = data.data.total || 0;
    renderExecSetHistory(items);
    updatePaginationUI(
      "exec_set",
      HistoryState.execSet.page,
      HistoryState.execSet.totalPages,
      HistoryState.execSet.total
    );
  }

  async function refreshActiveTab(forceFirstPage = false) {
    try {
      if (HistoryState.activeTab === "exec_set") {
        const p = forceFirstPage ? 1 : HistoryState.execSet.page;
        await loadExecSetPage(p);
      } else {
        const p = forceFirstPage ? 1 : HistoryState.single.page;
        await loadSinglePage(p);
      }
    } catch (e) {
      console.error(e);
      addTaskLog &&
        addTaskLog(`[错误] ${e.message || "加载历史失败"}`, "danger");
    }
  }

  function initTabs() {
    if (!historyTabSingle || !historyTabExecSet) return;
    historyTabSingle.addEventListener("click", () => {
      HistoryState.activeTab = "single";
      historyTabSingle.classList.add("border-primary", "text-primary");
      historyTabSingle.classList.remove("text-light");
      historyTabExecSet.classList.remove("border-primary", "text-primary");
      historyTabExecSet.classList.add("text-light");
      historyPanelSingle &&
        historyPanelSingle.classList.remove("hidden");
      historyPanelExecSet &&
        historyPanelExecSet.classList.add("hidden");
      historyExecSetPagination &&
        historyExecSetPagination.classList.add("hidden");
      historySinglePagination &&
        historySinglePagination.classList.remove("hidden");
      refreshActiveTab(false);
    });
    historyTabExecSet.addEventListener("click", () => {
      HistoryState.activeTab = "exec_set";
      historyTabExecSet.classList.add("border-primary", "text-primary");
      historyTabExecSet.classList.remove("text-light");
      historyTabSingle.classList.remove("border-primary", "text-primary");
      historyTabSingle.classList.add("text-light");
      historyPanelExecSet &&
        historyPanelExecSet.classList.remove("hidden");
      historyPanelSingle &&
        historyPanelSingle.classList.add("hidden");
      historySinglePagination &&
        historySinglePagination.classList.add("hidden");
      historyExecSetPagination &&
        historyExecSetPagination.classList.remove("hidden");
      refreshActiveTab(false);
    });
  }

  function initPagination() {
    historySinglePrevPage &&
      historySinglePrevPage.addEventListener("click", () => {
        const next = Math.max(1, HistoryState.single.page - 1);
        loadSinglePage(next).catch((e) => {
          console.error(e);
        });
      });
    historySingleNextPage &&
      historySingleNextPage.addEventListener("click", () => {
        const next = Math.min(
          HistoryState.single.totalPages,
          HistoryState.single.page + 1
        );
        loadSinglePage(next).catch((e) => {
          console.error(e);
        });
      });

    historyExecSetPrevPage &&
      historyExecSetPrevPage.addEventListener("click", () => {
        const next = Math.max(1, HistoryState.execSet.page - 1);
        loadExecSetPage(next).catch((e) => {
          console.error(e);
        });
      });
    historyExecSetNextPage &&
      historyExecSetNextPage.addEventListener("click", () => {
        const next = Math.min(
          HistoryState.execSet.totalPages,
          HistoryState.execSet.page + 1
        );
        loadExecSetPage(next).catch((e) => {
          console.error(e);
        });
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
      renderSingleHistory([]);
      renderExecSetHistory([]);
      updatePaginationUI("single", 1, 1, 0);
      updatePaginationUI("exec_set", 1, 1, 0);
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
    // 初次加载：默认进入“单用例执行历史”第一页
    initPagination();
    refreshActiveTab(true);
    initTabs();
    initClearButton();
  }

  window.History = {
    initHistory,
    renderHistory: refreshActiveTab,
    appendTask,
  };
})();

