// 在线设备模块

(function () {
  const { Elements, Common, AppState } = window;
  const {
    deviceList,
    onlineDeviceCount,
    refreshDeviceBtn,
    atxGuideBtn,
    runningTaskTable,
    runningTaskCount,
    refreshRunningTasksBtn,
  } = Elements || {};
  const { apiGet, apiPost, addTaskLog, parseDateTime, formatDuration } =
    Common || {};

  async function loadDeviceList() {
    if (!deviceList || !onlineDeviceCount) return;
    try {
      deviceList.innerHTML = `
        <div class="text-center text-light py-8">
          <i class="fa fa-spinner fa-spin text-2xl mb-2"></i>
          <p>加载设备中...</p>
        </div>
      `;
      const data = await apiGet("/api/device/list");
      if (data.code === 200 && Array.isArray(data.data)) {
        const devices = data.data;
        onlineDeviceCount.textContent = devices.length;
        if (devices.length === 0) {
          deviceList.innerHTML = `
            <div class="text-center text-light py-8">
              <i class="fa fa-mobile text-2xl mb-2 opacity-50"></i>
              <p>未发现在线设备，请检查ADB连接</p>
            </div>
          `;
          Elements.startTestBtn && (Elements.startTestBtn.disabled = true);
          return;
        }

        deviceList.innerHTML = devices
          .map(
            (device) => `
          <div class="border border-gray-200 rounded-lg p-3 hover:border-primary transition-colors cursor-pointer device-item"
               data-device-id="${device.device_id}">
            <div class="flex justify-between items-start">
              <div>
                <h4 class="font-medium">${device.device_name || device.device_id}</h4>
                <p class="text-sm text-light mt-1">
                  <span>型号：${device.model || "未知"}</span> |
                  <span>Android ${device.android_version || "未知"}</span>
                </p>
              </div>
              <span class="bg-success/10 text-success text-xs px-2 py-1 rounded-full">
                在线
              </span>
            </div>
          </div>
        `
          )
          .join("");

        // 设备点击选择
        document.querySelectorAll(".device-item").forEach((item) => {
          item.addEventListener("click", () => {
            document.querySelectorAll(".device-item").forEach((i) =>
              i.classList.remove("border-primary", "bg-primary/5")
            );
            item.classList.add("border-primary", "bg-primary/5");
            // 更新启动按钮状态（单用例 + 执行集）
            window.Suites?.updateStartBtnStatus?.();
            window.ExecSets?.updateStartExecSetBtnStatus?.();
          });
        });

        // 默认选中第一个
        const first = document.querySelector(".device-item");
        if (first) {
          first.classList.add("border-primary", "bg-primary/5");
        }
      } else {
        throw new Error(data.msg || "加载设备列表失败");
      }
    } catch (e) {
      console.error("加载设备列表失败:", e);
      deviceList.innerHTML = `
        <div class="text-center text-danger py-8">
          <i class="fa fa-exclamation-circle text-2xl mb-2"></i>
          <p>${e.message}</p>
        </div>
      `;
    }
  }

  async function loadRunningTaskTable() {
    if (!runningTaskTable) return;
    try {
      runningTaskTable.innerHTML = `
        <tr>
          <td colspan="5" class="text-center py-4 text-light">
            <i class="fa fa-spinner fa-spin mr-1"></i>加载运行中任务...
          </td>
        </tr>
      `;
      const data = await apiGet("/api/test/running");
      if (data.code === 200 && Array.isArray(data.data)) {
        const tasks = data.data;
        if (runningTaskCount) {
          runningTaskCount.textContent = tasks.length;
        }
        if (!tasks.length) {
          runningTaskTable.innerHTML = `
            <tr>
              <td colspan="5" class="text-center py-4 text-light">
                暂无运行中任务
              </td>
            </tr>
          `;
          return;
        }
        const now = new Date();
        runningTaskTable.innerHTML = tasks
          .map(
            (t) => {
              let elapsedText = "-";
              try {
                const start = parseDateTime && parseDateTime(t.start_time);
                if (start) {
                  const diffSec = Math.max(
                    0,
                    Math.floor((now.getTime() - start.getTime()) / 1000)
                  );
                  elapsedText = formatDuration
                    ? formatDuration(diffSec)
                    : `${diffSec}s`;
                }
              } catch (e) {
                elapsedText = "-";
              }
              return `
          <tr class="border-b border-gray-100 hover:bg-gray-50">
            <td class="py-2 px-2 max-w-[8rem] overflow-hidden text-ellipsis whitespace-nowrap" title="${t.task_id}">${t.task_id}</td>
            <td class="py-2 px-2 max-w-[7rem] overflow-hidden text-ellipsis whitespace-nowrap" title="${t.device_id || "-"}">${t.device_id || "-"}</td>
            <td class="py-2 px-2">
              <span class="px-2 py-0.5 rounded-full text-[11px] ${
                t.status === "running"
                  ? "bg-success/10 text-success"
                  : "bg-warning/10 text-warning"
              }">
                ${t.status || "-"}
              </span>
            </td>
            <td class="py-2 px-2">${elapsedText}</td>
            <td class="py-2 px-2">
              <button
                class="text-danger hover:text-danger/80 text-xs stop-running-task-btn"
                data-task-id="${t.task_id}"
              >
                <i class="fa fa-stop mr-1"></i>终止
              </button>
            </td>
          </tr>
        `;
            }
          )
          .join("");

        // 绑定终止按钮事件
        runningTaskTable
          .querySelectorAll(".stop-running-task-btn")
          .forEach((btn) => {
            btn.addEventListener("click", async () => {
              const taskId = btn.dataset.taskId;
              if (
                !confirm(
                  `确定要终止正在执行的任务 ${taskId} 吗？该操作可能会中断当前用例执行。`
                )
              ) {
                return;
              }
              try {
                const resp = await apiPost(`/api/test/stop/${taskId}`);
                if (resp.code === 200) {
                  addTaskLog &&
                    addTaskLog(
                      `[成功] 任务 ${taskId} 已被终止`,
                      "success"
                    );
                  if (AppState && AppState.currentTaskId === taskId) {
                    AppState.currentTaskId = null;
                    AppState.currentTaskMeta = null;
                    if (AppState.refreshInterval) {
                      clearInterval(AppState.refreshInterval);
                      AppState.refreshInterval = null;
                    }
                  }
                  await loadRunningTaskTable();
                } else {
                  throw new Error(resp.msg || "终止任务失败");
                }
              } catch (e) {
                console.error("终止任务失败:", e);
                addTaskLog &&
                  addTaskLog(
                    `[错误] 终止任务失败：${e.message}`,
                    "danger"
                  );
              }
            });
          });
      } else {
        throw new Error(data.msg || "获取运行中任务失败");
      }
    } catch (e) {
      console.error("加载运行中任务失败:", e);
      runningTaskTable.innerHTML = `
        <tr>
          <td colspan="5" class="text-center py-4 text-danger text-xs">
            加载失败：${e.message}
          </td>
        </tr>
      `;
    }
  }

  function getSelectedDeviceId() {
    const selected = document.querySelector(".device-item.border-primary");
    return selected ? selected.dataset.deviceId : null;
  }

  function initDevices() {
    if (refreshDeviceBtn) {
      refreshDeviceBtn.addEventListener("click", loadDeviceList);
    }
    // ATX 安装指南 Tip
    const atxGuideModal = document.getElementById("atx-guide-modal");
    const closeAtxGuideBtn = document.getElementById("close-atx-guide-btn");
    const atxGuideOkBtn = document.getElementById("atx-guide-ok-btn");
    function openAtxGuide() {
      if (!atxGuideModal) return;
      atxGuideModal.classList.remove("hidden");
    }
    function closeAtxGuide() {
      if (!atxGuideModal) return;
      atxGuideModal.classList.add("hidden");
    }
    if (atxGuideBtn) {
      atxGuideBtn.addEventListener("click", openAtxGuide);
    } else {
      // 兼容旧 Elements 未收录时的直接查找
      const btn = document.getElementById("atx-guide-btn");
      btn && btn.addEventListener("click", openAtxGuide);
    }
    closeAtxGuideBtn && closeAtxGuideBtn.addEventListener("click", closeAtxGuide);
    atxGuideOkBtn && atxGuideOkBtn.addEventListener("click", closeAtxGuide);
    atxGuideModal &&
      atxGuideModal.addEventListener("click", (e) => {
        if (e.target === atxGuideModal) closeAtxGuide();
      });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeAtxGuide();
    });
    if (refreshRunningTasksBtn) {
      refreshRunningTasksBtn.addEventListener("click", loadRunningTaskTable);
    }
    // 首次加载运行中任务列表
    loadRunningTaskTable();
    // 在线设备列表不轮询，仅首次加载与手动刷新（刷新按钮 / 顶部全局刷新）
    setInterval(loadRunningTaskTable, 10000);
  }

  window.Devices = {
    initDevices,
    loadDeviceList,
    loadRunningTaskTable,
    getSelectedDeviceId,
  };
})();

