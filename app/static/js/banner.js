// 顶部时间与整体刷新（banner 模块）

(function () {
  const { currentTime, refreshBtn } = window.Elements || {};
  const { addTaskLog } = window.Common || {};

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
    if (!currentTime || !refreshBtn) return;
    updateCurrentTime();
    setInterval(updateCurrentTime, 1000);
    refreshBtn.addEventListener("click", handleRefreshClick);
  }

  window.Banner = { initBanner };
})();

