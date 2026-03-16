// 任务状态日志模块（独立封装）
(function () {
  const { Elements } = window || {};
  const taskLogEl = Elements ? Elements.taskLog : document.getElementById("task-log");

  function addLog(message, type = "info") {
    if (!taskLogEl) return;

    const logTypes = {
      info: "text-dark",
      success: "text-success",
      warning: "text-warning",
      danger: "text-danger",
    };

    const logElement = document.createElement("p");
    logElement.className = `${logTypes[type] || "text-dark"} mb-1`;
    logElement.innerHTML = `[${new Date().toLocaleTimeString()}] ${message}`;

    taskLogEl.appendChild(logElement);
    taskLogEl.scrollTop = taskLogEl.scrollHeight;
  }

  function clearLog() {
    if (!taskLogEl) return;
    taskLogEl.innerHTML =
      '<p class="text-light italic">等待测试任务启动...</p>';
  }

  window.TaskLog = {
    addLog,
    clearLog,
  };
})();

