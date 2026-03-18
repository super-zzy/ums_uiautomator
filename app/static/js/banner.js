// 顶部时间与整体刷新（banner 模块）

(function () {
  const {
    currentTime,
    refreshBtn,
    execSetCount,
    historySingleCount,
    historyExecSetCount,
  } = window.Elements || {};
  const { addTaskLog, apiGet } = window.Common || {};

  function updateCurrentTime() {
    if (!currentTime) return;
    const now = new Date();
    currentTime.textContent = now.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  async function loadOverviewStats() {
    try {
      const resp = await apiGet("/api/test/overview");
      if (!resp || resp.code !== 200 || !resp.data) {
        throw new Error((resp && resp.msg) || "获取概览统计失败");
      }
      const data = resp.data;
      if (execSetCount) {
        execSetCount.textContent = data.exec_set_count ?? 0;
      }
      if (historySingleCount) {
        historySingleCount.textContent = data.history_single_count ?? 0;
      }
      if (historyExecSetCount) {
        historyExecSetCount.textContent = data.history_exec_set_count ?? 0;
      }
    } catch (e) {
      console.error("加载概览统计失败:", e);
      addTaskLog &&
        addTaskLog(`[错误] 加载概览统计失败：${e.message}`, "danger");
    }
  }

  async function handleRefreshClick() {
    if (!refreshBtn) return;
    const icon = refreshBtn.querySelector("i");
    if (icon) {
      icon.classList.add("fa-spin");
    }
    try {
      // 统一调度设备、用例、运行中任务刷新
      await Promise.all([
        window.Devices?.loadDeviceList(),
        window.Suites?.loadTestSuites(),
        window.Suites?.loadRunningTasks?.(),
        loadOverviewStats(),
      ]);
    } catch (e) {
      console.error("全局刷新失败", e);
      addTaskLog && addTaskLog(`[错误] 刷新数据失败：${e.message}`, "danger");
    } finally {
      if (icon) {
        icon.classList.remove("fa-spin");
      }
    }
  }

  function initBanner() {
    if (currentTime) {
      updateCurrentTime();
      setInterval(updateCurrentTime, 1000);
    }
    // 首次进入页面时加载概览统计
    loadOverviewStats();
    if (refreshBtn) {
      refreshBtn.addEventListener("click", handleRefreshClick);
    }
  }

  window.Banner = { initBanner };
})();

