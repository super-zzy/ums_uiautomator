// 用例管理与单用例执行模块

(function () {
  const { Elements, AppState, Common } = window;
  const {
    testSuiteSelect,
    startTestBtn,
    stopTestBtn,
    viewReportBtn,
  } = Elements || {};
  const { apiGet, apiPost, addTaskLog } = Common || {};

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
    if (testSuiteSelect) {
      testSuiteSelect.addEventListener("change", () => {
        updateStartBtnStatus();
        // 同时更新编辑/删除按钮状态（简化：只看是否有值）
        Elements.editSuiteBtn &&
          (Elements.editSuiteBtn.disabled = !testSuiteSelect.value);
        Elements.deleteSuiteBtn &&
          (Elements.deleteSuiteBtn.disabled = !testSuiteSelect.value);
      });
    }
    startTestBtn &&
      startTestBtn.addEventListener("click", startTestTask);
    stopTestBtn &&
      stopTestBtn.addEventListener("click", stopCurrentTask);
    if (viewReportBtn) {
      viewReportBtn.addEventListener("click", () => {
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

